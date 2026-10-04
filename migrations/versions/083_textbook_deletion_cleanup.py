"""Persist cleanup of deleted textbooks independently of textbook foreign keys."""

from alembic import op

revision = "083_textbook_deletion_cleanup"
down_revision = "082_more_to_skills_textbooks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE education_book_deletion_cleanup (
            textbook_id UUID PRIMARY KEY,
            household_id UUID NOT NULL,
            lease_token UUID,
            next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            attempts INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX idx_education_book_deletion_cleanup_due
        ON education_book_deletion_cleanup (next_attempt_at, textbook_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE education_book_deletion_cleanup")
