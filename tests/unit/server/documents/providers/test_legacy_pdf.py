from __future__ import annotations

from pathlib import Path

from src.server.documents.contracts import InspectionResult, ParseRequest, SourceDocument
from src.server.documents.providers.legacy_pdf import LegacyPdfExtractor
from src.utils.pdf_text import PdfTextResult


def _request(tmp_path: Path, *, classification: str) -> ParseRequest:
    return ParseRequest(
        source=SourceDocument(
            document_id="doc-A1b2C3d4E5f6",
            source_path=tmp_path / "source.pdf",
            original_filename="source.pdf",
            media_type="application/pdf",
            document_format="pdf",
        ),
        inspection=InspectionResult(
            inspector_id="pdf-inspector",
            inspector_name="PDF Inspector",
            inspector_version="1.17.0",
            status="completed",
            detected_format="pdf",
            classification=classification,  # type: ignore[arg-type]
        ),
        parser_id="legacy-pdf-text",
        output_dir=tmp_path / "output",
    )


def test_legacy_parser_can_return_empty_markdown_with_warning_for_scan(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "src.server.documents.providers.legacy_pdf.extract_pdf_text",
        lambda *args, **kwargs: PdfTextResult(
            markdown="",
            backend="pypdf",
            extracted_pages=(),
            total_pages=1,
        ),
    )
    request = _request(tmp_path, classification="scanned")

    bundle = LegacyPdfExtractor().parse(request)

    assert (request.output_dir / "document.md").read_text(encoding="utf-8") == ""
    assert bundle.primary_relative_path == "document.md"
    assert bundle.artifacts[0].metadata == {
        "backend": "pypdf",
        "extracted_pages": [],
        "total_pages": 1,
        "warning": "Pages without a usable text layer may be missing or empty.",
    }


def test_legacy_parser_records_extracted_page_provenance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "src.server.documents.providers.legacy_pdf.extract_pdf_text",
        lambda *args, **kwargs: PdfTextResult(
            markdown="--- Page 1 ---\n\nNotes",
            backend="pdfplumber",
            extracted_pages=(1,),
            total_pages=2,
        ),
    )
    request = _request(tmp_path, classification="mixed")

    bundle = LegacyPdfExtractor().parse(request)

    assert bundle.artifacts[0].metadata["extracted_pages"] == [1]
    assert bundle.artifacts[0].metadata["total_pages"] == 2
