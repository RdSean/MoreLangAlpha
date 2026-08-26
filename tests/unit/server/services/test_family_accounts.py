"""Authorization and read-model contracts for parent family account views."""

from unittest.mock import AsyncMock

import pytest

from src.server.services import family_accounts
from src.server.database.auth_accounts import ParentMembershipRequiredError


PARENT = {
    "user_id": "parent-1",
    "email": "parent@example.test",
    "name": "Parent",
    "role": "parent",
    "household_id": "household-1",
}
STUDENT = {
    "user_id": "student-1",
    "email": None,
    "username": "student.lee",
    "name": "Student",
    "role": "student",
    "household_id": "household-1",
}
OTHER_HOUSEHOLD_STUDENT = {
    **STUDENT,
    "user_id": "student-2",
    "username": "student.other",
    "household_id": "household-2",
}
FLASH = {
    "workspace_id": "flash-1",
    "user_id": "student-1",
    "name": "Flash",
    "description": "Flash mode conversations",
    "status": "flash",
    "updated_at": "2026-08-18T00:00:00Z",
}


@pytest.mark.asyncio
async def test_list_children_only_returns_students_and_flash_summary(monkeypatch):
    monkeypatch.setattr(
        family_accounts,
        "list_household_members_for_parent",
        AsyncMock(return_value=[PARENT, STUDENT]),
    )
    ensure_flash = AsyncMock(return_value=FLASH)
    monkeypatch.setattr(family_accounts, "get_or_create_flash_workspace", ensure_flash)

    children = await family_accounts.list_family_children("parent-1")

    assert children == [
        {
            **STUDENT,
            "flash_workspace": {
                "workspace_id": "flash-1",
                "name": "Flash",
                "status": "flash",
                "updated_at": "2026-08-18T00:00:00Z",
            },
        }
    ]
    ensure_flash.assert_awaited_once_with("student-1")


@pytest.mark.asyncio
async def test_child_workspace_requires_parent_membership(monkeypatch):
    monkeypatch.setattr(
        family_accounts,
        "list_household_members_for_parent",
        AsyncMock(side_effect=ParentMembershipRequiredError("parent required")),
    )

    with pytest.raises(ParentMembershipRequiredError):
        await family_accounts.get_family_child_workspace("student-1", "student-1")


@pytest.mark.asyncio
async def test_child_workspace_rejects_cross_household_student(monkeypatch):
    monkeypatch.setattr(
        family_accounts,
        "list_household_members_for_parent",
        AsyncMock(return_value=[PARENT, OTHER_HOUSEHOLD_STUDENT]),
    )
    ensure_flash = AsyncMock(return_value=FLASH)
    monkeypatch.setattr(family_accounts, "get_or_create_flash_workspace", ensure_flash)

    with pytest.raises(family_accounts.FamilyMemberNotFoundError):
        await family_accounts.get_family_child_workspace("parent-1", "student-2")

    ensure_flash.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [("user_id", "other-student"), ("status", "running")],
)
async def test_child_workspace_rejects_workspace_not_owned_by_student_or_not_flash(
    monkeypatch, field, value
):
    monkeypatch.setattr(
        family_accounts,
        "list_household_members_for_parent",
        AsyncMock(return_value=[PARENT, STUDENT]),
    )
    workspace = {**FLASH, field: value}
    monkeypatch.setattr(
        family_accounts,
        "get_or_create_flash_workspace",
        AsyncMock(return_value=workspace),
    )

    with pytest.raises(family_accounts.FamilyWorkspaceNotFoundError):
        await family_accounts.get_family_child_workspace("parent-1", "student-1")


@pytest.mark.asyncio
async def test_replay_rejects_thread_from_another_workspace(monkeypatch):
    monkeypatch.setattr(
        family_accounts,
        "list_household_members_for_parent",
        AsyncMock(return_value=[PARENT, STUDENT]),
    )
    monkeypatch.setattr(
        family_accounts,
        "get_or_create_flash_workspace",
        AsyncMock(return_value=FLASH),
    )
    monkeypatch.setattr(
        family_accounts,
        "get_replay_thread_data",
        AsyncMock(
            return_value=(
                "student-1",
                {"conversation_thread_id": "thread-1", "workspace_id": "other-workspace"},
                [],
                [],
                [],
                [],
            )
        ),
    )

    with pytest.raises(family_accounts.FamilyThreadNotFoundError):
        await family_accounts.get_family_child_replay("parent-1", "student-1", "thread-1")


@pytest.mark.asyncio
async def test_parent_reads_and_updates_a_same_household_students_grade(monkeypatch):
    monkeypatch.setattr(
        family_accounts,
        "list_household_members_for_parent",
        AsyncMock(return_value=[PARENT, STUDENT]),
    )
    profile = {"household_id": "household-1", "user_id": "student-1", "grade_code": "g5"}
    monkeypatch.setattr(
        family_accounts,
        "get_student_grade_profile",
        AsyncMock(return_value=profile),
    )
    update = AsyncMock(return_value=profile)
    monkeypatch.setattr(family_accounts, "upsert_student_grade_profile", update)

    assert await family_accounts.get_family_child_education_profile("parent-1", "student-1") == profile
    assert (
        await family_accounts.update_family_child_education_profile(
            "parent-1", "student-1", grade_code="g5"
        )
        == profile
    )
    update.assert_awaited_once_with(
        household_id="household-1", user_id="student-1", grade_code="g5"
    )


@pytest.mark.asyncio
async def test_student_and_cross_household_callers_cannot_manage_student_grade(monkeypatch):
    monkeypatch.setattr(
        family_accounts,
        "list_household_members_for_parent",
        AsyncMock(side_effect=ParentMembershipRequiredError("parent required")),
    )
    with pytest.raises(ParentMembershipRequiredError):
        await family_accounts.get_family_child_education_profile("student-1", "student-1")

    monkeypatch.setattr(
        family_accounts,
        "list_household_members_for_parent",
        AsyncMock(return_value=[PARENT, OTHER_HOUSEHOLD_STUDENT]),
    )
    with pytest.raises(family_accounts.FamilyMemberNotFoundError):
        await family_accounts.update_family_child_education_profile(
            "parent-1", "student-2", grade_code="g6"
        )
