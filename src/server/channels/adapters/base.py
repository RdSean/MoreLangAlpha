"""Generic channel transport and presentation adapter base."""

from __future__ import annotations

import json
from abc import ABCMeta
from typing import Any

from src.server.channels.contracts import (
    BindingCredentials,
    BindingRoute,
    DeliveryReceipt,
    InboundMedia,
    InboundMessage,
    LinkChallenge,
    LinkPollResult,
    OutboundMessage,
    ReplyContext,
    ResolvedImage,
    UpdateBatch,
)
from src.server.channels.events import (
    Commentary,
    MessageChunk,
    MessageStop,
    ToolCallChunk,
)


_TRANSPORT_METHODS = (
    "begin_link",
    "poll_link",
    "fetch_updates",
    "normalize",
    "resolve_images",
    "deliver",
)


class _ChannelAdapterMeta(ABCMeta):
    """Keep structural compatibility for existing adapters and test doubles."""

    def __instancecheck__(cls, instance: object) -> bool:
        if cls is ChannelAdapter:
            return all(callable(getattr(instance, name, None)) for name in _TRANSPORT_METHODS) and bool(
                getattr(instance, "channel_type", None)
            )
        return super().__instancecheck__(instance)


class ChannelAdapter(metaclass=_ChannelAdapterMeta):
    """Translate one platform into generic values and presentation events.

    Transport methods remain the required provider surface.  The concrete base
    methods below are intentionally platform-neutral defaults modeled after the
    Hermes adapter contract; a channel may override only the presentation
    capabilities it actually supports.
    """

    channel_type: str = "unknown"
    max_outbound_text_length: int | None = None
    supports_code_blocks: bool = False
    supports_status_text: bool = False

    async def begin_link(
        self, previous_credentials: BindingCredentials | None = None
    ) -> LinkChallenge:
        raise NotImplementedError

    async def poll_link(
        self,
        challenge: LinkChallenge,
        verification_code: str | None = None,
    ) -> LinkPollResult:
        raise NotImplementedError

    async def fetch_updates(
        self,
        credentials: BindingCredentials,
        cursor: str | None,
    ) -> UpdateBatch:
        raise NotImplementedError

    def normalize(
        self,
        raw_update: object,
        binding: BindingRoute,
    ) -> InboundMessage:
        raise NotImplementedError

    async def resolve_images(
        self,
        media: tuple[InboundMedia, ...],
        *,
        max_bytes: int,
        max_pixels: int,
    ) -> tuple[ResolvedImage, ...]:
        raise NotImplementedError

    async def deliver(
        self,
        credentials: BindingCredentials,
        reply_context: ReplyContext,
        message: OutboundMessage,
    ) -> DeliveryReceipt:
        raise NotImplementedError

    def supports_draft_streaming(
        self,
        chat_type: str | None = None,
        metadata: dict[str, Any] | None = None,
        chat_id: str | None = None,
    ) -> bool:
        return False

    def prefers_fresh_final_streaming(
        self, content: str, metadata: dict[str, Any] | None = None
    ) -> bool:
        return False

    def render_message_event(self, event: Any, sink: Any) -> None:
        """Map ordinary stream events onto a presentation sink."""

        if isinstance(event, MessageChunk):
            if event.text:
                sink.on_delta(event.text)
        elif isinstance(event, MessageStop):
            if not event.final:
                sink.on_segment_break()
        elif isinstance(event, Commentary) and event.text:
            sink.on_commentary(event.text)

    def format_tool_event(
        self,
        event: Any,
        *,
        mode: str = "all",
        preview_max_len: int = 40,
    ) -> str | None:
        """Format a tool start as compact gateway chrome.

        Returning ``None`` is the explicit adapter contract for consuming tool
        events on channels where progress bubbles are not useful.
        """

        if not isinstance(event, ToolCallChunk):
            return None
        if not event.tool_name:
            return None
        if mode == "verbose" and event.args:
            rendered = json.dumps(event.args, ensure_ascii=False, default=str)
            if preview_max_len > 0:
                rendered = rendered[:preview_max_len]
            return f"tool {event.tool_name}: {rendered}"
        preview = self.format_tool_preview(event.preview or "", preview_max_len)
        return f"tool {event.tool_name}: {preview}" if preview else f"tool {event.tool_name}"

    def format_tool_preview(self, preview: str, max_len: int = 40) -> str:
        if max_len > 0 and len(preview) > max_len:
            return f"{preview[: max_len - 3]}..."
        return preview


__all__ = ["ChannelAdapter"]
