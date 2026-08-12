"""Role-bound HTTP contracts for education homework endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.server.app.education.router import router
from src.server.utils.api import get_current_user_id


TASK = {
    "task_id": "bc5734a8-8a30-459f-a1f3-8551feb4c169",
    "task_rule_id": "6eebf7fb-9579-4c5d-825a-2e595b7f1b18",
    "household_id": "11056628-0d77-4c02-a1da-e692b65e629b",
    "assigned_student_id": "student-1",
    "occurrence_date": "2026-08-09",
    "due_at": datetime(2026, 8, 9, 9, tzinfo=timezone.utc),
    "title": "Read chapter one",
    "description": "Write three observations.",
    "status": "open",
}


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as session:
        yield session


@pytest.mark.asyncio
async def test_task_creation_requires_an_authenticated_parent(client):
    response = await client.post(
        "/api/v1/education/tasks",
        json={
            "assigned_student_id": "student-1",
            "title": "Read chapter one",
            "due_at": "2026-08-09T09:00:00Z",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_parent_creates_a_materialized_task_instance(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    with patch("src.server.app.education.router.create_task", new=AsyncMock(return_value=TASK)) as create:
        response = await client.post(
            "/api/v1/education/tasks",
            json={
                "assigned_student_id": "student-1",
                "title": "Read chapter one",
                "description": "Write three observations.",
                "due_at": "2026-08-09T09:00:00Z",
                "frequency": "once",
            },
        )

    assert response.status_code == 201
    assert response.json()["status"] == "open"
    assert create.await_args.kwargs["parent_user_id"] == "parent-1"


@pytest.mark.asyncio
async def test_student_submits_with_an_idempotency_key(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"
    submission = {"submission_id": "s-1", "task_id": TASK["task_id"], "sequence": 1, "submission_text": "Done"}
    with patch("src.server.app.education.router.submit_task", new=AsyncMock(return_value=submission)) as submit:
        response = await client.post(
            f"/api/v1/education/tasks/{TASK['task_id']}/submissions",
            json={"submission_text": "Done", "idempotency_key": "ec4075f0-6e7a-4f3d-bf56-c04121bbb395"},
        )

    assert response.status_code == 201
    assert response.json()["sequence"] == 1
    assert submit.await_args.kwargs["student_user_id"] == "student-1"


@pytest.mark.asyncio
async def test_parent_review_accepts_text_feedback_only(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    review = {"review_id": "r-1", "submission_id": "s-1", "decision": "revision_requested", "feedback_text": "Please add examples."}
    with patch("src.server.app.education.router.review_task", new=AsyncMock(return_value=review)) as review_task:
        response = await client.post(
            f"/api/v1/education/tasks/{TASK['task_id']}/reviews",
            json={"decision": "revision_requested", "feedback_text": "Please add examples."},
        )

    assert response.status_code == 201
    assert response.json()["feedback_text"] == "Please add examples."
    assert review_task.await_args.kwargs["parent_user_id"] == "parent-1"
