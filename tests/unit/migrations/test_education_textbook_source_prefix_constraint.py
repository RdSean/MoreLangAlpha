from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "064_strengthen_textbook_source_prefix_constraint.py"
)


def test_final_prefix_constraint_follows_the_compatibility_repair() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "064_textbook_source_prefix_constraint"
    assert migration["down_revision"] == "063_textbook_artifact_source_prefix"


def test_final_prefix_constraint_keeps_only_explicit_safe_shapes() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    migration = runpy.run_path(str(MIGRATION_PATH))
    compatibility = migration["_COMPATIBILITY_REGEX"]

    assert "LIKE 'education/%'" not in source
    assert "v[1-9][0-9]*/source-bundles" in compatibility
    assert (
        "[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
        "[89ab][0-9a-f]{3}-[0-9a-f]{12}/source-bundles"
        in compatibility
    )
    assert (
        "source-bundles/[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}"
        in compatibility
    )
    assert "DROP CONSTRAINT IF EXISTS" in source
    assert "ADD CONSTRAINT" in source


def test_final_prefix_downgrade_keeps_the_same_safe_compatibility_set() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["_DOWNGRADE_REGEX"] == migration["_COMPATIBILITY_REGEX"]
