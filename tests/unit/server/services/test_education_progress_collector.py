"""Live semantic progress collection contracts for managed education runs."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.server.database.education_textbooks import (
    ProgressEventPersistenceOutcome,
    ProgressEventPersistenceResult,
)
from src.server.services import education_progress_collector
from src.server.services import education_generation_progress
from src.server.services import education_structure_jobs


JOB_ID = "4d0112f8-0e00-4f1f-990a-4bc1b1cc20f3"
ATTEMPT_ID = "6f3f2de2-5c58-4bc2-84bc-95e97acd37f6"
RUN_ID = "61ad89e0-f2eb-474a-b74a-a67580a51aa7"


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


class _GrowingSandbox:
    def __init__(self, payloads: list[bytes]) -> None:
        self.payloads = payloads
        self.calls = 0
        self.paths: list[str] = []

    async def adownload_file_bytes(self, path: str) -> bytes | None:
        self.paths.append(path)
        index = min(self.calls, len(self.payloads) - 1)
        self.calls += 1
        return self.payloads[index]


class _Store:
    def __init__(self, *, fail_times: int = 0) -> None:
        self.rows: dict[tuple[str, int], dict] = {}
        self.calls: list[dict] = []
        self.fail_times = fail_times

    async def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_times:
            self.fail_times -= 1
            raise RuntimeError("temporary persistence outage")
        key = (str(kwargs["attempt_id"]), int(kwargs["sequence"]))
        event = dict(kwargs["event"])
        if key in self.rows:
            existing = self.rows[key]
            matches = (
                (existing.get("metadata") or {}) == (event.get("metadata") or {})
                and all(
                    existing.get(field) == event.get(field)
                    for field in (
                        "event_key",
                        "stage",
                        "substage",
                        "status",
                        "label",
                        "detail",
                        "node_key",
                        "current_value",
                        "total_value",
                    )
                )
            )
            return ProgressEventPersistenceResult(
                outcome=(
                    ProgressEventPersistenceOutcome.ALREADY_EXISTS
                    if matches
                    else ProgressEventPersistenceOutcome.REJECTED
                ),
                event=existing if matches else None,
            )
        row = {
            "event_id": len(self.rows) + 1,
            "generation_job_id": kwargs["generation_job_id"],
            "attempt_id": kwargs["attempt_id"],
            "run_id": kwargs.get("run_id"),
            "sequence": kwargs["sequence"],
            **event,
        }
        self.rows[key] = row
        return ProgressEventPersistenceResult(
            outcome=ProgressEventPersistenceOutcome.INSERTED,
            event=row,
        )


def _collector(
    monkeypatch,
    sandbox,
    store: _Store,
    *,
    clock=None,
    checkpoint_stop_event=None,
) -> education_progress_collector.ManagedProgressCollector:
    monkeypatch.setattr(
        education_progress_collector,
        "persist_generation_progress_event",
        store,
    )
    return education_progress_collector.ManagedProgressCollector(
        sandbox=sandbox,
        generation_job_id=JOB_ID,
        attempt_id=ATTEMPT_ID,
        run_id=RUN_ID,
        clock=clock,
        poll_interval=0.01,
        checkpoint_stop_event=checkpoint_stop_event,
    )


@pytest.mark.asyncio
async def test_collector_persists_growing_events_before_managed_run_finishes(
    monkeypatch,
) -> None:
    first = (
        b'{"event_key":"chapter:start","stage":"chapter_analysis","status":"running"}\n'
    )
    second = (
        first
        + b'{"event_key":"content:start","stage":"content_processing","status":"running"}\n'
    )
    sandbox = _GrowingSandbox([first, second])
    store = _Store()
    collector = _collector(monkeypatch, sandbox, store)

    await collector.poll_once()
    assert len(store.rows) == 1

    await collector.poll_once()

    assert [row["sequence"] for row in store.rows.values()] == [1, 2]
    assert {(row["stage"], row["status"]) for row in store.rows.values()} == {
        ("chapter_analysis", "running"),
        ("content_processing", "running"),
    }


@pytest.mark.asyncio
async def test_collector_keeps_incomplete_final_line_for_the_next_poll(
    monkeypatch,
) -> None:
    first = (
        b'{"event_key":"chapter:start","stage":"chapter_analysis","status":"running"}\n'
    )
    partial = (
        first
        + b'{"event_key":"content:start","stage":"content_processing",'
        + b'"status":"running"}'
    )
    sandbox = _GrowingSandbox([partial, partial + b"\n"])
    store = _Store()
    collector = _collector(monkeypatch, sandbox, store)

    await collector.poll_once()
    assert len(store.rows) == 1

    await collector.poll_once()

    assert len(store.rows) == 2
    assert store.rows[(ATTEMPT_ID, 2)]["stage"] == "content_processing"


@pytest.mark.asyncio
async def test_collector_replay_is_idempotent_by_attempt_sequence(
    monkeypatch,
) -> None:
    payload = (
        b'{"event_key":"chapter:start","stage":"chapter_analysis","status":"running"}\n'
    )
    sandbox = _GrowingSandbox([payload, payload])
    store = _Store()
    collector = _collector(monkeypatch, sandbox, store)

    await collector.poll_once()

    restarted = _collector(monkeypatch, sandbox, store)
    await restarted.poll_once()

    assert len(store.rows) == 1
    assert [call["sequence"] for call in store.calls] == [1, 1]
    assert restarted.latest_event_by_key["chapter:start"]["sequence"] == 1


@pytest.mark.asyncio
async def test_transient_persistence_failure_retries_same_offset_and_sequence(
    monkeypatch,
) -> None:
    payload = (
        b'{"event_key":"chapter:start","stage":"chapter_analysis","status":"running"}\n'
    )
    sandbox = _GrowingSandbox([payload])
    store = _Store(fail_times=1)
    collector = _collector(monkeypatch, sandbox, store)

    await collector.poll_once()

    assert store.rows == {}
    assert collector.errors

    await collector.poll_once()

    assert len(store.rows) == 1
    assert [call["sequence"] for call in store.calls] == [1, 1]
    assert store.rows[(ATTEMPT_ID, 1)]["event_key"] == "chapter:start"


@pytest.mark.asyncio
async def test_collector_bounds_lines_and_file_reads(monkeypatch) -> None:
    oversized_line = b"x" * (
        education_generation_progress.MAX_PROGRESS_EVENT_BYTES + 1
    )
    sandbox = _GrowingSandbox([oversized_line + b"\n"])
    store = _Store()
    collector = _collector(monkeypatch, sandbox, store)

    await collector.poll_once()

    assert store.rows == {}
    assert collector.errors

    oversized_file = b"x" * (education_progress_collector.MAX_PROGRESS_FILE_BYTES + 1)
    sandbox = _GrowingSandbox([oversized_file])
    collector = _collector(monkeypatch, sandbox, _Store())

    await collector.poll_once()

    assert collector.errors


@pytest.mark.asyncio
async def test_stop_flushes_the_final_appended_event(monkeypatch) -> None:
    first = (
        b'{"event_key":"chapter:start","stage":"chapter_analysis","status":"running"}\n'
    )
    final = (
        first
        + b'{"event_key":"chapter:done","stage":"chapter_analysis","status":"completed"}\n'
    )
    sandbox = _GrowingSandbox([first, final])
    store = _Store()
    collector = _collector(monkeypatch, sandbox, store)

    await collector.start()
    await asyncio.sleep(0.02)
    await collector.stop()

    assert [row["event_key"] for row in store.rows.values()] == [
        "chapter:start",
        "chapter:done",
    ]


@pytest.mark.asyncio
async def test_fallback_emits_only_after_idle_sanitized_activity(monkeypatch) -> None:
    clock = _Clock()
    payload = (
        b'{"event_key":"chapter:start","stage":"chapter_analysis","status":"running"}\n'
    )
    sandbox = _GrowingSandbox([payload])
    store = _Store()
    collector = _collector(monkeypatch, sandbox, store, clock=clock)

    await collector.poll_once()
    clock.value = 1.0
    collector.note_activity()
    clock.value = 17.0
    await collector.poll_once()

    fallback = store.rows[(ATTEMPT_ID, 2)]
    assert fallback["stage"] == "chapter_analysis"
    assert fallback["substage"] == "executing"
    assert fallback["label"] == "执行环境步骤"
    assert fallback["metadata"]["fallback"] is True

    clock.value = 35.0
    await collector.poll_once()
    assert len(store.rows) == 2


@pytest.mark.asyncio
async def test_fallback_does_not_regress_a_completed_stage(monkeypatch) -> None:
    clock = _Clock()
    payload = (
        b'{"event_key":"chapter:start","stage":"chapter_analysis","status":"running"}\n'
        b'{"event_key":"chapter:start","stage":"chapter_analysis","status":"completed"}\n'
    )
    sandbox = _GrowingSandbox([payload])
    store = _Store()
    collector = _collector(monkeypatch, sandbox, store, clock=clock)

    await collector.poll_once()
    clock.value = 1.0
    collector.note_activity()
    clock.value = 17.0
    await collector.poll_once()

    assert len(store.rows) == 2
    assert [row["status"] for row in store.rows.values()] == [
        "running",
        "completed",
    ]


@pytest.mark.asyncio
async def test_fallback_only_targets_the_current_unfinished_stage(monkeypatch) -> None:
    clock = _Clock()
    payload = (
        b'{"event_key":"chapter","stage":"chapter_analysis","status":"completed"}\n'
        b'{"event_key":"content","stage":"content_processing","status":"running"}\n'
    )
    sandbox = _GrowingSandbox([payload])
    store = _Store()
    collector = _collector(monkeypatch, sandbox, store, clock=clock)

    await collector.poll_once()
    clock.value = 1.0
    collector.note_activity()
    clock.value = 17.0
    await collector.poll_once()

    fallback = store.rows[(ATTEMPT_ID, 3)]
    assert fallback["stage"] == "content_processing"
    assert fallback["status"] == "running"


@pytest.mark.asyncio
async def test_completed_chapter_event_sets_stop_signal_once(
    monkeypatch,
) -> None:
    payload = b'{"event_key":"chapter:done","stage":"chapter_analysis","status":"completed"}\n'
    sandbox = _GrowingSandbox([payload, payload])
    store = _Store()
    stop_event = asyncio.Event()

    collector = _collector(
        monkeypatch,
        sandbox,
        store,
        checkpoint_stop_event=stop_event,
    )

    await collector.poll_once()
    await collector.poll_once()

    assert stop_event.is_set()
    assert collector.checkpoint_requested is True


@pytest.mark.asyncio
async def test_already_existing_matching_event_can_set_missing_stop_signal(
    monkeypatch,
) -> None:
    event = {
        "event_key": "chapter:done",
        "stage": "chapter_analysis",
        "status": "completed",
        "label": "chapter_analysis completed",
        "metadata": {},
    }
    store = _Store()
    store.rows[(ATTEMPT_ID, 1)] = {
        "event_id": 1,
        "generation_job_id": JOB_ID,
        "attempt_id": ATTEMPT_ID,
        "run_id": RUN_ID,
        "sequence": 1,
        **event,
    }
    sandbox = _GrowingSandbox(
        [
            b'{"event_key":"chapter:done","stage":"chapter_analysis",'
            b'"status":"completed"}\n'
        ]
    )
    stop_event = asyncio.Event()

    collector = _collector(
        monkeypatch,
        sandbox,
        store,
        checkpoint_stop_event=stop_event,
    )

    await collector.poll_once()

    assert stop_event.is_set()
    assert not collector.errors


@pytest.mark.asyncio
async def test_rejected_sequence_payload_mismatch_never_triggers_checkpoint(
    monkeypatch,
) -> None:
    store = _Store()
    store.rows[(ATTEMPT_ID, 1)] = {
        "event_id": 1,
        "generation_job_id": JOB_ID,
        "attempt_id": ATTEMPT_ID,
        "run_id": RUN_ID,
        "sequence": 1,
        "event_key": "chapter:done",
        "stage": "chapter_analysis",
        "status": "completed",
        "label": "different durable payload",
        "metadata": {},
    }
    sandbox = _GrowingSandbox(
        [
            b'{"event_key":"chapter:done","stage":"chapter_analysis",'
            b'"status":"completed","label":"replacement"}\n'
        ]
    )
    stop_event = asyncio.Event()

    collector = _collector(
        monkeypatch,
        sandbox,
        store,
        checkpoint_stop_event=stop_event,
    )

    await collector.poll_once()

    assert not stop_event.is_set()
    assert collector.checkpoint_requested is False
    assert collector.errors


@pytest.mark.asyncio
async def test_shared_workflow_wrapper_runs_collector_around_idle_stream(
    monkeypatch,
) -> None:
    lifecycle: list[str] = []

    class _Collector:
        async def start(self) -> None:
            lifecycle.append("start")

        async def stop(self) -> None:
            lifecycle.append("stop")

        def note_activity(self) -> None:
            lifecycle.append("activity")

    async def workflow():
        try:
            yield "safe-tool-event"
        finally:
            lifecycle.append("graph-closed")

    monkeypatch.setattr(
        education_structure_jobs,
        "touch_generation_attempt",
        AsyncMock(return_value=None),
    )

    events = [
        event
        async for event in education_structure_jobs.managed_generation_workflow_events(
            workflow(),
            generation_job_id=JOB_ID,
            attempt_id=ATTEMPT_ID,
            root_run_id=RUN_ID,
            progress_collector=_Collector(),
        )
    ]

    assert events == ["safe-tool-event"]
    assert lifecycle == ["start", "activity", "graph-closed", "stop"]


@pytest.mark.asyncio
async def test_shared_workflow_wrapper_stops_on_checkpoint_without_extra_event(
    monkeypatch,
) -> None:
    lifecycle: list[str] = []

    class _Collector:
        async def start(self) -> None:
            lifecycle.append("start")

        async def stop(self) -> None:
            lifecycle.append("stop")

        def note_activity(self) -> None:
            lifecycle.append("activity")

    closed = asyncio.Event()

    async def workflow():
        try:
            yield "simultaneous-event"
            await asyncio.sleep(3600)
        finally:
            lifecycle.append("graph-closed")
            closed.set()

    async def archive_checkpoint() -> None:
        assert closed.is_set()
        lifecycle.append("archive")

    checkpoint = asyncio.Event()
    checkpoint.set()
    monkeypatch.setattr(
        education_structure_jobs,
        "touch_generation_attempt",
        AsyncMock(return_value=None),
    )

    events = [
        event
        async for event in education_structure_jobs.managed_generation_workflow_events(
            workflow(),
            generation_job_id=JOB_ID,
            attempt_id=ATTEMPT_ID,
            root_run_id=RUN_ID,
            progress_collector=_Collector(),
            checkpoint_stop_event=checkpoint,
            on_checkpoint_stop=archive_checkpoint,
        )
    ]

    assert events == []
    assert lifecycle == ["start", "graph-closed", "stop", "archive"]


@pytest.mark.asyncio
async def test_checkpoint_archive_failure_clears_stop_signal(
    monkeypatch,
) -> None:
    lifecycle: list[str] = []

    class _Collector:
        async def start(self) -> None:
            lifecycle.append("start")

        async def stop(self) -> None:
            lifecycle.append("stop")

        def note_activity(self) -> None:
            lifecycle.append("activity")

    async def workflow():
        try:
            await asyncio.sleep(3600)
            if False:
                yield "unused"
        finally:
            lifecycle.append("graph-closed")

    async def archive_checkpoint() -> None:
        lifecycle.append("archive")
        raise RuntimeError("archive failed")

    checkpoint = asyncio.Event()
    checkpoint.set()
    monkeypatch.setattr(
        education_structure_jobs,
        "touch_generation_attempt",
        AsyncMock(return_value=None),
    )

    with pytest.raises(RuntimeError, match="archive failed"):
        async for _event in education_structure_jobs.managed_generation_workflow_events(
            workflow(),
            generation_job_id=JOB_ID,
            attempt_id=ATTEMPT_ID,
            root_run_id=RUN_ID,
            progress_collector=_Collector(),
            checkpoint_stop_event=checkpoint,
            on_checkpoint_stop=archive_checkpoint,
        ):
            pass

    assert not checkpoint.is_set()
    assert lifecycle == ["start", "graph-closed", "stop", "archive"]
