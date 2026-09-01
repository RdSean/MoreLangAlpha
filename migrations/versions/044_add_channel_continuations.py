"""Persist channel answer tails that require a fresh provider context.

Revision ID: 044
Revises: 043
Create Date: 2026-09-01
"""

from alembic import op


revision = "044"
down_revision = "043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE channel_continuations (
            continuation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            binding_id UUID NOT NULL REFERENCES channel_bindings(binding_id)
                ON DELETE CASCADE,
            session_id UUID NOT NULL REFERENCES channel_sessions(session_id)
                ON DELETE CASCADE,
            source_inbound_message_id UUID NOT NULL
                REFERENCES channel_inbound_messages(inbound_message_id)
                ON DELETE CASCADE,
            binding_epoch INTEGER NOT NULL,
            parts_ciphertext BYTEA NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'done', 'expired')),
            expires_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE INDEX idx_channel_continuations_pending
        ON channel_continuations (session_id, created_at, continuation_id)
        WHERE status = 'pending'
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_channel_continuations_pending")
    op.execute("DROP TABLE IF EXISTS channel_continuations")
