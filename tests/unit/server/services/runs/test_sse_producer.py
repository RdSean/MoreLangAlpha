"""Replay-profile contracts for RunSSEProducer."""

from __future__ import annotations

import pytest

from src.server.services.runs.sse_producer import RunSSEProducer


_COMPACT_ALLOWED = (
    "metadata",
    "warning",
    "error",
    "interrupt",
    "model_retry",
    "model_fallback",
)
_COMPACT_FILTERED = (
    "message_chunk",
    "tool_call_chunks",
    "tool_calls",
    "tool_call_result",
    "compaction_chunk",
    "context_window",
    "provenance",
    "steering_delivered",
)


def test_education_compact_filters_before_sequence_allocation_and_accumulation():
    producer = RunSSEProducer(
        thread_id="thread-1",
        run_id="run-1",
        replay_profile="education_compact",
    )

    allowed_frames = [
        producer._format_sse_event(event_type, {"value": event_type})
        for event_type in _COMPACT_ALLOWED
    ]
    filtered_frames = [
        producer._format_sse_event(event_type, {"value": event_type})
        for event_type in _COMPACT_FILTERED
    ]

    assert all(frame for frame in allowed_frames)
    assert filtered_frames == [""] * len(_COMPACT_FILTERED)
    assert producer.event_sequence == len(_COMPACT_ALLOWED)
    assert [event["event"] for event in producer.get_sse_events()] == list(
        _COMPACT_ALLOWED
    )


def test_full_profile_keeps_raw_replay_events():
    producer = RunSSEProducer(
        thread_id="thread-1",
        run_id="run-1",
        replay_profile="full",
    )

    frames = [
        producer._format_sse_event(event_type, {"value": event_type})
        for event_type in _COMPACT_FILTERED
    ]

    assert all(frames)
    assert producer.event_sequence == len(_COMPACT_FILTERED)
    assert [event["event"] for event in producer.get_sse_events()] == list(
        _COMPACT_FILTERED
    )


@pytest.mark.asyncio
async def test_stream_workflow_filters_compact_empty_sentinel():
    producer = RunSSEProducer(
        thread_id="thread-1",
        run_id="run-1",
        replay_profile="education_compact",
    )

    async def fake_stream(*_args, **_kwargs):
        yield ""
        yield "id: 1\nevent: metadata\ndata: {}\n\n"

    producer._stream_workflow_unfiltered = fake_stream

    frames = [
        frame
        async for frame in producer.stream_workflow(
            graph=object(),
            input_state={},
            config={},
        )
    ]

    assert frames == ["id: 1\nevent: metadata\ndata: {}\n\n"]


def test_education_compact_finishes_far_below_redis_quota_under_raw_delta_pressure():
    producer = RunSSEProducer(
        thread_id="thread-1",
        run_id="run-1",
        replay_profile="education_compact",
    )

    emitted_replay_events = 0
    for index in range(150_001):
        emitted_replay_events += bool(
            producer._format_sse_event(
                "message_chunk",
                {
                    "thread_id": "thread-1",
                    "agent": "main",
                    "id": "message-1",
                    "content": str(index),
                },
            )
        )
    emitted_replay_events += bool(
        producer._format_sse_event("metadata", {"thread_id": "thread-1"})
    )

    stored_sse_events = len(producer.get_sse_events() or [])

    assert emitted_replay_events < 1_000
    assert stored_sse_events < 1_000
