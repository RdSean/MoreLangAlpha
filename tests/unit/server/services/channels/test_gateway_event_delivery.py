from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.server.channels.adapters.base import ChannelAdapter
from src.server.channels.contracts import (
    AgentTurnResult,
    DeliveryReceipt,
    InboundKind,
    LinkChallenge,
    LinkPollResult,
    OutboundMessage,
    TextPart,
    UpdateBatch,
)
from src.server.channels.events import Commentary, MessageChunk, ToolCallChunk
from src.server.services.channels.gateway_runner import GatewayRunner


class EventChannel(ChannelAdapter):
    channel_type = "wechat"
    max_outbound_text_length = None

    def render_message_event(self, event, sink) -> None:
        if isinstance(event, MessageChunk):
            if event.content_type == "text" and event.agent == "main":
                sink.on_delta(event.text)

    async def begin_link(self, previous_credentials=None) -> LinkChallenge:
        raise NotImplementedError

    async def poll_link(self, challenge, verification_code=None) -> LinkPollResult:
        raise NotImplementedError

    async def fetch_updates(self, credentials, cursor) -> UpdateBatch:
        raise NotImplementedError

    def normalize(self, raw_update, binding):
        raise NotImplementedError

    async def resolve_images(self, media, *, max_bytes, max_pixels):
        return ()

    async def deliver(
        self, credentials, reply_context, message: OutboundMessage
    ) -> DeliveryReceipt:
        raise NotImplementedError

    def format_tool_event(self, event, *, mode="all", preview_max_len=40):
        return None


@pytest.mark.asyncio
async def test_runner_persists_channel_rendered_text_and_keeps_session_ref() -> None:
    claim = SimpleNamespace(
        binding_id=uuid4(),
        binding_epoch=1,
        kind=InboundKind.MESSAGE,
        session_id=uuid4(),
        agent_session_ref="thread-1",
        peer_ref="peer",
        peer_lookup_hash="peer-hash",
        user_id="user-1",
        channel_type="wechat",
        media=(),
        request_key="request-1",
        text="hello",
        inbound_message_id=uuid4(),
        lease_generation=1,
        attempts=1,
    )
    acked: list[AgentTurnResult] = []

    @asynccontextmanager
    async def active_epoch_fence(_binding_id, _binding_epoch):
        yield True

    async def run_turn(_session, _turn, on_event=None):
        assert on_event is not None
        on_event(MessageChunk("内部", agent="main", content_type="reasoning"))
        on_event(Commentary("工具处理中", agent="main"))
        on_event(ToolCallChunk("search"))
        on_event(MessageChunk("最终", agent="main", content_type="text"))
        return AgentTurnResult(parts=(TextPart("legacy polluted result"),), session_ref="thread-2")

    agent = SimpleNamespace(
        open_session=AsyncMock(),
        run_turn=run_turn,
    )

    async def ack(_claim, result):
        acked.append(result)
        return True

    repository = SimpleNamespace(
        claim_pending_inbound=AsyncMock(return_value=[claim]),
        hold_active_binding_epoch=active_epoch_fence,
        ack_inbound_and_enqueue_deliveries=ack,
        nack_inbound=AsyncMock(return_value=True),
    )
    runner = GatewayRunner(
        channel_adapters={"wechat": EventChannel()},
        agent_adapter=agent,
        repository=repository,
    )

    assert await runner.process_inbound_once() == 1
    assert acked[0].parts == (TextPart("最终"),)
    assert acked[0].session_ref == "thread-2"
