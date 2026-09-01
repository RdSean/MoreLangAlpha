"""Add durable, encrypted storage for generic external messaging channels.

Revision ID: 042
Revises: 041
Create Date: 2026-08-28
"""

from alembic import op


revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE channel_bindings (
            binding_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            channel_type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'reauth_required', 'disabled')),
            credentials_ciphertext BYTEA,
            cursor_ciphertext BYTEA,
            bound_peer_ciphertext BYTEA,
            idle_timeout_seconds INTEGER NOT NULL DEFAULT 21600
                CHECK (idle_timeout_seconds BETWEEN 60 AND 604800),
            lease_owner VARCHAR(255),
            lease_expires_at TIMESTAMPTZ,
            lease_generation INTEGER NOT NULL DEFAULT 0,
            last_error_code VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (user_id, channel_type)
        )
    """)
    op.execute("""
        CREATE TABLE channel_link_attempts (
            attempt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
            channel_type VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL DEFAULT 'waiting'
                CHECK (status IN ('waiting', 'scanned', 'verification_required',
                                 'linked', 'expired', 'failed', 'cancelled')),
            qr_code_url TEXT NOT NULL,
            poll_state_ciphertext BYTEA NOT NULL,
            expires_at TIMESTAMPTZ NOT NULL,
            lease_owner VARCHAR(255),
            lease_expires_at TIMESTAMPTZ,
            lease_generation INTEGER NOT NULL DEFAULT 0,
            last_error_code VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE channel_sessions (
            session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            binding_id UUID NOT NULL REFERENCES channel_bindings(binding_id) ON DELETE CASCADE,
            peer_lookup_hash VARCHAR(64) NOT NULL,
            peer_ciphertext BYTEA NOT NULL,
            agent_session_ref_ciphertext BYTEA,
            status VARCHAR(16) NOT NULL DEFAULT 'active'
                CHECK (status IN ('active', 'closed')),
            last_inbound_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            closed_at TIMESTAMPTZ
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_channel_sessions_active_peer
        ON channel_sessions (binding_id, peer_lookup_hash)
        WHERE status = 'active'
    """)
    op.execute("""
        CREATE TABLE channel_inbound_messages (
            inbound_message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            binding_id UUID NOT NULL REFERENCES channel_bindings(binding_id) ON DELETE CASCADE,
            session_id UUID REFERENCES channel_sessions(session_id) ON DELETE SET NULL,
            provider_message_id VARCHAR(255) NOT NULL,
            kind VARCHAR(16) NOT NULL CHECK (kind IN ('message', 'ignored', 'rejected')),
            status VARCHAR(16) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'claimed', 'done', 'dead', 'ignored', 'rejected')),
            peer_lookup_hash VARCHAR(64),
            text_content TEXT,
            media_ciphertext BYTEA,
            reply_context_ciphertext BYTEA,
            received_at TIMESTAMPTZ NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            lease_owner VARCHAR(255),
            lease_expires_at TIMESTAMPTZ,
            lease_generation INTEGER NOT NULL DEFAULT 0,
            next_retry_at TIMESTAMPTZ,
            last_error_code VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            processed_at TIMESTAMPTZ,
            UNIQUE (binding_id, provider_message_id)
        )
    """)
    op.execute("""
        CREATE INDEX idx_channel_inbound_claimable
        ON channel_inbound_messages (received_at)
        WHERE status IN ('pending', 'claimed')
    """)
    op.execute("""
        CREATE INDEX idx_channel_inbound_session_order
        ON channel_inbound_messages (session_id, received_at, inbound_message_id)
        WHERE status IN ('pending', 'claimed')
    """)
    op.execute("""
        CREATE TABLE channel_delivery_outbox (
            delivery_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            inbound_message_id UUID NOT NULL
                REFERENCES channel_inbound_messages(inbound_message_id) ON DELETE CASCADE,
            session_id UUID NOT NULL REFERENCES channel_sessions(session_id) ON DELETE CASCADE,
            binding_id UUID NOT NULL REFERENCES channel_bindings(binding_id) ON DELETE CASCADE,
            sequence_no INTEGER NOT NULL CHECK (sequence_no >= 0),
            client_id UUID NOT NULL,
            payload_ciphertext BYTEA NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'claimed', 'done', 'dead')),
            attempts INTEGER NOT NULL DEFAULT 0,
            lease_owner VARCHAR(255),
            lease_expires_at TIMESTAMPTZ,
            lease_generation INTEGER NOT NULL DEFAULT 0,
            next_retry_at TIMESTAMPTZ,
            last_error_code VARCHAR(64),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            UNIQUE (inbound_message_id, sequence_no)
        )
    """)
    op.execute("""
        CREATE INDEX idx_channel_delivery_claimable
        ON channel_delivery_outbox (next_retry_at, created_at)
        WHERE status IN ('pending', 'claimed')
    """)
    op.execute("""
        CREATE INDEX idx_channel_delivery_session_order
        ON channel_delivery_outbox (session_id, sequence_no, created_at)
        WHERE status IN ('pending', 'claimed')
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_channel_delivery_session_order")
    op.execute("DROP INDEX IF EXISTS idx_channel_delivery_claimable")
    op.execute("DROP TABLE IF EXISTS channel_delivery_outbox")
    op.execute("DROP INDEX IF EXISTS idx_channel_inbound_session_order")
    op.execute("DROP INDEX IF EXISTS idx_channel_inbound_claimable")
    op.execute("DROP TABLE IF EXISTS channel_inbound_messages")
    op.execute("DROP INDEX IF EXISTS uq_channel_sessions_active_peer")
    op.execute("DROP TABLE IF EXISTS channel_sessions")
    op.execute("DROP TABLE IF EXISTS channel_link_attempts")
    op.execute("DROP TABLE IF EXISTS channel_bindings")
