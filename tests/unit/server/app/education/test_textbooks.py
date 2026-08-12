"""Role-safe HTTP contracts for versioned family textbook routes."""

from unittest.mock import AsyncMock, patch

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
        "version_id": "version-1",
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
        "version_id": "version-1",
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
