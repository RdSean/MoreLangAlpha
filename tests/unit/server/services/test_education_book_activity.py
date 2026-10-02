"""Bounded public activity projection and reconnect contracts."""

from __future__ import annotations

from contextlib import asynccontextmanager
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_actions_are_scoped_rate_limited_and_ignore_model_messages():
    from src.server.services.education_book_activity import BookActivityObserver

    append = AsyncMock(return_value={"outcome": "stored", "high_water_seq": 1})
    observer = BookActivityObserver(
        job_id=uuid4(),
        item_id=uuid4(),
        attempt_token=uuid4(),
        item_kind="material",
        append=append,
        publish=AsyncMock(),
        monotonic=lambda: 10.0,
    )
    for action in (
        "clarifying_concepts",
        "clarifying_concepts",
        "explaining_source_examples",
        "unknown",
        "reading_context",
        "",
    ):
        await observer(
            "artifact",
            {
                "artifact_type": "report_progress",
                "artifact_id": "material_writing",
                "status": "succeeded",
                "payload": {
                    "stage": "material_writing",
                    "action": action,
                    "message": "private",
                    "status": "failed",
                },
            },
        )
    assert [call.kwargs["message"] for call in append.await_args_list] == [
        "正在澄清概念与术语",
        "正在整理原文示例",
    ]
    assert [call.kwargs["metadata"] for call in append.await_args_list] == [
        {"stage": "material_writing", "action": "clarifying_concepts"},
        {"stage": "material_writing", "action": "explaining_source_examples"},
    ]
    assert all(call.kwargs["status"] == "running" for call in append.await_args_list)


@pytest.mark.asyncio
async def test_activity_hint_is_compact_and_contains_no_event_body(monkeypatch):
    from src.server.services import education_book_activity

    publish = AsyncMock(return_value=1)
    monkeypatch.setattr(
        education_book_activity,
        "get_cache_client",
        lambda: SimpleNamespace(
            enabled=True,
            client=SimpleNamespace(publish=publish),
        ),
    )
    job_id = uuid4()

    await education_book_activity.publish_book_activity_hint(job_id, 42)

    channel, raw_payload = publish.await_args.args
    payload = json.loads(raw_payload)
    assert channel == education_book_activity.book_activity_channel(job_id)
    assert payload == {"job_id": str(job_id), "high_water_seq": 42}
    assert len(raw_payload.encode("utf-8")) < 2 * 1024
    assert "message" not in payload
    assert "metadata" not in payload


@pytest.mark.asyncio
async def test_observer_projects_only_tool_identity_and_never_arguments_or_results():
    from src.server.services.education_book_activity import BookActivityObserver

    append = AsyncMock(
        side_effect=[
            {"outcome": "stored", "high_water_seq": 1},
            {"outcome": "stored", "high_water_seq": 2},
        ]
    )
    publish = AsyncMock()
    job_id = uuid4()
    item_id = uuid4()
    attempt_token = uuid4()
    observer = BookActivityObserver(
        job_id=job_id,
        item_id=item_id,
        attempt_token=attempt_token,
        item_kind="material",
        append=append,
        publish=publish,
    )

    await observer(
        "tool_calls",
        {
            "tool_calls": [
                {
                    "id": "call-secret",
                    "name": "Read",
                    "args": {"file_path": "inputs/source/private-answer.md"},
                }
            ]
        },
    )
    await observer(
        "tool_call_result",
        {
            "tool_call_id": "call-secret",
            "status": "success",
            "content": "the complete private source and model output",
        },
    )

    assert append.await_count == 2
    start = append.await_args_list[0].kwargs
    finish = append.await_args_list[1].kwargs
    assert start["kind"] == finish["kind"] == "tool"
    assert start["status"] == "running"
    assert finish["status"] == "succeeded"
    serialized = repr([start, finish])
    assert "private-answer" not in serialized
    assert "complete private source" not in serialized
    assert start["metadata"] == {
        "tool_call_id": "call-secret",
        "tool_name": "Read",
    }
    assert publish.await_count == 2


@pytest.mark.asyncio
async def test_observer_drops_all_raw_model_deltas_under_pressure():
    from src.server.services.education_book_activity import BookActivityObserver

    append = AsyncMock()
    observer = BookActivityObserver(
        job_id=uuid4(),
        item_id=uuid4(),
        attempt_token=uuid4(),
        item_kind="material",
        append=append,
        publish=AsyncMock(),
    )

    for index in range(150_001):
        await observer(
            "message_chunk",
            {"content": f"private reasoning delta {index}"},
        )

    append.assert_not_awaited()


@pytest.mark.asyncio
async def test_public_progress_uses_scoped_server_message_and_is_rate_limited():
    from src.server.services.education_book_activity import BookActivityObserver

    append = AsyncMock(return_value={"outcome": "stored", "high_water_seq": 1})
    clock_values = iter((10.0, 10.25, 11.01))
    observer = BookActivityObserver(
        job_id=uuid4(),
        item_id=uuid4(),
        attempt_token=uuid4(),
        item_kind="structure",
        append=append,
        publish=AsyncMock(),
        monotonic=lambda: next(clock_values),
    )
    event = {
        "artifact_type": "report_progress",
        "artifact_id": "structure_organizing",
        "status": "succeeded",
        "payload": {
            "message": "model-controlled message",
            "stage": "structure_organizing",
            "status": "failed",
        },
    }

    await observer("artifact", event)
    await observer("artifact", event)
    await observer("artifact", event)

    assert append.await_count == 2
    assert all(
        call.kwargs["message"] == "正在整理章节层级" for call in append.await_args_list
    )
    assert all(call.kwargs["status"] == "running" for call in append.await_args_list)
    assert all(
        call.kwargs["metadata"] == {"stage": "structure_organizing"}
        for call in append.await_args_list
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event",
    (
        {
            "artifact_type": "report_progress",
            "artifact_id": "structure_organizing",
            "payload": {"message": "legacy free text"},
        },
        {
            "artifact_type": "report_progress",
            "artifact_id": "material_writing",
            "payload": {"stage": "material_writing"},
        },
        {
            "artifact_type": "report_progress",
            "artifact_id": "unknown_stage",
            "payload": {"stage": "unknown_stage"},
        },
        {
            "artifact_type": "report_progress",
            "artifact_id": "custom-event-key",
            "payload": {"stage": "structure_reading"},
        },
    ),
)
async def test_public_progress_ignores_untrusted_or_cross_item_events(event):
    from src.server.services.education_book_activity import BookActivityObserver

    append = AsyncMock()
    observer = BookActivityObserver(
        job_id=uuid4(),
        item_id=uuid4(),
        attempt_token=uuid4(),
        item_kind="structure",
        append=append,
        publish=AsyncMock(),
    )

    await observer("artifact", event)

    append.assert_not_awaited()


@pytest.mark.asyncio
async def test_progress_tool_start_and_result_are_hidden_from_tool_activity():
    from src.server.services.education_book_activity import BookActivityObserver

    append = AsyncMock(
        side_effect=[
            {"outcome": "stored", "high_water_seq": 1},
            {"outcome": "stored", "high_water_seq": 2},
        ]
    )
    observer = BookActivityObserver(
        job_id=uuid4(),
        item_id=uuid4(),
        attempt_token=uuid4(),
        item_kind="material",
        append=append,
        publish=AsyncMock(),
    )

    await observer(
        "tool_calls",
        {
            "tool_calls": [
                {"id": "progress-1", "name": "report_progress"},
                {"id": "read-1", "name": "Read"},
            ]
        },
    )
    await observer(
        "tool_call_result",
        {"tool_call_id": "progress-1", "status": "success"},
    )
    await observer(
        "tool_call_result",
        {"tool_call_id": "read-1", "status": "success"},
    )

    assert [call.kwargs["message"] for call in append.await_args_list] == [
        "Running Read",
        "Finished Read",
    ]
    assert observer._tool_names == {}
    assert observer._suppressed_tool_ids == {}


@pytest.mark.asyncio
async def test_observer_stops_projecting_details_after_budget_exhaustion():
    from src.server.services.education_book_activity import BookActivityObserver

    append = AsyncMock(
        return_value={"outcome": "budget_exhausted", "high_water_seq": None}
    )
    record_drops = AsyncMock(return_value={"outcome": "stored", "high_water_seq": 2})
    publish = AsyncMock()
    observer = BookActivityObserver(
        job_id=uuid4(),
        item_id=uuid4(),
        attempt_token=uuid4(),
        item_kind="material",
        append=append,
        record_drops=record_drops,
        publish=publish,
        monotonic=lambda: 10.0,
    )

    for index in range(5_000):
        await observer(
            "tool_calls",
            {"tool_calls": [{"id": f"call-{index}", "name": "Read"}]},
        )

    append.assert_awaited_once()
    assert len(observer._tool_names) == 1
    record_drops.assert_not_awaited()

    await observer.flush()

    record_drops.assert_awaited_once_with(
        job_id=observer.job_id,
        item_id=observer.item_id,
        attempt_token=observer.attempt_token,
        dropped_count=4_999,
    )
    publish.assert_awaited_once_with(observer.job_id, 2)


@pytest.mark.asyncio
async def test_observer_stops_retrying_detail_writes_after_repository_failure():
    from src.server.services.education_book_activity import BookActivityObserver

    append = AsyncMock(side_effect=RuntimeError("activity database unavailable"))
    mark_unavailable = AsyncMock(
        return_value={"outcome": "stored", "high_water_seq": 4}
    )
    publish = AsyncMock()
    observer = BookActivityObserver(
        job_id=uuid4(),
        item_id=uuid4(),
        attempt_token=uuid4(),
        item_kind="material",
        append=append,
        mark_unavailable=mark_unavailable,
        publish=publish,
    )
    event = {"tool_calls": [{"id": "call-1", "name": "Read"}]}

    with pytest.raises(RuntimeError, match="activity database unavailable"):
        await observer("tool_calls", event)
    await observer("tool_calls", event)

    append.assert_awaited_once()
    mark_unavailable.assert_awaited_once_with(
        job_id=observer.job_id,
        item_id=observer.item_id,
        attempt_token=observer.attempt_token,
    )
    publish.assert_awaited_once_with(observer.job_id, 4)


@pytest.mark.asyncio
async def test_observer_retries_unavailable_marker_during_final_flush():
    from src.server.services.education_book_activity import BookActivityObserver

    append = AsyncMock(side_effect=RuntimeError("activity database unavailable"))
    mark_unavailable = AsyncMock(
        side_effect=[
            RuntimeError("activity status unavailable"),
            {"outcome": "stored", "high_water_seq": 4},
        ]
    )
    observer = BookActivityObserver(
        job_id=uuid4(),
        item_id=uuid4(),
        attempt_token=uuid4(),
        item_kind="material",
        append=append,
        mark_unavailable=mark_unavailable,
        publish=AsyncMock(),
    )

    with pytest.raises(RuntimeError, match="activity database unavailable"):
        await observer("tool_calls", {"tool_calls": [{"id": "call-1", "name": "Read"}]})
    await observer.flush()

    assert mark_unavailable.await_count == 2


@pytest.mark.asyncio
async def test_budget_exhaustion_counts_remaining_calls_in_the_same_event():
    from src.server.services.education_book_activity import BookActivityObserver

    append = AsyncMock(
        return_value={"outcome": "budget_exhausted", "high_water_seq": 1}
    )
    record_drops = AsyncMock(return_value={"outcome": "stored", "high_water_seq": 2})
    observer = BookActivityObserver(
        job_id=uuid4(),
        item_id=uuid4(),
        attempt_token=uuid4(),
        item_kind="material",
        append=append,
        record_drops=record_drops,
        publish=AsyncMock(),
        monotonic=lambda: 10.0,
    )

    await observer(
        "tool_calls",
        {
            "tool_calls": [
                {"id": "call-1", "name": "Read"},
                {"id": "call-2", "name": "Bash"},
                {"id": "call-3", "name": "ExecuteCode"},
            ]
        },
    )
    await observer.flush()

    append.assert_awaited_once()
    assert record_drops.await_args.kwargs["dropped_count"] == 2


@pytest.mark.asyncio
async def test_budget_exhaustion_filters_progress_noise_and_invalid_stages():
    from src.server.services.education_book_activity import BookActivityObserver

    append = AsyncMock(
        return_value={"outcome": "budget_exhausted", "high_water_seq": 1}
    )
    record_drops = AsyncMock(return_value={"outcome": "stored", "high_water_seq": 2})
    observer = BookActivityObserver(
        job_id=uuid4(),
        item_id=uuid4(),
        attempt_token=uuid4(),
        item_kind="structure",
        append=append,
        record_drops=record_drops,
        publish=AsyncMock(),
        monotonic=lambda: 10.0,
    )

    await observer("tool_calls", {"tool_calls": [{"id": "read-1", "name": "Read"}]})
    await observer(
        "tool_calls",
        {"tool_calls": [{"id": "progress-1", "name": "report_progress"}]},
    )
    await observer(
        "artifact",
        {
            "artifact_type": "report_progress",
            "artifact_id": "structure_reading",
            "payload": {"stage": "structure_reading"},
        },
    )
    await observer(
        "artifact",
        {
            "artifact_type": "report_progress",
            "artifact_id": "material_writing",
            "payload": {"stage": "material_writing"},
        },
    )
    await observer(
        "artifact",
        {
            "artifact_type": "report_progress",
            "artifact_id": "structure_reading",
            "payload": {"stage": "structure_reading"},
        },
    )
    await observer(
        "tool_call_result",
        {"tool_call_id": "progress-1", "status": "success"},
    )
    await observer.flush()

    record_drops.assert_awaited_once_with(
        job_id=observer.job_id,
        item_id=observer.item_id,
        attempt_token=observer.attempt_token,
        dropped_count=1,
    )


@pytest.mark.asyncio
async def test_tool_budget_only_disables_tools_and_preserves_actions():
    from src.server.services.education_book_activity import BookActivityObserver

    append = AsyncMock(
        side_effect=[
            {"outcome": "tool_budget_exhausted", "high_water_seq": 1},
            {"outcome": "stored", "high_water_seq": 2},
        ]
    )
    record_drops = AsyncMock(return_value={"outcome": "stored", "high_water_seq": 3})
    observer = BookActivityObserver(
        job_id=uuid4(),
        item_id=uuid4(),
        attempt_token=uuid4(),
        item_kind="material",
        append=append,
        record_drops=record_drops,
        publish=AsyncMock(),
        monotonic=lambda: 10.0,
    )
    await observer(
        "tool_calls",
        {
            "tool_calls": [
                {"id": "read", "name": "Read"},
                {"id": "bash", "name": "Bash"},
                {"id": "progress", "name": "report_progress"},
            ]
        },
    )
    for call_id in ("read", "bash", "progress"):
        await observer(
            "tool_call_result", {"tool_call_id": call_id, "status": "success"}
        )
    await observer(
        "artifact",
        {
            "artifact_type": "report_progress",
            "artifact_id": "material_writing",
            "payload": {"stage": "material_writing", "action": "clarifying_concepts"},
        },
    )
    await observer.flush()
    assert [call.kwargs["kind"] for call in append.await_args_list] == [
        "tool",
        "progress",
    ]
    assert record_drops.await_args.kwargs["dropped_count"] == 3
    assert observer._tool_names == {}
    assert observer._suppressed_tool_ids == {}


class _PageRepository:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    async def get_book_activity_page(self, **kwargs):
        self.calls.append(kwargs)
        if len(self.pages) == 1:
            return self.pages[0]
        return self.pages.pop(0)


def _page(*, seqs: list[int], high_water: int, status: str):
    return {
        "job_id": str(uuid4()),
        "status": status,
        "activity_status": "available",
        "events": [{"seq": seq} for seq in seqs],
        "high_water_seq": high_water,
        "cursor_expired": False,
        "has_more": False,
    }


@pytest.mark.asyncio
async def test_stream_subscribes_then_rereads_pg_to_close_notification_race():
    from src.server.services.education_book_activity import BookActivityService

    initial = _page(seqs=[1], high_water=1, status="running")
    caught_up = {
        **_page(seqs=[2], high_water=2, status="succeeded"),
        "job_id": initial["job_id"],
    }
    repository = _PageRepository([initial, caught_up])

    @asynccontextmanager
    async def subscribe(_channel):
        async def wait(_timeout):
            return ("timeout", None)

        yield wait

    service = BookActivityService(repository=repository, subscribe=subscribe)

    pages = [
        page
        async for page in service.pages(
            job_id=initial["job_id"],
            parent_user_id="parent-1",
            after_seq=0,
        )
    ]

    assert [[event["seq"] for event in page["events"]] for page in pages] == [
        [1],
        [2],
    ]
    assert repository.calls[1]["after_seq"] == 1


@pytest.mark.asyncio
async def test_stream_drains_snapshot_pages_before_waiting_for_redis():
    from src.server.services.education_book_activity import BookActivityService

    initial = {
        **_page(seqs=list(range(1, 201)), high_water=500, status="running"),
        "has_more": True,
    }
    middle = {
        **_page(seqs=list(range(201, 401)), high_water=500, status="running"),
        "job_id": initial["job_id"],
        "has_more": True,
    }
    terminal = {
        **_page(seqs=list(range(401, 501)), high_water=500, status="succeeded"),
        "job_id": initial["job_id"],
    }
    repository = _PageRepository([initial, middle, terminal])
    wait_calls = 0

    @asynccontextmanager
    async def subscribe(_channel):
        async def wait(_timeout):
            nonlocal wait_calls
            wait_calls += 1
            return ("timeout", None)

        yield wait

    service = BookActivityService(repository=repository, subscribe=subscribe)

    pages = [
        page
        async for page in service.pages(
            job_id=initial["job_id"],
            parent_user_id="parent-1",
            after_seq=0,
        )
    ]

    assert [len(page["events"]) for page in pages] == [200, 200, 100]
    assert [call["after_seq"] for call in repository.calls] == [0, 200, 400]
    assert wait_calls == 0


@pytest.mark.asyncio
async def test_stream_recovers_from_redis_unavailable_using_pg_reread():
    from src.server.services.education_book_activity import BookActivityService

    initial = _page(seqs=[], high_water=0, status="running")
    terminal = {
        **_page(seqs=[1, 2], high_water=2, status="failed"),
        "job_id": initial["job_id"],
    }
    repository = _PageRepository([initial, terminal])

    @asynccontextmanager
    async def unavailable(_channel):
        yield None

    service = BookActivityService(repository=repository, subscribe=unavailable)

    pages = [
        page
        async for page in service.pages(
            job_id=initial["job_id"],
            parent_user_id="parent-1",
            after_seq=0,
        )
    ]

    assert pages[-1]["status"] == "failed"
    assert [event["seq"] for event in pages[-1]["events"]] == [1, 2]


@pytest.mark.asyncio
async def test_stream_yields_activity_availability_change_without_a_new_event():
    from src.server.services.education_book_activity import BookActivityService

    initial = _page(seqs=[], high_water=0, status="running")
    unavailable = {
        **initial,
        "activity_status": "unavailable",
    }
    terminal = {
        **unavailable,
        "status": "failed",
    }
    repository = _PageRepository([initial, unavailable, terminal])

    @asynccontextmanager
    async def subscribe(_channel):
        async def wait(_timeout):
            return ("hint", None)

        yield wait

    service = BookActivityService(repository=repository, subscribe=subscribe)
    pages = [
        page
        async for page in service.pages(
            job_id=initial["job_id"],
            parent_user_id="parent-1",
            after_seq=0,
        )
    ]

    assert [page["activity_status"] for page in pages] == [
        "available",
        "unavailable",
        "unavailable",
    ]
