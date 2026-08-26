"""Make homework creation and attachment retries durable and idempotent.

Revision ID: 041
Revises: 040
Create Date: 2026-08-26
"""

from alembic import op


revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE education_task_rules
        ADD COLUMN idempotency_key UUID
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_education_task_rules_creator_idempotency
        ON education_task_rules (household_id, created_by_user_id, idempotency_key)
        WHERE idempotency_key IS NOT NULL
    """)
    op.execute("""
        ALTER TABLE education_assets
        ADD COLUMN staging_key UUID,
        ADD COLUMN staging_slot SMALLINT,
        ADD CONSTRAINT education_assets_staging_pair_check CHECK (
            (staging_key IS NULL AND staging_slot IS NULL)
            OR (staging_key IS NOT NULL AND staging_slot IS NOT NULL
                AND staging_slot BETWEEN 0 AND 19)
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_education_assets_staging_slot
        ON education_assets (household_id, created_by_user_id, staging_key, staging_slot)
        WHERE staging_key IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_education_assets_staging_slot")
    op.execute("""
        ALTER TABLE education_assets
        DROP CONSTRAINT IF EXISTS education_assets_staging_pair_check,
        DROP COLUMN IF EXISTS staging_slot,
        DROP COLUMN IF EXISTS staging_key
    """)
    op.execute("DROP INDEX IF EXISTS uq_education_task_rules_creator_idempotency")
    op.execute("ALTER TABLE education_task_rules DROP COLUMN IF EXISTS idempotency_key")
