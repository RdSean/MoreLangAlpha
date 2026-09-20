from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "072_add_structure_validation_warnings.py"
)


def test_warning_migration_follows_legacy_removal() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "072_structure_validation_warnings"
    assert migration["down_revision"] == "071_remove_legacy_teaching_packages"


def test_warning_migration_adds_json_array() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "ADD COLUMN validation_warnings JSONB" in source
    assert "DEFAULT '[]'::jsonb" in source
