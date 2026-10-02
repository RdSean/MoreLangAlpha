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
from src.server.services.education_textbooks import TextbookPermissionError
from src.server.utils.api import get_current_user_id


TEXTBOOK = {
    "textbook_id": "bc5734a8-8a30-459f-a1f3-8551feb4c169",
    "household_id": "6eebf7fb-9579-4c5d-825a-2e595b7f1b18",
    "title": "英语第二册",
    "slug": "english-2",
    "created_by_user_id": "parent-1",
}

MANAGED_JOB_ID = UUID("9998bb1a-687a-4d45-815d-5b1dd6ed2f17")


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
async def test_student_cannot_create_or_publish_a_textbook(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"
    with patch(
        "src.server.app.education.textbooks.create_textbook",
        new=AsyncMock(
            side_effect=TextbookPermissionError(
                "Only a parent can create family textbooks"
            )
        ),
    ):
        response = await client.post(
            "/api/v1/education/textbooks", json={"title": "英语第二册"}
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_parent_creates_textbook_and_starts_explicit_processing(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    job = {
        "job_id": "6eebf7fb-9579-4c5d-825a-2e595b7f1b18",
        "version_id": "65f47c8c-f452-47bd-8619-58ccd2a1f10c",
        "status": "queued",
    }
    with (
        patch(
            "src.server.app.education.textbooks.create_textbook",
            new=AsyncMock(return_value=TEXTBOOK),
        ) as create,
        patch(
            "src.server.app.education.textbooks.start_processing",
            new=AsyncMock(return_value=job),
        ) as start,
    ):
        created = await client.post(
            "/api/v1/education/textbooks", json={"title": "英语第二册"}
        )
        queued = await client.post(
            f"/api/v1/education/textbooks/{TEXTBOOK['textbook_id']}/processing",
            json={"source_asset_ids": ["bc5734a8-8a30-459f-a1f3-8551feb4c169"]},
        )

    assert created.status_code == 201
    assert queued.status_code == 202
    assert create.await_args.kwargs["parent_user_id"] == "parent-1"
    assert start.await_args.kwargs["source_asset_ids"] == [
        "bc5734a8-8a30-459f-a1f3-8551feb4c169"
    ]


@pytest.mark.asyncio
async def test_parent_starts_processing_from_parse_jobs_with_the_new_service(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    job = {
        "job_id": "6eebf7fb-9579-4c5d-825a-2e595b7f1b18",
        "version_id": "65f47c8c-f452-47bd-8619-58ccd2a1f10c",
        "status": "queued",
    }
    with patch(
        "src.server.app.education.textbooks.start_processing_from_parse_jobs",
        new=AsyncMock(return_value=job),
        create=True,
    ) as start:
        response = await client.post(
            f"/api/v1/education/textbooks/{TEXTBOOK['textbook_id']}/processing",
            json={"source_parse_job_ids": ["job-A1b2C3d4E5f6"]},
        )

    assert response.status_code == 202
    start.assert_awaited_once_with(
        parent_user_id="parent-1",
        textbook_id=TEXTBOOK["textbook_id"],
        source_parse_job_ids=["job-A1b2C3d4E5f6"],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {},
        {
            "source_asset_ids": ["bc5734a8-8a30-459f-a1f3-8551feb4c169"],
            "source_parse_job_ids": ["job-A1b2C3d4E5f6"],
        },
    ],
)
async def test_textbook_processing_requires_exactly_one_source_selection(client, body):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    legacy = AsyncMock()
    parse_jobs = AsyncMock()
    with (
        patch(
            "src.server.app.education.textbooks.start_processing",
            new=legacy,
        ),
        patch(
            "src.server.app.education.textbooks.start_processing_from_parse_jobs",
            new=parse_jobs,
            create=True,
        ),
    ):
        response = await client.post(
            f"/api/v1/education/textbooks/{TEXTBOOK['textbook_id']}/processing",
            json=body,
        )

    assert response.status_code == 422
    legacy.assert_not_awaited()
    parse_jobs.assert_not_awaited()


@pytest.mark.asyncio
async def test_parent_create_serializes_uuid_identifiers_from_database(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    textbook_id = uuid4()
    household_id = uuid4()
    textbook = {
        "textbook_id": textbook_id,
        "household_id": household_id,
        "title": "英语第二册",
        "slug": "english-2",
        "created_by_user_id": "parent-1",
    }
    with patch(
        "src.server.app.education.textbooks.create_textbook",
        new=AsyncMock(return_value=textbook),
    ):
        response = await client.post(
            "/api/v1/education/textbooks", json={"title": "英语第二册"}
        )

    assert response.status_code == 201
    assert response.json()["textbook_id"] == str(textbook_id)
    assert response.json()["household_id"] == str(household_id)


@pytest.mark.asyncio
async def test_parent_detail_exposes_safe_review_sources_and_page_mappings(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    version_id = uuid4()
    source_id = uuid4()
    chapter_id = uuid4()
    question_id = uuid4()
    detail = {
        **TEXTBOOK,
        "versions": [
            {
                "version_id": version_id,
                "sequence": 1,
                "status": "review",
                "extractor_name": "local_pypdf",
                "extractor_version": "1",
                "processing_error": None,
                "processing_job_id": None,
                "processing_job_status": None,
                "processing_attempt_count": None,
                "chapter_count": 1,
                "is_published": False,
                "publication_id": None,
                "sources": [
                    {
                        "legacy": True,
                        "position": 1,
                        "asset_id": source_id,
                        "original_filename": "body.pdf",
                        "content_type": "application/pdf",
                        "size_bytes": 12,
                        "storage_key": "education/private/body.pdf",
                    }
                ],
                "chapters": [
                    {
                        "chapter_id": chapter_id,
                        "position": 1,
                        "slug": "01-introduction",
                        "title": "导读",
                        "page_start": 1,
                        "page_end": 10,
                        "markdown": "# 教材正文",
                        "teaching_material": "# 学习材料",
                        "questions": [
                            {
                                "question_id": question_id,
                                "position": 1,
                                "prompt": "下一步做什么？",
                                "options": {"A": "完成知识检查"},
                                "correct_option": "A",
                                "explanation": "形成学习证据。",
                                "knowledge_point": "学习证据",
                            }
                        ],
                    }
                ],
                "assignments": [],
            }
        ],
    }
    with patch(
        "src.server.app.education.textbooks.get_parent_textbook",
        new=AsyncMock(return_value=detail),
    ):
        response = await client.get(
            f"/api/v1/education/textbooks/{TEXTBOOK['textbook_id']}"
        )

    assert response.status_code == 200
    assert response.json()["versions"][0]["sources"] == [
        {
            "legacy": True,
            "position": 1,
            "asset_id": str(source_id),
            "original_filename": "body.pdf",
            "content_type": "application/pdf",
            "size_bytes": 12,
        }
    ]
    assert response.json()["versions"][0]["chapters"][0]["page_start"] == 1
    assert "storage_key" not in response.text


@pytest.mark.asyncio
async def test_parent_detail_exposes_safe_frozen_artifact_sources(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    version_id = uuid4()
    detail = {
        **TEXTBOOK,
        "versions": [
            {
                "version_id": version_id,
                "sequence": 1,
                "status": "failed",
                "chapter_count": 0,
                "is_published": False,
                "publication_id": None,
                "processing_error": "sandbox unavailable",
                "sources": [
                    {
                        "legacy": False,
                        "position": 1,
                        "document_id": "doc-A1b2C3d4E5f6",
                        "producer_job_id": "job-A1b2C3d4E5f6",
                        "primary_artifact_id": "art-A1b2C3d4E5f6",
                        "filename": "textbook.pdf",
                        "media_type": "application/pdf",
                        "format": "pdf",
                        "parser_id": "datalab",
                        "parser_name": "Datalab",
                        "parser_version": "2",
                        "parse_completed_at": "2026-09-16T10:00:00Z",
                        "primary_sha256": "a" * 64,
                        "document_deleted": False,
                        "document_accessible": True,
                        "snapshot_prefix": "education/private/secret/",
                        "storage_key": "documents/private/secret.md",
                    }
                ],
                "chapters": [],
                "assignments": [],
            }
        ],
    }
    with patch(
        "src.server.app.education.textbooks.get_parent_textbook",
        new=AsyncMock(return_value=detail),
    ):
        response = await client.get(
            f"/api/v1/education/textbooks/{TEXTBOOK['textbook_id']}"
        )

    assert response.status_code == 200
    assert response.json()["versions"][0]["sources"] == [
        {
            "legacy": False,
            "position": 1,
            "document_id": "doc-A1b2C3d4E5f6",
            "producer_job_id": "job-A1b2C3d4E5f6",
            "primary_artifact_id": "art-A1b2C3d4E5f6",
            "filename": "textbook.pdf",
            "media_type": "application/pdf",
            "format": "pdf",
            "parser_id": "datalab",
            "parser_name": "Datalab",
            "parser_version": "2",
            "parse_completed_at": "2026-09-16T10:00:00Z",
            "primary_sha256": "a" * 64,
            "document_deleted": False,
            "document_accessible": True,
        }
    ]
    assert "snapshot_prefix" not in response.text
    assert "storage_key" not in response.text


@pytest.mark.asyncio
async def test_parent_lists_only_safe_completed_parse_job_candidates(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    candidates = [
        {
            "producer_job_id": "job-A1b2C3d4E5f6",
            "document_id": "doc-A1b2C3d4E5f6",
            "primary_artifact_id": "art-A1b2C3d4E5f6",
            "filename": "textbook.pdf",
            "media_type": "application/pdf",
            "format": "pdf",
            "parser_id": "datalab",
            "parser_name": "Datalab",
            "parser_version": "2",
            "parse_completed_at": "2026-09-16T10:00:00Z",
            "size_bytes": 2048,
            "artifact_count": 4,
            "storage_key": "documents/private/secret.md",
        }
    ]
    with patch(
        "src.server.app.education.textbooks.list_completed_textbook_parse_jobs",
        new=AsyncMock(return_value=candidates),
        create=True,
    ) as listed:
        response = await client.get("/api/v1/education/textbook-parse-jobs/completed")

    assert response.status_code == 200
    assert response.json() == [
        {
            "producer_job_id": "job-A1b2C3d4E5f6",
            "document_id": "doc-A1b2C3d4E5f6",
            "primary_artifact_id": "art-A1b2C3d4E5f6",
            "filename": "textbook.pdf",
            "media_type": "application/pdf",
            "format": "pdf",
            "parser_id": "datalab",
            "parser_name": "Datalab",
            "parser_version": "2",
            "parse_completed_at": "2026-09-16T10:00:00Z",
            "size_bytes": 2048,
            "artifact_count": 4,
        }
    ]
    listed.assert_awaited_once_with(parent_user_id="parent-1")


@pytest.mark.asyncio
async def test_parent_can_requeue_only_a_failed_processing_job(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    job_id = "6eebf7fb-9579-4c5d-825a-2e595b7f1b18"
    response_job = {
        "job_id": job_id,
        "version_id": "65f47c8c-f452-47bd-8619-58ccd2a1f10c",
        "status": "queued",
        "attempt_count": 2,
    }
    with patch(
        "src.server.app.education.textbooks.retry_processing_for_parent",
        new=AsyncMock(return_value=response_job),
    ) as retry:
        response = await client.post(
            f"/api/v1/education/textbook-processing/{job_id}/retry"
        )

    assert response.status_code == 202
    retry.assert_awaited_once_with(parent_user_id="parent-1", job_id=job_id)


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
