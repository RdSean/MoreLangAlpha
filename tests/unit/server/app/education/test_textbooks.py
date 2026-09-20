"""Role-safe HTTP contracts for versioned family textbook routes."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.server.app.education.textbooks import router
from src.server.services.education_textbooks import TextbookPermissionError
from src.server.utils.api import get_current_user_id


TEXTBOOK = {
    "textbook_id": "bc5734a8-8a30-459f-a1f3-8551feb4c169",
    "household_id": "6eebf7fb-9579-4c5d-825a-2e595b7f1b18",
    "title": "英语第二册",
    "slug": "english-2",
    "created_by_user_id": "parent-1",
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
