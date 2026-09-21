"""Contract for assigning knowledge points to one Reading."""

from pathlib import Path


SOURCE = Path(
    "migrations/versions/074_add_kp_reading_scope.py"
).read_text(encoding="utf-8")


def test_kp_reading_scope_migration_follows_scope_table() -> None:
    assert 'revision = "074_kp_reading_scope"' in SOURCE
    assert 'down_revision = "073_textbook_scopes"' in SOURCE


def test_kp_reading_scope_migration_allows_only_known_slots() -> None:
    assert "ADD COLUMN scope_slot VARCHAR(16)" in SOURCE
    assert "scope_slot IN ('reading_a', 'reading_b')" in SOURCE
