"""Interface implemented by a concrete external messaging platform."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.server.channels.contracts import (
    BindingCredentials,
    BindingView,
    DeliveryReceipt,
    InboundMessage,
    LinkChallenge,
    LinkPollResult,
    OutboundMessage,
    ReplyContext,
    UpdateBatch,
)


@runtime_checkable
class ChannelAdapter(Protocol):
    """Translate one external messaging platform into generic channel values."""

    channel_type: str

    async def begin_link(self) -> LinkChallenge: ...

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
        binding: BindingView,
    ) -> InboundMessage: ...

    async def deliver(
        self,
        credentials: BindingCredentials,
        reply_context: ReplyContext,
        message: OutboundMessage,
    ) -> DeliveryReceipt: ...

