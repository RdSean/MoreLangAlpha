"""Concurrency behavior for user-scoped channel linking."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.server.services.channels import linking
from src.server.channels.contracts import LinkPollResult, LinkStatus


@pytest.mark.asyncio
async def test_poll_returns_current_status_when_another_request_holds_attempt_lease(
    monkeypatch,
) -> None:
    attempt_id = uuid4()
    current = {
        "attempt_id": attempt_id,
        "channel_type": "wechat",
        "status": "waiting",
        "poll_state": "{}",
        "qr_code_url": "https://example.invalid/qr",
        "expires_at": __import__("datetime").datetime.now(__import__("datetime").UTC),
    }
    claim = AsyncMock(return_value=None)
    get_attempt = AsyncMock(return_value=current)

    class Adapter:
        async def poll_link(self, *args, **kwargs):
            raise AssertionError(
                "the adapter must not poll an attempt leased elsewhere"
            )

    monkeypatch.setattr(linking.channel_db, "claim_link_attempt", claim, raising=False)
    monkeypatch.setattr(linking.channel_db, "get_link_attempt_for_user", get_attempt)

    response = await linking.poll_link("user-1", attempt_id, Adapter())

    assert response.status == "waiting"
    claim.assert_awaited_once()


@pytest.mark.asyncio
async def test_poll_bounds_provider_wait_inside_the_attempt_lease(monkeypatch) -> None:
    attempt_id = uuid4()
    attempt = {
        "attempt_id": attempt_id,
        "channel_type": "wechat",
        "status": "waiting",
        "poll_state": '{"qrcode":"qr-1"}',
        "qr_code_url": "https://example.invalid/qr",
        "expires_at": __import__("datetime").datetime.now(__import__("datetime").UTC),
        "lease_generation": 2,
    }
    current = {**attempt, "status": "waiting"}
    claim = AsyncMock(return_value=attempt)
    finalize = AsyncMock(return_value=True)
    get_attempt = AsyncMock(return_value=current)
    observed_timeouts = []

    async def wait_for(awaitable, *, timeout):
        observed_timeouts.append(timeout)
        return await awaitable

    adapter = SimpleNamespace(
        poll_link=AsyncMock(return_value=LinkPollResult(status=LinkStatus.WAITING))
    )
    config = SimpleNamespace(
        link_attempt_lease_seconds=30,
        link_poll_timeout_seconds=10,
    )
    monkeypatch.setattr(linking.channel_db, "claim_link_attempt", claim)
    monkeypatch.setattr(linking.channel_db, "finalize_link_attempt", finalize)
    monkeypatch.setattr(linking.channel_db, "get_link_attempt_for_user", get_attempt)
    monkeypatch.setattr(
        linking, "get_channel_gateway_config", lambda: config, raising=False
    )
    monkeypatch.setattr(
        linking, "asyncio", SimpleNamespace(wait_for=wait_for), raising=False
    )

    await linking.poll_link("user-1", attempt_id, adapter)

    assert claim.await_args.kwargs["lease_seconds"] == 30
    assert observed_timeouts == [10]
