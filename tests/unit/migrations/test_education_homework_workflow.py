"""Regression contracts for the K12 homework workflow schema upgrade."""

from __future__ import annotations

from pathlib import Path
import runpy


def _workflow_schema_migration_source() -> str:
    return (
        Path(__file__).parents[3]
        / "migrations/versions/035_add_education_homework_workflow.py"
    ).read_text()


def _workflow_compatibility_repair_source() -> str:
    return (
        Path(__file__).parents[3]
        / "migrations/versions/036_repair_education_homework_workflow.py"
    ).read_text()


def _workflow_weekday_repair_source() -> str:
    return (
        Path(__file__).parents[3]
        / "migrations/versions/037_repair_education_weekday_validation.py"
    ).read_text()


def _workflow_revalidation_source() -> str:
    return (
        Path(__file__).parents[3]
        / "migrations/versions/038_revalidate_education_homework_recurrence.py"
    ).read_text()


def _workflow_finalization_source() -> str:
    return (
        Path(__file__).parents[3]
        / "migrations/versions/039_finalize_education_homework_workflow.py"
    ).read_text()


def _workflow_open_submission_repair_source() -> str:
    return (
        Path(__file__).parents[3]
        / "migrations/versions/040_repair_open_education_tasks_with_submissions.py"
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
    migration = _workflow_schema_migration_source()

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
    migration = _workflow_schema_migration_source()

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


def test_workflow_repair_keeps_legacy_writes_compatible_until_service_cutover():
    migration = _workflow_compatibility_repair_source()

    migration_path = (
        Path(__file__).parents[3]
        / "migrations/versions/036_repair_education_homework_workflow.py"
    )
    migration_globals = runpy.run_path(str(migration_path))

    assert migration_globals["revision"] == "036"
    assert migration_globals["down_revision"] == "035"

    assert "mark_education_task_completed_on_submission" in migration
    assert "AFTER INSERT ON education_task_submissions" in migration
    assert "completed_at = COALESCE(tasks.completed_at, NEW.created_at)" in migration
    assert "ALTER COLUMN submission_kind SET DEFAULT 'check_in'" in migration
    assert "DROP CONSTRAINT IF EXISTS education_task_reviews_submission_id_key" in migration
    assert "'feedback', 'revision_requested', 'completed'" in migration
    assert "CHECK (status IN ('open', 'submitted', 'revision_requested', 'completed', 'cancelled'))" in migration
    assert "Downgrading 036 is source-safe" in migration
    assert "WHEN 'submitted' THEN 'completed'" in migration
    assert "WHEN 'revision_requested' THEN 'completed'" in migration
    assert "WHERE tasks.status IN ('submitted', 'revision_requested')" in migration


def test_workflow_repair_validates_weekly_iso_days_and_restores_review_uniqueness():
    migration = _workflow_compatibility_repair_source()

    assert "'once', 'daily', 'weekdays', 'weekly'" in migration
    assert "recurrence ->> 'frequency'" in migration
    assert "CREATE OR REPLACE FUNCTION education_weekdays_are_valid" in migration
    assert "education_weekdays_are_valid(recurrence -> 'weekdays')" in migration
    assert "jsonb_array_length(weekdays) = 0" in migration
    assert "jsonb_array_elements_text(weekdays)" in migration
    assert "'1', '2', '3', '4', '5', '6', '7'" in migration
    assert "Downgrading loses append-only review history" in migration
    assert "ROW_NUMBER() OVER" in migration
    assert "ADD CONSTRAINT education_task_reviews_submission_id_key" in migration


def test_weekday_repair_rejects_json_null_array_elements():
    migration = _workflow_weekday_repair_source()
    migration_globals = runpy.run_path(
        str(
            Path(__file__).parents[3]
            / "migrations/versions/037_repair_education_weekday_validation.py"
        )
    )

    assert migration_globals["revision"] == "037"
    assert migration_globals["down_revision"] == "036"
    assert "CREATE OR REPLACE FUNCTION education_weekdays_are_valid" in migration
    assert "weekday.value IS NULL" in migration


def test_revalidation_migration_rejects_dirty_weekly_recurrences_before_rebuild():
    migration = _workflow_revalidation_source()
    migration_globals = runpy.run_path(
        str(
            Path(__file__).parents[3]
            / "migrations/versions/038_revalidate_education_homework_recurrence.py"
        )
    )

    assert migration_globals["revision"] == "038"
    assert migration_globals["down_revision"] == "037"
    assert "Cannot apply migration 038: invalid weekly recurrence metadata exists" in migration
    assert "NOT education_weekdays_are_valid(recurrence -> 'weekdays')" in migration
    assert "DROP CONSTRAINT IF EXISTS education_task_rules_recurrence_frequency_check" in migration
    assert "ADD CONSTRAINT education_task_rules_recurrence_frequency_check" in migration


def test_finalization_migration_removes_legacy_states_and_completion_trigger():
    migration = _workflow_finalization_source()
    migration_globals = runpy.run_path(
        str(
            Path(__file__).parents[3]
            / "migrations/versions/039_finalize_education_homework_workflow.py"
        )
    )

    assert migration_globals["revision"] == "039"
    assert migration_globals["down_revision"] == "038"
    assert "DROP TRIGGER IF EXISTS education_task_submission_completion_mark" in migration
    assert "DROP FUNCTION IF EXISTS mark_education_task_completed_on_submission()" in migration
    assert "CHECK (status IN ('open', 'completed', 'cancelled'))" in migration
    assert "CHECK (decision IN ('feedback', 'revision_requested'))" in migration
    assert "tasks.status IN ('submitted', 'revision_requested', 'completed')" in migration
    assert "FOREIGN KEY (subject_code, type_code)" in migration
    assert "REFERENCES education_subject_homework_types(subject_code, type_code)" in migration
    assert "WHERE records.subject_code IS NULL" in migration
    assert "OR records.type_code IS NULL" in migration
    assert "grade_code = NULL" in migration


def test_open_submission_repair_completes_legacy_open_tasks_from_first_submission():
    migration = _workflow_open_submission_repair_source()
    migration_globals = runpy.run_path(
        str(
            Path(__file__).parents[3]
            / "migrations/versions/040_repair_open_education_tasks_with_submissions.py"
        )
    )

    assert migration_globals["revision"] == "040"
    assert migration_globals["down_revision"] == "039"
    assert "WHERE tasks.status = 'open'" in migration
    assert "SET status = 'completed'" in migration
    assert "MIN(submissions.created_at)" in migration
