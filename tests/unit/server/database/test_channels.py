"""SQL boundary tests for durable channel gateway persistence."""

from __future__ import annotations

from pathlib import Path


def test_channel_repository_uses_pgcrypto_and_durable_deduplication() -> None:
    source = (Path(__file__).parents[4] / "src/server/database/channels.py").read_text(
        encoding="utf-8"
    )

    assert "pgp_sym_encrypt" in source
    assert "pgp_sym_decrypt" in source
    assert "ON CONFLICT (binding_id, provider_message_id) DO NOTHING" in source
    assert "lease_generation" in source


def test_delivery_claim_joins_the_referenced_inbound_context() -> None:
    source = (Path(__file__).parents[4] / "src/server/database/channels.py").read_text(
        encoding="utf-8"
    )

    assert "JOIN channel_inbound_messages" in source
    assert "reply_context_ciphertext" in source


def test_claim_ctes_separate_read_and_update_expressions() -> None:
    source = (Path(__file__).parents[4] / "src/server/database/channels.py").read_text(
        encoding="utf-8"
    )

    assert "FOR UPDATE SKIP LOCKED\n                    ),\n                    claimed AS" in source
    assert "LIMIT %s FOR UPDATE SKIP LOCKED\n                    ),\n                    claimed AS" in source
