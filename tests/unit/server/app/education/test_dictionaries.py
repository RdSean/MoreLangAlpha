"""HTTP contracts for read-only K12 homework dictionaries."""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.server.app.education.router import router
from src.server.services.education_homework import EducationDictionaryPermissionError
from src.server.utils.api import get_current_user_id


DICTIONARIES = {
    "timezone": "Asia/Tokyo",
    "subjects": [
        {
            "code": "chinese",
            "name": "语文",
            "color": "#D95D39",
            "sort_order": 1,
            "homework_types": [
                {"code": "preview", "name": "预习", "sort_order": 1},
                {"code": "practice", "name": "练习", "sort_order": 2},
            ],
        }
    ],
    "grade_levels": [
        {"code": "g1", "name": "一年级", "stage": "primary", "sort_order": 1}
    ],
    "practice_sources": [
        {"code": "schoolwork", "name": "校内作业", "sort_order": 1}
    ],
}


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as session:
        yield session


@pytest.mark.asyncio
async def test_household_member_reads_subjects_with_only_valid_homework_types(client):
    with patch(
        "src.server.app.education.router.get_homework_dictionaries",
        new=AsyncMock(return_value=DICTIONARIES),
    ) as get_dictionaries:
        response = await client.get("/api/v1/education/dictionaries")

    assert response.status_code == 200
    assert response.json() == DICTIONARIES
    get_dictionaries.assert_awaited_once_with("student-1")


@pytest.mark.asyncio
async def test_non_household_user_cannot_read_homework_dictionaries(client):
    with patch(
        "src.server.app.education.router.get_homework_dictionaries",
        new=AsyncMock(side_effect=EducationDictionaryPermissionError("Household membership is required")),
    ):
        response = await client.get("/api/v1/education/dictionaries")

    assert response.status_code == 403
