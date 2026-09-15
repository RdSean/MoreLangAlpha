from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "045_add_document_library.py"
)


def test_document_library_migration_follows_channel_continuations() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "045"
    assert migration["down_revision"] == "044"


def test_document_library_schema_contains_required_tables_and_contracts() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for table in (
        "document_datasets",
        "documents",
        "document_dataset_items",
        "document_tags",
        "document_tag_assignments",
        "document_inspections",
        "document_parse_jobs",
        "document_artifacts",
    ):
        assert f"CREATE TABLE {table}" in source

    for prefix in ("dts", "doc", "ins", "job", "art", "tag"):
        assert f"^{prefix}-[0-9A-Za-z]{{12}}$" in source

    assert "source_size_bytes" in source
    assert "source_sha256" in source
    assert "status_version" in source
    assert "lease_expires_at" in source
    assert "producer_job_id" in source
    assert "artifact_kind" in source
    assert "schema_name" in source
    assert "schema_version" in source
    assert "locator JSONB" in source
    assert "metadata JSONB" in source


def test_derived_artifacts_do_not_store_source_integrity_or_revisions() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    artifact_block = source.split("CREATE TABLE document_artifacts", 1)[1].split(
        "CREATE INDEX",
        1,
    )[0]

    assert "size_bytes" not in artifact_block
    assert "sha256" not in artifact_block
    assert "revision" not in artifact_block
