"""Authorization for read-only K12 homework dictionaries."""

from typing import Any

from src.server.database.education_homework import list_homework_dictionaries
from src.server.database.education_members import get_membership_for_user


class EducationDictionaryPermissionError(PermissionError):
    """The caller has no household role that can use education dictionaries."""


async def get_homework_dictionaries(user_id: str) -> dict[str, list[dict[str, Any]]]:
    """Return global dictionaries only to authenticated household members."""
    membership = await get_membership_for_user(user_id)
    if not membership or membership.get("role") not in {"parent", "student"}:
        raise EducationDictionaryPermissionError("Household membership is required")
    return await list_homework_dictionaries()
