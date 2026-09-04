from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader, PdfWriter

from src.utils import pdf_text
from src.utils.pdf_text import (
    PdfPageLimitError,
    PdfTextResult,
    extract_pdf_text,
    extract_pdf_text_with_backend,
)


FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "documents"


def _two_text_page_pdf() -> bytes:
    reader = PdfReader(FIXTURES / "text.pdf")
    writer = PdfWriter()
    writer.add_page(reader.pages[0])
    writer.add_page(reader.pages[0])
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def test_pdfplumber_is_primary_for_digital_pdf() -> None:
    result = extract_pdf_text(FIXTURES / "text.pdf", max_pages=10)

    assert result.backend == "pdfplumber"
    assert result.extracted_pages == (1,)
    assert result.total_pages == 1
    assert "Digital Algebra Notes" in result.markdown


def test_single_backend_interface_runs_only_the_requested_backend(monkeypatch) -> None:
    expected = PdfTextResult("fallback", "pypdf", (1,), 1)

    def unexpected_pdfplumber(*args, **kwargs):
        raise AssertionError("pdfplumber must not run")

    monkeypatch.setattr(pdf_text, "_extract_with_pdfplumber", unexpected_pdfplumber)
    monkeypatch.setattr(
        pdf_text,
        "_extract_with_pypdf",
        lambda *args, **kwargs: expected,
    )

    result = extract_pdf_text_with_backend(
        b"%PDF-1.4 fake",
        backend="pypdf",
        max_pages=10,
        max_output_bytes=1024,
    )

    assert result is expected


def test_pypdf_is_fallback_when_pdfplumber_fails(monkeypatch) -> None:
    def fail_pdfplumber(*args, **kwargs):
        raise RuntimeError("pdfplumber unavailable")

    monkeypatch.setattr(pdf_text, "_extract_with_pdfplumber", fail_pdfplumber)

    result = extract_pdf_text(FIXTURES / "text.pdf", max_pages=10)

    assert result.backend == "pypdf"
    assert result.extracted_pages == (1,)
    assert "Digital Algebra Notes" in result.markdown


def test_pypdf_is_fallback_when_primary_is_below_minimum(monkeypatch) -> None:
    monkeypatch.setattr(
        pdf_text,
        "_extract_with_pdfplumber",
        lambda *args, **kwargs: PdfTextResult(
            markdown="tiny",
            backend="pdfplumber",
            extracted_pages=(1,),
            total_pages=1,
        ),
    )

    result = extract_pdf_text(
        FIXTURES / "text.pdf",
        max_pages=10,
        minimum_chars=50,
    )

    assert result.backend == "pypdf"
    assert "Digital Algebra Notes" in result.markdown


def test_each_extracted_page_has_stable_markdown_heading() -> None:
    result = extract_pdf_text(_two_text_page_pdf(), max_pages=10)

    assert result.extracted_pages == (1, 2)
    assert result.markdown.count("--- Page 1 ---") == 1
    assert result.markdown.count("--- Page 2 ---") == 1


def test_output_byte_cap_stops_at_a_page_boundary() -> None:
    result = extract_pdf_text(
        _two_text_page_pdf(),
        max_pages=10,
        max_output_bytes=1,
    )

    assert result.extracted_pages == (1,)
    assert "--- Page 2 ---" not in result.markdown


def test_empty_text_layer_returns_no_usable_text() -> None:
    result = extract_pdf_text(FIXTURES / "scanned.pdf", max_pages=10)

    assert result.backend == "pypdf"
    assert result.markdown == ""
    assert result.extracted_pages == ()
    assert result.total_pages == 1


def test_page_cap_is_checked_by_pdfplumber() -> None:
    with pytest.raises(PdfPageLimitError) as error:
        extract_pdf_text(_two_text_page_pdf(), max_pages=1)

    assert error.value.page_count == 2
    assert error.value.max_pages == 1


def test_page_cap_is_checked_by_pypdf_fallback(monkeypatch) -> None:
    def fail_pdfplumber(*args, **kwargs):
        raise RuntimeError("force fallback")

    monkeypatch.setattr(pdf_text, "_extract_with_pdfplumber", fail_pdfplumber)

    with pytest.raises(PdfPageLimitError) as error:
        extract_pdf_text(_two_text_page_pdf(), max_pages=1)

    assert error.value.page_count == 2
    assert error.value.max_pages == 1
