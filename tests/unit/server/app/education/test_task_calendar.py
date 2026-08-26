"""HTTP contracts for role-bound homework calendar summaries."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.server.app.education.router import router
from src.server.services.education_tasks import EducationTaskNotFoundError
from src.server.utils.api import get_current_user_id


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as session:
        yield session


@pytest.mark.asyncio
async def test_parent_reads_calendar_with_colored_daily_task_summaries(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    calendar = {
        "student_id": "student-1",
        "start_date": "2026-08-01",
        "end_date": "2026-08-31",
        "days": [
            {
                "date": "2026-08-01",
                "task_count": 1,
                "completed_count": 0,
                "overdue_count": 1,
                "tasks": [
                        {
                            "task_id": "bc5734a8-8a30-459f-a1f3-8551feb4c169",
                            "task_rule_id": "6eebf7fb-9579-4c5d-825a-2e595b7f1b18",
                            "household_id": "11056628-0d77-4c02-a1da-e692b65e629b",
                            "assigned_student_id": "student-1",
                            "occurrence_date": "2026-08-01",
                            "due_at": datetime(2026, 8, 1, 9, tzinfo=timezone.utc),
                            "title": "Read chapter one",
                            "description": "",
                        "subject_code": "chinese",
                        "subject_color": "#D95D39",
                        "type_code": "read",
                            "status": "open",
                            "completed_at": None,
                            "is_completed": False,
                            "is_overdue": True,
                    }
                ],
            }
        ],
        "stats": {"today_count": 1, "week_count": 2, "overdue_count": 3, "completed_count": 4},
    }
    with patch(
        "src.server.app.education.router.get_task_calendar", new=AsyncMock(return_value=calendar)
    ) as read:
        response = await client.get(
            "/api/v1/education/tasks/calendar?start_date=2026-08-01&end_date=2026-08-31&student_id=student-1"
        )

    assert response.status_code == 200
    assert response.json()["days"][0]["tasks"][0]["subject_color"] == "#D95D39"
    assert response.json()["days"][0]["overdue_count"] == 1
    assert read.await_args.kwargs["user_id"] == "parent-1"
    assert read.await_args.kwargs["student_id"] == "student-1"


@pytest.mark.asyncio
async def test_calendar_hides_outside_household_student(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    with patch(
        "src.server.app.education.router.get_task_calendar",
        new=AsyncMock(side_effect=EducationTaskNotFoundError("Student account not found")),
    ):
        response = await client.get(
            "/api/v1/education/tasks/calendar?start_date=2026-08-01&end_date=2026-08-31&student_id=other-student"
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_calendar_requires_both_date_boundaries(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"

    response = await client.get("/api/v1/education/tasks/calendar?start_date=2026-08-01")

    assert response.status_code == 422
