from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "063_align_textbook_artifact_source_prefix.py"
)


def test_prefix_upgrade_follows_the_artifact_source_migration() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "063_textbook_artifact_source_prefix"
    assert migration["down_revision"] == "062_textbook_artifact_sources"


def test_prefix_migration_uses_only_explicit_safe_compatibility_forms() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    migration = runpy.run_path(str(MIGRATION_PATH))
    compatibility = migration["_COMPATIBILITY_REGEX"]

    assert "DROP CONSTRAINT IF EXISTS" in source
    assert "ADD CONSTRAINT" in source
    assert (
        "education_textbook_artifact_sources_snapshot_prefix_check" in source
    )
    assert "LIKE 'education/%'" not in source
    assert "v[1-9][0-9]*/source-bundles" in compatibility
    assert (
        "source-bundles/[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}"
        in compatibility
    )
    assert "source-bundles/[0-9]{2,}/" in compatibility


def test_prefix_downgrade_restores_the_same_explicit_safe_set() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert source.count("_replace_constraint(regex=_COMPATIBILITY_REGEX)") == 2
    assert "_NEW_PREFIX" not in source
