"""HTTP/PG acceptance stays responsive while the simulated object IO is blocked."""

import asyncio
from importlib import import_module
from time import monotonic
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

from fastapi import FastAPI
import httpx
import psycopg
import pytest

from tests.integration.test_education_books_db import _seed_parent_household
from tests.integration.test_education_book_jobs_db import _seed_pending, IDENTITY
from tests.unit.server.services.test_education_textbook_source_snapshots import (
    _parse_job,
    _artifact,
    DOCUMENT_ID,
    PRODUCER_JOB_ID,
    PRIMARY_ARTIFACT_ID,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_http_acceptance_and_idempotent_retry_do_not_wait_for_source_io(
    patched_get_db_connection, seed_user, monkeypatch, test_db_uri, record_property
):
    from src.server.app.education.textbooks import router
    from src.server.database import education_book_deletion as deletion
    from src.server.database.education_book_jobs import claim_next_preparation_item
    from src.server.services import education_book_activity as activity
    from src.server.services import education_book_preparation as preparation
    from src.server.services import education_textbook_source_snapshots as snapshots
    from src.server.services import education_textbooks as textbooks
    from src.server.utils.api import get_current_user_id

    parent = seed_user["user_id"]
    async with patched_get_db_connection() as conn:
        await _seed_parent_household(conn, parent_user_id=parent)
    primary_key = f"documents/{DOCUMENT_ID}/artifacts/{PRODUCER_JOB_ID}/document.md"
    artifact = _artifact(
        artifact_id=PRIMARY_ARTIFACT_ID,
        artifact_kind="primary_document",
        relative_path="document.md",
        storage_key=primary_key,
    )
    monkeypatch.setattr(
        snapshots, "get_owned_parse_job", AsyncMock(return_value=_parse_job())
    )
    monkeypatch.setattr(snapshots, "list_artifacts", AsyncMock(return_value=[artifact]))
    monkeypatch.setattr(textbooks, "get_more_to_skills_identity", lambda: IDENTITY)
    monkeypatch.setattr(deletion, "get_db_connection_string", lambda: test_db_uri)
    monkeypatch.setattr(activity, "publish_book_activity_hint", AsyncMock())
    monkeypatch.setattr(preparation, "publish_book_activity_hint", AsyncMock())
    started, release = asyncio.Event(), asyncio.Event()
    objects = {}

    async def read(key):
        if key == primary_key:
            started.set()
            await release.wait()
            return b"# Test textbook\n\nA source paragraph.\n"
        return objects.get(key)

    async def write(key, content, content_type, *, max_size):
        assert len(content) <= max_size
        objects[key] = content
        return True

    reads = AsyncMock(side_effect=read)
    monkeypatch.setattr(snapshots, "_read_object", reads)
    monkeypatch.setattr(snapshots, "_write_object", write)
    monkeypatch.setattr(snapshots, "_delete_object", AsyncMock(return_value=True))
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user_id] = lambda: parent
    payload = {
        "title": "Isolated HTTP textbook",
        "parse_job_id": PRODUCER_JOB_ID,
        "primary_artifact_id": PRIMARY_ARTIFACT_ID,
        "idempotency_key": "http-acceptance",
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        clock = monotonic()
        response = await asyncio.wait_for(
            client.post("/api/v1/education/textbooks", json=payload), 2
        )
        record_property("accepted_ms", round((monotonic() - clock) * 1000, 3))
        assert response.status_code == 202, response.text
        assert response.json()["acceptance"] == "accepted_new"
        reads.assert_not_awaited()
        book_id, job_id = response.json()["textbook_id"], response.json()["job_id"]
        item = await claim_next_preparation_item(
            worker_id="http-test", lease_seconds=30
        )
        worker = asyncio.create_task(
            preparation.prepare_book_item(
                item=item, worker_id="http-test", lease_seconds=30
            )
        )
        try:
            await asyncio.wait_for(started.wait(), 2)
            assert not worker.done()
            clock = monotonic()
            retry = await asyncio.wait_for(
                client.post("/api/v1/education/textbooks", json=payload), 2
            )
            record_property(
                "reused_while_io_blocked_ms", round((monotonic() - clock) * 1000, 3)
            )
            assert retry.status_code == 202, retry.text
            assert retry.json() == {
                "textbook_id": book_id,
                "job_id": job_id,
                "acceptance": "reused",
            }
            source = await client.get(
                f"/api/v1/education/textbooks/{book_id}/source",
                params={"start_line": 1, "end_line": 2},
            )
            assert source.status_code == 409
            job = (await client.get(f"/api/v1/education/book-jobs/{job_id}")).json()
            assert job["items"][0]["execution_phase"] == "source_freezing"
            assert job["items"][0]["preparation_progress"] == {
                "verified_resources": 0,
                "total_resources": 1,
            }
        finally:
            release.set()
            await asyncio.wait_for(worker, 5)
        workbench = (await client.get(f"/api/v1/education/textbooks/{book_id}")).json()
        assert workbench["source_status"] == "ready"
        job = (await client.get(f"/api/v1/education/book-jobs/{job_id}")).json()
        assert job["items"][0]["execution_phase"] == "runtime_queue"
        async with patched_get_db_connection() as conn:
            row = await (
                await conn.execute(
                    "SELECT run_id,managed_workspace_id FROM education_book_job_items WHERE item_id=%s",
                    (item["item_id"],),
                )
            ).fetchone()
            assert row == {"run_id": None, "managed_workspace_id": None}


async def test_rollback_refuses_pending_sources_and_durable_attempt_history(
    patched_get_db_connection, seed_user, monkeypatch
):
    from src.server.database.education_book_jobs import (
        claim_next_preparation_item,
        fail_book_item,
    )

    book, _ = await _seed_pending(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    migration = import_module("migrations.versions.084_textbook_preparation_timing")
    statements = []
    monkeypatch.setattr(migration, "execute", statements.append)
    migration.downgrade()
    async with patched_get_db_connection() as conn:
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="explicit preservation of attempt history",
        ):
            async with conn.transaction():
                for statement in statements:
                    async with psycopg.AsyncClientCursor(conn) as cursor:
                        await cursor.execute(statement, ())
        assert (
            await (
                await conn.execute(
                    "SELECT source_status FROM education_textbooks WHERE textbook_id=%s",
                    (book["textbook_id"],),
                )
            ).fetchone()
        )["source_status"] == "pending"
    item = await claim_next_preparation_item(
        worker_id="rollback-test", lease_seconds=30
    )
    await fail_book_item(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        safe_error="test",
        stop_remaining=True,
    )
    async with patched_get_db_connection() as conn:
        # Even compatible source metadata must not permit destructive history removal.
        await conn.execute(
            "UPDATE education_textbooks SET source_status='ready',source_content_sha256=%s,source_size_bytes=1,source_snapshot_prefix=%s,source_markdown_key=%s WHERE textbook_id=%s",
            (
                "a" * 64,
                f"education/{book['household_id']}/textbooks/{book['textbook_id']}/source/",
                f"education/{book['household_id']}/textbooks/{book['textbook_id']}/source/document.md",
                book["textbook_id"],
            ),
        )
        with pytest.raises(
            psycopg.errors.RaiseException,
            match="explicit preservation of attempt history",
        ):
            async with conn.transaction():
                for statement in statements:
                    async with psycopg.AsyncClientCursor(conn) as cursor:
                        await cursor.execute(statement, ())
        assert (
            await (
                await conn.execute(
                    "SELECT count(*) AS n FROM education_book_job_attempts WHERE item_id=%s",
                    (item["item_id"],),
                )
            ).fetchone()
        )["n"] == 1


async def test_statistics_http_denies_student_and_foreign_parent(
    patched_get_db_connection, seed_user
):
    from src.server.app.education.textbooks import router
    from src.server.utils.api import get_current_user_id

    book, _ = await _seed_pending(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    student, foreign_parent = f"student-{uuid4().hex}", f"foreign-{uuid4().hex}"
    async with patched_get_db_connection() as conn:
        await conn.execute(
            "INSERT INTO users(user_id,name) VALUES (%s,'Student'),(%s,'Foreign parent')",
            (student, foreign_parent),
        )
        await conn.execute(
            "INSERT INTO education_memberships(household_id,user_id,role,display_name) VALUES (%s,%s,'student','Student')",
            (book["household_id"], student),
        )
        await _seed_parent_household(conn, parent_user_id=foreign_parent)
    app = FastAPI()
    app.include_router(router)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        for user in (student, foreign_parent):
            app.dependency_overrides[get_current_user_id] = lambda: user
            result = await client.get(
                f"/api/v1/education/book-jobs/{book['job_id']}/statistics"
            )
            assert result.status_code == 404
        app.dependency_overrides[get_current_user_id] = lambda: seed_user["user_id"]
        result = await client.get(
            f"/api/v1/education/book-jobs/{book['job_id']}/statistics"
        )
        assert result.status_code == 200
        assert result.json()["job_id"] == str(UUID(str(book["job_id"])))
