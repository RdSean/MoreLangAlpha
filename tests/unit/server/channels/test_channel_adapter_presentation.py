import asyncio
from unittest.mock import AsyncMock

import pytest

from src.server.channels.adapters.base import ChannelAdapter
from src.server.channels.adapters.wechat_ilink import WeChatILinkAdapter
from src.server.channels.contracts import BindingCredentials, ReplyContext, TextPart
from src.server.channels.events import MessageChunk, MessageStop, ToolCallChunk


class Sink:
    def __init__(self) -> None:
        self.deltas: list[str] = []
        self.breaks = 0
        self.commentary: list[str] = []

    def on_delta(self, text: str) -> None:
        self.deltas.append(text)

    def on_segment_break(self) -> None:
        self.breaks += 1

    def on_commentary(self, text: str) -> None:
        self.commentary.append(text)


def test_channel_adapter_exposes_hermes_style_capability_defaults() -> None:
    adapter = WeChatILinkAdapter()

    assert adapter.supports_code_blocks is False
    assert adapter.supports_draft_streaming() is False
    assert adapter.prefers_fresh_final_streaming("answer") is False
    assert adapter.supports_typing is True
    assert ChannelAdapter().supports_typing is False


@pytest.mark.asyncio
async def test_base_typing_loop_is_cancellable_and_provider_errors_are_non_fatal() -> None:
    adapter = ChannelAdapter()
    adapter.send_typing = AsyncMock(side_effect=RuntimeError("provider down"))
    adapter.stop_typing = AsyncMock()
    stop_event = asyncio.Event()

    task = asyncio.create_task(
        adapter.keep_typing(
            BindingCredentials("b", "fake", ()),
            ReplyContext("peer", (("context_token", "ctx"),)),
            stop_event=stop_event,
            interval=0.01,
        )
    )
    await asyncio.sleep(0.02)
    stop_event.set()
    await asyncio.wait_for(task, timeout=1)

    adapter.send_typing.assert_awaited()
    adapter.stop_typing.assert_awaited_once()


@pytest.mark.asyncio
async def test_base_adapter_exposes_lifecycle_and_outbound_defaults() -> None:
    adapter = ChannelAdapter()
    credentials = BindingCredentials("b", "fake", ())

    await adapter.on_binding_start(credentials)
    await adapter.on_binding_stop(credentials)
    await adapter.send_typing(credentials, ReplyContext("peer"))
    await adapter.stop_typing(credentials, ReplyContext("peer"))

    parts = (TextPart("answer"),)
    assert adapter.prepare_outbound_parts(parts) == parts


def test_channel_adapter_default_message_rendering_targets_sink() -> None:
    adapter = WeChatILinkAdapter()
    sink = Sink()

    ChannelAdapter.render_message_event(adapter, MessageChunk("one"), sink)
    ChannelAdapter.render_message_event(adapter, MessageStop(), sink)
    ChannelAdapter.render_message_event(adapter, MessageChunk("two"), sink)

    assert sink.deltas == ["one", "two"]
    assert sink.breaks == 1


def test_channel_adapter_default_tool_formatter_supports_compact_and_verbose_modes() -> None:
    adapter = WeChatILinkAdapter()
    event = ToolCallChunk("search", preview="long query", args={"q": "long query"})

    compact = ChannelAdapter.format_tool_event(
        adapter, event, mode="all", preview_max_len=40
    )
    verbose = ChannelAdapter.format_tool_event(
        adapter, event, mode="verbose", preview_max_len=200
    )

    assert compact is not None and "search" in compact and "long query" in compact
    assert verbose is not None and '"q": "long query"' in verbose


def test_wechat_presentation_keeps_only_main_ordinary_text() -> None:
    adapter = WeChatILinkAdapter()
    sink = Sink()

    adapter.render_message_event(
        MessageChunk(
            "reasoning",
            agent="main",
            content_type="reasoning",
            role="assistant",
        ),
        sink,
    )
    adapter.render_message_event(
        MessageChunk(
            "subagent",
            agent="task:one",
            content_type="text",
            role="assistant",
        ),
        sink,
    )
    adapter.render_message_event(
        MessageChunk(
            "answer", agent="main", content_type="text", role="assistant"
        ),
        sink,
    )
    adapter.render_message_event(MessageStop(final=True), sink)

    assert sink.deltas == ["answer"]
    assert sink.breaks == 0
    assert adapter.format_tool_event(ToolCallChunk("search")) is None
