from dataclasses import FrozenInstanceError

import pytest

from src.server.channels.events import (
    Commentary,
    GatewayNotice,
    LongToolHint,
    MessageChunk,
    MessageStop,
    StreamEvent,
    ToolCallChunk,
    ToolCallFinished,
)


def test_message_events_keep_source_metadata_without_provider_knowledge() -> None:
    event = MessageChunk(
        text="internal",
        agent="task:research",
        content_type="reasoning",
        role="assistant",
    )

    assert event.text == "internal"
    assert event.agent == "task:research"
    assert event.content_type == "reasoning"
    assert event.role == "assistant"
    with pytest.raises(FrozenInstanceError):
        event.text = "changed"  # type: ignore[misc]


def test_stream_event_vocabulary_carries_lifecycle_and_tool_facts() -> None:
    events: tuple[StreamEvent, ...] = (
        MessageChunk("answer"),
        MessageStop(final=True),
        Commentary("working"),
        ToolCallChunk("search", preview="query", args={"q": "query"}, index=2),
        ToolCallFinished("search", duration=0.4, ok=False, index=2),
        LongToolHint("search", duration=4.0),
        GatewayNotice("online", "ready"),
    )

    assert len(events) == 7
    assert events[3].index == 2  # type: ignore[union-attr]
    assert events[4].ok is False  # type: ignore[union-attr]
    assert events[6].kind == "online"  # type: ignore[union-attr]
