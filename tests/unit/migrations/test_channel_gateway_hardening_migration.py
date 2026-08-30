"""Schema coverage for the post-launch channel durability hardening."""

from __future__ import annotations

from pathlib import Path
import runpy


MIGRATIONS = Path(__file__).parents[3] / "migrations/versions"


def test_channel_hardening_follows_the_initial_gateway_schema() -> None:
    migration = runpy.run_path(str(MIGRATIONS / "043_harden_channel_gateway_fences.py"))

    assert migration["revision"] == "043"
    assert migration["down_revision"] == "042"


def test_channel_hardening_adds_epoch_and_monotonic_delivery_order() -> None:
    source = (MIGRATIONS / "043_harden_channel_gateway_fences.py").read_text(
        encoding="utf-8"
    )

    assert "binding_epoch" in source
    assert "session_delivery_order" in source
    assert "ALTER COLUMN peer_ciphertext DROP NOT NULL" in source


def test_hardening_downgrade_discards_cleared_poll_state_before_not_null() -> None:
    source = (MIGRATIONS / "043_harden_channel_gateway_fences.py").read_text(
        encoding="utf-8"
    )

    discard_cleared_attempts = """DELETE FROM channel_link_attempts
        WHERE poll_state_ciphertext IS NULL"""
    restore_not_null = """ALTER TABLE channel_link_attempts
        ALTER COLUMN poll_state_ciphertext SET NOT NULL"""

    assert discard_cleared_attempts in source
    assert source.index(discard_cleared_attempts) < source.index(restore_not_null)


def test_hardening_downgrade_discards_retired_payload_before_not_null() -> None:
    source = (MIGRATIONS / "043_harden_channel_gateway_fences.py").read_text(
        encoding="utf-8"
    )

    discard_retired_deliveries = """DELETE FROM channel_delivery_outbox
        WHERE payload_ciphertext IS NULL"""
    restore_not_null = """ALTER TABLE channel_delivery_outbox
        ALTER COLUMN payload_ciphertext SET NOT NULL"""

    assert discard_retired_deliveries in source
    assert source.index(discard_retired_deliveries) < source.index(restore_not_null)
