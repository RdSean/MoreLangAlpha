"""Use the household creator as the shared model owner.

Revision ID: 033
Revises: 032
"""

from alembic import op


revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE education_households
            ADD COLUMN model_owner_user_id VARCHAR(255)
                REFERENCES users(user_id) ON DELETE RESTRICT
        """
    )
    op.execute(
        """
        UPDATE education_households AS households
        SET model_owner_user_id = parents.user_id
        FROM LATERAL (
            SELECT memberships.user_id
            FROM education_memberships AS memberships
            WHERE memberships.household_id = households.household_id
              AND memberships.role = 'parent'
            ORDER BY memberships.created_at ASC
            LIMIT 1
        ) AS parents
        WHERE households.model_owner_user_id IS NULL
        """
    )
    op.execute(
        """
        CREATE TABLE student_llm_preferences (
            user_id VARCHAR(255) PRIMARY KEY
                REFERENCES users(user_id) ON DELETE CASCADE,
            household_id UUID NOT NULL,
            model_key VARCHAR(255) NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (household_id, user_id)
                REFERENCES education_memberships(household_id, user_id)
                ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_student_llm_preferences_household_user
        ON student_llm_preferences (household_id, user_id)
        """
    )
    op.execute(
        """
        ALTER TABLE conversation_usages
            ADD COLUMN household_id UUID,
            ADD COLUMN credential_source VARCHAR(32),
            ADD COLUMN model_snapshot JSONB
        """
    )
    op.execute(
        """
        ALTER TABLE conversation_usages
            ADD CONSTRAINT conversation_usages_household_fk
                FOREIGN KEY (household_id)
                REFERENCES education_households(household_id)
                ON DELETE SET NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE conversation_usages
            DROP CONSTRAINT IF EXISTS conversation_usages_household_fk,
            DROP COLUMN IF EXISTS model_snapshot,
            DROP COLUMN IF EXISTS credential_source,
            DROP COLUMN IF EXISTS household_id
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_student_llm_preferences_household_user")
    op.execute("DROP TABLE IF EXISTS student_llm_preferences")
    op.execute("ALTER TABLE education_households DROP COLUMN IF EXISTS model_owner_user_id")
