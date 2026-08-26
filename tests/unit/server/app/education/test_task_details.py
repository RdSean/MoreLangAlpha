"""HTTP contracts for role-scoped homework task detail timelines."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.server.app.education.router import router
from src.server.services.education_tasks import EducationTaskNotFoundError
from src.server.utils.api import get_current_user_id


TASK_ID = "bc5734a8-8a30-459f-a1f3-8551feb4c169"
DETAIL = {
    "task_id": TASK_ID,
    "task_rule_id": "6eebf7fb-9579-4c5d-825a-2e595b7f1b18",
    "household_id": "11056628-0d77-4c02-a1da-e692b65e629b",
    "assigned_student_id": "student-1",
    "occurrence_date": "2026-08-09",
    "due_at": datetime(2026, 8, 9, 9, tzinfo=timezone.utc),
    "title": "Read chapter one",
    "description": "Write three observations.",
    "subject_code": "chinese",
    "type_code": "read",
    "grade_code": "g5",
    "status": "completed",
    "completed_at": datetime(2026, 8, 9, 8, tzinfo=timezone.utc),
    "parent_materials": [
        {
            "asset_id": "c0b32d33-cccb-4a80-a706-59ef75c2fd85",
            "original_filename": "instructions.pdf",
            "content_type": "application/pdf",
            "size_bytes": 200,
            "created_at": datetime(2026, 8, 8, tzinfo=timezone.utc),
            "download_endpoint": "/api/v1/education/assets/c0b32d33-cccb-4a80-a706-59ef75c2fd85/download",
        },
        {
            "asset_id": "11056628-0d77-4c02-a1da-e692b65e629b",
            "original_filename": "reference.png",
            "content_type": "image/png",
            "size_bytes": 100,
            "created_at": datetime(2026, 8, 8, 1, tzinfo=timezone.utc),
            "download_endpoint": "/api/v1/education/assets/11056628-0d77-4c02-a1da-e692b65e629b/download",
        },
    ],
    "submissions": [
        {
            "submission_id": "f7621c7f-32d9-4f91-ae5e-68b4a48ae449",
            "task_id": TASK_ID,
            "submitted_by_user_id": "student-1",
            "sequence": 1,
            "submission_kind": "check_in",
            "submission_text": "Done",
            "created_at": datetime(2026, 8, 9, 8, tzinfo=timezone.utc),
            "assets": [
                {
                    "asset_id": "b7d68290-57bc-49ab-86b5-4fec27cbd5b1",
                    "original_filename": "answer-1.jpg",
                    "content_type": "image/jpeg",
                    "size_bytes": 300,
                    "created_at": datetime(2026, 8, 9, 8, tzinfo=timezone.utc),
                    "download_endpoint": "/api/v1/education/assets/b7d68290-57bc-49ab-86b5-4fec27cbd5b1/download",
                },
                {
                    "asset_id": "7cf41fd8-3461-44ed-859a-fbe01f26bb3d",
                    "original_filename": "answer-2.pdf",
                    "content_type": "application/pdf",
                    "size_bytes": 400,
                    "created_at": datetime(2026, 8, 9, 8, 1, tzinfo=timezone.utc),
                    "download_endpoint": "/api/v1/education/assets/7cf41fd8-3461-44ed-859a-fbe01f26bb3d/download",
                },
            ],
            "reviews": [
                {
                    "review_id": "f0227a9a-2d6c-4554-b89a-c1e2fecd1a91",
                    "submission_id": "f7621c7f-32d9-4f91-ae5e-68b4a48ae449",
                    "reviewed_by_user_id": "parent-1",
                    "decision": "revision_requested",
                    "feedback_text": "Please add examples.",
                    "created_at": datetime(2026, 8, 9, 10, tzinfo=timezone.utc),
                },
                {
                    "review_id": "e77eb99c-1039-4d5a-bde5-2e4f1b38eb38",
                    "submission_id": "f7621c7f-32d9-4f91-ae5e-68b4a48ae449",
                    "reviewed_by_user_id": "parent-1",
                    "decision": "feedback",
                    "feedback_text": "Nice revision plan.",
                    "created_at": datetime(2026, 8, 9, 11, tzinfo=timezone.utc),
                },
            ],
        },
        {
            "submission_id": "df95b828-a1cc-4a8e-bb26-bc5208722fc2",
            "task_id": TASK_ID,
            "submitted_by_user_id": "student-1",
            "sequence": 2,
            "submission_kind": "revision",
            "submission_text": "Added examples",
            "created_at": datetime(2026, 8, 9, 12, tzinfo=timezone.utc),
            "assets": [],
            "reviews": [],
        },
    ],
}


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as session:
        yield session


@pytest.mark.asyncio
async def test_parent_task_detail_keeps_materials_and_submissions_separate(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    with patch(
        "src.server.app.education.router.get_task_detail",
        new=AsyncMock(return_value=DETAIL),
    ) as get_detail:
        response = await client.get(f"/api/v1/education/tasks/{TASK_ID}")

    assert response.status_code == 200
    payload = response.json()
    assert [asset["original_filename"] for asset in payload["parent_materials"]] == [
        "instructions.pdf", "reference.png"
    ]
    assert [submission["sequence"] for submission in payload["submissions"]] == [1, 2]
    assert [asset["original_filename"] for asset in payload["submissions"][0]["assets"]] == [
        "answer-1.jpg", "answer-2.pdf"
    ]
    assert [review["decision"] for review in payload["submissions"][0]["reviews"]] == [
        "revision_requested", "feedback"
    ]
    assert "storage_key" not in response.text
    assert "download_endpoint" in payload["parent_materials"][0]
    assert get_detail.await_args.kwargs == {"user_id": "parent-1", "task_id": TASK_ID}


@pytest.mark.asyncio
async def test_assigned_student_can_read_the_same_task_detail(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"
    with patch(
        "src.server.app.education.router.get_task_detail",
        new=AsyncMock(return_value=DETAIL),
    ) as get_detail:
        response = await client.get(f"/api/v1/education/tasks/{TASK_ID}")

    assert response.status_code == 200
    assert response.json()["submissions"][1]["submission_kind"] == "revision"
    assert get_detail.await_args.kwargs["user_id"] == "student-1"


@pytest.mark.asyncio
async def test_task_detail_hides_cross_household_or_unassigned_student_tasks(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "other-student"
    with patch(
        "src.server.app.education.router.get_task_detail",
        new=AsyncMock(side_effect=EducationTaskNotFoundError("not found")),
    ):
        response = await client.get(f"/api/v1/education/tasks/{TASK_ID}")

    assert response.status_code == 404
    assert response.json()["detail"] == "Homework task not found"
