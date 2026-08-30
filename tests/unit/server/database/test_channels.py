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

    assert (
        "FOR UPDATE SKIP LOCKED\n                    ),\n                    claimed AS"
        in source
    )
    assert (
        "LIMIT %s FOR UPDATE SKIP LOCKED\n                    ),\n                    claimed AS"
        in source
    )


def test_rejected_inbound_is_persisted_as_a_terminal_audit_record() -> None:
    source = (Path(__file__).parents[4] / "src/server/database/channels.py").read_text(
        encoding="utf-8"
    )

    assert "elif message.kind is InboundKind.REJECTED" in source
    assert 'status = "rejected"' in source


def test_closed_sessions_can_ack_historical_inbound_after_idle_rotation() -> None:
    source = (Path(__file__).parents[4] / "src/server/database/channels.py").read_text(
        encoding="utf-8"
    )

    ack_start = source.index("async def ack_inbound_and_enqueue_deliveries")
    ack_source = source[ack_start : source.index("async def nack_inbound", ack_start)]

    assert "WHERE session_id = %s AND binding_epoch = %s" in ack_source
    assert "WHERE session_id = %s AND status = 'active'" not in ack_source


def test_gateway_holds_a_share_lock_while_fencing_external_side_effects() -> None:
    source = (Path(__file__).parents[4] / "src/server/database/channels.py").read_text(
        encoding="utf-8"
    )

    assert "async def hold_active_binding_epoch" in source
    assert "FOR SHARE" in source


def test_delivery_claims_use_a_monotonic_session_order_and_binding_epoch() -> None:
    source = (Path(__file__).parents[4] / "src/server/database/channels.py").read_text(
        encoding="utf-8"
    )

    assert "session_delivery_order" in source
    assert "prior.session_delivery_order < o.session_delivery_order" in source
    assert "b.binding_epoch = c.binding_epoch" in source


def test_inbound_persistence_checks_binding_epoch_before_advancing_cursor() -> None:
    source = (Path(__file__).parents[4] / "src/server/database/channels.py").read_text(
        encoding="utf-8"
    )

    assert "binding_epoch = %s" in source
    assert (
        "WHERE binding_id = %s AND status = 'active' AND binding_epoch = %s" in source
    )


def test_reused_qr_binding_finalization_preserves_the_active_binding_epoch() -> None:
    source = (Path(__file__).parents[4] / "src/server/database/channels.py").read_text(
        encoding="utf-8"
    )

    finalize_start = source.index("async def finalize_link_attempt")
    finalize_source = source[finalize_start : source.index("async def _retire_binding_rows", finalize_start)]
    assert "result.reuse_existing_binding" in finalize_source
    assert "status = 'active'" in finalize_source
    assert "status = 'failed', poll_state_ciphertext = NULL" in finalize_source
