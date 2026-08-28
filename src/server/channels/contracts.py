"""Provider-neutral values shared by channel gateways and agent adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class LinkStatus(str, Enum):
    """The current state of a channel account linking challenge."""

    PENDING = "pending"
    LINKED = "linked"
    EXPIRED = "expired"
    FAILED = "failed"


class InboundKind(str, Enum):
    """Whether a normalized provider update may be processed."""

    MESSAGE = "message"
    IGNORED = "ignored"
    REJECTED = "rejected"


@dataclass(frozen=True)
class LinkChallenge:
    """A short-lived platform-specific pairing challenge represented generically."""

    channel_type: str
    challenge_ref: str
    qr_code_url: str
    expires_at: datetime


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
    """Non-secret binding information suitable for routing and display."""

    binding_ref: str
    channel_type: str
    external_account_ref: str
    display_name: str | None = None


@dataclass(frozen=True)
class LinkPollResult:
    """The result of one link-challenge poll."""

    status: LinkStatus
    binding: BindingView | None = None
    credentials: BindingCredentials | None = None
    detail: str | None = None


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
class InboundMessage:
    """A normalized message or an explicitly non-processable provider update."""

    provider_message_id: str
    peer_ref: str | None
    received_at: datetime
    kind: InboundKind
    text: str | None = None
    media_refs: tuple[str, ...] = ()
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
class AgentTurn:
    """One normalized inbound turn supplied to an agent adapter."""

    turn_ref: str
    text: str | None
    media_refs: tuple[str, ...]
    received_at: datetime


@dataclass(frozen=True)
class AgentTurnResult:
    """A completed provider-neutral response from an agent adapter."""

    message: OutboundMessage

