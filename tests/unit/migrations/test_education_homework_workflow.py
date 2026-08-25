"""Regression contracts for the K12 homework workflow schema upgrade."""

from __future__ import annotations

from pathlib import Path
import runpy


def _migration_source() -> str:
    return (
        Path(__file__).parents[3]
        / "migrations/versions/035_add_education_homework_workflow.py"
    ).read_text()


def test_homework_workflow_migration_follows_seeded_dictionaries():
    migration_path = (
        Path(__file__).parents[3]
        / "migrations/versions/035_add_education_homework_workflow.py"
    )

    migration = runpy.run_path(str(migration_path))

    assert migration["revision"] == "035"
    assert migration["down_revision"] == "034"


def test_student_profiles_are_scoped_to_student_memberships_and_grades():
    migration = _migration_source()

    assert "CREATE TABLE education_student_profiles" in migration
    assert "user_id VARCHAR(255) NOT NULL" in migration
    assert "household_id UUID NOT NULL" in migration
    assert "grade_code VARCHAR(4)" in migration
    assert "FOREIGN KEY (household_id, user_id)" in migration
    assert "REFERENCES education_memberships(household_id, user_id)" in migration
    assert "REFERENCES education_grade_levels(code)" in migration
    assert "memberships.role = 'student'" in migration
    assert "INSERT INTO education_student_profiles" in migration


def test_tasks_and_rules_keep_nullable_classification_snapshots():
    migration = _migration_source()

    for table in ("education_task_rules", "education_tasks"):
        assert f"ALTER TABLE {table}" in migration
        for column in (
            "subject_code VARCHAR(16)",
            "type_code VARCHAR(16)",
            "practice_source_code VARCHAR(16)",
            "grade_code VARCHAR(4)",
        ):
            assert column in migration

    assert "REFERENCES education_subjects(code)" in migration
    assert "REFERENCES education_homework_types(code)" in migration
    assert "REFERENCES education_practice_sources(code)" in migration
    assert "REFERENCES education_grade_levels(code)" in migration
    assert "practice_source_code IS NULL OR type_code = 'practice'" in migration


def test_workflow_migration_updates_completion_recurrence_submissions_and_reviews():
    migration = _migration_source()

    assert "completed_at TIMESTAMPTZ" in migration
    assert "idx_education_tasks_household_occurrence" in migration
    assert "'once', 'daily', 'weekdays', 'weekly'" in migration
    assert "recurrence ->> 'frequency'" in migration
    assert "submission_kind VARCHAR(16)" in migration
    assert "'check_in'" in migration
    assert "'revision'" in migration
    assert "DROP CONSTRAINT IF EXISTS education_task_reviews_submission_id_key" in migration
    assert "'feedback', 'revision_requested'" in migration
    assert "WHEN 'completed' THEN 'feedback'" in migration
    assert "WHEN 'submitted' THEN 'completed'" in migration
    assert "WHEN 'revision_requested' THEN 'completed'" in migration
    assert "'open', 'completed', 'cancelled'" in migration
