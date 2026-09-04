from __future__ import annotations

from pathlib import Path

import pytest

from src.server.documents.contracts import (
    InspectionResult,
    ParseRequest,
    ParserIncompatibleError,
    SourceDocument,
)
from src.server.documents.providers.anydoc import AnydocExtractor


FIXTURES = Path(__file__).resolve().parents[5] / "tests" / "fixtures" / "documents"


def _request(
    tmp_path: Path,
    *,
    classification: str,
    source_path: Path | None = None,
) -> ParseRequest:
    return ParseRequest(
        source=SourceDocument(
            document_id="doc-A1b2C3d4E5f6",
            source_path=source_path or tmp_path / "source.pdf",
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
        parser_id="anydoc-local",
        output_dir=tmp_path / "output",
    )


def test_anydoc_rejects_mixed_before_execution(tmp_path: Path, monkeypatch) -> None:
    import anydoc

    def must_not_run(*args, **kwargs):
        raise AssertionError("AnyDoc must not execute for mixed PDFs")

    monkeypatch.setattr(anydoc, "to_markdown", must_not_run)

    with pytest.raises(ParserIncompatibleError):
        AnydocExtractor().parse(_request(tmp_path, classification="mixed"))


def test_anydoc_maps_needs_ocr_to_parser_incompatible(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import anydoc

    def needs_ocr(*args, **kwargs):
        raise anydoc.NeedsOcrError("page 1 needs OCR")

    monkeypatch.setattr(anydoc, "to_markdown", needs_ocr)

    with pytest.raises(ParserIncompatibleError) as error:
        AnydocExtractor().parse(_request(tmp_path, classification="text_based"))

    assert error.value.code == "parser_incompatible"
    assert "OCR" in error.value.safe_message
    assert not (_request(tmp_path, classification="text_based").output_dir / "document.md").exists()


def test_anydoc_writes_primary_markdown_bundle(tmp_path: Path, monkeypatch) -> None:
    import anydoc

    calls: list[tuple[Path, str]] = []

    def to_markdown(path: Path, *, ocr: str) -> str:
        calls.append((path, ocr))
        return "# Notes\n"

    monkeypatch.setattr(anydoc, "to_markdown", to_markdown)

    request = _request(tmp_path, classification="text_based")
    bundle = AnydocExtractor().parse(request)

    assert calls == [(request.source.source_path, "reject")]
    assert (request.output_dir / "document.md").read_text(encoding="utf-8") == "# Notes\n"
    assert bundle.primary_relative_path == "document.md"
    assert bundle.artifacts[0].artifact_kind == "primary_document"
    assert bundle.artifacts[0].format == "gfm"


def test_anydoc_empty_result_is_incompatible_without_partial_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import anydoc

    monkeypatch.setattr(anydoc, "to_markdown", lambda *args, **kwargs: "  \n")
    request = _request(tmp_path, classification="text_based")

    with pytest.raises(ParserIncompatibleError, match="mixed"):
        AnydocExtractor().parse(request)

    assert not (request.output_dir / "document.md").exists()


@pytest.mark.integration
def test_real_anydoc_extracts_text_fixture(tmp_path: Path) -> None:
    request = _request(
        tmp_path,
        classification="text_based",
        source_path=FIXTURES / "text.pdf",
    )

    bundle = AnydocExtractor().parse(request)

    assert bundle.primary_relative_path == "document.md"
    assert "Digital Algebra Notes" in (request.output_dir / "document.md").read_text(
        encoding="utf-8"
    )


@pytest.mark.integration
@pytest.mark.parametrize(
    ("filename", "classification"),
    [
        ("mixed.pdf", "mixed"),
        ("scanned.pdf", "scanned"),
        ("image-based.pdf", "image_based"),
    ],
)
def test_real_anydoc_refuses_ocr_fixtures_without_partial_output(
    tmp_path: Path,
    filename: str,
    classification: str,
) -> None:
    request = _request(
        tmp_path,
        classification=classification,
        source_path=FIXTURES / filename,
    )

    with pytest.raises(ParserIncompatibleError):
        AnydocExtractor().parse(request)

    assert not (request.output_dir / "document.md").exists()
