"""Public contract tests for platform-neutral messaging channels."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.server.channels.adapters.base import ChannelAdapter
from src.server.channels.agent_adapters.base import AgentAdapter
from src.server.channels.contracts import (
    AgentSession,
    AgentTurn,
    AgentTurnResult,
    BindingCredentials,
    BindingRoute,
    BindingView,
    DeliveryReceipt,
    InboundKind,
    InboundMedia,
    InboundMessage,
    LinkChallenge,
    LinkPollResult,
    LinkPollState,
    LinkStatus,
    MediaPart,
    OpenSessionRequest,
    OutboundMessage,
    ReplyContext,
    ResolvedImage,
    TextPart,
    UpdateBatch,
)


NOW = datetime(2026, 8, 28, 12, 0, tzinfo=UTC)


class FakeChannel:
    channel_type = "fake"

    async def begin_link(self) -> LinkChallenge:
        return LinkChallenge(
            channel_type=self.channel_type,
            challenge_ref="challenge-1",
            qr_code_url="https://example.invalid/qr",
            expires_at=NOW,
            provider_poll_state=LinkPollState(
                values=(
                    ("qrcode", "provider-private-qrcode"),
                    ("poll_base_url", "https://provider.invalid/poll"),
                )
            ),
        )

    async def poll_link(
        self,
        challenge: LinkChallenge,
        verification_code: str | None = None,
    ) -> LinkPollResult:
        assert challenge.challenge_ref == "challenge-1"
        assert challenge.provider_poll_state.values[0] == (
            "qrcode",
            "provider-private-qrcode",
        )
        assert verification_code == "123456"
        return LinkPollResult(
            status=LinkStatus.LINKED,
            binding=BindingView(
                binding_ref="binding-1",
                channel_type=self.channel_type,
                display_name="Test account",
            ),
            routing=BindingRoute(binding_ref="binding-1", peer_ref="account-1"),
            credentials=BindingCredentials(
                binding_ref="binding-1",
                channel_type=self.channel_type,
                values=(("access_token", "secret"),),
            ),
        )

    async def fetch_updates(
        self,
        credentials: BindingCredentials,
        cursor: str | None,
    ) -> UpdateBatch:
        assert credentials.binding_ref == "binding-1"
        assert cursor is None
        return UpdateBatch(updates=({"event": "message"},), next_cursor="cursor-1")

    def normalize(
        self,
        raw_update: object,
        binding: BindingRoute,
    ) -> InboundMessage:
        assert raw_update == {"event": "message"}
        assert binding.peer_ref == "account-1"
        return InboundMessage(
            provider_message_id="provider-message-1",
            peer_ref="peer-1",
            received_at=NOW,
            kind=InboundKind.MESSAGE,
            text="Hello",
            media=(
                InboundMedia(
                    ref="media-1",
                    mime_type="image/png",
                    byte_size=256,
                    width=16,
                    height=16,
                ),
            ),
            reply_context=ReplyContext(
                route_ref="reply-route-1",
                values=(("reply_token", "reply-secret"),),
            ),
        )

    async def deliver(
        self,
        credentials: BindingCredentials,
        reply_context: ReplyContext,
        message: OutboundMessage,
    ) -> DeliveryReceipt:
        assert credentials.channel_type == self.channel_type
        assert reply_context.route_ref == "reply-route-1"
        assert message.client_id == "outbound-1"
        assert message.parts == (TextPart(text="Hi"),)
        return DeliveryReceipt(
            accepted=True,
            provider_message_id="provider-message-2",
            delivered_at=NOW,
        )


class FakeAgent:
    async def open_session(self, request: OpenSessionRequest) -> AgentSession:
        assert request.actor_ref == "user-1"
        return AgentSession(ref="opaque-agent-session", opened_at=NOW)

    async def run_turn(
        self,
        session: AgentSession,
        turn: AgentTurn,
    ) -> AgentTurnResult:
        assert session.ref == "opaque-agent-session"
        assert turn.text == "Hello"
        assert turn.images == (
            ResolvedImage(
                content_ref="workspace-image-1",
                mime_type="image/png",
                byte_size=256,
                width=16,
                height=16,
            ),
        )
        return AgentTurnResult(
            message=OutboundMessage(
                client_id="outbound-1",
                parts=(TextPart(text="Hi"),),
            )
        )


@pytest.mark.asyncio
async def test_fake_adapters_satisfy_generic_runtime_contracts():
    channel = FakeChannel()
    agent = FakeAgent()

    assert isinstance(channel, ChannelAdapter)
    assert isinstance(agent, AgentAdapter)

    challenge = await channel.begin_link()
    linked = await channel.poll_link(challenge, verification_code="123456")
    assert linked.status is LinkStatus.LINKED
    assert linked.binding is not None
    assert linked.routing is not None
    assert linked.credentials is not None

    batch = await channel.fetch_updates(linked.credentials, cursor=None)
    inbound = channel.normalize(batch.updates[0], linked.routing)
    assert inbound.kind is InboundKind.MESSAGE
    assert inbound.provider_message_id == "provider-message-1"
    assert inbound.peer_ref == "peer-1"
    assert inbound.text == "Hello"
    assert inbound.media[0].mime_type == "image/png"
    assert inbound.reply_context is not None

    session = await agent.open_session(
        OpenSessionRequest(
            binding_ref="binding-1",
            actor_ref="user-1",
            peer_ref="peer-1",
            session_key="session-1",
        )
    )
    result = await agent.run_turn(
        session,
        AgentTurn(
            turn_ref="turn-1",
            text=inbound.text,
            images=(
                ResolvedImage(
                    content_ref="workspace-image-1",
                    mime_type=inbound.media[0].mime_type,
                    byte_size=inbound.media[0].byte_size,
                    width=inbound.media[0].width,
                    height=inbound.media[0].height,
                ),
            ),
            received_at=inbound.received_at,
        ),
    )
    receipt = await channel.deliver(
        linked.credentials,
        inbound.reply_context,
        result.message,
    )

    assert session.ref == "opaque-agent-session"
    assert result.message.client_id == "outbound-1"
    assert result.message.parts == (TextPart(text="Hi"),)
    assert receipt.accepted is True


def test_contract_values_preserve_message_states_and_future_media_parts():
    ignored = InboundMessage(
        provider_message_id="provider-message-ignored",
        peer_ref="peer-1",
        received_at=NOW,
        kind=InboundKind.IGNORED,
        reason="unsupported_media",
    )
    rejected = InboundMessage(
        provider_message_id="provider-message-rejected",
        peer_ref="peer-1",
        received_at=NOW,
        kind=InboundKind.REJECTED,
        reason="invalid_signature",
    )
    outbound = OutboundMessage(
        client_id="outbound-2",
        parts=(
            TextPart(text="A caption"),
            MediaPart(media_ref="asset-1", mime_type="image/png", caption="An image"),
        )
    )

    assert ignored.text is None
    assert ignored.media == ()
    assert rejected.reply_context is None
    assert outbound.parts[0] == TextPart(text="A caption")
    assert isinstance(outbound.parts[1], MediaPart)

    with pytest.raises(FrozenInstanceError):
        outbound.parts = ()  # type: ignore[misc]


def test_binding_view_excludes_private_peer_routing_data():
    binding = BindingView(
        binding_ref="binding-1",
        channel_type="fake",
        display_name="Test account",
    )
    routing = BindingRoute(binding_ref="binding-1", peer_ref="private-peer-1")

    assert tuple(field.name for field in fields(BindingView)) == (
        "binding_ref",
        "channel_type",
        "display_name",
    )
    assert binding.display_name == "Test account"
    assert routing.peer_ref == "private-peer-1"


def test_link_challenge_keeps_provider_poll_state_outside_display_fields():
    challenge = LinkChallenge(
        channel_type="fake",
        challenge_ref="challenge-1",
        qr_code_url="https://example.invalid/qr",
        expires_at=NOW,
        provider_poll_state=LinkPollState(
            values=(
                ("qrcode", "provider-private-qrcode"),
                ("poll_base_url", "https://provider.invalid/poll"),
            )
        ),
    )

    assert challenge.provider_poll_state.values[1] == (
        "poll_base_url",
        "https://provider.invalid/poll",
    )
    assert tuple(field.name for field in fields(LinkChallenge)) == (
        "channel_type",
        "challenge_ref",
        "qr_code_url",
        "expires_at",
        "provider_poll_state",
    )


def test_link_results_use_explicit_states_without_persisting_verification_codes():
    assert tuple(LinkStatus) == (
        LinkStatus.WAITING,
        LinkStatus.SCANNED,
        LinkStatus.VERIFICATION_REQUIRED,
        LinkStatus.LINKED,
        LinkStatus.EXPIRED,
        LinkStatus.FAILED,
    )
    assert LinkPollResult(status=LinkStatus.VERIFICATION_REQUIRED).status is (
        LinkStatus.VERIFICATION_REQUIRED
    )

    contract_records = (
        LinkChallenge,
        LinkPollResult,
        BindingCredentials,
        BindingView,
        BindingRoute,
    )
    assert all(
        "verification_code" not in {field.name for field in fields(record)}
        for record in contract_records
    )


def test_contract_modules_do_not_import_runtime_or_provider_implementations():
    import src.server.channels.adapters.base as channel_base
    import src.server.channels.agent_adapters.base as agent_base
    import src.server.channels.contracts as contracts

    sources = "\n".join(
        Path(module.__file__).read_text(encoding="utf-8")
        for module in (contracts, channel_base, agent_base)
    ).lower()

    for forbidden in ("fastapi", "chatrequest", "langgraph", "wechat", "thread_id"):
        assert forbidden not in sources
