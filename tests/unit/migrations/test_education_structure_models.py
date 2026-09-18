from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "066_add_textbook_structure_models.py"
)


def test_structure_migration_follows_textbook_source_asset_manifest() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "066_textbook_structure_models"
    assert migration["down_revision"] == "065_textbook_source_asset_manifest"


def test_structure_migration_persists_reviewable_unit_and_knowledge_identity() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for table in (
        "education_textbook_structures",
        "education_structure_units",
        "education_structure_knowledge_points",
        "education_generation_jobs",
        "education_generation_attempts",
    ):
        assert f"CREATE TABLE {table}" in source

    assert "UNIQUE (version_id, sequence)" in source
    assert "UNIQUE (structure_id, position)" in source
    assert "UNIQUE (unit_id, position)" in source
    assert "UNIQUE (unit_id, slug)" in source
    assert "source_refs JSONB NOT NULL DEFAULT '[]'::jsonb" in source
    assert "confidence REAL NOT NULL" in source
    assert "schema_version VARCHAR(64) NOT NULL" in source


def test_generation_job_scope_requires_exactly_one_target() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "scope IN ('structure', 'lesson')" in source
    assert "scope = 'structure'" in source
    assert "scope = 'lesson'" in source
    assert "structure_id IS NOT NULL" in source
    assert "knowledge_point_id IS NOT NULL" in source


def test_structure_migration_downgrades_only_its_own_tables() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "DROP TABLE IF EXISTS education_generation_attempts" in source
    assert "DROP TABLE IF EXISTS education_generation_jobs" in source
    assert "DROP TABLE IF EXISTS education_structure_knowledge_points" in source
    assert "DROP TABLE IF EXISTS education_structure_units" in source
    assert "DROP TABLE IF EXISTS education_textbook_structures" in source
    assert (
        "DROP CONSTRAINT IF EXISTS fk_education_generation_jobs_latest_attempt"
        in source
    )
    assert "DROP TABLE IF EXISTS education_textbook_versions" not in source
