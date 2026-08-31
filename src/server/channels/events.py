"""Provider-neutral presentation events emitted by agent adapters."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypeAlias


@dataclass(frozen=True)
class MessageChunk:
    """Incremental assistant text plus source metadata from the agent stream."""

    text: str
    agent: str | None = None
    content_type: str | None = None
    role: str | None = None


@dataclass(frozen=True)
class MessageStop:
    """Marks the end of an assistant text segment."""

    final: bool = False


@dataclass(frozen=True)
class Commentary:
    """A complete interim assistant message."""

    text: str
    agent: str | None = None


@dataclass(frozen=True)
class ToolCallChunk:
    """Facts about a tool invocation; presentation is adapter-owned."""

    tool_name: str
    preview: str | None = None
    args: dict[str, Any] | None = None
    index: int = 0


@dataclass(frozen=True)
class ToolCallFinished:
    """Completion metadata for a tool invocation."""

    tool_name: str
    duration: float = 0.0
    ok: bool = True
    index: int = 0
    tool_call_id: str | None = None


@dataclass(frozen=True)
class LongToolHint:
    """A gateway hint emitted after a long-running tool call."""

    tool_name: str = ""
    duration: float = 0.0


@dataclass(frozen=True)
class GatewayNotice:
    """A gateway lifecycle notice with optional structured details."""

    kind: str
    text: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


StreamEvent: TypeAlias = (
    MessageChunk
    | MessageStop
    | Commentary
    | ToolCallChunk
    | ToolCallFinished
    | LongToolHint
    | GatewayNotice
)


__all__ = [
    "Commentary",
    "GatewayNotice",
    "LongToolHint",
    "MessageChunk",
    "MessageStop",
    "StreamEvent",
    "ToolCallChunk",
    "ToolCallFinished",
]
