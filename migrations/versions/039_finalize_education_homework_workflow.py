"""Finalize homework completion as independent from reviews.

Revision ID: 039
Revises: 038
"""

from alembic import op


revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def _restore_completion_trigger() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION mark_education_task_completed_on_submission()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $fn$
        BEGIN
            UPDATE education_tasks AS tasks
            SET completed_at = COALESCE(tasks.completed_at, NEW.created_at)
            WHERE tasks.task_id = NEW.task_id
              AND tasks.status <> 'cancelled';
            RETURN NEW;
        END;
        $fn$
        """
    )
    op.execute(
        """
        CREATE TRIGGER education_task_submission_completion_mark
        AFTER INSERT ON education_task_submissions
        FOR EACH ROW
        EXECUTE FUNCTION mark_education_task_completed_on_submission()
        """
    )


def upgrade() -> None:
    # A legacy state only proves completion if there is a student submission.
    # Rows without one are retained as actionable open tasks rather than being
    # presented to a student as already completed.
    op.execute(
        """
        UPDATE education_tasks AS tasks
        SET status = CASE
                WHEN EXISTS (
                    SELECT 1 FROM education_task_submissions AS submissions
                    WHERE submissions.task_id = tasks.task_id
                ) THEN 'completed'
                ELSE 'open'
            END,
            completed_at = CASE
                WHEN EXISTS (
                    SELECT 1 FROM education_task_submissions AS submissions
                    WHERE submissions.task_id = tasks.task_id
                ) THEN COALESCE(
                    tasks.completed_at,
                    (
                        SELECT MIN(submissions.created_at)
                        FROM education_task_submissions AS submissions
                        WHERE submissions.task_id = tasks.task_id
                    )
                )
                ELSE NULL
            END
        WHERE tasks.status IN ('submitted', 'revision_requested', 'completed')
        """
    )
    op.execute(
        """
        UPDATE education_task_reviews
        SET decision = 'feedback'
        WHERE decision = 'completed'
        """
    )

    # Old rows may carry only individually valid subject and type codes. They
    # have no settled classification if that pair is not in the dictionary.
    for table in ("education_task_rules", "education_tasks"):
        op.execute(
            f"""
            UPDATE {table} AS records
            SET subject_code = NULL,
                type_code = NULL,
                practice_source_code = NULL
            WHERE records.subject_code IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM education_subject_homework_types AS mappings
                  WHERE mappings.subject_code = records.subject_code
                    AND mappings.type_code = records.type_code
              )
            """
        )
        op.execute(
            f"""
            UPDATE {table}
            SET subject_code = NULL,
                type_code = NULL,
                practice_source_code = NULL
            WHERE type_code = 'practice' AND practice_source_code IS NULL
            """
        )
        op.execute(
            f"""
            ALTER TABLE {table}
                DROP CONSTRAINT IF EXISTS {table}_practice_source_check,
                ADD CONSTRAINT {table}_practice_source_check
                    CHECK (
                        (type_code IS NULL AND practice_source_code IS NULL)
                        OR (type_code = 'practice' AND practice_source_code IS NOT NULL)
                        OR (type_code <> 'practice' AND practice_source_code IS NULL)
                    ),
                ADD CONSTRAINT {table}_subject_type_check
                    CHECK ((subject_code IS NULL) = (type_code IS NULL)),
                ADD CONSTRAINT {table}_subject_type_fkey
                    FOREIGN KEY (subject_code, type_code)
                    REFERENCES education_subject_homework_types(subject_code, type_code)
                    ON DELETE RESTRICT
            """
        )

    op.execute(
        """
        ALTER TABLE education_tasks
            DROP CONSTRAINT IF EXISTS education_tasks_status_check,
            ADD CONSTRAINT education_tasks_status_check
                CHECK (status IN ('open', 'completed', 'cancelled'))
        """
    )
    op.execute(
        """
        ALTER TABLE education_task_reviews
            DROP CONSTRAINT IF EXISTS education_task_reviews_decision_check,
            ADD CONSTRAINT education_task_reviews_decision_check
                CHECK (decision IN ('feedback', 'revision_requested'))
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS education_task_submission_completion_mark
        ON education_task_submissions
        """
    )
    op.execute("DROP FUNCTION IF EXISTS mark_education_task_completed_on_submission()")


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE education_task_reviews
            DROP CONSTRAINT IF EXISTS education_task_reviews_decision_check,
            ADD CONSTRAINT education_task_reviews_decision_check
                CHECK (decision IN ('feedback', 'revision_requested', 'completed'))
        """
    )
    op.execute(
        """
        ALTER TABLE education_tasks
            DROP CONSTRAINT IF EXISTS education_tasks_status_check,
            ADD CONSTRAINT education_tasks_status_check
                CHECK (status IN ('open', 'submitted', 'revision_requested', 'completed', 'cancelled'))
        """
    )
    for table in ("education_tasks", "education_task_rules"):
        op.execute(
            f"""
            ALTER TABLE {table}
                DROP CONSTRAINT IF EXISTS {table}_subject_type_fkey,
                DROP CONSTRAINT IF EXISTS {table}_subject_type_check,
                DROP CONSTRAINT IF EXISTS {table}_practice_source_check,
                ADD CONSTRAINT {table}_practice_source_check
                    CHECK (practice_source_code IS NULL OR type_code = 'practice')
            """
        )
    _restore_completion_trigger()
