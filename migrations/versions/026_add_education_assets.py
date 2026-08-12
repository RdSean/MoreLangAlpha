"""Add private household-scoped education attachment metadata.

Revision ID: 026
Revises: 025
"""

from alembic import op


revision = "026"
down_revision = "025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE education_assets (
            asset_id UUID PRIMARY KEY,
            household_id UUID NOT NULL
                REFERENCES education_households(household_id) ON DELETE CASCADE,
            created_by_user_id VARCHAR(255) NOT NULL
                REFERENCES users(user_id) ON DELETE CASCADE,
            storage_key TEXT NOT NULL UNIQUE CHECK (storage_key LIKE 'education/%'),
            original_filename VARCHAR(255) NOT NULL,
            content_type VARCHAR(100) NOT NULL,
            size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX idx_education_assets_household_created
        ON education_assets (household_id, created_at DESC)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE education_assets")
