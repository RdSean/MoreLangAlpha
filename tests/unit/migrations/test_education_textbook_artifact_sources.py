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
    table_block = source.split(
        "CREATE TABLE education_textbook_artifact_sources", 1
    )[1].split("CREATE INDEX", 1)[0]

    assert "CREATE TABLE education_textbook_artifact_sources" in source
    assert "PRIMARY KEY (version_id, producer_job_id)" in source
    assert "UNIQUE (version_id, position)" in source
    assert "REFERENCES education_textbook_versions(version_id) ON DELETE RESTRICT" in source
    assert "FOREIGN KEY" not in table_block
    assert "REFERENCES documents" not in table_block
    assert "REFERENCES document_parse_jobs" not in table_block
    assert "REFERENCES document_artifacts" not in table_block
    for column in (
        "source_filename VARCHAR",
        "source_media_type VARCHAR",
        "source_format VARCHAR",
        "parser_id VARCHAR",
        "parser_name VARCHAR",
        "parser_version VARCHAR",
        "parse_completed_at TIMESTAMPTZ",
    ):
        assert column in table_block
    assert "primary_sha256 ~ '^[0-9a-f]{64}$'" in source
    assert "snapshot_prefix ~" in source
    assert (
        "idx_education_textbook_artifact_sources_document" in source
        and "(document_id, producer_job_id, version_id)" in source
    )


def test_artifact_source_migration_keeps_legacy_sources_intact() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "DROP TABLE IF EXISTS education_textbook_sources" not in source
    assert "ALTER TABLE education_textbook_sources" not in source
