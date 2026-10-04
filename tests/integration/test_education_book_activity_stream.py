"""PostgreSQL authority and activity-budget integration coverage."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.server.services.education_book_structure import MoreToSkillsIdentity


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

IDENTITY = MoreToSkillsIdentity(
    version="2.1.0",
    skill_sha256="b" * 64,
    schema_sha256="c" * 64,
)


async def _seed_running_item(connection_factory, *, parent_user_id: str) -> dict:
    from src.server.database.education_book_jobs import claim_next_book_item
    from src.server.database.education_books import create_textbook_with_initial_job

    household_id = uuid4()
    textbook_id = uuid4()
    prefix = f"education/{household_id}/textbooks/{textbook_id}/source/"
    async with connection_factory() as conn, conn.transaction():
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO education_households (
                    household_id, name, model_owner_user_id
                ) VALUES (%s, 'Activity household', %s)
                """,
                (household_id, parent_user_id),
            )
            await cur.execute(
                """
                INSERT INTO education_memberships (
                    household_id, user_id, role, display_name
                ) VALUES (%s, %s, 'parent', 'Parent')
                """,
                (household_id, parent_user_id),
            )
    created = await create_textbook_with_initial_job(
        textbook_id=textbook_id,
        parent_user_id=parent_user_id,
        household_id=str(household_id),
        title="Activity Book",
        slug=f"activity-{uuid4().hex}",
        source={
            "document_id": f"doc-{uuid4().hex}",
            "parse_job_id": f"parse-{uuid4().hex}",
            "primary_artifact_id": f"artifact-{uuid4().hex}",
            "filename": "book.pdf",
            "media_type": "application/pdf",
            "format": "pdf",
            "parser_id": "datalab",
            "parser_name": "Datalab",
            "parser_version": "2",
            "parse_completed_at": "2026-10-02T00:00:00+09:00",
            "content_sha256": "a" * 64,
            "size_bytes": 128,
            "snapshot_prefix": prefix,
            "markdown_key": f"{prefix}artifacts/document.md",
            "blocks_key": f"{prefix}artifacts/blocks.json",
            "report_key": f"{prefix}artifacts/report.json",
            "asset_manifest": [],
            "snapshot": {"format": "langalpha-textbook-source-snapshot/v2"},
        },
        idempotency_key="activity-structure",
        identity=IDENTITY,
    )
    claimed = await claim_next_book_item(worker_id="activity-worker", lease_seconds=60)
    assert claimed is not None
    return {**created, **claimed, "household_id": household_id}


async def test_parent_authorized_job_snapshot_projects_only_public_fields(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.app.education.book_models import (
        BookJobItemResponse,
        BookJobResponse,
    )
    from src.server.database.education_book_jobs import get_book_job_for_parent

    item = await _seed_running_item(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
    )

    snapshot = await get_book_job_for_parent(
        job_id=item["job_id"],
        parent_user_id=seed_user["user_id"],
    )
    denied = await get_book_job_for_parent(
        job_id=item["job_id"],
        parent_user_id="other-parent",
    )

    assert snapshot is not None
    public = BookJobResponse.model_validate(snapshot)
    assert public.job_id == str(item["job_id"])
    assert len(public.items) == 1
    assert public.items[0].kind == "structure"
    assert denied is None
    assert set(snapshot) == set(BookJobResponse.model_fields)
    assert set(snapshot["items"][0]) == set(BookJobItemResponse.model_fields)


async def test_parent_authorized_job_snapshot_is_consistent_during_finalize(
    patched_get_db_connection,
    seed_user,
    test_db_uri,
    monkeypatch,
) -> None:
    import psycopg

    from src.server.database import education_book_jobs as book_job_repository

    item = await _seed_running_item(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
    )
    read_started = asyncio.Event()
    update_done = asyncio.Event()
    interleaved = False

    class CursorProxy:
        def __init__(self, cursor_context):
            self._cursor_context = cursor_context
            self._cursor = None
            self._sql = ""

        async def __aenter__(self):
            self._cursor = await self._cursor_context.__aenter__()
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return await self._cursor_context.__aexit__(exc_type, exc, traceback)

        async def execute(self, sql, params=None):
            self._sql = sql
            return await self._cursor.execute(sql, params)

        async def fetchone(self):
            nonlocal interleaved
            row = await self._cursor.fetchone()
            if not interleaved and "SELECT jobs.job_id" in self._sql:
                interleaved = True
                read_started.set()
                await update_done.wait()
            return row

        async def fetchall(self):
            return await self._cursor.fetchall()

    class ConnectionProxy:
        def __init__(self, connection):
            self._connection = connection

        def cursor(self, *args, **kwargs):
            return CursorProxy(self._connection.cursor(*args, **kwargs))

        def __getattr__(self, name):
            return getattr(self._connection, name)

    @asynccontextmanager
    async def interleaved_connection():
        async with patched_get_db_connection() as connection:
            yield ConnectionProxy(connection)

    async def finalize_between_reads() -> None:
        await read_started.wait()
        try:
            async with await psycopg.AsyncConnection.connect(test_db_uri) as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        UPDATE education_book_job_items
                        SET status = 'succeeded', finished_at = NOW(), updated_at = NOW()
                        WHERE item_id = %s
                        """,
                        (item["item_id"],),
                    )
                    await cur.execute(
                        """
                        UPDATE education_book_jobs
                        SET status = 'succeeded', succeeded_items = 1,
                            finished_at = NOW(), updated_at = NOW()
                        WHERE job_id = %s
                        """,
                        (item["job_id"],),
                    )
                await conn.commit()
        finally:
            update_done.set()

    monkeypatch.setattr(
        book_job_repository,
        "get_db_connection",
        interleaved_connection,
    )
    finalizer = asyncio.create_task(finalize_between_reads())

    snapshot = await book_job_repository.get_book_job_for_parent(
        job_id=item["job_id"],
        parent_user_id=seed_user["user_id"],
    )
    await finalizer

    assert snapshot is not None
    assert (snapshot["status"], snapshot["items"][0]["status"]) in {
        ("running", "running"),
        ("succeeded", "succeeded"),
    }
    timing = snapshot["items"][0]["timing_summary"]
    assert (timing["terminal_at"] is None) == (snapshot["items"][0]["status"] == "running")


async def test_detail_budget_bounds_rows_bytes_and_keeps_terminal_events(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_activity import (
        append_book_activity_event,
        get_book_activity_page,
    )
    from src.server.database.education_book_jobs import fail_book_item

    item = await _seed_running_item(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
    )
    for index in range(1_100):
        await append_book_activity_event(
            job_id=item["job_id"],
            item_id=item["item_id"],
            attempt_token=item["attempt_token"],
            dedupe_key=f"detail:{index}",
            kind="tool",
            status="running",
            message="Reading source " + ("界" * 480),
            metadata={"tool_name": "Read", "tool_call_id": str(index)},
        )
    await fail_book_item(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        safe_error="Generated output was invalid",
        stop_remaining=False,
    )

    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT
                    count(*) FILTER (
                        WHERE metadata->>'budget_class' = 'detail'
                    ) AS detail_count,
                    coalesce(sum(
                        CASE WHEN metadata->>'budget_class' = 'detail'
                        THEN (metadata->>'activity_bytes')::int ELSE 0 END
                    ), 0) AS detail_bytes,
                    count(*) FILTER (
                        WHERE metadata->>'budget_class' = 'summary'
                    ) AS summary_count,
                    count(*) FILTER (
                        WHERE metadata->>'budget_class' = 'terminal'
                    ) AS terminal_count
                FROM education_book_activity_events
                WHERE job_id = %s
                """,
                (item["job_id"],),
            )
            counts = await cur.fetchone()

    assert counts["detail_count"] <= 1_000
    assert counts["detail_bytes"] <= 1024 * 1024
    assert counts["summary_count"] == 1
    assert counts["terminal_count"] == 2

    page = await get_book_activity_page(
        job_id=item["job_id"],
        parent_user_id=seed_user["user_id"],
        after_seq=0,
        limit=2_100,
    )
    assert page is not None
    assert page["status"] == "failed"
    assert page["high_water_seq"] == max(event["seq"] for event in page["events"])
    assert page["cursor_expired"] is False
    assert [(event["kind"], event["status"]) for event in page["events"][-2:]] == [
        ("item", "failed"),
        ("job", "failed"),
    ]


@pytest.mark.parametrize("message", ("Reading source", "Reading source " + "界" * 480))
async def test_tool_sub_budget_preserves_semantics_across_observers(
    patched_get_db_connection,
    seed_user,
    message,
):
    from src.server.database.education_book_activity import (
        append_book_activity_event,
        get_book_activity_page,
    )
    from src.server.services.education_book_activity import BookActivityObserver

    item = await _seed_running_item(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )

    async def append(index):
        return await append_book_activity_event(
            job_id=item["job_id"],
            item_id=item["item_id"],
            attempt_token=item["attempt_token"],
            dedupe_key=f"tool:{index}",
            kind="tool",
            status="running",
            message=message,
            metadata={"tool_name": "Read", "tool_call_id": str(index)},
        )

    results = []
    for start in range(0, 810, 10):
        results.extend(
            await asyncio.gather(*(append(index) for index in range(start, start + 10)))
        )
    assert any(result["outcome"] == "tool_budget_exhausted" for result in results)
    assert all(
        result["outcome"] in {"stored", "tool_budget_exhausted"} for result in results
    )
    for _ in range(2):
        observer = BookActivityObserver(
            job_id=item["job_id"],
            item_id=item["item_id"],
            attempt_token=item["attempt_token"],
            item_kind="structure",
            publish=AsyncMock(),
        )
        await observer(
            "tool_calls", {"tool_calls": [{"id": f"late-{uuid4()}", "name": "Bash"}]}
        )
        await observer(
            "artifact",
            {
                "artifact_type": "report_progress",
                "artifact_id": "structure_reading",
                "payload": {"stage": "structure_reading"},
            },
        )
    page = await get_book_activity_page(
        job_id=item["job_id"],
        parent_user_id=seed_user["user_id"],
        after_seq=0,
        limit=2100,
    )
    tools = [event for event in page["events"] if event["kind"] == "tool"]
    progress = [event for event in page["events"] if event["kind"] == "progress"]
    assert len(tools) <= 800
    async with patched_get_db_connection() as conn, conn.cursor() as cur:
        await cur.execute(
            "SELECT sum((metadata->>'activity_bytes')::int) AS bytes FROM education_book_activity_events WHERE job_id = %s AND kind = 'tool'",
            (item["job_id"],),
        )
        assert (await cur.fetchone())["bytes"] <= 768 * 1024
    assert len(progress) >= 1
    assert len([event for event in page["events"] if event["kind"] == "summary"]) == 1


async def test_activity_page_detects_future_cursor_and_parent_scope(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_activity import get_book_activity_page

    item = await _seed_running_item(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
    )

    future = await get_book_activity_page(
        job_id=item["job_id"],
        parent_user_id=seed_user["user_id"],
        after_seq=99,
        limit=100,
    )
    denied = await get_book_activity_page(
        job_id=item["job_id"],
        parent_user_id="other-parent",
        after_seq=0,
        limit=100,
    )

    assert future is not None
    assert future["cursor_expired"] is True
    assert denied is None


async def test_activity_page_exposes_durable_unavailable_status(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_activity import (
        get_book_activity_page,
        mark_book_activity_unavailable,
    )

    item = await _seed_running_item(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
    )

    result = await mark_book_activity_unavailable(
        job_id=item["job_id"],
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
    )
    page = await get_book_activity_page(
        job_id=item["job_id"],
        parent_user_id=seed_user["user_id"],
        after_seq=0,
        limit=100,
    )

    assert result == {"outcome": "stored", "high_water_seq": 0}
    assert page is not None
    assert page["activity_status"] == "unavailable"
    assert page["events"] == []


async def test_scoped_progress_persists_server_message_and_replays_by_seq(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.app.education.book_models import BookActivityPageResponse
    from src.server.database.education_book_activity import get_book_activity_page
    from src.server.services.education_book_activity import BookActivityObserver

    item = await _seed_running_item(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
    )
    observer = BookActivityObserver(
        job_id=item["job_id"],
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        item_kind="structure",
        publish=AsyncMock(),
        monotonic=lambda: 10.0,
    )

    await observer(
        "artifact",
        {
            "artifact_type": "report_progress",
            "artifact_id": "structure_organizing",
            "status": "succeeded",
            "payload": {
                "stage": "structure_organizing",
                "message": "untrusted model text",
            },
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

    page = await get_book_activity_page(
        job_id=item["job_id"],
        parent_user_id=seed_user["user_id"],
        after_seq=0,
        limit=100,
    )
    assert page is not None
    public = BookActivityPageResponse.model_validate(page)
    assert public.job_id == str(item["job_id"])
    assert public.events[0].job_id == str(item["job_id"])
    assert len(page["events"]) == 1
    event = page["events"][0]
    assert event["kind"] == "progress"
    assert event["status"] == "running"
    assert event["message"] == "正在整理章节层级"
    assert event["metadata"] == {"stage": "structure_organizing"}
    assert page["high_water_seq"] == event["seq"]

    caught_up = await get_book_activity_page(
        job_id=item["job_id"],
        parent_user_id=seed_user["user_id"],
        after_seq=event["seq"],
        limit=100,
    )
    assert caught_up is not None
    assert caught_up["events"] == []
    assert caught_up["high_water_seq"] == event["seq"]


async def test_event_size_limit_counts_the_complete_public_envelope(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_activity import append_book_activity_event

    item = await _seed_running_item(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
    )

    with pytest.raises(ValueError, match="serialized size limit"):
        await append_book_activity_event(
            job_id=item["job_id"],
            item_id=item["item_id"],
            attempt_token=item["attempt_token"],
            dedupe_key="oversized-envelope",
            kind="progress",
            status="running",
            message="m" * 512,
            metadata={"stage": "s" * 1_400},
        )


async def test_budget_summary_coalesces_dropped_updates_for_one_second(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_activity import get_book_activity_page
    from src.server.services.education_book_activity import BookActivityObserver

    item = await _seed_running_item(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
    )
    async with patched_get_db_connection() as conn, conn.transaction():
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO education_book_activity_events (
                    job_id, seq, dedupe_key, item_id, kind, status,
                    message, metadata
                )
                SELECT %s, value, 'seed:' || value, %s,
                       'tool', 'running', 'seed',
                       '{"budget_class":"detail","activity_bytes":256}'::jsonb
                FROM generate_series(1, 1000) AS value
                """,
                (item["job_id"], item["item_id"]),
            )
            await cur.execute(
                """
                UPDATE education_book_jobs SET high_water_seq = 1000
                WHERE job_id = %s
                """,
                (item["job_id"],),
            )

    observer = BookActivityObserver(
        job_id=item["job_id"],
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        item_kind="structure",
        publish=AsyncMock(),
        monotonic=lambda: 10.0,
    )
    for index in range(2):
        await observer(
            "tool_calls",
            {"tool_calls": [{"id": f"overflow-{index}", "name": "Read"}]},
        )

    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT seq, (metadata->>'dropped_count')::int AS dropped_count
                FROM education_book_activity_events
                WHERE job_id = %s AND dedupe_key = 'activity-detail-budget'
                """,
                (item["job_id"],),
            )
            summary = await cur.fetchone()

    assert summary["dropped_count"] == 1
    first_summary_seq = summary["seq"]

    await observer.flush()

    page = await get_book_activity_page(
        job_id=item["job_id"],
        parent_user_id=seed_user["user_id"],
        after_seq=first_summary_seq,
        limit=100,
    )
    assert page is not None
    assert len(page["events"]) == 1
    assert page["events"][0]["kind"] == "summary"
    assert page["events"][0]["metadata"]["dropped_count"] == 2
    assert page["events"][0]["seq"] == page["high_water_seq"]


async def test_cancel_records_one_terminal_event_for_item_and_job(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_jobs import mark_book_job_cancelled

    item = await _seed_running_item(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
    )

    cancelled = await mark_book_job_cancelled(
        job_id=item["job_id"],
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
    )

    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT kind, status, metadata->>'budget_class' AS budget_class
                FROM education_book_activity_events
                WHERE job_id = %s ORDER BY seq
                """,
                (item["job_id"],),
            )
            events = await cur.fetchall()

    assert cancelled["status"] == "cancelled"
    assert [
        (event["kind"], event["status"], event["budget_class"]) for event in events
    ] == [
        ("item", "cancelled", "terminal"),
        ("job", "cancelled", "terminal"),
    ]


async def test_long_business_error_cannot_rollback_terminal_state(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_activity import get_book_activity_page
    from src.server.database.education_book_jobs import fail_book_item

    item = await _seed_running_item(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
    )

    failed = await fail_book_item(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        safe_error="x" * 513,
        stop_remaining=False,
    )
    page = await get_book_activity_page(
        job_id=item["job_id"],
        parent_user_id=seed_user["user_id"],
        after_seq=0,
        limit=100,
    )

    assert failed["status"] == "failed"
    assert page is not None
    assert len(page["events"][0]["message"]) == 512
    assert page["events"][0]["status"] == "failed"
