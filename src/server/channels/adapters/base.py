"""Interface implemented by a concrete external messaging platform."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

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


@runtime_checkable
class ChannelAdapter(Protocol):
    """Translate one external messaging platform into generic channel values."""

    channel_type: str
    max_outbound_text_length: int | None

    async def begin_link(
        self, previous_credentials: BindingCredentials | None = None
    ) -> LinkChallenge: ...

    async def poll_link(
        self,
        challenge: LinkChallenge,
        verification_code: str | None = None,
    ) -> LinkPollResult: ...

    async def fetch_updates(
        self,
        credentials: BindingCredentials,
        cursor: str | None,
    ) -> UpdateBatch: ...

    def normalize(
        self,
        raw_update: object,
        binding: BindingRoute,
    ) -> InboundMessage: ...

    async def resolve_images(
        self,
        media: tuple[InboundMedia, ...],
        *,
        max_bytes: int,
        max_pixels: int,
    ) -> tuple[ResolvedImage, ...]: ...

    async def deliver(
        self,
        credentials: BindingCredentials,
        reply_context: ReplyContext,
        message: OutboundMessage,
    ) -> DeliveryReceipt: ...
