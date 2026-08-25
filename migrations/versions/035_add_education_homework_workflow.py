"""Add student profiles and an append-only homework workflow.

Revision ID: 035
Revises: 034
"""

from alembic import op


revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE education_student_profiles (
            household_id UUID NOT NULL,
            user_id VARCHAR(255) NOT NULL,
            grade_code VARCHAR(4)
                REFERENCES education_grade_levels(code) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (household_id, user_id),
            FOREIGN KEY (household_id, user_id)
                REFERENCES education_memberships(household_id, user_id)
                ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE OR REPLACE FUNCTION validate_education_student_profile_membership()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $fn$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM education_student_profiles AS profiles
                LEFT JOIN education_memberships AS memberships
                  ON memberships.household_id = profiles.household_id
                 AND memberships.user_id = profiles.user_id
                WHERE memberships.role IS DISTINCT FROM 'student'
            ) THEN
                RAISE EXCEPTION 'Education student profiles require a student household membership';
            END IF;
            RETURN NULL;
        END;
        $fn$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER education_student_profile_membership_check
        AFTER INSERT OR UPDATE OF household_id, user_id
        ON education_student_profiles
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION validate_education_student_profile_membership()
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER education_membership_student_profile_check
        AFTER UPDATE OF role OR DELETE
        ON education_memberships
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION validate_education_student_profile_membership()
        """
    )
    op.execute(
        """
        INSERT INTO education_student_profiles (household_id, user_id)
        SELECT memberships.household_id, memberships.user_id
        FROM education_memberships AS memberships
        WHERE memberships.role = 'student'
        ON CONFLICT (household_id, user_id) DO NOTHING
        """
    )

    for table in ("education_task_rules", "education_tasks"):
        op.execute(
            f"""
            ALTER TABLE {table}
                ADD COLUMN subject_code VARCHAR(16)
                    REFERENCES education_subjects(code) ON DELETE RESTRICT,
                ADD COLUMN type_code VARCHAR(16)
                    REFERENCES education_homework_types(code) ON DELETE RESTRICT,
                ADD COLUMN practice_source_code VARCHAR(16)
                    REFERENCES education_practice_sources(code) ON DELETE RESTRICT,
                ADD COLUMN grade_code VARCHAR(4)
                    REFERENCES education_grade_levels(code) ON DELETE RESTRICT,
                ADD CONSTRAINT {table}_practice_source_check
                    CHECK (practice_source_code IS NULL OR type_code = 'practice')
            """
        )

    op.execute(
        """
        ALTER TABLE education_task_rules
            ADD CONSTRAINT education_task_rules_recurrence_frequency_check
            CHECK (
                recurrence ? 'frequency'
                AND recurrence ? 'start_date'
                AND recurrence ? 'due_time'
                AND recurrence ->> 'frequency' IN ('once', 'daily', 'weekdays', 'weekly')
                AND (
                    recurrence ->> 'frequency' <> 'weekly'
                    OR jsonb_typeof(recurrence -> 'weekdays') = 'array'
                )
            )
        """
    )

    op.execute(
        """
        ALTER TABLE education_tasks
            ADD COLUMN completed_at TIMESTAMPTZ
        """
    )
    op.execute(
        """
        UPDATE education_tasks AS tasks
        SET status = CASE tasks.status
                WHEN 'submitted' THEN 'completed'
                WHEN 'revision_requested' THEN 'completed'
                ELSE tasks.status
            END,
            completed_at = (
                SELECT MAX(submissions.created_at)
                FROM education_task_submissions AS submissions
                WHERE submissions.task_id = tasks.task_id
            )
        WHERE tasks.status IN ('submitted', 'revision_requested')
          AND EXISTS (
              SELECT 1
              FROM education_task_submissions AS submissions
              WHERE submissions.task_id = tasks.task_id
          )
        """
    )
    # Invalid legacy rows without a submission have not been completed by a
    # student. Keep them actionable rather than silently claiming completion.
    op.execute(
        """
        UPDATE education_tasks
        SET status = 'open'
        WHERE status IN ('submitted', 'revision_requested')
        """
    )
    op.execute(
        """
        UPDATE education_tasks AS tasks
        SET completed_at = (
            SELECT MAX(submissions.created_at)
            FROM education_task_submissions AS submissions
            WHERE submissions.task_id = tasks.task_id
        )
        WHERE tasks.status = 'completed'
          AND tasks.completed_at IS NULL
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
        CREATE INDEX idx_education_tasks_household_occurrence
        ON education_tasks (household_id, occurrence_date DESC)
        """
    )

    op.execute(
        """
        ALTER TABLE education_task_submissions
            ADD COLUMN submission_kind VARCHAR(16)
        """
    )
    op.execute(
        """
        UPDATE education_task_submissions
        SET submission_kind = CASE
            WHEN sequence = 1 THEN 'check_in'
            ELSE 'revision'
        END
        """
    )
    op.execute(
        """
        ALTER TABLE education_task_submissions
            ALTER COLUMN submission_kind SET NOT NULL,
            ADD CONSTRAINT education_task_submissions_submission_kind_check
                CHECK (submission_kind IN ('check_in', 'revision'))
        """
    )

    op.execute(
        """
        ALTER TABLE education_task_reviews
            DROP CONSTRAINT IF EXISTS education_task_reviews_submission_id_key,
            DROP CONSTRAINT IF EXISTS education_task_reviews_decision_check
        """
    )
    op.execute(
        """
        UPDATE education_task_reviews
        SET decision = CASE decision
            WHEN 'completed' THEN 'feedback'
            ELSE decision
        END
        """
    )
    op.execute(
        """
        ALTER TABLE education_task_reviews
            ADD CONSTRAINT education_task_reviews_decision_check
                CHECK (decision IN ('feedback', 'revision_requested'))
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS education_membership_student_profile_check ON education_memberships")
    op.execute("DROP TRIGGER IF EXISTS education_student_profile_membership_check ON education_student_profiles")
    op.execute("DROP FUNCTION IF EXISTS validate_education_student_profile_membership()")

    op.execute("DROP INDEX IF EXISTS idx_education_tasks_household_occurrence")
    op.execute(
        """
        ALTER TABLE education_task_reviews
            DROP CONSTRAINT IF EXISTS education_task_reviews_decision_check
        """
    )
    op.execute("UPDATE education_task_reviews SET decision = 'completed' WHERE decision = 'feedback'")
    op.execute(
        """
        ALTER TABLE education_task_reviews
            ADD CONSTRAINT education_task_reviews_decision_check
                CHECK (decision IN ('revision_requested', 'completed'))
        """
    )
    op.execute(
        """
        ALTER TABLE education_task_submissions
            DROP CONSTRAINT IF EXISTS education_task_submissions_submission_kind_check,
            DROP COLUMN submission_kind
        """
    )
    op.execute(
        """
        ALTER TABLE education_tasks
            DROP CONSTRAINT IF EXISTS education_tasks_status_check,
            ADD CONSTRAINT education_tasks_status_check
                CHECK (status IN ('open', 'submitted', 'revision_requested', 'completed', 'cancelled')),
            DROP COLUMN completed_at
        """
    )
    op.execute(
        """
        ALTER TABLE education_task_rules
            DROP CONSTRAINT IF EXISTS education_task_rules_recurrence_frequency_check
        """
    )
    for table in ("education_tasks", "education_task_rules"):
        op.execute(
            f"""
            ALTER TABLE {table}
                DROP CONSTRAINT IF EXISTS {table}_practice_source_check,
                DROP COLUMN subject_code,
                DROP COLUMN type_code,
                DROP COLUMN practice_source_code,
                DROP COLUMN grade_code
            """
        )
    op.execute("DROP TABLE education_student_profiles")
