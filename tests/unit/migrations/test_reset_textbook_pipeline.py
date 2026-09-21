"""Contract for the destructive textbook pipeline reset."""

from pathlib import Path


SOURCE = Path(
    "migrations/versions/075_reset_textbook_pipeline.py"
).read_text(encoding="utf-8")


def test_reset_migration_follows_kp_reading_scope() -> None:
    assert 'revision = "075_reset_textbook_pipeline"' in SOURCE
    assert 'down_revision = "074_kp_reading_scope"' in SOURCE


def test_reset_migration_clears_only_the_textbook_dependency_graph() -> None:
    assert "TRUNCATE TABLE education_textbooks" in SOURCE
    assert "RESTART IDENTITY CASCADE" in SOURCE
    assert "DROP DATABASE" not in SOURCE
    assert "TRUNCATE TABLE education_assets" not in SOURCE
