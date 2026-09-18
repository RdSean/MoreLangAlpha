from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "067_add_kp_lessons.py"
)


def test_kp_lesson_migration_follows_structure_models() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "067_kp_lessons"
    assert migration["down_revision"] == "066_textbook_structure_models"


def test_kp_lesson_migration_keeps_revisions_and_publication_freeze() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for table in (
        "education_kp_lessons",
        "education_kp_lesson_revisions",
        "education_publication_kp_lessons",
    ):
        assert f"CREATE TABLE {table}" in source

    assert "knowledge_point_id UUID NOT NULL UNIQUE" in source
    assert "UNIQUE (lesson_id, revision)" in source
    assert "content_sha256 VARCHAR(64) NOT NULL" in source
    assert "PRIMARY KEY (publication_id, knowledge_point_id)" in source


def test_kp_lesson_migration_downgrades_only_its_own_tables() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "DROP TABLE IF EXISTS education_publication_kp_lessons" in source
    assert "DROP TABLE IF EXISTS education_kp_lesson_revisions" in source
    assert "DROP TABLE IF EXISTS education_kp_lessons" in source
    assert "DROP TABLE IF EXISTS education_textbook_publications" not in source
