"""Provider-neutral values shared by channel gateways and agent adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class LinkStatus(str, Enum):
    """The current state of a channel account linking challenge."""

    WAITING = "waiting"
    SCANNED = "scanned"
    VERIFICATION_REQUIRED = "verification_required"
    LINKED = "linked"
    EXPIRED = "expired"
    FAILED = "failed"


class InboundKind(str, Enum):
    """Whether a normalized provider update may be processed."""

    MESSAGE = "message"
    IGNORED = "ignored"
    REJECTED = "rejected"


@dataclass(frozen=True)
class LinkPollState:
    """Opaque provider state needed to poll a pairing challenge.

    Services persist these values encrypted and never expose them in a display
    response.
    """

    values: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class LinkChallenge:
    """A short-lived platform-specific pairing challenge represented generically."""

    channel_type: str
    challenge_ref: str
    qr_code_url: str
    expires_at: datetime
    provider_poll_state: LinkPollState


@dataclass(frozen=True)
class BindingCredentials:
    """Opaque provider credentials for one binding.

    The gateway encrypts these values before persistence. Adapters receive them
    only after the gateway decrypts the binding for the current operation.
    """

    binding_ref: str
    channel_type: str
    values: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class BindingView:
    """Non-secret binding information suitable for a settings display."""

    binding_ref: str
    channel_type: str
    display_name: str | None = None


@dataclass(frozen=True)
class BindingRoute:
    """Private routing data for a binding, stored with the binding's secrets."""

    binding_ref: str
    peer_ref: str


@dataclass(frozen=True)
class LinkPollResult:
    """The result of one link-challenge poll."""

    status: LinkStatus
    next_poll_state: LinkPollState | None = None
    binding: BindingView | None = None
    routing: BindingRoute | None = None
    credentials: BindingCredentials | None = None


@dataclass(frozen=True)
class UpdateBatch:
    """Raw provider updates and the cursor to persist after handling them."""

    updates: tuple[object, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class ReplyContext:
    """Opaque per-message data required by a provider to send a reply."""

    route_ref: str
    values: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class InboundMedia:
    """A provider media reference and metadata collected during normalization."""

    ref: str
    mime_type: str
    byte_size: int | None = None
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class InboundMessage:
    """A normalized message or an explicitly non-processable provider update."""

    provider_message_id: str
    peer_ref: str | None
    received_at: datetime
    kind: InboundKind
    text: str | None = None
    media: tuple[InboundMedia, ...] = ()
    reply_context: ReplyContext | None = None
    reason: str | None = None


@dataclass(frozen=True)
class TextPart:
    """A text component of an outbound message."""

    text: str


@dataclass(frozen=True)
class MediaPart:
    """A future media component represented without provider-specific types."""

    media_ref: str
    mime_type: str
    caption: str | None = None


@dataclass(frozen=True)
class OutboundMessage:
    """A provider-neutral reply composed from text and media components."""

    client_id: str
    parts: tuple[TextPart | MediaPart, ...]


@dataclass(frozen=True)
class DeliveryReceipt:
    """The outcome reported by a provider after an outbound delivery attempt."""

    accepted: bool
    provider_message_id: str | None
    delivered_at: datetime
    detail: str | None = None


@dataclass(frozen=True)
class OpenSessionRequest:
    """Information an agent adapter needs to open an opaque conversation session."""

    binding_ref: str
    actor_ref: str
    peer_ref: str
    session_key: str


@dataclass(frozen=True)
class AgentSession:
    """An agent-owned session handle; callers must treat ``ref`` as opaque."""

    ref: str
    opened_at: datetime


@dataclass(frozen=True)
class ResolvedImage:
    """A validated internal image reference that can be supplied to an agent."""

    content_ref: str
    mime_type: str
    byte_size: int | None = None
    width: int | None = None
    height: int | None = None


@dataclass(frozen=True)
class AgentTurn:
    """One normalized inbound turn supplied to an agent adapter."""

    request_key: str
    text: str | None
    received_at: datetime
    images: tuple[ResolvedImage, ...] = ()


@dataclass(frozen=True)
class AgentTurnResult:
    """Provider-neutral response content from an agent adapter.

    The gateway owns splitting this content and assigning durable delivery IDs
    while it writes the outbound rows.
    """

    parts: tuple[TextPart | MediaPart, ...]
