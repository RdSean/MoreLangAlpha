from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "068_add_structure_publications.py"
)


def test_structure_publication_migration_follows_kp_lessons() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "068_structure_publications"
    assert migration["down_revision"] == "067_kp_lessons"


def test_publication_supports_exactly_one_package_or_structure() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS structure_id UUID" in source
    assert "ALTER COLUMN teaching_package_id DROP NOT NULL" in source
    assert "teaching_package_id IS NOT NULL" in source
    assert "structure_id IS NOT NULL" in source
    assert "education_textbook_publications_target_check" in source


def test_structure_publication_downgrade_only_removes_structure_target() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "DROP CONSTRAINT IF EXISTS education_textbook_publications_target_check" in source
    assert "DROP COLUMN IF EXISTS structure_id" in source
    assert "ALTER COLUMN teaching_package_id SET NOT NULL" in source
