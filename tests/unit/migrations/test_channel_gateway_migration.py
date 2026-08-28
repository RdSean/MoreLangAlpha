"""Source-level contracts for the encrypted generic channel schema."""

from __future__ import annotations

from pathlib import Path


MIGRATION = (
    Path(__file__).parents[3] / "migrations/versions/042_add_channel_gateway.py"
)


def test_channel_gateway_schema_has_durable_dedup_and_fences() -> None:
    source = MIGRATION.read_text(encoding="utf-8")

    for table in (
        "channel_bindings",
        "channel_link_attempts",
        "channel_sessions",
        "channel_inbound_messages",
        "channel_delivery_outbox",
    ):
        assert f"CREATE TABLE {table}" in source

    assert "UNIQUE (user_id, channel_type)" in source
    assert "UNIQUE (binding_id, provider_message_id)" in source
    assert "UNIQUE (inbound_message_id, sequence_no)" in source
    assert "credentials_ciphertext BYTEA" in source
    assert "reply_context_ciphertext BYTEA" in source
    assert "attempts INTEGER NOT NULL DEFAULT 0" in source
    assert "lease_generation INTEGER NOT NULL DEFAULT 0" in source
    assert "pgp_sym_encrypt" not in source
    assert "DROP TABLE IF EXISTS channel_delivery_outbox" in source
