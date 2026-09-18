from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "069_add_learning_items_and_profiles.py"
)


def test_learning_items_and_profiles_follow_structure_publications() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "069_learning_items_and_profiles"
    assert migration["down_revision"] == "068_structure_publications"


def test_learning_assets_are_assignment_scoped() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for table in (
        "education_learning_kp_progress",
        "education_learning_items",
        "education_processing_profiles",
    ):
        assert f"CREATE TABLE {table}" in source

    assert "PRIMARY KEY (assignment_id, knowledge_point_id)" in source
    assert "kind VARCHAR(24) NOT NULL" in source
    assert "knowledge_point_id IS NOT NULL" in source
    assert "unit_id IS NOT NULL" in source
    assert "profile_sha256 VARCHAR(64) NOT NULL" in source


def test_learning_asset_migration_downgrades_only_new_tables() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "DROP TABLE IF EXISTS education_learning_items" in source
    assert "DROP TABLE IF EXISTS education_learning_kp_progress" in source
    assert "DROP TABLE IF EXISTS education_processing_profiles" in source
    assert "DROP TABLE IF EXISTS education_textbook_publications" not in source
