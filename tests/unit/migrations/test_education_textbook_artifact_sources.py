from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "062_add_textbook_artifact_sources.py"
)


def test_artifact_source_migration_follows_document_usage_records() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "062_textbook_artifact_sources"
    assert migration["down_revision"] == "061_document_usage_records"


def test_artifact_source_schema_binds_versions_to_completed_parse_bundles() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "CREATE TABLE education_textbook_artifact_sources" in source
    assert "PRIMARY KEY (version_id, producer_job_id)" in source
    assert "UNIQUE (version_id, position)" in source
    assert "REFERENCES education_textbook_versions(version_id) ON DELETE RESTRICT" in source
    assert "REFERENCES documents(document_id) ON DELETE RESTRICT" in source
    assert (
        "REFERENCES document_parse_jobs(job_id, document_id)" in source
        and "ON DELETE RESTRICT" in source
    )
    assert (
        "REFERENCES document_artifacts(artifact_id, producer_job_id)" in source
        and "ON DELETE RESTRICT" in source
    )
    assert "primary_sha256 ~ '^[0-9a-f]{64}$'" in source
    assert "snapshot_prefix LIKE 'education/%'" in source
    assert (
        "idx_education_textbook_artifact_sources_document" in source
        and "(document_id, producer_job_id, version_id)" in source
    )


def test_artifact_source_migration_keeps_legacy_sources_intact() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "DROP TABLE IF EXISTS education_textbook_sources" not in source
    assert "ALTER TABLE education_textbook_sources" not in source
