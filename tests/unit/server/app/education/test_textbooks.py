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
async def test_textbook_mutations_serialize_uuid_identifiers_from_database(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    textbook_id = uuid4()
    version_id = uuid4()
    job_id = uuid4()
    publication_id = uuid4()
    assignment_id = uuid4()
    chapter_id = uuid4()
    question_id = uuid4()
    teaching_package_id = uuid4()
    answer_id = uuid4()
    job = {"job_id": job_id, "version_id": version_id, "status": "queued"}
    publication = {
        "publication_id": publication_id,
        "version_id": version_id,
        "teaching_package_id": teaching_package_id,
    }
    assignment = {
        "assignment_id": assignment_id,
        "publication_id": publication_id,
        "student_user_id": "student-1",
    }
    progress = {
        "assignment_id": assignment_id,
        "chapter_id": chapter_id,
        "status": "learning",
    }
    answer = {
        "answer_id": answer_id,
        "assignment_id": assignment_id,
        "question_id": question_id,
        "selected_option": "A",
        "is_correct": True,
    }
    with (
        patch(
            "src.server.app.education.textbooks.start_processing",
            new=AsyncMock(return_value=job),
        ),
        patch(
            "src.server.app.education.textbooks.publish_version",
            new=AsyncMock(return_value=publication),
        ),
        patch(
            "src.server.app.education.textbooks.assign_publication",
            new=AsyncMock(return_value=assignment),
        ),
        patch(
            "src.server.app.education.textbooks.record_learning_progress",
            new=AsyncMock(return_value=progress),
        ),
        patch(
            "src.server.app.education.textbooks.answer_learning_question",
            new=AsyncMock(return_value=answer),
        ),
    ):
        queued = await client.post(
            f"/api/v1/education/textbooks/{textbook_id}/processing",
            json={"source_asset_ids": [str(uuid4())]},
        )
        published = await client.post(
            f"/api/v1/education/textbooks/{textbook_id}/versions/{version_id}/publish",
            json={"teaching_package_id": str(teaching_package_id)},
        )
        assigned = await client.post(
            f"/api/v1/education/textbook-publications/{publication_id}/assignments",
            json={"student_user_id": "student-1"},
        )
        recorded = await client.post(
            f"/api/v1/education/learning/{assignment_id}/chapters/{chapter_id}/progress",
            json={"status": "learning"},
        )
        answered = await client.post(
            f"/api/v1/education/learning/{assignment_id}/questions/{question_id}/answers",
            json={"selected_option": "A"},
        )

    for response, identifier in (
        (queued, job_id),
        (published, publication_id),
        (assigned, assignment_id),
        (recorded, assignment_id),
        (answered, answer_id),
    ):
        assert response.status_code in {200, 201, 202}
        assert str(identifier) in response.text


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
            "asset_id": str(source_id),
            "original_filename": "body.pdf",
            "content_type": "application/pdf",
            "size_bytes": 12,
        }
    ]
    assert response.json()["versions"][0]["chapters"][0]["page_start"] == 1
    assert "storage_key" not in response.text


@pytest.mark.asyncio
async def test_student_reader_returns_only_assigned_published_content(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"
    learning = {
        "assignment_id": "bc5734a8-8a30-459f-a1f3-8551feb4c169",
        "textbook_title": "英语第二册",
        "chapters": [
            {
                "chapter_id": "6eebf7fb-9579-4c5d-825a-2e595b7f1b18",
                "title": "导读",
                "markdown": "# 导读",
                "questions": [],
            }
        ],
    }
    with patch(
        "src.server.app.education.textbooks.get_student_learning",
        new=AsyncMock(return_value=learning),
    ) as read:
        response = await client.get(
            f"/api/v1/education/learning/{learning['assignment_id']}"
        )

    assert response.status_code == 200
    assert response.json()["chapters"][0]["markdown"] == "# 导读"
    assert read.await_args.kwargs == {
        "student_user_id": "student-1",
        "assignment_id": learning["assignment_id"],
    }


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
async def test_parent_starts_a_managed_teaching_package_for_own_reviewed_content(
    client,
):
    """The route delegates only the parent identity and immutable content version."""
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    content_version_id = uuid4()
    job_id = uuid4()
    teaching_package_id = uuid4()
    projected_job = {
        "job_id": job_id,
        "teaching_package_id": teaching_package_id,
        "content_version_id": content_version_id,
        "status": "running",
        "phase": "preparing",
        "attempt_count": 1,
        "completed_chapter_count": 0,
        "total_chapter_count": 2,
        "actions": ["cancel"],
        "events": [],
        "attempts": [],
    }
    with patch(
        "src.server.app.education.textbooks.queue_teaching_package_for_parent",
        new=AsyncMock(return_value=projected_job),
        create=True,
    ) as start:
        response = await client.post(
            f"/api/v1/education/textbook-versions/{content_version_id}/teaching-packages"
        )

    assert response.status_code == 202
    assert response.json()["status"] == "running"
    start.assert_awaited_once_with(
        parent_user_id="parent-1", content_version_id=str(content_version_id)
    )


@pytest.mark.asyncio
async def test_student_cannot_read_or_cancel_a_managed_teaching_job(client):
    """Teaching runs are parent-only even when the job id is known."""
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"
    job_id = uuid4()
    denied = TextbookPermissionError("Only a parent can manage teaching jobs")
    with (
        patch(
            "src.server.app.education.textbooks.get_teaching_job_projection",
            new=AsyncMock(side_effect=denied),
            create=True,
        ),
        patch(
            "src.server.app.education.textbooks.cancel_teaching_job_for_parent",
            new=AsyncMock(side_effect=denied),
            create=True,
        ),
    ):
        read = await client.get(f"/api/v1/education/teaching-jobs/{job_id}")
        cancelled = await client.post(
            f"/api/v1/education/teaching-jobs/{job_id}/cancel"
        )

    assert read.status_code == 403
    assert cancelled.status_code == 403


@pytest.mark.asyncio
async def test_teaching_job_response_whitelists_the_safe_progress_projection(client):
    """The public job contract must not forward storage or managed-run details."""
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    job_id = uuid4()
    response_job = {
        "job_id": job_id,
        "teaching_package_id": uuid4(),
        "content_version_id": uuid4(),
        "status": "generating_teaching",
        "phase": "generating_teaching",
        "attempt_count": 2,
        "completed_chapter_count": 1,
        "total_chapter_count": 3,
        "actions": ["cancel"],
        "events": [
            {
                "sequence": 2,
                "phase": "generating_teaching",
                "summary": "已完成第 1 章教学材料生成",
                "asset_kind": "teaching",
                "storage_key": "education/private/source.pdf",
                "raw_sse": "data: secret",
            }
        ],
        "attempts": [
            {
                "attempt_id": uuid4(),
                "root_run_id": uuid4(),
                "status": "running",
                "managed_workspace_id": uuid4(),
                "managed_path": "/managed/textbook-job/private",
            }
        ],
        "storage_key": "education/private/package",
        "minio_url": "http://minio.invalid/private",
        "managed_path": "/managed/textbook-job/private",
    }
    with patch(
        "src.server.app.education.textbooks.get_teaching_job_projection",
        new=AsyncMock(return_value=response_job),
        create=True,
    ):
        response = await client.get(f"/api/v1/education/teaching-jobs/{job_id}")

    assert response.status_code == 200
    assert response.json()["events"] == [
        {
            "sequence": 2,
            "phase": "generating_teaching",
            "summary": "已完成第 1 章教学材料生成",
            "chapter_id": None,
            "asset_kind": "teaching",
            "created_at": None,
        }
    ]
    assert "storage_key" not in response.text
    assert "minio" not in response.text.lower()
    assert "/managed/" not in response.text


@pytest.mark.asyncio
async def test_student_chapter_context_requires_their_published_assignment(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"
    assignment_id = "bc5734a8-8a30-459f-a1f3-8551feb4c169"
    chapter_id = "6eebf7fb-9579-4c5d-825a-2e595b7f1b18"
    context = {
        "assignment_id": assignment_id,
        "chapter_id": chapter_id,
        "content": "# 导读",
    }
    with patch(
        "src.server.app.education.textbooks.get_student_chapter_context",
        new=AsyncMock(return_value=context),
    ) as get_context:
        response = await client.get(
            f"/api/v1/education/learning/{assignment_id}/chapters/{chapter_id}/context"
        )

    assert response.status_code == 200
    assert response.json()["content"] == "# 导读"
    get_context.assert_awaited_once_with(
        student_user_id="student-1", assignment_id=assignment_id, chapter_id=chapter_id
    )


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
