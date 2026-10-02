"""Replay-profile contracts for RunSSEProducer."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, call

from src.server.services.runs import stream_writer
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

    closed = False

    async def fake_stream(*_args, **_kwargs):
        nonlocal closed
        try:
            yield ""
            yield "id: 1\nevent: metadata\ndata: {}\n\n"
        finally:
            closed = True

    producer._stream_workflow_unfiltered = fake_stream

    stream = producer.stream_workflow(
        graph=object(),
        input_state={},
        config={},
    )
    frame = await anext(stream)
    assert frame == "id: 1\nevent: metadata\ndata: {}\n\n"

    await stream.aclose()
    assert closed is True


@pytest.mark.asyncio
async def test_compact_stream_awaits_observer_before_filtering_raw_events():
    observer = AsyncMock()
    producer = RunSSEProducer(
        thread_id="thread-1",
        run_id="run-1",
        replay_profile="education_compact",
        event_observer=observer,
    )

    async def fake_stream(*_args, **_kwargs):
        yield producer._format_sse_event(
            "tool_calls",
            {
                "tool_calls": [
                    {
                        "id": "call-1",
                        "name": "Read",
                        "args": {"file_path": "inputs/source/document.md"},
                    }
                ]
            },
        )
        yield producer._format_sse_event(
            "message_chunk",
            {"content": "private model delta"},
        )
        yield producer._format_sse_event("metadata", {"run_id": "run-1"})

    producer._stream_workflow_unfiltered = fake_stream

    frames = [
        frame
        async for frame in producer.stream_workflow(
            graph=object(),
            input_state={},
            config={},
        )
    ]

    assert len(frames) == 1
    assert "event: metadata" in frames[0]
    assert observer.await_args_list == [
        call(
            "tool_calls",
            {
                "tool_calls": [
                    {
                        "id": "call-1",
                        "name": "Read",
                        "args": {"file_path": "inputs/source/document.md"},
                    }
                ]
            },
        ),
        call("message_chunk", {"content": "private model delta"}),
        call("metadata", {"run_id": "run-1"}),
    ]


@pytest.mark.asyncio
async def test_observer_failure_never_breaks_workflow_stream():
    observer = AsyncMock(side_effect=RuntimeError("activity database unavailable"))
    producer = RunSSEProducer(
        thread_id="thread-1",
        run_id="run-1",
        replay_profile="education_compact",
        event_observer=observer,
    )

    async def fake_stream(*_args, **_kwargs):
        yield producer._format_sse_event("metadata", {"run_id": "run-1"})

    producer._stream_workflow_unfiltered = fake_stream

    frames = [
        frame
        async for frame in producer.stream_workflow(
            graph=object(),
            input_state={},
            config={},
        )
    ]

    assert len(frames) == 1
    assert "event: metadata" in frames[0]


@pytest.mark.asyncio
async def test_stream_flushes_stateful_observer_after_final_event():
    class Observer:
        def __init__(self):
            self.events = []
            self.flush = AsyncMock()

        async def __call__(self, event_type, data):
            self.events.append((event_type, data))

    observer = Observer()
    producer = RunSSEProducer(
        thread_id="thread-1",
        run_id="run-1",
        replay_profile="education_compact",
        event_observer=observer,
    )

    async def fake_stream(*_args, **_kwargs):
        yield producer._format_sse_event("metadata", {"run_id": "run-1"})

    producer._stream_workflow_unfiltered = fake_stream

    _frames = [
        frame
        async for frame in producer.stream_workflow(
            graph=object(), input_state={}, config={}
        )
    ]

    observer.flush.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_education_compact_finishes_far_below_redis_quota_under_raw_delta_pressure(
    monkeypatch,
):
    class FakeCache:
        enabled = True

        def __init__(self):
            self.event_ids: list[int] = []

        async def pipelined_event_buffer(self, _key, **kwargs):
            self.event_ids.append(kwargs["event_id"])

    cache = FakeCache()
    monkeypatch.setattr(stream_writer, "get_cache_client", lambda: cache)
    producer = RunSSEProducer(
        thread_id="thread-1",
        run_id="run-1",
        replay_profile="education_compact",
    )

    emitted_replay_events = 0
    replay_frames: list[str] = []
    for index in range(150_001):
        frame = producer._format_sse_event(
            "message_chunk",
            {
                "thread_id": "thread-1",
                "agent": "main",
                "id": "message-1",
                "content": str(index),
            },
        )
        emitted_replay_events += bool(frame)
        if frame:
            replay_frames.append(frame)
    emitted_replay_events += bool(
        frame := producer._format_sse_event(
            "metadata",
            {"thread_id": "thread-1"},
        )
    )
    if frame:
        replay_frames.append(frame)

    for frame in replay_frames:
        await stream_writer.buffer_event(
            "thread-1",
            "run-1",
            frame,
            max_stored_messages=1_000,
        )

    stored_sse_events = len(producer.get_sse_events() or [])

    assert emitted_replay_events < 1_000
    assert stored_sse_events < 1_000
    assert len(cache.event_ids) < 1_000
