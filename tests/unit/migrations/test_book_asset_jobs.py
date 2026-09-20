from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "070_add_book_asset_jobs.py"
)


def test_book_asset_migration_follows_learning_items() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "070_book_asset_jobs"
    assert migration["down_revision"] == "069_learning_items_and_profiles"


def test_book_asset_migration_adds_assets_scope_and_manifest() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "ADD COLUMN book_asset_prefix" in source
    assert "ADD COLUMN book_asset_manifest" in source
    assert "'structure', 'assets', 'lesson'" in source
    assert "scope IN ('structure', 'assets')" in source


def test_book_asset_migration_downgrades_only_its_own_columns_and_checks() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "DROP COLUMN IF EXISTS book_asset_manifest" in source
    assert "DROP COLUMN IF EXISTS book_asset_prefix" in source
    assert "DROP TABLE IF EXISTS education_textbook_structures" not in source
