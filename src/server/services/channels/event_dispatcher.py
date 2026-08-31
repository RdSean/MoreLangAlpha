"""Route agent stream events through channel-owned presentation policy."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from src.server.channels.contracts import TextPart
from src.server.channels.events import (
    Commentary,
    GatewayNotice,
    LongToolHint,
    MessageChunk,
    MessageStop,
    StreamEvent,
    ToolCallChunk,
)

logger = logging.getLogger(__name__)


class PresentationSink:
    """Collect rendered user-facing text while preserving segment order."""

    def __init__(self) -> None:
        self._parts: list[TextPart] = []
        self._current: list[str] = []

    def on_delta(self, text: str) -> None:
        if text:
            self._current.append(text)

    def on_segment_break(self) -> None:
        self._flush()

    def on_commentary(self, text: str) -> None:
        self._flush()
        if text:
            self._parts.append(TextPart(text))

    def _flush(self) -> None:
        if self._current:
            self._parts.append(TextPart("".join(self._current)))
            self._current.clear()

    @property
    def parts(self) -> tuple[TextPart, ...]:
        self._flush()
        return tuple(self._parts)


class ChannelEventDispatcher:
    """Dispatch structured events without coupling agents to a platform."""

    def __init__(
        self,
        adapter: Any,
        sink: PresentationSink | None = None,
        *,
        enqueue_tool_line: Callable[[str], None] | None = None,
        tool_mode: str = "all",
        preview_max_len: int = 40,
        on_long_tool: Callable[[LongToolHint], None] | None = None,
        on_notice: Callable[[GatewayNotice], None] | None = None,
    ) -> None:
        self.adapter = adapter
        self.sink = sink
        self._enqueue_tool_line = enqueue_tool_line
        self.tool_mode = tool_mode or "all"
        self.preview_max_len = preview_max_len
        self._on_long_tool = on_long_tool
        self._on_notice = on_notice
        self._last_tool: str | None = None

    def dispatch(self, event: StreamEvent) -> None:
        """Route one event; presentation failures never fail the agent turn."""

        try:
            if isinstance(event, (MessageChunk, MessageStop, Commentary)):
                if self.sink is not None:
                    self.adapter.render_message_event(event, self.sink)
                return
            if isinstance(event, ToolCallChunk):
                if self.tool_mode == "off" or self._enqueue_tool_line is None:
                    return
                if self.tool_mode == "new" and event.tool_name == self._last_tool:
                    return
                self._last_tool = event.tool_name
                line = self.adapter.format_tool_event(
                    event,
                    mode=self.tool_mode,
                    preview_max_len=self.preview_max_len,
                )
                if line:
                    self._enqueue_tool_line(line)
                return
            if isinstance(event, LongToolHint):
                if self._on_long_tool is not None:
                    self._on_long_tool(event)
                return
            if isinstance(event, GatewayNotice) and self._on_notice is not None:
                self._on_notice(event)
        except Exception:
            logger.debug("channel presentation event failed", exc_info=True)


__all__ = ["ChannelEventDispatcher", "PresentationSink"]
