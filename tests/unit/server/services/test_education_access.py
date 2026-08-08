"""Authorization contracts for the student Flash-only Agent boundary."""

from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.server.services import education_access


@pytest.mark.asyncio
async def test_student_is_denied_non_flash_agent_capabilities(monkeypatch):
    monkeypatch.setattr(
        education_access,
        "get_membership_for_user",
        AsyncMock(return_value={"role": "student", "household_id": "household-1"}),
    )

    with pytest.raises(HTTPException) as exc_info:
        await education_access.require_nonstudent_agent_features("student-1")

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_student_can_use_only_a_private_flash_workspace(monkeypatch):
    monkeypatch.setattr(
        education_access,
        "get_membership_for_user",
        AsyncMock(return_value={"role": "student", "household_id": "household-1"}),
    )

    await education_access.require_student_flash_workspace("student-1", {"status": "flash"})
    with pytest.raises(HTTPException) as exc_info:
        await education_access.require_student_flash_workspace("student-1", {"status": "running"})

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_parent_keeps_general_agent_capabilities(monkeypatch):
    monkeypatch.setattr(
        education_access,
        "get_membership_for_user",
        AsyncMock(return_value={"role": "parent", "household_id": "household-1"}),
    )

    await education_access.require_nonstudent_agent_features("parent-1")
    await education_access.require_student_flash_workspace("parent-1", {"status": "running"})
