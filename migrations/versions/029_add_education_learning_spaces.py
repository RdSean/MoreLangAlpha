"""Persist canonical Flash conversations for published textbook assignments.

Revision ID: 029
Revises: 028
"""

from alembic import op


revision = "029"
down_revision = "028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE education_processing_jobs
        ADD COLUMN claim_expires_at TIMESTAMPTZ
    """)
    op.execute("""
        CREATE TABLE education_learning_spaces (
            assignment_id UUID PRIMARY KEY
                REFERENCES education_textbook_assignments(assignment_id) ON DELETE RESTRICT,
            workspace_id UUID NOT NULL
                REFERENCES workspaces(workspace_id) ON DELETE RESTRICT,
            conversation_thread_id UUID NOT NULL UNIQUE
                REFERENCES conversation_threads(conversation_thread_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX idx_education_learning_spaces_thread
        ON education_learning_spaces (conversation_thread_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE education_learning_spaces")
    op.execute(
        "ALTER TABLE education_processing_jobs DROP COLUMN IF EXISTS claim_expires_at"
    )
