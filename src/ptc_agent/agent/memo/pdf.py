"""PDF text extraction on raw bytes — pdfplumber primary, pypdf fallback.

Mirrors the internals of ``src/tools/web/inhouse/extractors/pdf.py`` but takes
``bytes`` directly instead of a URL. The crawler's ``PdfExtractor`` downloads
the PDF over HTTP — wrong entry point for memo uploads where the bytes are
already in hand.
"""

from __future__ import annotations

import asyncio
import logging

from ptc_agent.agent.memo.schema import (
    MEMO_CONTENT_MIN_CHARS,
    MEMO_MAX_CONTENT_BYTES,
)
from src.utils.pdf_text import (
    PdfPageLimitError,
    PdfTextBackend,
    extract_pdf_text_with_backend as extract_document_pdf_text_with_backend,
)

logger = logging.getLogger(__name__)

_EXTRACTION_TIMEOUT_S = 30

# Bound the per-PDF page count to keep extraction memory predictable. A 1000-page
# large document decompressed and held in memory comfortably crosses 1 GB on
# pdfplumber. 500 pages covers any realistic memo input; documents that exceed
# this almost always belong in a different workflow (e.g. summarized externally
# or chunked for retrieval) and should not blow up the FastAPI worker.
_MAX_PDF_PAGES = 500

# Cap on concurrent PDF extractions across the worker. pdfplumber holds the
# entire parsed page tree in memory until the ``with`` block exits — peak RSS
# per extraction can hit ~1 GB on the documented 500-page cap. Two concurrent
# extractions therefore bound peak memory at ~2 GB regardless of how many
# uploads land at once. Additional uploads queue on this semaphore.
_EXTRACTION_CONCURRENCY = 2
_EXTRACTION_SEM = asyncio.Semaphore(_EXTRACTION_CONCURRENCY)


class MemoPdfExtractionError(Exception):
    """Raised when a PDF yields less than ``MEMO_CONTENT_MIN_CHARS`` of text.

    Typical cause: the PDF has no text layer (scanned document). Surface as
    HTTP 422 at the router so the user knows to run OCR first.
    """


class MemoPdfTooManyPagesError(MemoPdfExtractionError):
    """Raised when a PDF exceeds the configured page-count cap."""


async def extract_pdf_text(content: bytes) -> str:
    """Extract readable text from PDF bytes.

    Tries pdfplumber first, falls back to pypdf. If neither yields at least
    ``MEMO_CONTENT_MIN_CHARS`` of non-whitespace text, raises
    ``MemoPdfExtractionError`` so the router can return 422 with a clear
    message.

    Concurrent extractions are bounded by ``_EXTRACTION_SEM`` so the FastAPI
    worker's RSS stays bounded even under a burst of PDF uploads.
    """
    async with _EXTRACTION_SEM:
        for backend in ("pdfplumber", "pypdf"):
            typed_backend: PdfTextBackend = backend
            try:
                result = await asyncio.wait_for(
                    asyncio.to_thread(
                        extract_document_pdf_text_with_backend,
                        content,
                        backend=typed_backend,
                        max_pages=_MAX_PDF_PAGES,
                        max_output_bytes=MEMO_MAX_CONTENT_BYTES,
                    ),
                    timeout=_EXTRACTION_TIMEOUT_S,
                )
                if _is_usable(result.markdown):
                    return result.markdown
            except asyncio.TimeoutError:
                logger.warning(
                    "memo pdf %s timed out (%ss)",
                    backend,
                    _EXTRACTION_TIMEOUT_S,
                )
            except PdfPageLimitError as error:
                raise MemoPdfTooManyPagesError(
                    f"PDF has {error.page_count} pages; max is {error.max_pages}. "
                    "Split the document or summarize first."
                ) from error
            except Exception as exc:
                logger.debug("memo pdf %s failed: %s", backend, exc)

    raise MemoPdfExtractionError(
        "Could not extract readable text from this PDF (it may be a scan). "
        "Try OCR first."
    )


def _is_usable(text: str | None) -> bool:
    return bool(text) and len(text.strip()) >= MEMO_CONTENT_MIN_CHARS
