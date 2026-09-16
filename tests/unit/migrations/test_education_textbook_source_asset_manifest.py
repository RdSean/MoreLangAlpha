from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "065_add_textbook_source_asset_manifest.py"
)


def test_source_asset_manifest_migration_adds_safe_default_column() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert migration["revision"] == "065_textbook_source_asset_manifest"
    assert migration["down_revision"] == "064_textbook_source_prefix_constraint"
    assert "ADD COLUMN IF NOT EXISTS asset_manifest JSONB" in source
    assert "NOT NULL DEFAULT '[]'::jsonb" in source


def test_source_asset_manifest_migration_drops_only_the_new_column() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "DROP COLUMN IF EXISTS asset_manifest" in source
    assert "DROP TABLE" not in source
