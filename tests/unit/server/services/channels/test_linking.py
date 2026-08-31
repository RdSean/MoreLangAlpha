"""Concurrency behavior for user-scoped channel linking."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.server.services.channels import linking
from src.server.channels.contracts import BindingCredentials, LinkChallenge, LinkPollResult, LinkPollState, LinkStatus


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
    assert response.qr_code_url == "https://example.invalid/qr"
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
    monkeypatch.setattr(linking.asyncio, "wait_for", wait_for)

    await linking.poll_link("user-1", attempt_id, adapter)

    assert claim.await_args.kwargs["lease_seconds"] == 30
    assert observed_timeouts == [10]


@pytest.mark.asyncio
async def test_start_link_passes_only_the_active_binding_credentials_to_adapter(monkeypatch) -> None:
    attempt_id = uuid4()
    previous = BindingCredentials(
        binding_ref="binding-1",
        channel_type="wechat",
        values=(("token", "known-token"),),
    )
    challenge = LinkChallenge(
        channel_type="wechat",
        challenge_ref="qr-1",
        qr_code_url="https://example.invalid/qr",
        expires_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
        provider_poll_state=LinkPollState(values=(("qrcode", "qr-1"),)),
    )
    adapter = SimpleNamespace(channel_type="wechat", begin_link=AsyncMock(return_value=challenge))
    monkeypatch.setattr(
        linking.channel_db,
        "get_active_binding_credentials",
        AsyncMock(return_value=previous),
        raising=False,
    )
    monkeypatch.setattr(
        linking.channel_db, "create_link_attempt", AsyncMock(return_value=attempt_id)
    )

    response = await linking.start_link("user-1", adapter)

    adapter.begin_link.assert_awaited_once_with(previous)
    assert response.attempt_id == attempt_id


@pytest.mark.asyncio
async def test_timed_out_poll_returns_waiting_and_finalizes_the_attempt(monkeypatch) -> None:
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
    finalize = AsyncMock(return_value=True)
    current = {**attempt, "status": "waiting"}

    async def time_out(_awaitable, *, timeout):
        _awaitable.close()
        raise TimeoutError

    monkeypatch.setattr(linking.channel_db, "claim_link_attempt", AsyncMock(return_value=attempt))
    monkeypatch.setattr(linking.channel_db, "finalize_link_attempt", finalize)
    monkeypatch.setattr(
        linking.channel_db, "get_link_attempt_for_user", AsyncMock(return_value=current)
    )
    monkeypatch.setattr(
        linking, "get_channel_gateway_config", lambda: SimpleNamespace(link_attempt_lease_seconds=30, link_poll_timeout_seconds=10)
    )
    monkeypatch.setattr(linking.asyncio, "wait_for", time_out)

    try:
        response = await linking.poll_link("user-1", attempt_id, SimpleNamespace(poll_link=AsyncMock()))
    except TimeoutError:
        response = None

    assert response is not None
    assert response.status == "waiting"
    assert finalize.await_args.kwargs["result"].status is LinkStatus.WAITING
