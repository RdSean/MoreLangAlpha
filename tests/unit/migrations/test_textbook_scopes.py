"""Contract for the reading-scope migration."""

from pathlib import Path


SOURCE = Path("migrations/versions/073_add_textbook_scopes.py").read_text()


def test_scope_migration_creates_the_scope_table():
    assert "CREATE TABLE education_textbook_scopes" in SOURCE
    assert "revision = \"073_textbook_scopes\"" in SOURCE
    assert "down_revision = \"072_structure_validation_warnings\"" in SOURCE


def test_scope_migration_bounds_every_range():
    assert "CHECK (line_start > 0)" in SOURCE
    assert "CHECK (line_end > line_start)" in SOURCE
    assert "CHECK (char_end > char_start)" in SOURCE


def test_scope_migration_limits_slots_to_the_two_readings():
    assert "slot IN ('reading_a', 'reading_b')" in SOURCE


def test_scope_migration_requires_a_parent_unit():
    assert "REFERENCES education_structure_units(unit_id)" in SOURCE
    assert "REFERENCES education_textbook_structures(structure_id)" in SOURCE
