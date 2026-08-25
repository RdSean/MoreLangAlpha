"""Repair homework workflow compatibility after the initial schema upgrade.

Revision ID: 036
Revises: 035
"""

from alembic import op


revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION education_weekdays_are_valid(weekdays JSONB)
        RETURNS BOOLEAN
        LANGUAGE SQL
        IMMUTABLE
        AS $fn$
            SELECT CASE
                WHEN weekdays IS NULL
                  OR weekdays = 'null'::jsonb
                  OR jsonb_typeof(weekdays) <> 'array'
                  OR jsonb_array_length(weekdays) = 0
                THEN FALSE
                ELSE NOT EXISTS (
                    SELECT 1
                    FROM jsonb_array_elements_text(weekdays) AS weekday(value)
                    WHERE weekday.value NOT IN ('1', '2', '3', '4', '5', '6', '7')
                )
            END
        $fn$
        """
    )
    op.execute(
        """
        ALTER TABLE education_task_rules
            DROP CONSTRAINT IF EXISTS education_task_rules_recurrence_frequency_check,
            ADD CONSTRAINT education_task_rules_recurrence_frequency_check
                CHECK (
                    recurrence ? 'frequency'
                    AND recurrence ? 'start_date'
                    AND recurrence ? 'due_time'
                    AND recurrence ->> 'frequency' IN ('once', 'daily', 'weekdays', 'weekly')
                    AND (
                        recurrence ->> 'frequency' <> 'weekly'
                        OR education_weekdays_are_valid(recurrence -> 'weekdays')
                    )
                )
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
    op.execute(
        """
        ALTER TABLE education_task_submissions
            ALTER COLUMN submission_kind SET DEFAULT 'check_in'
        """
    )
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
        DROP TRIGGER IF EXISTS education_task_submission_completion_mark
        ON education_task_submissions
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
    op.execute(
        """
        ALTER TABLE education_task_reviews
            DROP CONSTRAINT IF EXISTS education_task_reviews_submission_id_key,
            DROP CONSTRAINT IF EXISTS education_task_reviews_decision_check,
            ADD CONSTRAINT education_task_reviews_decision_check
                CHECK (decision IN ('feedback', 'revision_requested', 'completed'))
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE education_task_reviews
            DROP CONSTRAINT IF EXISTS education_task_reviews_decision_check
        """
    )
    op.execute(
        """
        UPDATE education_task_reviews
        SET decision = 'feedback'
        WHERE decision = 'completed'
        """
    )
    # Downgrading loses append-only review history: retain the newest review for
    # each submission before restoring the old one-review-per-submission schema.
    op.execute(
        """
        DELETE FROM education_task_reviews
        WHERE review_id IN (
            SELECT review_id
            FROM (
                SELECT review_id,
                       ROW_NUMBER() OVER (
                           PARTITION BY submission_id
                           ORDER BY created_at DESC, review_id DESC
                       ) AS duplicate_position
                FROM education_task_reviews
            ) AS ranked_reviews
            WHERE duplicate_position > 1
        )
        """
    )
    op.execute(
        """
        ALTER TABLE education_task_reviews
            ADD CONSTRAINT education_task_reviews_decision_check
                CHECK (decision IN ('feedback', 'revision_requested')),
            ADD CONSTRAINT education_task_reviews_submission_id_key
                UNIQUE (submission_id)
        """
    )
    op.execute("DROP TRIGGER IF EXISTS education_task_submission_completion_mark ON education_task_submissions")
    op.execute("DROP FUNCTION IF EXISTS mark_education_task_completed_on_submission()")
    op.execute(
        """
        ALTER TABLE education_task_submissions
            ALTER COLUMN submission_kind DROP DEFAULT
        """
    )
    op.execute(
        """
        ALTER TABLE education_tasks
            DROP CONSTRAINT IF EXISTS education_tasks_status_check
        """
    )
    # Downgrading 036 is source-safe in this unmerged feature branch: no
    # released database version depends on this downgrade body, and normalizing
    # legacy states before restoring 035's strict constraint prevents rollback
    # from failing on rows written while the compatibility bridge was active.
    op.execute(
        """
        UPDATE education_tasks AS tasks
        SET status = CASE tasks.status
                WHEN 'submitted' THEN 'completed'
                WHEN 'revision_requested' THEN 'completed'
                ELSE tasks.status
            END,
            completed_at = COALESCE(
                tasks.completed_at,
                (
                    SELECT MAX(submissions.created_at)
                    FROM education_task_submissions AS submissions
                    WHERE submissions.task_id = tasks.task_id
                ),
                tasks.created_at
            )
        WHERE tasks.status IN ('submitted', 'revision_requested')
          AND EXISTS (
              SELECT 1
              FROM education_task_submissions AS submissions
              WHERE submissions.task_id = tasks.task_id
          )
        """
    )
    op.execute(
        """
        UPDATE education_tasks
        SET status = 'open'
        WHERE status IN ('submitted', 'revision_requested')
        """
    )
    op.execute(
        """
        ALTER TABLE education_tasks
            ADD CONSTRAINT education_tasks_status_check
                CHECK (status IN ('open', 'completed', 'cancelled'))
        """
    )
    op.execute(
        """
        ALTER TABLE education_task_rules
            DROP CONSTRAINT IF EXISTS education_task_rules_recurrence_frequency_check
        """
    )
    op.execute("DROP FUNCTION IF EXISTS education_weekdays_are_valid(JSONB)")
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
