"""Revalidate weekly homework recurrence metadata after validator repair.

Revision ID: 038
Revises: 037
"""

from alembic import op


revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM education_task_rules
                WHERE recurrence ->> 'frequency' = 'weekly'
                  AND NOT education_weekdays_are_valid(recurrence -> 'weekdays')
            ) THEN
                RAISE EXCEPTION
                    'Cannot apply migration 038: invalid weekly recurrence metadata exists; repair or delete the affected task rules before retrying';
            END IF;
        END $$;
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


def downgrade() -> None:
    # Migration 038 only revalidates the same corrected 037 constraint.
    return None
