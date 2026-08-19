"""Parent-only read models for household student accounts and Flash history."""

from typing import Any

from src.server.database.auth_accounts import (
    ParentMembershipRequiredError,
    list_household_members_for_parent,
)
from src.server.database.conversation import (
    get_replay_thread_data,
    get_workspace_threads,
)
from src.server.database.workspace import get_or_create_flash_workspace


class FamilyMemberNotFoundError(LookupError):
    """The requested student is not in the parent's household."""


class FamilyThreadNotFoundError(LookupError):
    """The requested thread is not owned by the student's Flash workspace."""


class FamilyWorkspaceNotFoundError(LookupError):
    """The deterministic Flash workspace cannot be used for this student."""


def _require_student_flash_workspace(
    workspace: dict[str, Any], student_user_id: str
) -> None:
    if (
        str(workspace.get("user_id")) != student_user_id
        or workspace.get("status") != "flash"
    ):
        raise FamilyWorkspaceNotFoundError("Student Flash workspace not found")


def _flash_summary(workspace: dict[str, Any]) -> dict[str, Any]:
    return {
        "workspace_id": str(workspace["workspace_id"]),
        "name": workspace.get("name") or "Flash",
        "status": workspace.get("status"),
        "updated_at": workspace.get("updated_at"),
    }


async def _require_student(parent_user_id: str, student_user_id: str) -> dict[str, Any]:
    members = await list_household_members_for_parent(parent_user_id)
    parent = next(
        (
            member
            for member in members
            if member["user_id"] == parent_user_id and member["role"] == "parent"
        ),
        None,
    )
    if parent is None:
        raise ParentMembershipRequiredError("Only a parent can view household members")
    for member in members:
        if (
            member["user_id"] == student_user_id
            and member["role"] == "student"
            and str(member["household_id"]) == str(parent["household_id"])
        ):
            return member
    raise FamilyMemberNotFoundError("Student account not found")


async def list_family_children(parent_user_id: str) -> list[dict[str, Any]]:
    """Return same-household students with an ensured Flash workspace summary."""
    members = await list_household_members_for_parent(parent_user_id)
    children: list[dict[str, Any]] = []
    for member in members:
        if member["role"] != "student":
            continue
        workspace = await get_or_create_flash_workspace(member["user_id"])
        _require_student_flash_workspace(workspace, member["user_id"])
        children.append({**member, "flash_workspace": _flash_summary(workspace)})
    return children


async def get_family_child_workspace(
    parent_user_id: str, student_user_id: str
) -> dict[str, Any]:
    """Ensure and return a student's private Flash workspace summary."""
    await _require_student(parent_user_id, student_user_id)
    workspace = await get_or_create_flash_workspace(student_user_id)
    _require_student_flash_workspace(workspace, student_user_id)
    return _flash_summary(workspace)


async def list_family_child_threads(
    parent_user_id: str,
    student_user_id: str,
    *,
    limit: int = 20,
    offset: int = 0,
    sort_by: str = "updated_at",
    sort_order: str = "desc",
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    """List thread metadata in a student's Flash workspace."""
    await _require_student(parent_user_id, student_user_id)
    workspace = await get_or_create_flash_workspace(student_user_id)
    _require_student_flash_workspace(workspace, student_user_id)
    threads, total = await get_workspace_threads(
        workspace_id=str(workspace["workspace_id"]),
        limit=limit,
        offset=offset,
        sort_by=sort_by,
        sort_order=sort_order,
    )
    return threads, total, _flash_summary(workspace)


async def get_family_child_replay(
    parent_user_id: str, student_user_id: str, thread_id: str
) -> tuple[str, dict[str, Any], list[dict], list[dict], list[dict], list[dict]]:
    """Return replay inputs only after parent/child/workspace ownership checks."""
    await _require_student(parent_user_id, student_user_id)
    workspace = await get_or_create_flash_workspace(student_user_id)
    _require_student_flash_workspace(workspace, student_user_id)
    replay = await get_replay_thread_data(thread_id)
    owner_id, thread, queries, responses, usages, provenance = replay
    if (
        owner_id != student_user_id
        or not thread
        or str(thread.get("workspace_id")) != str(workspace["workspace_id"])
    ):
        raise FamilyThreadNotFoundError("Student thread not found")
    return owner_id, thread, queries, responses, usages, provenance


__all__ = [
    "FamilyMemberNotFoundError",
    "FamilyThreadNotFoundError",
    "FamilyWorkspaceNotFoundError",
    "ParentMembershipRequiredError",
    "get_family_child_replay",
    "get_family_child_workspace",
    "list_family_child_threads",
    "list_family_children",
]
