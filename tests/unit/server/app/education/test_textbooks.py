"""Role-safe HTTP contracts for versioned family textbook routes."""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.server.app.education.textbooks import router
import src.server.app.education.textbooks as textbook_routes
from src.server.services.education_textbooks import (
    TextbookNotFoundError,
    TextbookPermissionError,
    TextbookTransitionError,
)
from src.server.utils.api import get_current_user_id


TEXTBOOK = {
    "textbook_id": "bc5734a8-8a30-459f-a1f3-8551feb4c169",
    "household_id": "6eebf7fb-9579-4c5d-825a-2e595b7f1b18",
    "title": "英语第二册",
    "slug": "english-2",
    "created_by_user_id": "parent-1",
}

MANAGED_JOB_ID = UUID("9998bb1a-687a-4d45-815d-5b1dd6ed2f17")
KNOWLEDGE_POINT_ID = UUID("4c3f4d0c-a508-4bff-a89f-a3a584a2fe86")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,code",
    [
        (None, 204),
        (TextbookPermissionError("parent only"), 403),
        (TextbookNotFoundError("not found"), 404),
        (TextbookTransitionError("active"), 409),
    ],
)
async def test_delete_textbook_http_contract(client, monkeypatch, error, code):
    client._transport.app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    delete = AsyncMock(side_effect=error)
    monkeypatch.setattr(textbook_routes, "delete_managed_textbook", delete)
    response = await client.delete(
        f"/api/v1/education/textbooks/{TEXTBOOK['textbook_id']}"
    )
    assert response.status_code == code
    delete.assert_awaited_once_with(
        parent_user_id="parent-1", textbook_id=UUID(TEXTBOOK["textbook_id"])
    )
    if code == 204:
        assert not response.content


@pytest.mark.asyncio
async def test_student_learning_list_projects_postgres_textbook_uuid(
    client, monkeypatch
):
    from src.server.services import education_textbooks as textbooks

    client._transport.app.dependency_overrides[get_current_user_id] = (
        lambda: "student-1"
    )
    assignment_id = uuid4()
    structure_id = uuid4()
    monkeypatch.setattr(
        textbooks,
        "get_membership_for_user",
        AsyncMock(return_value={"role": "student"}),
    )
    monkeypatch.setattr(
        textbooks,
        "list_student_textbook_assignments",
        AsyncMock(
            return_value=[
                {
                    "assignment_id": assignment_id,
                    "textbook_id": UUID(TEXTBOOK["textbook_id"]),
                    "textbook_title": TEXTBOOK["title"],
                    "structure_id": structure_id,
                    "knowledge_point_count": 4,
                    "completed_knowledge_point_count": 1,
                    "created_at": datetime.now(timezone.utc),
                }
            ]
        ),
    )

    response = await client.get("/api/v1/education/learning")

    assert response.status_code == 200
    assert response.json()[0]["textbook_id"] == TEXTBOOK["textbook_id"]
    assert response.json()[0]["assignment_id"] == str(assignment_id)
    assert response.json()[0]["structure_id"] == str(structure_id)
    assert response.json()[0]["completed_knowledge_point_count"] == 1


def _source_candidate() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "document_id": "doc-A1b2C3d4E5f6",
        "parse_job_id": "job-A1b2C3d4E5f6",
        "primary_artifact_id": "art-A1b2C3d4E5f6",
        "filename": "English.md",
        "media_type": "text/markdown",
        "parser_id": "datalab",
        "parser_name": "Datalab",
        "completed_at": now,
        "content_sha256": "a" * 64,
        "size_bytes": 128,
        "image_count": 1,
    }


def _workbench_snapshot() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "textbook_id": TEXTBOOK["textbook_id"],
        "title": TEXTBOOK["title"],
        "structure_status": "ready",
        "materials": {"total": 1, "ready": 1},
        "current_job": None,
        "updated_at": now,
        "source": {**_source_candidate(), "frozen_at": now},
        "current_structure_id": UUID("0cf0c918-23dc-44a2-8ad7-6a8788279f3e"),
        "recent_job": None,
        "assigned_student_count": 0,
    }


def _assignment(student_user_id: str = "student-1") -> dict:
    return {
        "textbook_id": TEXTBOOK["textbook_id"],
        "student_user_id": student_user_id,
        "assigned_at": datetime.now(timezone.utc),
    }


def _managed_job_snapshot() -> dict:
    now = datetime.now(timezone.utc)
    return {
        "job_id": str(MANAGED_JOB_ID),
        "textbook_id": TEXTBOOK["textbook_id"],
        "kind": "materials",
        "status": "running",
        "total_items": 2,
        "succeeded_items": 1,
        "failed_items": 0,
        "cancelled_items": 0,
        "not_run_items": 0,
        "high_water_seq": 3,
        "activity_status": "available",
        "created_at": now,
        "started_at": now,
        "finished_at": None,
        "safe_error": None,
        "depth": "lesson",
        "requirements": None,
        "replace_existing": False,
        "include_supplementary": True,
        "items": [
            {
                "item_id": UUID("86f03a73-7604-4097-905b-768e6ad0f644"),
                "kind": "material",
                "position": 1,
                "knowledge_point_id": UUID("4c3f4d0c-a508-4bff-a89f-a3a584a2fe86"),
                "skill_kp_id": "unit-1-k1",
                "status": "succeeded",
                "attempt": 1,
                "safe_error": None,
                "started_at": now,
                "finished_at": now,
            },
            {
                "item_id": UUID("a5f8dcd6-58c8-4ea7-b3dd-a1f8bf276a63"),
                "kind": "supplementary",
                "position": 2,
                "knowledge_point_id": None,
                "skill_kp_id": None,
                "status": "running",
                "attempt": 1,
                "safe_error": None,
                "started_at": now,
                "finished_at": None,
            },
        ],
    }


def _activity_event(seq: int) -> dict:
    return {
        "seq": seq,
        "job_id": str(MANAGED_JOB_ID),
        "item_id": None,
        "kind": "tool",
        "status": "running",
        "message": f"Running tool {seq}",
        "metadata": {
            "tool_name": "Read",
            "budget_class": "detail",
            "activity_bytes": 256,
        },
        "created_at": datetime.now(timezone.utc),
    }


def _activity_page(
    *,
    events: list[dict],
    high_water_seq: int,
    status: str = "running",
    activity_status: str = "available",
    cursor_expired: bool = False,
    has_more: bool = False,
) -> dict:
    return {
        "job_id": str(MANAGED_JOB_ID),
        "status": status,
        "activity_status": activity_status,
        "events": events,
        "high_water_seq": high_water_seq,
        "cursor_expired": cursor_expired,
        "has_more": has_more,
    }


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as session:
        yield session


@pytest.mark.asyncio
async def test_parent_reads_public_managed_job_snapshot(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    with patch(
        "src.server.app.education.textbooks.get_book_job_for_parent",
        new=AsyncMock(return_value=_managed_job_snapshot()),
        create=True,
    ) as read_job:
        response = await client.get(f"/api/v1/education/book-jobs/{MANAGED_JOB_ID}")

    assert response.status_code == 200
    payload = response.json()
    assert [item["kind"] for item in payload["items"]] == [
        "material",
        "supplementary",
    ]
    assert "attempt_token" not in payload["items"][0]
    read_job.assert_awaited_once_with(
        job_id=MANAGED_JOB_ID,
        parent_user_id="parent-1",
    )


@pytest.mark.asyncio
async def test_managed_job_routes_hide_missing_or_cross_household_job(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "student-or-other-parent"
    with patch(
        "src.server.app.education.textbooks.get_book_job_for_parent",
        new=AsyncMock(return_value=None),
        create=True,
    ):
        snapshot = await client.get(f"/api/v1/education/book-jobs/{MANAGED_JOB_ID}")
        events = await client.get(
            f"/api/v1/education/book-jobs/{MANAGED_JOB_ID}/events"
        )

    assert snapshot.status_code == 404
    assert events.status_code == 404


@pytest.mark.asyncio
async def test_activity_sse_ids_follow_delivered_events_not_high_water():
    observed_after_seq: list[int] = []
    first_page_closed = asyncio.Event()

    class FakeActivityService:
        async def pages(self, *, job_id, parent_user_id, after_seq):
            observed_after_seq.append(after_seq)
            if after_seq == 0:
                try:
                    yield _activity_page(
                        events=[_activity_event(seq) for seq in range(1, 201)],
                        high_water_seq=500,
                        has_more=True,
                    )
                    await asyncio.Event().wait()
                finally:
                    first_page_closed.set()
                return
            yield _activity_page(
                events=[_activity_event(seq) for seq in range(201, 501)],
                high_water_seq=500,
                status="succeeded",
            )

    with (
        patch.object(
            textbook_routes,
            "get_book_job_for_parent",
            new=AsyncMock(return_value=_managed_job_snapshot()),
            create=True,
        ),
        patch.object(
            textbook_routes,
            "BookActivityService",
            return_value=FakeActivityService(),
            create=True,
        ),
    ):
        first = await textbook_routes.stream_managed_book_job_events(
            job_id=MANAGED_JOB_ID,
            user_id="parent-1",
            after_seq=0,
        )
        first_iterator = first.body_iterator
        first_frame = await anext(first_iterator)
        await first_iterator.aclose()

        resumed = await textbook_routes.stream_managed_book_job_events(
            job_id=MANAGED_JOB_ID,
            user_id="parent-1",
            after_seq=200,
        )
        resumed_frames = [chunk async for chunk in resumed.body_iterator]

    assert first_page_closed.is_set()
    assert first_frame.startswith("id: 200\nevent: snapshot\n")
    assert resumed_frames[0].startswith("id: 500\nevent: snapshot\n")
    assert observed_after_seq == [0, 200]
    payload = json.loads(resumed_frames[0].split("data: ", 1)[1])
    assert payload["events"][0]["seq"] == 201
    assert payload["events"][-1]["seq"] == 500
    assert "budget_class" not in payload["events"][0]["metadata"]
    assert "activity_bytes" not in payload["events"][0]["metadata"]


@pytest.mark.asyncio
async def test_activity_sse_empty_snapshot_does_not_advance_id():
    class EmptyActivityService:
        async def pages(self, **_kwargs):
            yield _activity_page(
                events=[],
                high_water_seq=9,
                activity_status="unavailable",
                cursor_expired=True,
            )

    with (
        patch.object(
            textbook_routes,
            "get_book_job_for_parent",
            new=AsyncMock(return_value=_managed_job_snapshot()),
            create=True,
        ),
        patch.object(
            textbook_routes,
            "BookActivityService",
            return_value=EmptyActivityService(),
            create=True,
        ),
    ):
        response = await textbook_routes.stream_managed_book_job_events(
            job_id=MANAGED_JOB_ID,
            user_id="parent-1",
            after_seq=4,
        )
        frames = [chunk async for chunk in response.body_iterator]

    assert frames[0].startswith("event: snapshot\n")
    assert not frames[0].startswith("id:")
    assert '"activity_status":"unavailable"' in frames[0]
    assert '"cursor_expired":true' in frames[0]


@pytest.mark.asyncio
async def test_parent_lists_managed_textbook_sources(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    with patch.object(
        textbook_routes,
        "list_book_source_candidates",
        new=AsyncMock(return_value=[_source_candidate()]),
        create=True,
    ) as list_sources:
        response = await client.get("/api/v1/education/textbook-sources")

    assert response.status_code == 200
    assert response.json()["items"][0]["parse_job_id"] == "job-A1b2C3d4E5f6"
    list_sources.assert_awaited_once_with(parent_user_id="parent-1")


@pytest.mark.asyncio
async def test_parent_accepts_managed_textbook_with_one_pinned_source(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    created = {
        "textbook_id": TEXTBOOK["textbook_id"],
        "job_id": str(MANAGED_JOB_ID),
        "acceptance": "accepted_new",
    }
    with patch.object(
        textbook_routes,
        "create_managed_textbook",
        new=AsyncMock(return_value=created),
        create=True,
    ) as create:
        response = await client.post(
            "/api/v1/education/textbooks",
            json={
                "parse_job_id": "job-A1b2C3d4E5f6",
                "primary_artifact_id": "art-A1b2C3d4E5f6",
                "title": "英语第二册",
                "idempotency_key": "create-english-2",
            },
        )

    assert response.status_code == 202
    assert response.json() == created
    create.assert_awaited_once_with(
        parent_user_id="parent-1",
        parse_job_id="job-A1b2C3d4E5f6",
        primary_artifact_id="art-A1b2C3d4E5f6",
        title="英语第二册",
        idempotency_key="create-english-2",
    )


@pytest.mark.asyncio
async def test_parent_reads_managed_workbench_and_content_without_storage_keys(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    structure = {
        "textbook_id": TEXTBOOK["textbook_id"],
        "structure_id": UUID("0cf0c918-23dc-44a2-8ad7-6a8788279f3e"),
        "schema_version": "1.0.0",
        "structure": {"schema_version": "1.0.0", "knowledge_points": []},
        "knowledge_points": [],
        "warnings": [],
    }
    source = {
        "textbook_id": TEXTBOOK["textbook_id"],
        "start_line": 2,
        "end_line": 3,
        "total_lines": 4,
        "markdown": "second\nthird",
    }
    material = {
        "textbook_id": TEXTBOOK["textbook_id"],
        "knowledge_point_id": KNOWLEDGE_POINT_ID,
        "skill_kp_id": "unit-1-k1",
        "material_available": True,
        "markdown": "# Lesson",
        "generated_at": datetime.now(timezone.utc),
        "depth": "lesson",
        "requirements": None,
        "content_sha256": "b" * 64,
    }
    with (
        patch.object(
            textbook_routes,
            "get_managed_textbook_workbench",
            new=AsyncMock(return_value=_workbench_snapshot()),
            create=True,
        ),
        patch.object(
            textbook_routes,
            "get_managed_textbook_structure",
            new=AsyncMock(return_value=structure),
            create=True,
        ),
        patch.object(
            textbook_routes,
            "get_managed_textbook_source",
            new=AsyncMock(return_value=source),
            create=True,
        ) as read_source,
        patch.object(
            textbook_routes,
            "get_managed_knowledge_point_material",
            new=AsyncMock(return_value=material),
            create=True,
        ),
    ):
        workbench_response = await client.get(
            f"/api/v1/education/textbooks/{TEXTBOOK['textbook_id']}"
        )
        structure_response = await client.get(
            f"/api/v1/education/textbooks/{TEXTBOOK['textbook_id']}/structure"
        )
        source_response = await client.get(
            f"/api/v1/education/textbooks/{TEXTBOOK['textbook_id']}/source",
            params={"start_line": 2, "end_line": 3},
        )
        material_response = await client.get(
            f"/api/v1/education/textbooks/{TEXTBOOK['textbook_id']}"
            f"/knowledge-points/{KNOWLEDGE_POINT_ID}/material"
        )

    assert workbench_response.status_code == 200
    assert structure_response.status_code == 200
    assert source_response.status_code == 200
    assert material_response.status_code == 200
    assert "storage_key" not in json.dumps(
        [
            workbench_response.json(),
            structure_response.json(),
            source_response.json(),
            material_response.json(),
        ]
    )
    read_source.assert_awaited_once_with(
        user_id="parent-1",
        textbook_id=UUID(TEXTBOOK["textbook_id"]),
        start_line=2,
        end_line=3,
    )


@pytest.mark.asyncio
async def test_managed_textbook_reads_hide_cross_household_records(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "other-parent"
    with patch.object(
        textbook_routes,
        "get_managed_textbook_workbench",
        new=AsyncMock(side_effect=TextbookNotFoundError("Textbook not found")),
        create=True,
    ):
        response = await client.get(
            f"/api/v1/education/textbooks/{TEXTBOOK['textbook_id']}"
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_managed_asset_response_is_private_and_digest_bound(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    with patch.object(
        textbook_routes,
        "open_managed_textbook_asset",
        new=AsyncMock(
            return_value={
                "content": b"png-bytes",
                "media_type": "image/png",
                "sha256": "d" * 64,
            }
        ),
        create=True,
    ) as open_asset:
        response = await client.get(
            f"/api/v1/education/textbooks/{TEXTBOOK['textbook_id']}"
            "/assets/art-I1m2A3g4E5f6"
        )

    assert response.status_code == 200
    assert response.content == b"png-bytes"
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"].startswith("private")
    assert response.headers["etag"] == f'"{"d" * 64}"'
    open_asset.assert_awaited_once_with(
        user_id="parent-1",
        textbook_id=UUID(TEXTBOOK["textbook_id"]),
        asset_id="art-I1m2A3g4E5f6",
    )


@pytest.mark.asyncio
async def test_parent_creates_cancels_and_retries_managed_book_jobs(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    create_job = AsyncMock(return_value=_managed_job_snapshot())
    cancel_job = AsyncMock(return_value=_managed_job_snapshot())
    retry_job = AsyncMock(return_value=_managed_job_snapshot())
    with (
        patch.object(
            textbook_routes,
            "create_managed_textbook_job",
            new=create_job,
            create=True,
        ),
        patch.object(
            textbook_routes,
            "cancel_managed_textbook_job",
            new=cancel_job,
            create=True,
        ),
        patch.object(
            textbook_routes,
            "retry_managed_textbook_job",
            new=retry_job,
            create=True,
        ),
    ):
        created = await client.post(
            f"/api/v1/education/textbooks/{TEXTBOOK['textbook_id']}/jobs",
            json={
                "kind": "materials",
                "knowledge_point_ids": [str(KNOWLEDGE_POINT_ID)],
                "depth": "lesson",
                "requirements": "Include examples",
                "replace_existing": False,
                "include_supplementary": True,
                "idempotency_key": "materials-1",
            },
        )
        cancelled = await client.post(
            f"/api/v1/education/book-jobs/{MANAGED_JOB_ID}/cancel"
        )
        retried = await client.post(
            f"/api/v1/education/book-jobs/{MANAGED_JOB_ID}/retry"
        )

    assert created.status_code == 202
    assert cancelled.status_code == 200
    assert retried.status_code == 202
    assert create_job.await_args.kwargs["parent_user_id"] == "parent-1"
    assert create_job.await_args.kwargs["textbook_id"] == UUID(TEXTBOOK["textbook_id"])
    assert create_job.await_args.kwargs["request"].kind == "materials"
    cancel_job.assert_awaited_once_with(
        parent_user_id="parent-1", job_id=MANAGED_JOB_ID
    )
    retry_job.assert_awaited_once_with(parent_user_id="parent-1", job_id=MANAGED_JOB_ID)


@pytest.mark.asyncio
async def test_parent_lists_assigns_and_revokes_managed_textbook_students(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    list_assignments = AsyncMock(return_value=[_assignment()])
    assign = AsyncMock(return_value=[_assignment(), _assignment("student-2")])
    revoke = AsyncMock(return_value=None)
    with (
        patch.object(
            textbook_routes,
            "list_managed_textbook_assignments",
            new=list_assignments,
            create=True,
        ),
        patch.object(
            textbook_routes,
            "assign_managed_textbook",
            new=assign,
            create=True,
        ),
        patch.object(
            textbook_routes,
            "revoke_managed_textbook",
            new=revoke,
            create=True,
        ),
    ):
        listed = await client.get(
            f"/api/v1/education/textbooks/{TEXTBOOK['textbook_id']}/assignments"
        )
        assigned = await client.post(
            f"/api/v1/education/textbooks/{TEXTBOOK['textbook_id']}/assignments",
            json={"student_user_ids": ["student-1", "student-2"]},
        )
        revoked = await client.request(
            "DELETE",
            f"/api/v1/education/textbooks/{TEXTBOOK['textbook_id']}/assignments",
            json={"student_user_ids": ["student-2"]},
        )

    assert listed.status_code == 200
    assert assigned.status_code == 200
    assert [row["student_user_id"] for row in assigned.json()] == [
        "student-1",
        "student-2",
    ]
    assert revoked.status_code == 204
    list_assignments.assert_awaited_once_with(
        parent_user_id="parent-1",
        textbook_id=UUID(TEXTBOOK["textbook_id"]),
    )
    assert assign.await_args.kwargs["student_user_ids"] == ["student-1", "student-2"]
    assert revoke.await_args.kwargs["student_user_ids"] == ["student-2"]


@pytest.mark.asyncio
async def test_assigned_student_reads_content_but_cannot_create_jobs(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"
    source = {
        "textbook_id": TEXTBOOK["textbook_id"],
        "start_line": 1,
        "end_line": 1,
        "total_lines": 1,
        "markdown": "lesson",
    }
    read_source = AsyncMock(return_value=source)
    create_job = AsyncMock(side_effect=TextbookNotFoundError("Textbook not found"))
    with (
        patch.object(
            textbook_routes,
            "get_managed_textbook_source",
            new=read_source,
        ),
        patch.object(
            textbook_routes,
            "create_managed_textbook_job",
            new=create_job,
        ),
    ):
        readable = await client.get(
            f"/api/v1/education/textbooks/{TEXTBOOK['textbook_id']}/source",
            params={"start_line": 1, "end_line": 1},
        )
        forbidden = await client.post(
            f"/api/v1/education/textbooks/{TEXTBOOK['textbook_id']}/jobs",
            json={
                "kind": "materials",
                "knowledge_point_ids": [str(KNOWLEDGE_POINT_ID)],
                "depth": "lesson",
                "requirements": None,
                "replace_existing": False,
                "include_supplementary": False,
                "idempotency_key": "student-job",
            },
        )

    assert readable.status_code == 200
    assert forbidden.status_code == 404
    read_source.assert_awaited_once_with(
        user_id="student-1",
        textbook_id=UUID(TEXTBOOK["textbook_id"]),
        start_line=1,
        end_line=1,
    )


@pytest.mark.asyncio
async def test_student_cannot_create_or_publish_a_textbook(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"
    with patch(
        "src.server.app.education.textbooks.create_managed_textbook",
        new=AsyncMock(
            side_effect=TextbookPermissionError(
                "Only a parent can create family textbooks"
            )
        ),
    ):
        response = await client.post(
            "/api/v1/education/textbooks",
            json={
                "parse_job_id": "job-A1b2C3d4E5f6",
                "primary_artifact_id": "art-A1b2C3d4E5f6",
                "title": "英语第二册",
                "idempotency_key": "student-create",
            },
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_parent_create_serializes_uuid_identifiers_from_database(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    textbook_id = uuid4()
    job_id = uuid4()
    created = {
        "textbook_id": textbook_id,
        "job_id": job_id,
    }
    with patch(
        "src.server.app.education.textbooks.create_managed_textbook",
        new=AsyncMock(return_value=created),
    ):
        response = await client.post(
            "/api/v1/education/textbooks",
            json={
                "parse_job_id": "job-A1b2C3d4E5f6",
                "primary_artifact_id": "art-A1b2C3d4E5f6",
                "title": "英语第二册",
                "idempotency_key": "create-uuid",
            },
        )

    assert response.status_code == 202
    assert response.json()["textbook_id"] == str(textbook_id)
    assert response.json()["job_id"] == str(job_id)


@pytest.mark.asyncio
async def test_student_gets_the_canonical_learning_chat_space(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"
    assignment_id = "bc5734a8-8a30-459f-a1f3-8551feb4c169"
    space = {
        "assignment_id": assignment_id,
        "conversation_thread_id": "6eebf7fb-9579-4c5d-825a-2e595b7f1b18",
        "workspace_id": "7b1f5807-6a0e-4cf2-aac8-07873c0b5830",
    }
    with patch(
        "src.server.app.education.textbooks.get_learning_chat_space",
        new=AsyncMock(return_value=space),
    ) as get_space:
        response = await client.get(
            f"/api/v1/education/learning/{assignment_id}/chat-space"
        )

    assert response.status_code == 200
    assert response.json()["conversation_thread_id"] == space["conversation_thread_id"]
    get_space.assert_awaited_once_with(user_id="student-1", assignment_id=assignment_id)


@pytest.mark.asyncio
async def test_parent_reads_assignment_chat_transcript_without_a_write_route(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    assignment_id = "bc5734a8-8a30-459f-a1f3-8551feb4c169"
    transcript = {
        "assignment_id": assignment_id,
        "conversation_thread_id": "6eebf7fb-9579-4c5d-825a-2e595b7f1b18",
        "messages": [{"role": "user", "content": "问题", "timestamp": "t1"}],
    }
    with patch(
        "src.server.app.education.textbooks.get_parent_learning_transcript",
        new=AsyncMock(return_value=transcript),
    ) as get_transcript:
        response = await client.get(
            f"/api/v1/education/learning/{assignment_id}/chat-transcript"
        )

    assert response.status_code == 200
    assert response.json()["messages"] == transcript["messages"]
    get_transcript.assert_awaited_once_with(
        parent_user_id="parent-1", assignment_id=assignment_id
    )
