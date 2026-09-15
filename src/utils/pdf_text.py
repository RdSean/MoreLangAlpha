"""Shared synchronous PDF text extraction with a deterministic fallback."""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Literal, TypeAlias


PdfTextBackend: TypeAlias = Literal["pdfplumber", "pypdf"]


@dataclass(frozen=True, slots=True)
class PdfTextResult:
    markdown: str
    backend: PdfTextBackend
    extracted_pages: tuple[int, ...]
    total_pages: int


class PdfPageLimitError(ValueError):
    """Raised before extraction when a backend observes too many pages."""

    def __init__(self, *, page_count: int, max_pages: int) -> None:
        super().__init__(f"PDF has {page_count} pages; max is {max_pages}")
        self.page_count = page_count
        self.max_pages = max_pages


def extract_pdf_text(
    path_or_bytes: Path | bytes,
    *,
    max_pages: int | None,
    minimum_chars: int = 1,
    max_output_bytes: int | None = None,
) -> PdfTextResult:
    """Extract Markdown using pdfplumber first and pypdf as fallback."""
    _validate_limits(
        max_pages=max_pages,
        minimum_chars=minimum_chars,
        max_output_bytes=max_output_bytes,
    )

    try:
        primary = extract_pdf_text_with_backend(
            path_or_bytes,
            backend="pdfplumber",
            max_pages=max_pages,
            max_output_bytes=max_output_bytes,
        )
    except PdfPageLimitError:
        raise
    except Exception:
        primary = None

    if primary is not None and len(primary.markdown.strip()) >= minimum_chars:
        return primary

    return extract_pdf_text_with_backend(
        path_or_bytes,
        backend="pypdf",
        max_pages=max_pages,
        max_output_bytes=max_output_bytes,
    )


def extract_pdf_text_with_backend(
    path_or_bytes: Path | bytes,
    *,
    backend: PdfTextBackend,
    max_pages: int | None,
    max_output_bytes: int | None = None,
) -> PdfTextResult:
    """Extract Markdown with one explicitly selected PDF backend."""
    _validate_limits(
        max_pages=max_pages,
        minimum_chars=0,
        max_output_bytes=max_output_bytes,
    )
    if backend == "pdfplumber":
        return _extract_with_pdfplumber(
            path_or_bytes,
            max_pages=max_pages,
            max_output_bytes=max_output_bytes,
        )
    if backend == "pypdf":
        return _extract_with_pypdf(
            path_or_bytes,
            max_pages=max_pages,
            max_output_bytes=max_output_bytes,
        )
    raise ValueError(f"Unsupported PDF text backend: {backend}")


def _extract_with_pdfplumber(
    path_or_bytes: Path | bytes,
    *,
    max_pages: int | None,
    max_output_bytes: int | None,
) -> PdfTextResult:
    import pdfplumber

    source = _reader_source(path_or_bytes)
    extracted: list[tuple[int, str]] = []
    accumulated_bytes = 0
    with pdfplumber.open(source) as pdf:
        total_pages = len(pdf.pages)
        _enforce_page_limit(total_pages, max_pages=max_pages)
        for page_number, page in enumerate(pdf.pages, start=1):
            try:
                text = page.extract_text() or ""
            finally:
                page.close()
            if not text.strip():
                continue
            extracted.append((page_number, text))
            accumulated_bytes += len(text.encode("utf-8"))
            if (
                max_output_bytes is not None
                and accumulated_bytes > max_output_bytes
            ):
                break

    return _build_result(
        backend="pdfplumber",
        extracted=extracted,
        total_pages=total_pages,
    )


def _extract_with_pypdf(
    path_or_bytes: Path | bytes,
    *,
    max_pages: int | None,
    max_output_bytes: int | None,
) -> PdfTextResult:
    import pypdf

    reader = pypdf.PdfReader(_reader_source(path_or_bytes))
    total_pages = len(reader.pages)
    _enforce_page_limit(total_pages, max_pages=max_pages)
    extracted: list[tuple[int, str]] = []
    accumulated_bytes = 0
    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        if not text.strip():
            continue
        extracted.append((page_number, text))
        accumulated_bytes += len(text.encode("utf-8"))
        if max_output_bytes is not None and accumulated_bytes > max_output_bytes:
            break

    return _build_result(
        backend="pypdf",
        extracted=extracted,
        total_pages=total_pages,
    )


def _build_result(
    *,
    backend: PdfTextBackend,
    extracted: list[tuple[int, str]],
    total_pages: int,
) -> PdfTextResult:
    return PdfTextResult(
        markdown="\n\n".join(
            f"--- Page {page_number} ---\n\n{text}"
            for page_number, text in extracted
        ),
        backend=backend,
        extracted_pages=tuple(page_number for page_number, _ in extracted),
        total_pages=total_pages,
    )


def _reader_source(path_or_bytes: Path | bytes) -> Path | BytesIO:
    if isinstance(path_or_bytes, Path):
        return path_or_bytes
    if isinstance(path_or_bytes, bytes):
        return BytesIO(path_or_bytes)
    raise TypeError("path_or_bytes must be a Path or bytes")


def _enforce_page_limit(page_count: int, *, max_pages: int | None) -> None:
    if max_pages is not None and page_count > max_pages:
        raise PdfPageLimitError(page_count=page_count, max_pages=max_pages)


def _validate_limits(
    *,
    max_pages: int | None,
    minimum_chars: int,
    max_output_bytes: int | None,
) -> None:
    if max_pages is not None and max_pages <= 0:
        raise ValueError("max_pages must be positive")
    if minimum_chars < 0:
        raise ValueError("minimum_chars cannot be negative")
    if max_output_bytes is not None and max_output_bytes <= 0:
        raise ValueError("max_output_bytes must be positive")
