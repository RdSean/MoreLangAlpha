"""PostgreSQL queue and fencing contracts for managed textbook jobs."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import pytest
import psycopg

from src.server.services.education_book_structure import MoreToSkillsIdentity
from src.server.services.education_book_structure import ParsedBookStructure


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

IDENTITY = MoreToSkillsIdentity(
    version="2.1.0",
    skill_sha256="b" * 64,
    schema_sha256="c" * 64,
)
CURRENT_IDENTITY = MoreToSkillsIdentity(
    version="2.1.1",
    skill_sha256="d" * 64,
    schema_sha256="e" * 64,
)


def _parsed_points(count: int = 2) -> ParsedBookStructure:
    points = tuple(
        {
            "id": f"u01-k{position:02d}",
            "title": f"Point {position}",
            "anchor": {
                "start_line": (position - 1) * 10 + 1,
                "end_line": position * 10,
            },
            "nodes": [],
        }
        for position in range(1, count + 1)
    )
    return ParsedBookStructure(
        document={
            "schema_version": "2.1.0",
            "source": {"path": "inputs/source/document.md"},
            "nodes": [],
            "knowledge_points": list(points),
            "coverage": {"excluded": [], "omitted": []},
        },
        knowledge_points=tuple(
            {
                "skill_kp_id": point["id"],
                "position": position,
                "title": point["title"],
                "unit_skill_node_id": None,
                "node_skill_ids": (),
                "start_line": point["anchor"]["start_line"],
                "end_line": point["anchor"]["end_line"],
                "raw": point,
            }
            for position, point in enumerate(points, start=1)
        ),
        warnings=(),
    )


def _parsed_two_points() -> ParsedBookStructure:
    return _parsed_points()


def _parsed_empty() -> ParsedBookStructure:
    return ParsedBookStructure(
        document={
            "schema_version": "2.1.0",
            "source": {"path": "inputs/source/document.md"},
            "nodes": [],
            "knowledge_points": [],
            "coverage": {"excluded": [], "omitted": []},
        },
        knowledge_points=(),
        warnings=(),
    )


async def _seed_book(
    connection_factory,
    *,
    parent_user_id: str,
    follow_up_request: dict | None = None,
) -> dict:
    from src.server.database.education_books import create_textbook_with_initial_job

    household_id = uuid4()
    textbook_id = uuid4()
    prefix = f"education/{household_id}/textbooks/{textbook_id}/source/"
    async with connection_factory() as db_conn, db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO education_households (
                    household_id, name, model_owner_user_id
                ) VALUES (%s, 'Queue household', %s)
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
        title="Queue Book",
        slug=f"queue-{uuid4().hex}",
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
            "parse_completed_at": "2026-10-01T00:00:00+00:00",
            "content_sha256": "a" * 64,
            "size_bytes": 128,
            "snapshot_prefix": prefix,
            "markdown_key": f"{prefix}artifacts/document.md",
            "blocks_key": f"{prefix}artifacts/blocks.json",
            "report_key": f"{prefix}artifacts/report.json",
            "asset_manifest": [],
            "snapshot": {"format": "langalpha-textbook-source-snapshot/v2"},
        },
        idempotency_key="initial-structure",
        identity=IDENTITY,
        follow_up_request=follow_up_request,
    )
    return {**created, "household_id": household_id}


async def test_two_workers_share_one_preparation_slot_and_ready_books_bypass_it(
    patched_get_db_connection,
    seed_user,
):
    import asyncio
    from src.server.database.education_book_jobs import claim_next_book_item

    books = [
        await _seed_book(patched_get_db_connection, parent_user_id=seed_user["user_id"])
        for _ in range(3)
    ]
    async with patched_get_db_connection() as conn:
        for book in books[:2]:
            await conn.execute(
                """UPDATE education_textbooks SET source_status='pending',source_content_sha256=NULL,
                source_size_bytes=NULL,source_snapshot_prefix=NULL,source_markdown_key=NULL,
                source_blocks_key=NULL,source_report_key=NULL,selected_source='{}',preparation_descriptor='{}'
                WHERE textbook_id=%s""",
                (book["textbook_id"],),
            )
    claims = await asyncio.gather(
        *[
            claim_next_book_item(
                worker_id=f"prep-{index}", lease_seconds=30, preparation_only=True
            )
            for index in range(2)
        ]
    )
    assert sum(claim is not None for claim in claims) == 1
    runtime = await claim_next_book_item(worker_id="runtime", lease_seconds=30)
    assert runtime["textbook_id"] == books[2]["textbook_id"]


async def _seed_pending(connection_factory, *, parent_user_id):
    book = await _seed_book(connection_factory, parent_user_id=parent_user_id)
    async with connection_factory() as conn:
        source = await (
            await conn.execute(
                "SELECT * FROM education_textbooks WHERE textbook_id=%s",
                (book["textbook_id"],),
            )
        ).fetchone()
        await conn.execute(
            """UPDATE education_textbooks SET source_status='pending',source_content_sha256=NULL,
            source_size_bytes=NULL,source_snapshot_prefix=NULL,source_markdown_key=NULL,
            source_blocks_key=NULL,source_report_key=NULL,selected_source='{}',preparation_descriptor='{}'
            WHERE textbook_id=%s""",
            (book["textbook_id"],),
        )
    return book, source


def _prepared_source(book, original, token):
    prefix = f"education/{book['household_id']}/textbooks/{book['textbook_id']}/source/attempts/{token}/"
    return {
        "document_id": original["source_document_id"],
        "parse_job_id": original["source_parse_job_id"],
        "primary_artifact_id": original["source_primary_artifact_id"],
        "snapshot_prefix": prefix,
        "markdown_key": f"{prefix}artifacts/document.md",
        "content_sha256": "a" * 64,
        "size_bytes": 128,
    }


@pytest.mark.parametrize("fence", ["expired", "cancelled"])
async def test_preparation_callbacks_reject_expired_lease_or_cancel_intent(
    patched_get_db_connection,
    seed_user,
    fence,
):
    from src.server.database.education_book_jobs import (
        claim_next_preparation_item,
        assert_book_preparation_current,
        update_book_preparation_progress,
        request_book_job_cancel,
        renew_book_item_lease,
        record_candidate_object,
    )
    from src.server.database.education_books import commit_prepared_book_source

    book, original = await _seed_pending(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    item = await claim_next_preparation_item(worker_id="prep", lease_seconds=30)
    if fence == "expired":
        async with patched_get_db_connection() as conn:
            await conn.execute(
                "UPDATE education_book_job_items SET lease_expires_at=NOW()-INTERVAL '1 second' WHERE item_id=%s",
                (item["item_id"],),
            )
    else:
        await request_book_job_cancel(job_id=book["job_id"])
    with pytest.raises(RuntimeError):
        await assert_book_preparation_current(
            item_id=item["item_id"], attempt_token=item["attempt_token"]
        )
    with pytest.raises(RuntimeError):
        await update_book_preparation_progress(
            item_id=item["item_id"],
            attempt_token=item["attempt_token"],
            verified_resources=1,
            total_resources=1,
        )
    with pytest.raises(RuntimeError):
        await commit_prepared_book_source(
            item_id=item["item_id"],
            attempt_token=item["attempt_token"],
            source=_prepared_source(book, original, item["attempt_token"]),
        )
    with pytest.raises(RuntimeError):
        await record_candidate_object(
            item_id=item["item_id"],
            attempt_token=item["attempt_token"],
            content_key=_prepared_source(book, original, item["attempt_token"])[
                "markdown_key"
            ],
        )
    assert not await renew_book_item_lease(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        worker_id="prep",
        lease_seconds=30,
    )


async def test_cancel_before_claim_marks_unprepared_source_cancelled(
    patched_get_db_connection, seed_user
):
    from src.server.database.education_book_jobs import mark_book_job_cancelled

    book, _ = await _seed_pending(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    await mark_book_job_cancelled(
        job_id=book["job_id"], item_id=None, attempt_token=None
    )
    async with patched_get_db_connection() as conn:
        row = await (
            await conn.execute(
                "SELECT source_status FROM education_textbooks WHERE textbook_id=%s",
                (book["textbook_id"],),
            )
        ).fetchone()
    assert row["source_status"] == "cancelled"


async def test_ready_to_runtime_keeps_attempt_and_expired_recovery_keeps_source(
    patched_get_db_connection, seed_user
):
    from src.server.database.education_book_jobs import (
        claim_next_preparation_item,
        claim_next_book_item,
        requeue_expired_book_preparation,
    )
    from src.server.database.education_books import commit_prepared_book_source

    book, original = await _seed_pending(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    item = await claim_next_preparation_item(worker_id="prep", lease_seconds=30)
    await commit_prepared_book_source(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        source=_prepared_source(book, original, item["attempt_token"]),
    )
    runtime = await claim_next_book_item(worker_id="runtime", lease_seconds=30)
    assert runtime["attempt_token"] == item["attempt_token"]
    assert runtime["attempt"] == 1
    async with patched_get_db_connection() as conn:
        await conn.execute(
            "UPDATE education_book_job_items SET lease_expires_at=NOW()-INTERVAL '1 second' WHERE item_id=%s",
            (item["item_id"],),
        )
    assert await requeue_expired_book_preparation(
        item_id=item["item_id"], attempt_token=item["attempt_token"]
    )
    assert (
        await claim_next_preparation_item(worker_id="prep-2", lease_seconds=30) is None
    )
    retry = await claim_next_book_item(worker_id="runtime-2", lease_seconds=30)
    assert retry["attempt_token"] != item["attempt_token"]
    assert retry["source_status"] == "ready"
    assert retry["attempt"] == 2


async def test_runtime_identity_is_registered_before_sandbox_and_retained_after_requeue(
    patched_get_db_connection, seed_user
):
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        create_book_item_runtime,
        requeue_expired_book_preparation,
        list_old_book_attempts_for_cleanup,
    )

    await _seed_book(patched_get_db_connection, parent_user_id=seed_user["user_id"])
    item = await claim_next_book_item(worker_id="runtime", lease_seconds=30)
    identity = {
        "attempt_token": str(item["attempt_token"]),
        "execution_id": str(item["execution_id"]),
    }
    runtime = await create_book_item_runtime(
        item_id=item["item_id"], attempt_token=item["attempt_token"], identity=identity
    )
    async with patched_get_db_connection() as conn:
        row = await (
            await conn.execute(
                "SELECT * FROM education_book_job_items WHERE item_id=%s",
                (item["item_id"],),
            )
        ).fetchone()
        assert str(row["managed_workspace_id"]) == runtime["workspace_id"]
        assert str(row["managed_thread_id"]) == runtime["thread_id"]
        assert row["run_id"] is None
        await conn.execute(
            "UPDATE education_book_job_items SET lease_expires_at=NOW()-INTERVAL '1 second' WHERE item_id=%s",
            (item["item_id"],),
        )
    assert await requeue_expired_book_preparation(
        item_id=item["item_id"], attempt_token=item["attempt_token"]
    )
    retry = await claim_next_book_item(worker_id="runtime-2", lease_seconds=30)
    assert retry["managed_workspace_id"] is None
    old = await list_old_book_attempts_for_cleanup()
    assert str(old[0]["managed_workspace_id"]) == runtime["workspace_id"]
    assert str(old[0]["managed_thread_id"]) == runtime["thread_id"]
    with pytest.raises(RuntimeError):
        await create_book_item_runtime(
            item_id=item["item_id"],
            attempt_token=item["attempt_token"],
            identity=identity,
        )
    async with patched_get_db_connection() as conn:
        assert (
            await (
                await conn.execute(
                    "SELECT count(*) AS n FROM workspaces WHERE config->'managed_execution'->>'attempt_token'=%s",
                    (str(item["attempt_token"]),),
                )
            ).fetchone()
        )["n"] == 1


async def test_sigkill_releases_preparation_io_lock_and_new_worker_fences_old_attempt(
    patched_get_db_connection,
    seed_user,
    test_db_uri,
):
    import asyncio
    import os
    import sys
    from src.server.database.education_book_jobs import (
        claim_next_preparation_item,
        requeue_expired_book_preparation,
        record_candidate_object,
        get_book_item_candidate_cleanup_context,
        assert_book_preparation_current,
    )
    from src.server.database.education_book_deletion import book_candidate_cleanup_guard

    book, original = await _seed_pending(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    item = await claim_next_preparation_item(worker_id="process-a", lease_seconds=30)
    candidate = _prepared_source(book, original, item["attempt_token"])["markdown_key"]
    await record_candidate_object(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        content_key=candidate,
    )
    script = """
import asyncio, os
from uuid import UUID
from src.server.database import education_book_deletion as deletion
deletion.get_db_connection_string = lambda: os.environ['PREPARATION_TEST_DB_URI']
async def main():
    async with deletion.book_item_storage_guard(item_id=UUID(os.environ['PREPARATION_TEST_ITEM']), preparation=True):
        print('LOCKED', flush=True)
        await asyncio.Event().wait()
asyncio.run(main())
"""
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-c",
        script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={
            **os.environ,
            "PREPARATION_TEST_DB_URI": test_db_uri,
            "PREPARATION_TEST_ITEM": str(item["item_id"]),
        },
    )
    try:
        assert await asyncio.wait_for(process.stdout.readline(), 20) == b"LOCKED\n"
        async with patched_get_db_connection() as conn:
            await conn.execute(
                "UPDATE education_book_job_items SET lease_expires_at=NOW()-INTERVAL '1 second' WHERE item_id=%s",
                (item["item_id"],),
            )
        assert not await requeue_expired_book_preparation(
            item_id=item["item_id"], attempt_token=item["attempt_token"]
        )
        from unittest.mock import patch

        with patch(
            "src.server.database.education_book_deletion.get_db_connection_string",
            return_value=test_db_uri,
        ):
            async with book_candidate_cleanup_guard(
                textbook_id=book["textbook_id"]
            ) as settled:
                assert not settled
        process.kill()
        await asyncio.wait_for(process.wait(), 10)
        assert await requeue_expired_book_preparation(
            item_id=item["item_id"], attempt_token=item["attempt_token"]
        )
        retry = await claim_next_preparation_item(
            worker_id="process-b", lease_seconds=30
        )
        assert retry["attempt"] == 2
        assert retry["attempt_token"] != item["attempt_token"]
        with pytest.raises(RuntimeError):
            await assert_book_preparation_current(
                item_id=item["item_id"], attempt_token=item["attempt_token"]
            )
        archived = await get_book_item_candidate_cleanup_context(
            item_id=item["item_id"], attempt_token=item["attempt_token"]
        )
        assert archived["candidate_objects"] == [candidate]
        async with patched_get_db_connection() as conn:
            attempt = await (
                await conn.execute(
                    "SELECT status FROM education_book_job_attempts WHERE attempt_token=%s",
                    (item["attempt_token"],),
                )
            ).fetchone()
        assert attempt["status"] == "interrupted"
    finally:
        if process.returncode is None:
            process.kill()
        await process.wait()


async def test_attempt_ledger_preserves_terminal_and_retry_round(
    patched_get_db_connection,
    seed_user,
):
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        fail_book_item,
        retry_book_job,
        get_book_job_for_parent,
    )

    book = await _seed_book(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    claimed = await claim_next_book_item(worker_id="timing-a", lease_seconds=30)
    assert claimed["execution_phase"] == "sandbox_preparation"
    await fail_book_item(
        item_id=claimed["item_id"],
        attempt_token=claimed["attempt_token"],
        safe_error="Failed",
        stop_remaining=True,
    )
    retried = await retry_book_job(
        source_job_id=book["job_id"],
        requested_by_user_id=seed_user["user_id"],
        idempotency_key="timing-retry",
        identity=IDENTITY,
    )
    assert retried["request_round"] == 2
    assert retried["previous_job_id"] == book["job_id"]
    second = await claim_next_book_item(worker_id="timing-b", lease_seconds=30)
    assert second["queued_at"] > claimed["queued_at"]
    async with patched_get_db_connection() as conn:
        rows = await (
            await conn.execute(
                "SELECT * FROM education_book_job_attempts ORDER BY claimed_at"
            )
        ).fetchall()
        assert len(rows) == 2
        assert rows[0]["status"] == "failed"
        assert rows[0]["terminal_at"] is not None
        assert rows[0]["attempt_token"] != rows[1]["attempt_token"]
        assert rows[1]["request_round"] == 2
    snapshot = await get_book_job_for_parent(
        job_id=retried["job_id"], parent_user_id=seed_user["user_id"]
    )
    assert snapshot["server_now"] is not None
    assert snapshot["items"][0]["timing_summary"]["total_ms"] is None


async def _seed_claimed_material_job(
    connection_factory,
    *,
    parent_user_id: str,
    include_supplementary: bool,
    target_count: int = 1,
) -> tuple[dict, dict, dict]:
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        create_materials_job,
    )
    from src.server.database.education_books import (
        commit_book_structure,
        get_current_structure,
    )

    created = await _seed_book(connection_factory, parent_user_id=parent_user_id)
    structure_claim = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert structure_claim is not None
    await commit_book_structure(
        textbook_id=created["textbook_id"],
        job_id=created["job_id"],
        item_id=created["item_id"],
        attempt_token=structure_claim["attempt_token"],
        parsed=_parsed_two_points(),
        validated_identity=IDENTITY,
    )
    structure = await get_current_structure(textbook_id=created["textbook_id"])
    assert structure is not None
    job = await create_materials_job(
        textbook_id=created["textbook_id"],
        requested_by_user_id=parent_user_id,
        knowledge_point_ids=[
            point["knowledge_point_id"]
            for point in structure["knowledge_points"][:target_count]
        ],
        depth="lesson",
        requirements=None,
        replace_existing=False,
        include_supplementary=include_supplementary,
        idempotency_key=f"cancel-fence-{uuid4().hex}",
        identity=IDENTITY,
    )
    claimed = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert claimed is not None and claimed["kind"] == "material"
    return created, job, claimed


async def test_claim_next_item_persists_attempt_execution_and_lease(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_jobs import claim_next_book_item

    created = await _seed_book(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )

    claimed = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)

    assert claimed is not None
    assert claimed["textbook_id"] == created["textbook_id"]
    assert claimed["job_id"] == created["job_id"]
    assert claimed["item_id"] == created["item_id"]
    assert claimed["operation"] == "structure"
    assert claimed["attempt"] == 1
    assert isinstance(claimed["attempt_token"], UUID)
    assert isinstance(claimed["execution_id"], UUID)
    assert claimed["lease_owner"] == "worker-a"
    assert isinstance(claimed["lease_expires_at"], datetime)
    assert await claim_next_book_item(worker_id="worker-b", lease_seconds=60) is None


async def test_authorized_material_job_snapshot_projects_knowledge_point_titles(
    patched_get_db_connection,
    seed_user,
):
    from src.server.database.education_book_jobs import get_book_job_for_parent
    from src.server.app.education.book_models import BookJobResponse

    _, job, _ = await _seed_claimed_material_job(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
        include_supplementary=True,
        target_count=2,
    )
    snapshot = await get_book_job_for_parent(
        job_id=job["job_id"], parent_user_id=seed_user["user_id"]
    )
    assert [item["knowledge_point_title"] for item in snapshot["items"]] == [
        "Point 1",
        "Point 2",
        None,
    ]
    assert (
        BookJobResponse.model_validate(snapshot).items[0].knowledge_point_title
        == "Point 1"
    )
    assert (
        await get_book_job_for_parent(
            job_id=job["job_id"], parent_user_id="other-parent"
        )
        is None
    )


async def test_expired_live_attempt_is_reconciled_by_another_worker_without_reclaim(
    patched_get_db_connection,
    seed_user,
    test_db_uri,
) -> None:
    from src.server.database.conversation import create_thread
    from src.server.database.education_book_jobs import (
        bind_book_item_runtime,
        claim_next_book_item,
    )
    from src.server.database.runs import lifecycle as lifecycle_db
    from src.server.database.workspace import create_workspace
    from src.server.services.education_book_recovery import reconcile_book_jobs_once

    created = await _seed_book(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    claimed = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert claimed is not None

    workspace = await create_workspace(
        user_id=seed_user["user_id"],
        name="Managed book recovery",
        description="integration test",
        config={"managed_execution": {"kind": "education_book"}},
        status="creating",
    )
    thread_id = str(uuid4())
    await create_thread(
        conversation_thread_id=thread_id,
        workspace_id=str(workspace["workspace_id"]),
        current_status="completed",
        msg_type="ptc",
        title="Managed book recovery",
        platform="education",
        metadata={"managed_execution": {"kind": "education_book"}},
    )
    run_id = str(uuid4())
    await lifecycle_db.start_run(
        run_id=run_id,
        thread_id=thread_id,
        request_key=run_id,
        metadata={"managed_execution": {"kind": "education_book"}},
        user_id=None,
    )
    await bind_book_item_runtime(
        item_id=claimed["item_id"],
        attempt_token=claimed["attempt_token"],
        workspace_id=workspace["workspace_id"],
        thread_id=thread_id,
        run_id=run_id,
    )

    async with (
        await psycopg.AsyncConnection.connect(test_db_uri, autocommit=True) as worker_a,
        await psycopg.AsyncConnection.connect(test_db_uri, autocommit=True) as observer,
    ):
        worker_a_pid = (
            await (await worker_a.execute("SELECT pg_backend_pid()")).fetchone()
        )[0]
        observer_pid = (
            await (await observer.execute("SELECT pg_backend_pid()")).fetchone()
        )[0]
        assert worker_a_pid != observer_pid
        await worker_a.execute(
            """
            UPDATE education_book_job_items
            SET lease_expires_at = NOW() - INTERVAL '1 second'
            WHERE item_id = %s AND attempt_token = %s
            """,
            (claimed["item_id"], claimed["attempt_token"]),
        )

        reconciled = await reconcile_book_jobs_once(
            worker_id="worker-b",
            lease_seconds=60,
        )

        row = await (
            await observer.execute(
                """
                SELECT status, attempt, attempt_token, execution_id,
                       lease_owner, lease_expires_at > NOW()
                FROM education_book_job_items WHERE item_id = %s
                """,
                (claimed["item_id"],),
            )
        ).fetchone()

    assert reconciled == 0
    assert row == (
        "running",
        1,
        claimed["attempt_token"],
        claimed["execution_id"],
        "worker-b",
        True,
    )
    assert await claim_next_book_item(worker_id="worker-c", lease_seconds=60) is None
    assert created["item_id"] == claimed["item_id"]


async def test_durable_cancel_intent_fences_a_queued_job_until_recovery(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        request_book_job_cancel,
    )

    created = await _seed_book(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )

    context = await request_book_job_cancel(job_id=created["job_id"])

    assert context is not None
    assert context["item_id"] is None
    assert context["thread_id"] is None
    assert context["run_id"] is None
    assert context["cancel_requested_at"] is not None
    assert await claim_next_book_item(worker_id="worker-a", lease_seconds=60) is None
    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT status, cancel_requested_at
                FROM education_book_jobs WHERE job_id = %s
                """,
                (created["job_id"],),
            )
            job = await cur.fetchone()
    assert job["status"] == "queued"
    assert job["cancel_requested_at"] is not None


async def test_structure_finalizer_rejects_a_durable_cancel_intent(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        request_book_job_cancel,
    )
    from src.server.database.education_books import commit_book_structure

    created = await _seed_book(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    claimed = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert claimed is not None
    await request_book_job_cancel(job_id=created["job_id"])

    with pytest.raises(RuntimeError, match="cancellation was requested"):
        await commit_book_structure(
            textbook_id=created["textbook_id"],
            job_id=created["job_id"],
            item_id=created["item_id"],
            attempt_token=claimed["attempt_token"],
            parsed=_parsed_two_points(),
            validated_identity=IDENTITY,
        )

    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*) AS count FROM education_book_structures WHERE created_by_job_id = %s",
                (created["job_id"],),
            )
            assert (await cur.fetchone())["count"] == 0


async def test_material_finalizer_rejects_a_durable_cancel_intent(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_jobs import (
        fail_book_item,
        finalize_material,
        list_book_jobs_pending_cancellation,
        mark_book_job_cancelled,
        record_candidate_object,
        request_book_job_cancel,
    )

    _created, job, claimed = await _seed_claimed_material_job(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
        include_supplementary=False,
    )
    content_key = f"education/test/{claimed['item_id']}/lesson.md"
    await record_candidate_object(
        item_id=claimed["item_id"],
        attempt_token=claimed["attempt_token"],
        content_key=content_key,
    )
    await request_book_job_cancel(job_id=job["job_id"])

    with pytest.raises(RuntimeError, match="cancellation was requested"):
        await finalize_material(
            item_id=claimed["item_id"],
            attempt_token=claimed["attempt_token"],
            content_key=content_key,
            content_sha256="d" * 64,
            size_bytes=100,
            generation_params={"depth": "lesson"},
        )

    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*) AS count FROM education_book_materials WHERE source_job_id = %s",
                (job["job_id"],),
            )
            assert (await cur.fetchone())["count"] == 0

    failed = await fail_book_item(
        item_id=claimed["item_id"],
        attempt_token=claimed["attempt_token"],
        safe_error="Cancellation fence rejected the late result",
        stop_remaining=False,
    )
    assert failed["status"] == "failed"
    pending = await list_book_jobs_pending_cancellation()
    assert [row["job_id"] for row in pending] == [job["job_id"]]
    cancelled = await mark_book_job_cancelled(
        job_id=job["job_id"],
        item_id=claimed["item_id"],
        attempt_token=claimed["attempt_token"],
    )
    assert cancelled["status"] == "cancelled"


async def test_partial_success_remains_recoverable_after_cancel_fence_rejection(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        fail_book_item,
        finalize_material,
        list_book_jobs_pending_cancellation,
        mark_book_job_cancelled,
        record_candidate_object,
        request_book_job_cancel,
    )

    _created, job, first = await _seed_claimed_material_job(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
        include_supplementary=False,
        target_count=2,
    )
    first_key = f"education/test/{first['item_id']}/lesson.md"
    await record_candidate_object(
        item_id=first["item_id"],
        attempt_token=first["attempt_token"],
        content_key=first_key,
    )
    await finalize_material(
        item_id=first["item_id"],
        attempt_token=first["attempt_token"],
        content_key=first_key,
        content_sha256="a" * 64,
        size_bytes=100,
        generation_params={},
    )
    second = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert second is not None and second["kind"] == "material"
    second_key = f"education/test/{second['item_id']}/lesson.md"
    await record_candidate_object(
        item_id=second["item_id"],
        attempt_token=second["attempt_token"],
        content_key=second_key,
    )
    await request_book_job_cancel(job_id=job["job_id"])

    with pytest.raises(RuntimeError, match="cancellation was requested"):
        await finalize_material(
            item_id=second["item_id"],
            attempt_token=second["attempt_token"],
            content_key=second_key,
            content_sha256="b" * 64,
            size_bytes=100,
            generation_params={},
        )
    partial = await fail_book_item(
        item_id=second["item_id"],
        attempt_token=second["attempt_token"],
        safe_error="Cancellation fence rejected the late result",
        stop_remaining=False,
    )

    assert partial["status"] == "partially_succeeded"
    pending = await list_book_jobs_pending_cancellation()
    assert [row["job_id"] for row in pending] == [job["job_id"]]
    cancelled = await mark_book_job_cancelled(
        job_id=job["job_id"],
        item_id=second["item_id"],
        attempt_token=second["attempt_token"],
    )
    assert cancelled["status"] == "cancelled"


async def test_batch_content_failure_keeps_old_material_and_continues_remaining_items(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        create_materials_job,
        fail_book_item,
        finalize_material,
        record_candidate_object,
        retry_book_job,
    )
    from src.server.database.education_books import (
        commit_book_structure,
        get_current_structure,
        get_managed_material_for_parent,
    )

    created = await _seed_book(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    structure_claim = await claim_next_book_item(
        worker_id="structure-worker", lease_seconds=60
    )
    assert structure_claim is not None
    await commit_book_structure(
        textbook_id=created["textbook_id"],
        job_id=created["job_id"],
        item_id=created["item_id"],
        attempt_token=structure_claim["attempt_token"],
        parsed=_parsed_points(4),
        validated_identity=IDENTITY,
    )
    structure = await get_current_structure(textbook_id=created["textbook_id"])
    assert structure is not None
    points = structure["knowledge_points"]

    async def commit_material(claimed: dict, digest_char: str) -> dict:
        content_key = (
            f"education/{created['household_id']}/textbooks/"
            f"{created['textbook_id']}/materials/{claimed['knowledge_point_id']}/"
            f"attempts/{claimed['attempt_token']}/{digest_char * 64}.md"
        )
        await record_candidate_object(
            item_id=claimed["item_id"],
            attempt_token=claimed["attempt_token"],
            content_key=content_key,
        )
        return await finalize_material(
            item_id=claimed["item_id"],
            attempt_token=claimed["attempt_token"],
            content_key=content_key,
            content_sha256=digest_char * 64,
            size_bytes=100,
            generation_params={"test": "batch-content-failure"},
        )

    old_job = await create_materials_job(
        textbook_id=created["textbook_id"],
        requested_by_user_id=seed_user["user_id"],
        knowledge_point_ids=[points[2]["knowledge_point_id"]],
        depth="lesson",
        requirements=None,
        replace_existing=False,
        include_supplementary=False,
        idempotency_key="old-third-material",
        identity=IDENTITY,
    )
    old_claim = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert old_claim is not None
    old_material = await commit_material(old_claim, "a")
    assert old_material["source_job_id"] == str(old_job["job_id"])

    batch = await create_materials_job(
        textbook_id=created["textbook_id"],
        requested_by_user_id=seed_user["user_id"],
        knowledge_point_ids=[point["knowledge_point_id"] for point in points],
        depth="lesson",
        requirements=None,
        replace_existing=True,
        include_supplementary=False,
        idempotency_key="replace-four-materials",
        identity=IDENTITY,
    )

    for index, digest_char in enumerate(("b", "c")):
        claimed = await claim_next_book_item(
            worker_id=f"worker-{index + 1}", lease_seconds=60
        )
        assert claimed is not None
        assert claimed["knowledge_point_id"] == points[index]["knowledge_point_id"]
        committed = await commit_material(claimed, digest_char)
        readable = await get_managed_material_for_parent(
            parent_user_id=seed_user["user_id"],
            textbook_id=created["textbook_id"],
            knowledge_point_id=points[index]["knowledge_point_id"],
        )
        assert readable is not None
        assert readable["content_key"] == committed["content_key"]

    third = await claim_next_book_item(worker_id="worker-3", lease_seconds=60)
    assert third is not None
    assert third["knowledge_point_id"] == points[2]["knowledge_point_id"]
    failed = await fail_book_item(
        item_id=third["item_id"],
        attempt_token=third["attempt_token"],
        safe_error="Generated material was invalid",
        stop_remaining=False,
    )
    assert failed["status"] == "running"
    assert failed["succeeded_items"] == 2
    assert failed["failed_items"] == 1
    preserved = await get_managed_material_for_parent(
        parent_user_id=seed_user["user_id"],
        textbook_id=created["textbook_id"],
        knowledge_point_id=points[2]["knowledge_point_id"],
    )
    assert preserved is not None
    assert preserved["content_key"] == old_material["content_key"]

    fourth = await claim_next_book_item(worker_id="worker-4", lease_seconds=60)
    assert fourth is not None
    assert fourth["knowledge_point_id"] == points[3]["knowledge_point_id"]
    await commit_material(fourth, "d")

    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT status, succeeded_items, failed_items,
                       cancelled_items, not_run_items
                FROM education_book_jobs WHERE job_id = %s
                """,
                (batch["job_id"],),
            )
            final_job = await cur.fetchone()
    assert final_job == {
        "status": "partially_succeeded",
        "succeeded_items": 3,
        "failed_items": 1,
        "cancelled_items": 0,
        "not_run_items": 0,
    }

    retried = await retry_book_job(
        source_job_id=batch["job_id"],
        requested_by_user_id=seed_user["user_id"],
        idempotency_key="retry-only-third-material",
        identity=IDENTITY,
    )
    assert len(retried["items"]) == 1
    assert retried["items"][0]["knowledge_point_id"] == points[2]["knowledge_point_id"]


async def test_supplementary_finalizer_rejects_a_durable_cancel_intent(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        finalize_material,
        finalize_supplementary,
        record_candidate_object,
        request_book_job_cancel,
    )

    _created, job, material = await _seed_claimed_material_job(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
        include_supplementary=True,
    )
    material_key = f"education/test/{material['item_id']}/lesson.md"
    await record_candidate_object(
        item_id=material["item_id"],
        attempt_token=material["attempt_token"],
        content_key=material_key,
    )
    await finalize_material(
        item_id=material["item_id"],
        attempt_token=material["attempt_token"],
        content_key=material_key,
        content_sha256="e" * 64,
        size_bytes=100,
        generation_params={"depth": "lesson"},
    )
    supplementary = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert supplementary is not None and supplementary["kind"] == "supplementary"
    files = [
        {
            "name": "glossary.md",
            "content_key": f"education/test/{supplementary['item_id']}/glossary.md",
            "content_sha256": "f" * 64,
            "size_bytes": 12,
        }
    ]
    await record_candidate_object(
        item_id=supplementary["item_id"],
        attempt_token=supplementary["attempt_token"],
        content_key=files[0]["content_key"],
    )
    await request_book_job_cancel(job_id=job["job_id"])

    with pytest.raises(RuntimeError, match="cancellation was requested"):
        await finalize_supplementary(
            item_id=supplementary["item_id"],
            attempt_token=supplementary["attempt_token"],
            result_snapshot={"files": files},
        )

    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT result_snapshot FROM education_book_job_items WHERE item_id = %s",
                (supplementary["item_id"],),
            )
            assert (await cur.fetchone())["result_snapshot"] is None


async def test_terminal_candidate_cleanup_uses_only_recorded_keys(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        fail_book_item,
        forget_book_candidate_object,
        get_book_item_candidate_cleanup_context,
        list_book_items_for_terminal_cleanup,
        record_candidate_object,
    )

    created = await _seed_book(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    claimed = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert claimed is not None
    candidate_key = f"education/test/attempts/{claimed['attempt_token']}/output.json"
    await record_candidate_object(
        item_id=claimed["item_id"],
        attempt_token=claimed["attempt_token"],
        content_key=candidate_key,
    )
    await fail_book_item(
        item_id=claimed["item_id"],
        attempt_token=claimed["attempt_token"],
        safe_error="invalid output",
        stop_remaining=False,
    )

    pending = await list_book_items_for_terminal_cleanup()
    assert [row["item_id"] for row in pending] == [created["item_id"]]
    context = await get_book_item_candidate_cleanup_context(
        item_id=claimed["item_id"],
        attempt_token=claimed["attempt_token"],
    )
    assert context == {
        "candidate_objects": [candidate_key],
        "result_snapshot": None,
        "kind": "structure",
        "knowledge_point_id": None,
        "textbook_id": created["textbook_id"],
        "household_id": created["household_id"],
        "ready_source_prefix": f"education/{created['household_id']}/textbooks/{created['textbook_id']}/source/",
    }

    assert await forget_book_candidate_object(
        item_id=claimed["item_id"],
        attempt_token=claimed["attempt_token"],
        content_key=candidate_key,
    )
    assert await list_book_items_for_terminal_cleanup() == []


async def test_material_attempt_recovers_idempotently_after_upload_and_transaction_failures(
    patched_get_db_connection,
    seed_user,
    monkeypatch,
) -> None:
    from src.server.database import education_book_jobs as job_db
    from src.server.services import education_book_storage as storage

    _created, _job, claimed = await _seed_claimed_material_job(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
        include_supplementary=False,
    )
    markdown = b"# Durable lesson\n"
    objects: dict[str, bytes] = {}
    upload_count = 0

    async def job_summary() -> dict:
        async with patched_get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT status, succeeded_items, failed_items,
                           cancelled_items, not_run_items,
                           (SELECT count(*) FROM education_book_activity_events
                            WHERE job_id = jobs.job_id
                              AND metadata->>'budget_class' = 'terminal'
                           ) AS terminal_events
                    FROM education_book_jobs AS jobs WHERE job_id = %s
                    """,
                    (claimed["job_id"],),
                )
                return await cur.fetchone()

    async def upload(key, content, _content_type, *, max_size):
        nonlocal upload_count
        assert len(content) <= max_size
        upload_count += 1
        if upload_count == 1:
            return False
        objects[key] = content
        return True

    async def read(key):
        return objects.get(key)

    monkeypatch.setattr(storage, "_upload", upload)
    monkeypatch.setattr(storage, "_read", read)

    with pytest.raises(storage.BookStorageError, match="could not be stored"):
        await storage.store_material(
            item_id=claimed["item_id"],
            attempt_token=claimed["attempt_token"],
            markdown=markdown,
            generation_params={"depth": "lesson"},
        )

    original_append = job_db.append_terminal_activity

    async def fail_terminal_activity(*_args, **_kwargs):
        raise RuntimeError("forced terminal activity transaction failure")

    monkeypatch.setattr(job_db, "append_terminal_activity", fail_terminal_activity)
    with pytest.raises(RuntimeError, match="forced terminal activity"):
        await storage.store_material(
            item_id=claimed["item_id"],
            attempt_token=claimed["attempt_token"],
            markdown=markdown,
            generation_params={"depth": "lesson"},
        )

    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT status, candidate_objects,
                       (SELECT count(*) FROM education_book_materials
                        WHERE source_item_id = items.item_id) AS material_count
                FROM education_book_job_items AS items WHERE item_id = %s
                """,
                (claimed["item_id"],),
            )
            rolled_back = await cur.fetchone()
    assert rolled_back["status"] == "running"
    assert len(rolled_back["candidate_objects"]) == 1
    assert rolled_back["material_count"] == 0
    assert await job_summary() == {
        "status": "running",
        "succeeded_items": 0,
        "failed_items": 0,
        "cancelled_items": 0,
        "not_run_items": 0,
        "terminal_events": 0,
    }

    monkeypatch.setattr(job_db, "append_terminal_activity", original_append)
    committed = await storage.store_material(
        item_id=claimed["item_id"],
        attempt_token=claimed["attempt_token"],
        markdown=markdown,
        generation_params={"depth": "lesson"},
    )
    committed_summary = await job_summary()
    repeated = await job_db.finalize_material(
        item_id=claimed["item_id"],
        attempt_token=claimed["attempt_token"],
        content_key=committed["content_key"],
        content_sha256=committed["content_sha256"],
        size_bytes=committed["size_bytes"],
        generation_params={"depth": "lesson"},
    )

    assert repeated == committed
    assert (
        await job_summary()
        == committed_summary
        == {
            "status": "succeeded",
            "succeeded_items": 1,
            "failed_items": 0,
            "cancelled_items": 0,
            "not_run_items": 0,
            "terminal_events": 2,
        }
    )
    assert committed["generation"] == 1
    assert upload_count == 3
    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT status, candidate_objects,
                       (SELECT count(*) FROM education_book_materials
                        WHERE source_item_id = items.item_id) AS material_count
                FROM education_book_job_items AS items WHERE item_id = %s
                """,
                (claimed["item_id"],),
            )
            settled = await cur.fetchone()
    assert settled["status"] == "succeeded"
    assert settled["candidate_objects"] == rolled_back["candidate_objects"]
    assert settled["material_count"] == 1


async def test_bind_runtime_ids_is_fenced_by_the_current_attempt(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_jobs import (
        bind_book_item_runtime,
        claim_next_book_item,
    )
    from src.server.database.runs import lifecycle as lifecycle_db
    from src.server.database.conversation import create_thread
    from src.server.database.workspace import create_workspace

    await _seed_book(patched_get_db_connection, parent_user_id=seed_user["user_id"])
    claimed = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert claimed is not None
    workspace = await create_workspace(
        user_id=seed_user["user_id"],
        name="Managed book execution",
        description="integration test",
        config={"managed_execution": {"kind": "education_book"}},
        status="creating",
    )
    workspace_id = str(workspace["workspace_id"])
    thread_id = str(uuid4())
    await create_thread(
        conversation_thread_id=thread_id,
        workspace_id=workspace_id,
        current_status="completed",
        msg_type="ptc",
        title="Managed book execution",
        platform="education",
        metadata={"managed_execution": {"kind": "education_book"}},
    )
    run_id = str(uuid4())
    await lifecycle_db.start_run(
        run_id=run_id,
        thread_id=thread_id,
        request_key=run_id,
        metadata={"managed_execution": {"kind": "education_book"}},
        user_id=None,
    )

    bound = await bind_book_item_runtime(
        item_id=claimed["item_id"],
        attempt_token=claimed["attempt_token"],
        workspace_id=workspace_id,
        thread_id=thread_id,
        run_id=run_id,
    )

    assert str(bound["managed_workspace_id"]) == workspace_id
    assert str(bound["managed_thread_id"]) == thread_id
    assert str(bound["run_id"]) == run_id
    with pytest.raises(RuntimeError, match="stale"):
        await bind_book_item_runtime(
            item_id=claimed["item_id"],
            attempt_token=uuid4(),
            workspace_id=workspace_id,
            thread_id=thread_id,
            run_id=run_id,
        )


async def test_global_item_failure_marks_remainder_not_run_and_retry_clones_only_unfinished(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        create_materials_job,
        fail_book_item,
        retry_book_job,
    )
    from src.server.database.education_books import (
        commit_book_structure,
        get_current_structure,
    )

    created = await _seed_book(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    structure_claim = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert structure_claim is not None
    await commit_book_structure(
        textbook_id=created["textbook_id"],
        job_id=created["job_id"],
        item_id=created["item_id"],
        attempt_token=structure_claim["attempt_token"],
        parsed=_parsed_two_points(),
        validated_identity=IDENTITY,
    )
    structure = await get_current_structure(textbook_id=created["textbook_id"])
    assert structure is not None
    material_job = await create_materials_job(
        textbook_id=created["textbook_id"],
        requested_by_user_id=seed_user["user_id"],
        knowledge_point_ids=[
            point["knowledge_point_id"] for point in structure["knowledge_points"]
        ],
        depth="lesson",
        requirements=None,
        replace_existing=False,
        include_supplementary=False,
        idempotency_key="materials-1",
        identity=IDENTITY,
    )
    material_claim = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert material_claim is not None

    failed = await fail_book_item(
        item_id=material_claim["item_id"],
        attempt_token=material_claim["attempt_token"],
        safe_error="Source snapshot unavailable",
        stop_remaining=True,
    )

    assert failed["status"] == "failed"
    assert failed["failed_items"] == 1
    assert failed["not_run_items"] == 1
    retried = await retry_book_job(
        source_job_id=material_job["job_id"],
        requested_by_user_id=seed_user["user_id"],
        idempotency_key="retry-1",
        identity=IDENTITY,
    )
    assert retried["status"] == "queued"
    assert [item["status"] for item in retried["items"]] == ["queued", "queued"]
    assert {item["knowledge_point_id"] for item in retried["items"]} == {
        point["knowledge_point_id"] for point in structure["knowledge_points"]
    }


async def test_cancelled_job_retry_clones_cancelled_items(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        create_materials_job,
        mark_book_job_cancelled,
        retry_book_job,
    )
    from src.server.database.education_books import (
        commit_book_structure,
        get_current_structure,
    )

    created = await _seed_book(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    structure_claim = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert structure_claim is not None
    await commit_book_structure(
        textbook_id=created["textbook_id"],
        job_id=created["job_id"],
        item_id=created["item_id"],
        attempt_token=structure_claim["attempt_token"],
        parsed=_parsed_two_points(),
        validated_identity=IDENTITY,
    )
    structure = await get_current_structure(textbook_id=created["textbook_id"])
    assert structure is not None
    material_job = await create_materials_job(
        textbook_id=created["textbook_id"],
        requested_by_user_id=seed_user["user_id"],
        knowledge_point_ids=[
            point["knowledge_point_id"] for point in structure["knowledge_points"]
        ],
        depth="lesson",
        requirements=None,
        replace_existing=False,
        include_supplementary=False,
        idempotency_key="materials-cancelled",
        identity=IDENTITY,
    )
    claimed = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert claimed is not None
    cancelled = await mark_book_job_cancelled(
        job_id=material_job["job_id"],
        item_id=claimed["item_id"],
        attempt_token=claimed["attempt_token"],
    )
    assert cancelled["status"] == "cancelled"
    assert cancelled["runtime_contexts"]
    assert set(cancelled["runtime_contexts"][0]) == {
        "item_id",
        "attempt_token",
        "thread_id",
        "run_id",
    }

    retried = await retry_book_job(
        source_job_id=material_job["job_id"],
        requested_by_user_id=seed_user["user_id"],
        idempotency_key="retry-cancelled",
        identity=CURRENT_IDENTITY,
    )

    assert [item["status"] for item in retried["items"]] == ["queued", "queued"]
    assert [item["knowledge_point_id"] for item in retried["items"]] == [
        point["knowledge_point_id"] for point in structure["knowledge_points"]
    ]
    assert retried["more_to_skills_version"] == CURRENT_IDENTITY.version
    assert retried["skill_sha256"] == CURRENT_IDENTITY.skill_sha256
    assert retried["schema_sha256"] == CURRENT_IDENTITY.schema_sha256


async def test_cancel_fence_wins_if_terminal_failure_callback_commits_first(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        fail_book_item,
        mark_book_job_cancelled,
    )

    created = await _seed_book(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    claimed = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert claimed is not None
    await fail_book_item(
        item_id=claimed["item_id"],
        attempt_token=claimed["attempt_token"],
        safe_error="terminal callback won the race",
        stop_remaining=True,
    )

    cancelled = await mark_book_job_cancelled(
        job_id=created["job_id"],
        item_id=claimed["item_id"],
        attempt_token=claimed["attempt_token"],
    )

    assert cancelled["status"] == "cancelled"
    assert cancelled["failed_items"] == 0
    assert cancelled["cancelled_items"] == 1
    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT kind, status, metadata->>'budget_class' AS budget_class
                FROM education_book_activity_events
                WHERE job_id = %s ORDER BY seq
                """,
                (created["job_id"],),
            )
            terminal_events = await cur.fetchall()
    assert [
        (event["kind"], event["status"], event["budget_class"])
        for event in terminal_events
    ] == [
        ("item", "cancelled", "terminal"),
        ("job", "cancelled", "terminal"),
    ]


async def test_structure_retry_preserves_follow_up_and_refreshes_skill_identity(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        fail_book_item,
        retry_book_job,
    )
    from src.server.database.education_books import commit_book_structure

    follow_up = {
        "operation": "materials",
        "depth": "lesson",
        "requirements": "Use examples.",
        "replace_existing": False,
        "include_supplementary": False,
    }
    created = await _seed_book(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
        follow_up_request=follow_up,
    )
    claimed = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert claimed is not None
    await fail_book_item(
        item_id=claimed["item_id"],
        attempt_token=claimed["attempt_token"],
        safe_error="Managed textbook skill identity changed after queueing",
        stop_remaining=True,
    )

    retried = await retry_book_job(
        source_job_id=created["job_id"],
        requested_by_user_id=seed_user["user_id"],
        idempotency_key="retry-structure-current-skill",
        identity=CURRENT_IDENTITY,
    )

    assert retried["follow_up_request"] == follow_up
    assert retried["more_to_skills_version"] == CURRENT_IDENTITY.version
    retried_claim = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert retried_claim is not None
    await commit_book_structure(
        textbook_id=created["textbook_id"],
        job_id=retried["job_id"],
        item_id=retried_claim["item_id"],
        attempt_token=retried_claim["attempt_token"],
        parsed=_parsed_two_points(),
        validated_identity=CURRENT_IDENTITY,
    )

    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT kind, more_to_skills_version, total_items
                FROM education_book_jobs
                WHERE textbook_id = %s
                ORDER BY created_at, job_id
                """,
                (created["textbook_id"],),
            )
            jobs = await cur.fetchall()
    assert [job["kind"] for job in jobs] == [
        "structure",
        "structure",
        "materials",
    ]
    assert jobs[-1]["more_to_skills_version"] == CURRENT_IDENTITY.version
    assert jobs[-1]["total_items"] == 2


async def test_structure_commit_creates_persisted_follow_up_materials_once(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_jobs import claim_next_book_item
    from src.server.database.education_books import commit_book_structure

    created = await _seed_book(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
        follow_up_request={
            "operation": "materials",
            "depth": "lesson",
            "requirements": "Use examples.",
            "replace_existing": False,
            "include_supplementary": False,
        },
    )
    claimed = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert claimed is not None

    first = await commit_book_structure(
        textbook_id=created["textbook_id"],
        job_id=created["job_id"],
        item_id=created["item_id"],
        attempt_token=claimed["attempt_token"],
        parsed=_parsed_two_points(),
        validated_identity=IDENTITY,
    )
    second = await commit_book_structure(
        textbook_id=created["textbook_id"],
        job_id=created["job_id"],
        item_id=created["item_id"],
        attempt_token=claimed["attempt_token"],
        parsed=_parsed_two_points(),
        validated_identity=IDENTITY,
    )

    assert second == first
    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT * FROM education_book_jobs
                WHERE textbook_id = %s
                ORDER BY created_at, job_id
                """,
                (created["textbook_id"],),
            )
            jobs = await cur.fetchall()
            assert [job["kind"] for job in jobs] == ["structure", "materials"]
            assert jobs[1]["status"] == "queued"
            assert jobs[1]["depth"] == "lesson"
            assert jobs[1]["requirements"] == "Use examples."
            await cur.execute(
                """
                SELECT kind, status
                FROM education_book_job_items
                WHERE job_id = %s ORDER BY position
                """,
                (jobs[1]["job_id"],),
            )
            assert await cur.fetchall() == [
                {"kind": "material", "status": "queued"},
                {"kind": "material", "status": "queued"},
            ]


@pytest.mark.parametrize(
    ("include_supplementary", "expected_follow_up_items"),
    [(False, []), (True, ["supplementary"])],
)
async def test_empty_structure_does_not_create_an_empty_follow_up_job(
    patched_get_db_connection,
    seed_user,
    include_supplementary,
    expected_follow_up_items,
) -> None:
    from src.server.database.education_book_jobs import claim_next_book_item
    from src.server.database.education_books import commit_book_structure

    created = await _seed_book(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
        follow_up_request={
            "operation": "materials",
            "depth": "lesson",
            "requirements": None,
            "replace_existing": False,
            "include_supplementary": include_supplementary,
        },
    )
    claimed = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert claimed is not None

    await commit_book_structure(
        textbook_id=created["textbook_id"],
        job_id=created["job_id"],
        item_id=created["item_id"],
        attempt_token=claimed["attempt_token"],
        parsed=_parsed_empty(),
        validated_identity=IDENTITY,
    )

    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT job_id, kind, total_items
                FROM education_book_jobs
                WHERE textbook_id = %s
                ORDER BY created_at, job_id
                """,
                (created["textbook_id"],),
            )
            jobs = await cur.fetchall()
            assert len(jobs) == 1 + int(include_supplementary)
            if not include_supplementary:
                return
            assert jobs[1]["kind"] == "materials"
            assert jobs[1]["total_items"] == 1
            await cur.execute(
                """
                SELECT kind FROM education_book_job_items
                WHERE job_id = %s ORDER BY position
                """,
                (jobs[1]["job_id"],),
            )
            assert [row["kind"] for row in await cur.fetchall()] == (
                expected_follow_up_items
            )


async def test_explicit_supplementary_item_commits_fixed_snapshot_and_fences_late_token(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        create_materials_job,
        finalize_material,
        finalize_supplementary,
        record_candidate_object,
    )
    from src.server.database.education_books import (
        commit_book_structure,
        get_current_structure,
    )

    created = await _seed_book(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    structure_claim = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert structure_claim is not None
    await commit_book_structure(
        textbook_id=created["textbook_id"],
        job_id=created["job_id"],
        item_id=created["item_id"],
        attempt_token=structure_claim["attempt_token"],
        parsed=_parsed_two_points(),
        validated_identity=IDENTITY,
    )
    structure = await get_current_structure(textbook_id=created["textbook_id"])
    assert structure is not None
    job = await create_materials_job(
        textbook_id=created["textbook_id"],
        requested_by_user_id=seed_user["user_id"],
        knowledge_point_ids=[
            point["knowledge_point_id"] for point in structure["knowledge_points"]
        ],
        depth="lesson",
        requirements="Generate all supporting files.",
        replace_existing=False,
        include_supplementary=True,
        idempotency_key="materials-with-supplementary",
        identity=IDENTITY,
    )

    assert job["total_items"] == 3
    assert [item["kind"] for item in job["items"]] == [
        "material",
        "material",
        "supplementary",
    ]
    for index in range(2):
        claim = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
        assert claim is not None and claim["kind"] == "material"
        content_key = f"education/test/material-{index}.md"
        await record_candidate_object(
            item_id=claim["item_id"],
            attempt_token=claim["attempt_token"],
            content_key=content_key,
        )
        await finalize_material(
            item_id=claim["item_id"],
            attempt_token=claim["attempt_token"],
            content_key=content_key,
            content_sha256=str(index) * 64,
            size_bytes=10,
            generation_params={"depth": "lesson"},
        )

    supplementary = await claim_next_book_item(worker_id="worker-a", lease_seconds=60)
    assert supplementary is not None and supplementary["kind"] == "supplementary"
    files = [
        {
            "name": name,
            "content_key": f"education/test/{name}",
            "content_sha256": str(index + 2) * 64,
            "size_bytes": 12,
        }
        for index, name in enumerate(("glossary.md", "patterns.md", "cheatsheet.md"))
    ]
    for file in files:
        await record_candidate_object(
            item_id=supplementary["item_id"],
            attempt_token=supplementary["attempt_token"],
            content_key=file["content_key"],
        )
    snapshot = {
        "item_id": str(supplementary["item_id"]),
        "attempt_token": str(supplementary["attempt_token"]),
        "files": files,
    }

    committed = await finalize_supplementary(
        item_id=supplementary["item_id"],
        attempt_token=supplementary["attempt_token"],
        result_snapshot=snapshot,
    )

    assert committed == snapshot
    with pytest.raises(RuntimeError, match="already finalized differently"):
        await finalize_supplementary(
            item_id=supplementary["item_id"],
            attempt_token=uuid4(),
            result_snapshot={**snapshot, "attempt_token": str(uuid4())},
        )
