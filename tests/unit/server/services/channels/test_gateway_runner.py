from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.server.channels.contracts import (
    AgentSession,
    AgentTurnResult,
    BindingCredentials,
    BindingRoute,
    DeliveryReceipt,
    InboundKind,
    InboundMessage,
    ReplyContext,
    TextPart,
    UpdateBatch,
)
from src.server.database.channels import BindingLease
from src.server.services.channels.gateway_runner import GatewayRunner
from src.server.services.channels import gateway_runner


def _lease():
    return BindingLease(
        binding_id=uuid4(),
        user_id="u1",
        channel_type="fake",
        credentials=BindingCredentials("b", "fake", (("token", "t"),)),
        route=BindingRoute("b", "peer"),
        cursor="old",
        generation=1,
    )


class FakeRepo:
    def __init__(self):
        self.persisted = []
        self.acked = []
        self.sessions = {}

    async def list_active_binding_ids(self, limit):
        return [self.lease.binding_id]

    async def claim_binding_lease(self, *args):
        return self.lease

    async def release_binding_lease(self, *args):
        return True

    async def persist_update_batch(self, binding_id, cursor, messages, **kwargs):
        self.persisted.extend(messages)
        return len(messages)

    async def get_or_rotate_session(self, **kwargs):
        raise AssertionError(
            "session rotation belongs to the durable insert transaction"
        )

    async def claim_pending_inbound(self, *args):
        return []

    async def claim_due_deliveries(self, *args):
        return []


class FakeChannel:
    channel_type = "fake"

    async def fetch_updates(self, credentials, cursor):
        return UpdateBatch(
            updates=({"message_id": "m1"},),
            next_cursor="new",
        )

    def normalize(self, raw, binding):
        return InboundMessage(
            provider_message_id="m1",
            peer_ref="peer",
            received_at=datetime.now(UTC),
            kind=InboundKind.MESSAGE,
            text="hello",
            reply_context=ReplyContext("peer", (("context_token", "ctx"),)),
        )


@pytest.mark.asyncio
async def test_ingest_persists_cursor_and_messages_without_calling_agent():
    repo = FakeRepo()
    repo.lease = _lease()
    runner = GatewayRunner(
        channel_adapters={"fake": FakeChannel()},
        agent_adapter=SimpleNamespace(),
        repository=repo,
    )
    await runner.ingest_binding(repo.lease)
    assert repo.persisted[0].provider_message_id == "m1"
    assert repo.persisted[0].peer_ref == "peer"


def test_outbound_text_is_split_to_the_provider_limit_in_order() -> None:
    parts = gateway_runner.split_outbound_parts(
        (TextPart("abcdef"),), max_text_length=3
    )

    assert parts == (TextPart("abc"), TextPart("def"))


@pytest.mark.asyncio
async def test_delivery_rechecks_binding_epoch_before_calling_the_provider() -> None:
    delivery = SimpleNamespace(
        delivery_id=uuid4(),
        binding_id=uuid4(),
        binding_epoch=2,
        channel_type="fake",
        payload={"text": "answer"},
        client_id=uuid4(),
        session_id=uuid4(),
        inbound_message_id=uuid4(),
        sequence_no=0,
        reply_context=ReplyContext("peer", (("context_token", "ctx"),)),
        lease_generation=1,
        credentials=BindingCredentials("binding", "fake", (("token", "t"),)),
        attempts=1,
    )
    adapter = SimpleNamespace(deliver=AsyncMock())
    held_epochs = []

    @asynccontextmanager
    async def inactive_epoch_fence(binding_id, binding_epoch):
        held_epochs.append((binding_id, binding_epoch))
        yield False

    repository = SimpleNamespace(
        claim_due_deliveries=AsyncMock(return_value=[delivery]),
        hold_active_binding_epoch=inactive_epoch_fence,
        ack_delivery=AsyncMock(return_value=True),
        nack_delivery=AsyncMock(return_value=True),
    )
    runner = GatewayRunner(
        channel_adapters={"fake": adapter},
        agent_adapter=SimpleNamespace(),
        repository=repository,
    )

    await runner.deliver_once()

    assert held_epochs == [(delivery.binding_id, 2)]
    adapter.deliver.assert_not_awaited()


@pytest.mark.asyncio
async def test_inbound_rechecks_binding_epoch_before_calling_flash() -> None:
    claim = SimpleNamespace(
        binding_id=uuid4(),
        binding_epoch=3,
        kind=InboundKind.MESSAGE,
        session_id=uuid4(),
        agent_session_ref="thread-1",
        peer_ref="peer",
        peer_lookup_hash="peer-hash",
        user_id="user-1",
        channel_type="fake",
        media=(),
        request_key="request-1",
        text="hello",
        inbound_message_id=uuid4(),
        lease_generation=1,
        attempts=1,
    )
    agent = SimpleNamespace(run_turn=AsyncMock())
    held_epochs = []

    @asynccontextmanager
    async def inactive_epoch_fence(binding_id, binding_epoch):
        held_epochs.append((binding_id, binding_epoch))
        yield False

    repository = SimpleNamespace(
        claim_pending_inbound=AsyncMock(return_value=[claim]),
        hold_active_binding_epoch=inactive_epoch_fence,
        ack_inbound_and_enqueue_deliveries=AsyncMock(return_value=True),
        nack_inbound=AsyncMock(return_value=True),
    )
    runner = GatewayRunner(
        channel_adapters={"fake": SimpleNamespace()},
        agent_adapter=agent,
        repository=repository,
    )

    await runner.process_inbound_once()

    assert held_epochs == [(claim.binding_id, 3)]
    agent.run_turn.assert_not_awaited()


@pytest.mark.asyncio
async def test_delivery_calls_provider_while_epoch_fence_is_held() -> None:
    delivery = SimpleNamespace(
        delivery_id=uuid4(),
        binding_id=uuid4(),
        binding_epoch=2,
        channel_type="fake",
        payload={"text": "answer"},
        client_id=uuid4(),
        session_id=uuid4(),
        inbound_message_id=uuid4(),
        sequence_no=0,
        reply_context=ReplyContext("peer", (("context_token", "ctx"),)),
        lease_generation=1,
        credentials=BindingCredentials("binding", "fake", (("token", "t"),)),
        attempts=1,
    )
    fence_held = False

    @asynccontextmanager
    async def active_epoch_fence(_binding_id, _binding_epoch):
        nonlocal fence_held
        fence_held = True
        try:
            yield True
        finally:
            fence_held = False

    async def deliver(*_args):
        assert fence_held
        return DeliveryReceipt(True, "provider-message", datetime.now(UTC))

    repository = SimpleNamespace(
        claim_due_deliveries=AsyncMock(return_value=[delivery]),
        hold_active_binding_epoch=active_epoch_fence,
        ack_delivery=AsyncMock(return_value=True),
        nack_delivery=AsyncMock(return_value=True),
    )
    runner = GatewayRunner(
        channel_adapters={"fake": SimpleNamespace(deliver=deliver)},
        agent_adapter=SimpleNamespace(),
        repository=repository,
    )

    assert await runner.deliver_once() == 1


@pytest.mark.asyncio
async def test_inbound_calls_flash_while_epoch_fence_is_held() -> None:
    claim = SimpleNamespace(
        binding_id=uuid4(),
        binding_epoch=3,
        kind=InboundKind.MESSAGE,
        session_id=uuid4(),
        agent_session_ref="thread-1",
        peer_ref="peer",
        peer_lookup_hash="peer-hash",
        user_id="user-1",
        channel_type="fake",
        media=(),
        request_key="request-1",
        text="hello",
        inbound_message_id=uuid4(),
        lease_generation=1,
        attempts=1,
    )
    fence_held = False

    @asynccontextmanager
    async def active_epoch_fence(_binding_id, _binding_epoch):
        nonlocal fence_held
        fence_held = True
        try:
            yield True
        finally:
            fence_held = False

    async def run_turn(_session, _turn):
        assert fence_held
        return AgentTurnResult(parts=(TextPart("answer"),), session_ref="thread-1")

    agent = SimpleNamespace(
        open_session=AsyncMock(
            return_value=AgentSession("thread-1", datetime.now(UTC), "user-1")
        ),
        run_turn=run_turn,
    )
    repository = SimpleNamespace(
        claim_pending_inbound=AsyncMock(return_value=[claim]),
        hold_active_binding_epoch=active_epoch_fence,
        ack_inbound_and_enqueue_deliveries=AsyncMock(return_value=True),
        nack_inbound=AsyncMock(return_value=True),
    )
    runner = GatewayRunner(
        channel_adapters={"fake": SimpleNamespace()},
        agent_adapter=agent,
        repository=repository,
    )

    assert await runner.process_inbound_once() == 1


@pytest.mark.asyncio
async def test_inbound_downloads_images_while_epoch_fence_is_held() -> None:
    claim = SimpleNamespace(
        binding_id=uuid4(),
        binding_epoch=3,
        kind=InboundKind.MESSAGE,
        session_id=uuid4(),
        agent_session_ref="thread-1",
        peer_ref="peer",
        peer_lookup_hash="peer-hash",
        user_id="user-1",
        channel_type="fake",
        media=(SimpleNamespace(),),
        request_key="request-1",
        text="hello",
        inbound_message_id=uuid4(),
        lease_generation=1,
        attempts=1,
    )
    fence_held = False
    image_fence_states = []

    @asynccontextmanager
    async def active_epoch_fence(_binding_id, _binding_epoch):
        nonlocal fence_held
        fence_held = True
        try:
            yield True
        finally:
            fence_held = False

    async def download_image(_media, *, max_bytes):
        assert max_bytes > 0
        image_fence_states.append(fence_held)
        return b"image"

    adapter = SimpleNamespace(
        download_image=download_image,
        validate_image=lambda *_args, **_kwargs: ("image/png", 1, 1),
    )
    repository = SimpleNamespace(
        claim_pending_inbound=AsyncMock(return_value=[claim]),
        hold_active_binding_epoch=active_epoch_fence,
        ack_inbound_and_enqueue_deliveries=AsyncMock(return_value=True),
        nack_inbound=AsyncMock(return_value=True),
    )
    agent = SimpleNamespace(
        run_turn=AsyncMock(
            return_value=AgentTurnResult(
                parts=(TextPart("answer"),), session_ref="thread-1"
            )
        )
    )
    runner = GatewayRunner(
        channel_adapters={"fake": adapter},
        agent_adapter=agent,
        repository=repository,
    )

    assert await runner.process_inbound_once() == 1
    assert image_fence_states == [True]
