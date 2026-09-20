from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "071_remove_legacy_teaching_packages.py"
)


def test_legacy_removal_follows_book_asset_jobs() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "071_remove_legacy_teaching_packages"
    assert migration["down_revision"] == "070_book_asset_jobs"


def test_legacy_removal_drops_only_incompatible_tables() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for table in (
        "education_teaching_archive_staging",
        "education_teaching_events",
        "education_teaching_attempts",
        "education_teaching_jobs",
        "education_teaching_package_questions",
        "education_teaching_package_chapters",
        "education_teaching_packages",
        "education_chapter_questions",
        "education_learning_progress",
        "education_learning_answers",
        "education_textbook_sources",
    ):
        assert f'_drop("{table}")' in source

    assert "DROP TABLE IF EXISTS education_practice_sources" not in source
    assert "DROP TABLE IF EXISTS education_learning_kp_progress" not in source
    assert "DROP TABLE IF EXISTS education_learning_items" not in source


def test_legacy_removal_makes_publications_structure_only() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "DROP COLUMN IF EXISTS teaching_package_id" in source
    assert "ALTER COLUMN structure_id SET NOT NULL" in source
    assert "WHERE structure_id IS NULL" in source
