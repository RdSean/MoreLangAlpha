"""Unit tests for memo PDF extraction's shared-core boundary."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest

from ptc_agent.agent.memo import pdf as memo_pdf
from ptc_agent.agent.memo.pdf import (
    MemoPdfExtractionError,
    MemoPdfTooManyPagesError,
    extract_pdf_text,
)
from src.utils.pdf_text import PdfPageLimitError, PdfTextBackend, PdfTextResult


def _result(
    markdown: str,
    *,
    backend: PdfTextBackend = "pdfplumber",
) -> PdfTextResult:
    return PdfTextResult(
        markdown=markdown,
        backend=backend,
        extracted_pages=(1,) if markdown else (),
        total_pages=1,
    )


class TestExtractPdfText:
    @pytest.mark.asyncio
    async def test_pdfplumber_timeout_still_gives_pypdf_a_full_attempt(
        self,
        monkeypatch,
    ):
        def extract_backend(content, *, backend, **kwargs):
            if backend == "pdfplumber":
                time.sleep(0.1)
                return _result("too late")
            return _result("x" * 100, backend="pypdf")

        monkeypatch.setattr(memo_pdf, "_EXTRACTION_TIMEOUT_S", 0.01)
        monkeypatch.setattr(
            memo_pdf,
            "extract_document_pdf_text_with_backend",
            extract_backend,
            raising=False,
        )

        text = await extract_pdf_text(b"%PDF-1.4 fake")

        assert text == "x" * 100

    @pytest.mark.asyncio
    async def test_delegates_with_memo_limits_and_returns_readable_text(self):
        content = b"%PDF-1.4 fake"
        readable = "This is a PDF with plenty of readable content spanning lines."
        with patch(
            "ptc_agent.agent.memo.pdf.extract_document_pdf_text_with_backend",
            return_value=_result(readable),
        ) as shared_extract:
            text = await extract_pdf_text(content)

        assert text == readable
        shared_extract.assert_called_once_with(
            content,
            backend="pdfplumber",
            max_pages=500,
            max_output_bytes=1_048_576,
        )

    @pytest.mark.asyncio
    async def test_empty_shared_result_raises_extraction_error(self):
        with patch(
            "ptc_agent.agent.memo.pdf.extract_document_pdf_text_with_backend",
            return_value=_result("", backend="pypdf"),
        ):
            with pytest.raises(MemoPdfExtractionError, match="readable text"):
                await extract_pdf_text(b"%PDF-1.4 scan")

    @pytest.mark.asyncio
    async def test_short_shared_result_raises_extraction_error(self):
        with patch(
            "ptc_agent.agent.memo.pdf.extract_document_pdf_text_with_backend",
            return_value=_result("tiny", backend="pypdf"),
        ):
            with pytest.raises(MemoPdfExtractionError):
                await extract_pdf_text(b"%PDF-1.4 scan")

    @pytest.mark.asyncio
    async def test_shared_failure_raises_extraction_error(self):
        with patch(
            "ptc_agent.agent.memo.pdf.extract_document_pdf_text_with_backend",
            side_effect=RuntimeError("both backends failed"),
        ):
            with pytest.raises(MemoPdfExtractionError):
                await extract_pdf_text(b"%PDF-1.4 broken")

    @pytest.mark.asyncio
    async def test_page_limit_preserves_memo_specific_error(self):
        with patch(
            "ptc_agent.agent.memo.pdf.extract_document_pdf_text_with_backend",
            side_effect=PdfPageLimitError(page_count=501, max_pages=500),
        ):
            with pytest.raises(
                MemoPdfTooManyPagesError,
                match="PDF has 501 pages; max is 500",
            ):
                await extract_pdf_text(b"%PDF-1.4 large")
