"""Regression contracts for the seeded K12 homework dictionaries."""

from __future__ import annotations

from pathlib import Path


def test_homework_dictionary_migration_seeds_the_agreed_k12_codes():
    migration = (
        Path(__file__).parents[3]
        / "migrations/versions/034_add_education_homework_dictionaries.py"
    ).read_text()

    for code in (
        "chinese",
        "math",
        "english",
        "physics",
        "chemistry",
        "biology",
        "history",
        "geography",
        "politics",
        "preview",
        "practice",
        "read",
        "recite",
        "write",
        "review",
        "research",
        "listen",
        "grammar",
        "speak",
        "schoolwork",
        "homework",
    ):
        assert f"'{code}'" in migration

    for grade in range(1, 13):
        assert f"'g{grade}'" in migration


def test_homework_dictionary_migration_keeps_subject_colours_and_type_links():
    migration = (
        Path(__file__).parents[3]
        / "migrations/versions/034_add_education_homework_dictionaries.py"
    ).read_text()

    assert "CREATE TABLE education_subjects" in migration
    assert "color CHAR(7) NOT NULL" in migration
    assert "CREATE TABLE education_homework_types" in migration
    assert "CREATE TABLE education_subject_homework_types" in migration
    assert "CREATE TABLE education_grade_levels" in migration
    assert "CREATE TABLE education_practice_sources" in migration
    assert "FOREIGN KEY (subject_code) REFERENCES education_subjects(code)" in migration
    assert "FOREIGN KEY (type_code) REFERENCES education_homework_types(code)" in migration
