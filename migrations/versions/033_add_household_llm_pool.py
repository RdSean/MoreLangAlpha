"""Add household-owned LLM endpoints and student model preferences.

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
        CREATE TABLE household_llm_endpoints (
            endpoint_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            household_id UUID NOT NULL
                REFERENCES education_households(household_id) ON DELETE CASCADE,
            display_name VARCHAR(128) NOT NULL,
            provider VARCHAR(64) NOT NULL,
            model_id VARCHAR(255) NOT NULL,
            base_url TEXT,
            api_key BYTEA,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_by VARCHAR(255) NOT NULL
                REFERENCES users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (household_id, endpoint_id),
            CHECK (length(trim(display_name)) > 0),
            CHECK (length(trim(provider)) > 0),
            CHECK (length(trim(model_id)) > 0)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE household_llm_settings (
            household_id UUID PRIMARY KEY
                REFERENCES education_households(household_id) ON DELETE CASCADE,
            default_endpoint_id UUID,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (household_id, default_endpoint_id)
                REFERENCES household_llm_endpoints(household_id, endpoint_id)
                ON DELETE SET NULL (default_endpoint_id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE student_llm_preferences (
            user_id VARCHAR(255) PRIMARY KEY
                REFERENCES users(user_id) ON DELETE CASCADE,
            household_id UUID NOT NULL,
            endpoint_id UUID,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (household_id, user_id)
                REFERENCES education_memberships(household_id, user_id)
                ON DELETE CASCADE,
            FOREIGN KEY (household_id, endpoint_id)
                REFERENCES household_llm_endpoints(household_id, endpoint_id)
                ON DELETE SET NULL (endpoint_id)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX idx_household_llm_endpoints_availability
        ON household_llm_endpoints
            (household_id, enabled, sort_order, display_name)
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
            ADD COLUMN llm_endpoint_id UUID,
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
                ON DELETE SET NULL,
            ADD CONSTRAINT conversation_usages_endpoint_fk
                FOREIGN KEY (llm_endpoint_id)
                REFERENCES household_llm_endpoints(endpoint_id)
                ON DELETE SET NULL
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE conversation_usages
            DROP CONSTRAINT IF EXISTS conversation_usages_endpoint_fk,
            DROP CONSTRAINT IF EXISTS conversation_usages_household_fk,
            DROP COLUMN IF EXISTS model_snapshot,
            DROP COLUMN IF EXISTS credential_source,
            DROP COLUMN IF EXISTS llm_endpoint_id,
            DROP COLUMN IF EXISTS household_id
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_student_llm_preferences_household_user")
    op.execute("DROP INDEX IF EXISTS idx_household_llm_endpoints_availability")
    op.execute("DROP TABLE IF EXISTS student_llm_preferences")
    op.execute("DROP TABLE IF EXISTS household_llm_settings")
    op.execute("DROP TABLE IF EXISTS household_llm_endpoints")
