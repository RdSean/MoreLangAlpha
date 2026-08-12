"""Authorization helpers for the restricted student Agent experience."""

from fastapi import HTTPException, status

from src.server.database.education_members import get_membership_for_user


async def is_student_account(user_id: str) -> bool:
    member = await get_membership_for_user(user_id)
    return bool(member and member["role"] == "student")


async def require_nonstudent_agent_features(user_id: str) -> None:
    """Reject student access to sandbox, Vault, MCP, and automation capabilities."""
    if await is_student_account(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student accounts are limited to private Flash sessions and family education.",
        )


async def require_student_flash_workspace(user_id: str, workspace: dict | None) -> None:
    """A student may own only their private Flash workspace, never a PTC workspace."""
    if await is_student_account(user_id) and (not workspace or workspace.get("status") != "flash"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Student accounts can use only their private Flash workspace.",
        )
