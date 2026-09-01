from src.server.channels.adapters.base import ChannelAdapter
from src.server.channels.events import (
    Commentary,
    MessageChunk,
    MessageStop,
    ToolCallChunk,
)
from src.server.channels.contracts import TextPart
from src.server.services.channels.event_dispatcher import (
    ChannelEventDispatcher,
    PresentationSink,
)


class FakeAdapter(ChannelAdapter):
    channel_type = "fake"

    def render_message_event(self, event, sink) -> None:
        super().render_message_event(event, sink)

    async def begin_link(self, previous_credentials=None):
        raise NotImplementedError

    async def poll_link(self, challenge, verification_code=None):
        raise NotImplementedError

    async def fetch_updates(self, credentials, cursor):
        raise NotImplementedError

    def normalize(self, raw_update, binding):
        raise NotImplementedError

    async def resolve_images(self, media, *, max_bytes, max_pixels):
        raise NotImplementedError

    async def deliver(self, credentials, reply_context, message):
        raise NotImplementedError


def test_presentation_sink_keeps_ordered_text_parts_and_segment_breaks() -> None:
    sink = PresentationSink()
    sink.on_delta("one")
    sink.on_segment_break()
    sink.on_commentary("note")
    sink.on_delta("two")

    assert sink.parts == (TextPart("one"), TextPart("note"), TextPart("two"))


def test_dispatcher_routes_messages_and_formats_tool_events() -> None:
    adapter = FakeAdapter()
    sink = PresentationSink()
    tool_lines: list[str] = []
    dispatcher = ChannelEventDispatcher(
        adapter, sink, enqueue_tool_line=tool_lines.append, tool_mode="all"
    )

    dispatcher.dispatch(MessageChunk("answer"))
    dispatcher.dispatch(Commentary("status"))
    dispatcher.dispatch(MessageStop(final=True))
    dispatcher.dispatch(ToolCallChunk("search", preview="query"))

    assert sink.parts == (TextPart("answer"), TextPart("status"))
    assert len(tool_lines) == 1
    assert "search" in tool_lines[0]


def test_dispatcher_supports_off_and_new_tool_modes() -> None:
    adapter = FakeAdapter()
    lines: list[str] = []
    dispatcher = ChannelEventDispatcher(
        adapter, enqueue_tool_line=lines.append, tool_mode="new"
    )
    dispatcher.dispatch(ToolCallChunk("search"))
    dispatcher.dispatch(ToolCallChunk("search"))
    dispatcher.dispatch(ToolCallChunk("open"))
    assert len(lines) == 2

    disabled: list[str] = []
    off = ChannelEventDispatcher(
        adapter, enqueue_tool_line=disabled.append, tool_mode="off"
    )
    off.dispatch(ToolCallChunk("search"))
    assert disabled == []


def test_dispatcher_consumes_adapter_errors() -> None:
    class BrokenAdapter(FakeAdapter):
        def render_message_event(self, event, sink) -> None:
            raise RuntimeError("presentation failed")

    sink = PresentationSink()
    dispatcher = ChannelEventDispatcher(BrokenAdapter(), sink)

    dispatcher.dispatch(MessageChunk("answer"))

    assert sink.parts == ()

