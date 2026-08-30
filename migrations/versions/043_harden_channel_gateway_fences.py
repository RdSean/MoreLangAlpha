"""Fence channel work across reconnects and preserve delivery order.

Revision ID: 043
Revises: 042
Create Date: 2026-08-30
"""

from alembic import op


revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE channel_bindings
        ADD COLUMN binding_epoch INTEGER NOT NULL DEFAULT 1
    """)
    op.execute("""
        ALTER TABLE channel_sessions
        ADD COLUMN binding_epoch INTEGER NOT NULL DEFAULT 1
    """)
    op.execute("""
        ALTER TABLE channel_sessions
        ALTER COLUMN peer_ciphertext DROP NOT NULL
    """)
    op.execute("""
        ALTER TABLE channel_inbound_messages
        ADD COLUMN binding_epoch INTEGER NOT NULL DEFAULT 1
    """)
    op.execute("""
        ALTER TABLE channel_delivery_outbox
        ADD COLUMN binding_epoch INTEGER NOT NULL DEFAULT 1,
        ADD COLUMN session_delivery_order BIGINT
    """)
    op.execute("""
        WITH ordered AS (
            SELECT delivery_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY session_id ORDER BY created_at, delivery_id
                   ) - 1 AS delivery_order
            FROM channel_delivery_outbox
        )
        UPDATE channel_delivery_outbox o
        SET session_delivery_order = ordered.delivery_order
        FROM ordered
        WHERE ordered.delivery_id = o.delivery_id
    """)
    op.execute("""
        ALTER TABLE channel_delivery_outbox
        ALTER COLUMN session_delivery_order SET NOT NULL,
        ALTER COLUMN payload_ciphertext DROP NOT NULL
    """)
    op.execute("""
        ALTER TABLE channel_link_attempts
        ALTER COLUMN poll_state_ciphertext DROP NOT NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_channel_delivery_session_order
        ON channel_delivery_outbox (session_id, session_delivery_order)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_channel_delivery_session_order")
    op.execute("""
        UPDATE channel_sessions
        SET peer_ciphertext = decode('', 'hex')
        WHERE peer_ciphertext IS NULL
    """)
    # 043 deliberately destroys this secret after a terminal QR flow. 042
    # requires a decryptable value, so discard the obsolete audit row rather
    # than leaving an invalid placeholder.
    op.execute("""
        DELETE FROM channel_link_attempts
        WHERE poll_state_ciphertext IS NULL
    """)
    # Retired outbox rows likewise have no payload compatible with the 042
    # schema, which made this column mandatory.
    op.execute("""
        DELETE FROM channel_delivery_outbox
        WHERE payload_ciphertext IS NULL
    """)
    op.execute("""
        ALTER TABLE channel_link_attempts
        ALTER COLUMN poll_state_ciphertext SET NOT NULL
    """)
    op.execute("""
        ALTER TABLE channel_delivery_outbox
        ALTER COLUMN payload_ciphertext SET NOT NULL,
        DROP COLUMN session_delivery_order,
        DROP COLUMN binding_epoch
    """)
    op.execute("""
        ALTER TABLE channel_inbound_messages
        DROP COLUMN binding_epoch
    """)
    op.execute("""
        ALTER TABLE channel_sessions
        ALTER COLUMN peer_ciphertext SET NOT NULL,
        DROP COLUMN binding_epoch
    """)
    op.execute("""
        ALTER TABLE channel_bindings
        DROP COLUMN binding_epoch
    """)
