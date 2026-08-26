"""Authorization contracts for K12 homework dictionary reads."""

from unittest.mock import AsyncMock

import pytest

from src.server.services import education_homework


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["parent", "student"])
async def test_household_members_can_read_homework_dictionaries(monkeypatch, role):
    monkeypatch.setattr(
        education_homework,
        "get_membership_for_user",
        AsyncMock(return_value={"household_id": "household-1", "role": role, "timezone": "Asia/Tokyo"}),
    )
    dictionaries = {"subjects": [], "grade_levels": [], "practice_sources": []}
    read = AsyncMock(return_value=dictionaries)
    monkeypatch.setattr(education_homework, "list_homework_dictionaries", read)

    assert await education_homework.get_homework_dictionaries("member-1") == {
        **dictionaries,
        "timezone": "Asia/Tokyo",
    }
    read.assert_awaited_once()


@pytest.mark.asyncio
async def test_non_household_user_cannot_read_homework_dictionaries(monkeypatch):
    monkeypatch.setattr(education_homework, "get_membership_for_user", AsyncMock(return_value=None))

    with pytest.raises(education_homework.EducationDictionaryPermissionError):
        await education_homework.get_homework_dictionaries("outside-user")
