from __future__ import annotations

from pathlib import Path

import pytest

from src.server.documents.contracts import (
    ArtifactSpec,
    JobProgress,
    ParserDescriptor,
    is_safe_artifact_path,
    validate_progress_transition,
)


def test_parser_descriptor_is_immutable() -> None:
    descriptor = ParserDescriptor(
        parser_id="anydoc-local",
        display_name="AnyDoc Local",
        version="0.2.4",
        supported_formats=frozenset({"pdf"}),
        supported_classifications=frozenset({"text_based"}),
        available=True,
        reason="Best for PDFs with a text layer.",
    )

    with pytest.raises(AttributeError):
        descriptor.available = False  # type: ignore[misc]


def test_artifact_spec_keeps_format_and_structured_metadata() -> None:
    artifact = ArtifactSpec(
        artifact_kind="structured_data",
        format="document_json",
        media_type="application/json",
        relative_path="document.json",
        schema_name="langalpha.document",
        schema_version="1",
        locator={"page": 3},
        metadata={"language": "zh-CN"},
    )

    assert artifact.schema_name == "langalpha.document"
    assert artifact.locator == {"page": 3}
    assert not hasattr(artifact, "size_bytes")
    assert not hasattr(artifact, "sha256")
    assert not hasattr(artifact, "revision")


@pytest.mark.parametrize(
    "relative_path",
    ["/tmp/document.md", "../document.md", "images/../../document.md", "", "."],
)
def test_artifact_relative_path_must_stay_in_bundle(
    tmp_path: Path,
    relative_path: str,
) -> None:
    assert not is_safe_artifact_path(tmp_path, relative_path)


def test_artifact_relative_path_rejects_symlink_escape(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-document.md"
    outside.write_text("outside", encoding="utf-8")
    (tmp_path / "link.md").symlink_to(outside)

    assert not is_safe_artifact_path(tmp_path, "link.md")


def test_artifact_relative_path_accepts_nested_bundle_file(tmp_path: Path) -> None:
    nested = tmp_path / "images"
    nested.mkdir()
    (nested / "page-001-01.png").write_bytes(b"png")

    assert is_safe_artifact_path(tmp_path, "images/page-001-01.png")


def test_progress_rejects_percentage_regression() -> None:
    previous = JobProgress(stage="parsing", percentage=60, status_version=4)

    with pytest.raises(ValueError, match="percentage"):
        validate_progress_transition(
            previous,
            stage="parsing",
            percentage=59,
            status_version=5,
        )


def test_progress_rejects_stage_regression() -> None:
    previous = JobProgress(stage="storing", percentage=80, status_version=4)

    with pytest.raises(ValueError, match="stage"):
        validate_progress_transition(
            previous,
            stage="parsing",
            percentage=90,
            status_version=5,
        )


def test_progress_rejects_stale_status_version() -> None:
    previous = JobProgress(stage="parsing", percentage=60, status_version=4)

    with pytest.raises(ValueError, match="status_version"):
        validate_progress_transition(
            previous,
            stage="storing",
            percentage=80,
            status_version=4,
        )


def test_progress_accepts_forward_transition() -> None:
    previous = JobProgress(stage="parsing", percentage=60, status_version=4)

    current = validate_progress_transition(
        previous,
        stage="storing",
        percentage=80,
        status_version=5,
    )

    assert current == JobProgress(
        stage="storing",
        percentage=80,
        status_version=5,
    )
