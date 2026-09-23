"""End-to-end contracts for live unified book-processing progress."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock
from uuid import uuid4

import psycopg
import pytest

from src.server.database import education_tasks, education_textbooks
from src.server.database.conversation.threads_write import create_thread
from src.server.database.workspace import create_workspace
from src.server.services import education_book_pipeline_jobs
from src.server.services import education_structure_jobs
from src.server.services.education_progress_collector import ManagedProgressCollector
from src.server.services.education_structure_progress import (
    get_book_pipeline_progress_for_parent,
)
from src.server.services.runs.sse_producer import RunSSEProducer


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


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


def _test_connection(conn: psycopg.AsyncConnection):
    @asynccontextmanager
    async def _connect():
        yield conn

    return _connect


async def _seed_running_pipeline(
    db_conn: psycopg.AsyncConnection,
    *,
    pause_after_chapter_analysis: bool = False,
) -> tuple[str, str, str, str]:
    parent_user_id = f"progress-parent-{uuid4()}"
    household_id = str(uuid4())
    textbook_id = str(uuid4())
    version_id = str(uuid4())
    generation_job_id = str(uuid4())
    attempt_id = str(uuid4())
    run_id = str(uuid4())
    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO users (user_id, name) VALUES (%s, %s)",
                (parent_user_id, "Progress parent"),
            )
            await cur.execute(
                """
                INSERT INTO education_households (
                    household_id, name, model_owner_user_id
                ) VALUES (%s, %s, %s)
                """,
                (household_id, "Progress household", parent_user_id),
            )
            await cur.execute(
                """
                INSERT INTO education_memberships (
                    household_id, user_id, role, display_name
                ) VALUES (%s, %s, 'parent', %s)
                """,
                (household_id, parent_user_id, "Progress parent"),
            )
            await cur.execute(
                """
                INSERT INTO education_textbooks (
                    textbook_id, household_id, title, slug, created_by_user_id
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    textbook_id,
                    household_id,
                    "Progress textbook",
                    f"progress-{uuid4().hex}",
                    parent_user_id,
                ),
            )
            await cur.execute(
                """
                INSERT INTO education_textbook_versions (
                    version_id, textbook_id, sequence, status, created_by_user_id
                ) VALUES (%s, %s, 1, 'review', %s)
                """,
                (version_id, textbook_id, parent_user_id),
            )
        workspace = await create_workspace(
            user_id=parent_user_id,
            name=f"Progress workspace {uuid4()}",
            status="running",
            conn=db_conn,
        )
        thread = await create_thread(
            conversation_thread_id=str(uuid4()),
            workspace_id=str(workspace["workspace_id"]),
            current_status="completed",
            msg_type="ptc",
            conn=db_conn,
        )
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO conversation_responses (
                    conversation_response_id, conversation_thread_id,
                    turn_index, status, created_at
                ) VALUES (%s, %s, 1, 'in_progress', NOW())
                """,
                (run_id, thread["conversation_thread_id"]),
            )
            await cur.execute(
                """
                INSERT INTO education_generation_jobs (
                    generation_job_id, version_id, scope, status,
                    attempt_count, processing_profile_sha256,
                    pause_after_chapter_analysis
                ) VALUES (%s, %s, 'book_pipeline', 'running', 1, %s, %s)
                """,
                (
                    generation_job_id,
                    version_id,
                    "b" * 64,
                    pause_after_chapter_analysis,
                ),
            )
            await cur.execute(
                """
                INSERT INTO education_generation_attempts (
                    attempt_id, generation_job_id, managed_workspace_id,
                    managed_thread_id, status, root_run_id
                ) VALUES (%s, %s, %s, %s, 'running', %s)
                """,
                (
                    attempt_id,
                    generation_job_id,
                    workspace["workspace_id"],
                    thread["conversation_thread_id"],
                    run_id,
                ),
            )
            await cur.execute(
                """
                UPDATE education_generation_jobs
                SET latest_attempt_id = %s
                WHERE generation_job_id = %s
                """,
                (attempt_id, generation_job_id),
            )
    return parent_user_id, generation_job_id, attempt_id, run_id


@pytest.mark.asyncio
async def test_live_pipeline_progress_is_durable_before_run_completion(
    cleanup_tables,
    db_conn,
    test_db_uri,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        parent_user_id,
        generation_job_id,
        attempt_id,
        run_id,
    ) = await _seed_running_pipeline(db_conn)
    test_connection = _test_connection(db_conn)
    monkeypatch.setattr(
        education_textbooks,
        "get_db_connection",
        test_connection,
    )
    monkeypatch.setattr(
        education_tasks,
        "get_db_connection",
        test_connection,
    )
    chapter_running = (
        b'{"event_key":"chapter_analysis:running:chapter","stage":"chapter_analysis",'
        b'"status":"running","label":"chapter structure identified"}\n'
    )
    remaining = (
        chapter_running
        + b'{"event_key":"chapter_analysis:completed:chapter","stage":"chapter_analysis",'
        b'"status":"completed","label":"chapter analysis complete"}\n'
        + b'{"event_key":"content_processing:running:content","stage":"content_processing",'
        b'"status":"running","label":"processing content tree"}\n'
        + b'{"event_key":"knowledge_point_generation:completed:knowledge",'
        b'"stage":"knowledge_point_generation","status":"completed",'
        b'"label":"knowledge candidates complete","total_value":22}\n'
    )
    sandbox = _GrowingSandbox([chapter_running, remaining])
    collector = ManagedProgressCollector(
        sandbox=sandbox,
        generation_job_id=generation_job_id,
        attempt_id=attempt_id,
        run_id=run_id,
        poll_interval=0.01,
    )

    await collector.poll_once()
    assert collector.errors == []
    async with await psycopg.AsyncConnection.connect(
        test_db_uri,
        autocommit=True,
        row_factory=psycopg.rows.dict_row,
    ) as readback_conn:
        async with readback_conn.cursor() as cur:
            await cur.execute(
                """
                SELECT event_key, stage, status
                FROM education_generation_progress_events
                WHERE generation_job_id = %s
                """,
                (generation_job_id,),
            )
            assert await cur.fetchall() == [
                {
                    "event_key": "chapter_analysis:running:chapter",
                    "stage": "chapter_analysis",
                    "status": "running",
                }
            ]
            await cur.execute(
                """
                SELECT status FROM education_generation_jobs
                WHERE generation_job_id = %s
                """,
                (generation_job_id,),
            )
            assert (await cur.fetchone())["status"] == "running"

    await collector.poll_once()
    assert collector.errors == []
    projection = await get_book_pipeline_progress_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    assert [stage["name"] for stage in projection["stages"]] == [
        "chapter_analysis",
        "content_processing",
        "knowledge_point_generation",
        "lesson_preparation",
    ]
    observed_stages = [
        stage["name"] for stage in projection["stages"] if stage["events"]
    ]
    assert observed_stages == [
        "chapter_analysis",
        "content_processing",
        "knowledge_point_generation",
    ]
    statuses = {stage["name"]: stage["status"] for stage in projection["stages"]}
    assert statuses == {
        "chapter_analysis": "completed",
        "content_processing": "running",
        "knowledge_point_generation": "completed",
        "lesson_preparation": "queued",
    }


@pytest.mark.asyncio
async def test_compact_replay_pressure_keeps_semantic_progress_durable(
    cleanup_tables,
    db_conn,
    test_db_uri,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _parent_user_id,
        generation_job_id,
        attempt_id,
        run_id,
    ) = await _seed_running_pipeline(db_conn)
    test_connection = _test_connection(db_conn)
    monkeypatch.setattr(
        education_textbooks,
        "get_db_connection",
        test_connection,
    )
    monkeypatch.setattr(
        education_tasks,
        "get_db_connection",
        test_connection,
    )

    producer = RunSSEProducer(
        thread_id="pressure-thread",
        run_id=run_id,
        replay_profile="education_compact",
    )
    emitted_replay_events = 0
    for index in range(150_001):
        emitted_replay_events += bool(
            producer._format_sse_event(
                "message_chunk",
                {
                    "thread_id": "pressure-thread",
                    "agent": "main",
                    "id": "message-1",
                    "content": str(index),
                },
            )
        )
    emitted_replay_events += bool(
        producer._format_sse_event(
            "metadata",
            {"thread_id": "pressure-thread", "run_id": run_id},
        )
    )
    stored_sse_events = len(producer.get_sse_events() or [])

    sandbox = _GrowingSandbox(
        [
            (
                b'{"event_key":"chapter_analysis:running:pressure",'
                b'"stage":"chapter_analysis","status":"running"}\n'
            )
        ]
    )
    collector = ManagedProgressCollector(
        sandbox=sandbox,
        generation_job_id=generation_job_id,
        attempt_id=attempt_id,
        run_id=run_id,
        poll_interval=0.01,
    )
    await collector.poll_once()

    async with await psycopg.AsyncConnection.connect(
        test_db_uri,
        autocommit=True,
        row_factory=psycopg.rows.dict_row,
    ) as readback_conn:
        async with readback_conn.cursor() as cur:
            await cur.execute(
                """
                SELECT COUNT(*) AS count
                FROM education_generation_progress_events
                WHERE generation_job_id = %s
                """,
                (generation_job_id,),
            )
            progress_rows_written = int((await cur.fetchone())["count"])

    assert emitted_replay_events < 1_000
    assert stored_sse_events < 1_000
    assert progress_rows_written > 0


@pytest.mark.asyncio
async def test_checkpoint_stops_before_archive_and_continuation_prompt_contract(
    cleanup_tables,
    db_conn,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        parent_user_id,
        generation_job_id,
        attempt_id,
        run_id,
    ) = await _seed_running_pipeline(
        db_conn,
        pause_after_chapter_analysis=True,
    )
    test_connection = _test_connection(db_conn)
    monkeypatch.setattr(
        education_textbooks,
        "get_db_connection",
        test_connection,
    )
    monkeypatch.setattr(
        education_tasks,
        "get_db_connection",
        test_connection,
    )
    payload = (
        b'{"event_key":"chapter_analysis:completed:chapter","stage":"chapter_analysis",'
        b'"status":"completed","label":"chapter analysis complete"}\n'
    )
    sandbox = _GrowingSandbox([payload])
    checkpoint_stop_event = asyncio.Event()
    workflow_closed = asyncio.Event()
    lifecycle: list[str] = []
    checkpoint_prefix = (
        "education/progress-household/progress-textbook/v1/"
        f"book-pipeline-checkpoints/{generation_job_id}/{attempt_id}"
    )

    async def workflow():
        try:
            yield "safe-managed-event"
            await asyncio.sleep(3600)
        finally:
            lifecycle.append("graph_closed")
            workflow_closed.set()

    async def archive_checkpoint() -> None:
        assert workflow_closed.is_set()
        lifecycle.append("archive")
        await education_book_pipeline_jobs.pause_book_pipeline_after_chapter_analysis(
            job={
                "generation_job_id": generation_job_id,
                "parent_user_id": parent_user_id,
            },
            attempt_id=attempt_id,
            checkpoint_bundle_prefix=checkpoint_prefix,
        )

    collector = ManagedProgressCollector(
        sandbox=sandbox,
        generation_job_id=generation_job_id,
        attempt_id=attempt_id,
        run_id=run_id,
        poll_interval=0.01,
        checkpoint_stop_event=checkpoint_stop_event,
    )
    monkeypatch.setattr(
        education_structure_jobs,
        "touch_generation_attempt",
        AsyncMock(return_value=None),
    )
    events = [
        event
        async for event in education_structure_jobs.managed_generation_workflow_events(
            workflow(),
            generation_job_id=generation_job_id,
            attempt_id=attempt_id,
            root_run_id=run_id,
            progress_collector=collector,
            checkpoint_stop_event=checkpoint_stop_event,
            on_checkpoint_stop=archive_checkpoint,
        )
    ]

    assert events == ["safe-managed-event"]
    assert checkpoint_stop_event.is_set()
    assert collector.checkpoint_requested is True
    assert lifecycle == ["graph_closed", "archive"]
    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT status, checkpoint_bundle_prefix
            FROM education_generation_jobs
            WHERE generation_job_id = %s
            """,
            (generation_job_id,),
        )
        assert await cur.fetchone() == {
            "status": "awaiting_review",
            "checkpoint_bundle_prefix": checkpoint_prefix,
        }
        await cur.execute(
            """
            SELECT event_key, stage, status
            FROM education_generation_progress_events
            WHERE generation_job_id = %s
            """,
            (generation_job_id,),
        )
        assert await cur.fetchall() == [
            {
                "event_key": "chapter_analysis:completed:chapter",
                "stage": "chapter_analysis",
                "status": "completed",
            }
        ]

    import_book_package = AsyncMock(
        side_effect=AssertionError("checkpoint must not import a partial package")
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "import_book_package",
        import_book_package,
    )
    finalized = await education_book_pipeline_jobs.finalize_book_pipeline_generation(
        job={
            "generation_job_id": generation_job_id,
            "parent_user_id": parent_user_id,
            "pause_after_chapter_analysis": True,
        },
        frozen_input={},
        attempt_id=attempt_id,
        root_run_id=run_id,
        sandbox=sandbox,
        terminal_status="completed",
        terminal_error=None,
        checkpoint_stop_event=checkpoint_stop_event,
    )
    assert finalized == {
        "status": "awaiting_review",
        "job_status": "awaiting_review",
    }
    import_book_package.assert_not_awaited()

    continuation_prompt = (
        education_structure_jobs.managed_book_pipeline_continuation_prompt(
            generation_job_id
        )
    )
    assert (
        continuation_prompt.partition("。")[0]
        == "managed mode=full-pipeline-continuation"
    )
    assert "mode=mode" not in continuation_prompt
    assert "Steps 4-9" in continuation_prompt
    assert "progress.jsonl" in continuation_prompt
