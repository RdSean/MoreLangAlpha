from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
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
    LinkPollState,
    OutboundMessage,
    ReplyContext,
    TextPart,
    UpdateBatch,
)
from src.server.database.channels import BindingLease, ClaimedInbound
from src.server.services.channels.gateway_runner import GatewayRunner


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

    async def list_active_binding_ids(self, limit): return [self.lease.binding_id]
    async def claim_binding_lease(self, *args): return self.lease
    async def release_binding_lease(self, *args): return True
    async def persist_update_batch(self, binding_id, cursor, messages):
        self.persisted.extend(messages)
        return len(messages)
    async def get_or_rotate_session(self, **kwargs):
        return SimpleNamespace(session_id=uuid4(), agent_session_ref=None)
    async def claim_pending_inbound(self, *args): return []
    async def claim_due_deliveries(self, *args): return []


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
    runner = GatewayRunner(channel_adapters={"fake": FakeChannel()}, agent_adapter=SimpleNamespace(), repository=repo)
    await runner.ingest_binding(repo.lease)
    assert repo.persisted[0].provider_message_id == "m1"

