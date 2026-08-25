"""Reject JSON null elements in weekly homework recurrence metadata.

Revision ID: 037
Revises: 036
"""

from alembic import op


revision = "037"
down_revision = "036"
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
                    WHERE weekday.value IS NULL
                       OR weekday.value NOT IN ('1', '2', '3', '4', '5', '6', '7')
                )
            END
        $fn$
        """
    )


def downgrade() -> None:
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
