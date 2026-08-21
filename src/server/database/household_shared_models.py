"""Database access for household-owned model references."""

from __future__ import annotations

from typing import Any

from psycopg.rows import dict_row

from src.server.database.education_members import list_household_membership_context
from src.server.database.pool import get_db_connection


class HouseholdMembershipError(PermissionError):
    """The requested user is not a member of the household."""


async def get_household_owner(household_id: str) -> str | None:
    """Return the designated model owner's user ID, if configured."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT model_owner_user_id FROM education_households WHERE household_id = %s",
                (household_id,),
            )
            row = await cur.fetchone()
    return str(row["model_owner_user_id"]) if row and row["model_owner_user_id"] else None


async def get_household_owner_for_user(user_id: str) -> dict[str, Any] | None:
    """Resolve a member's household and designated owner in one query."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT memberships.household_id, memberships.user_id,
                       memberships.role, households.model_owner_user_id
                FROM education_memberships AS memberships
                JOIN education_households AS households
                  ON households.household_id = memberships.household_id
                WHERE memberships.user_id = %s
                ORDER BY memberships.created_at ASC
                LIMIT 1
                """,
                (user_id,),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_household_model_owner(user_id: str) -> dict[str, Any] | None:
    """Resolve a member's owner and reject an owner without parent membership."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT memberships.household_id, households.model_owner_user_id
                FROM education_memberships AS memberships
                JOIN education_households AS households
                  ON households.household_id = memberships.household_id
                WHERE memberships.user_id = %s
                ORDER BY memberships.created_at ASC
                LIMIT 1
                """,
                (user_id,),
            )
            household = await cur.fetchone()
            if not household or not household["model_owner_user_id"]:
                return None
            await cur.execute(
                """
                SELECT user_id
                FROM education_memberships
                WHERE household_id = %s
                  AND user_id = %s
                  AND role = 'parent'
                """,
                (household["household_id"], household["model_owner_user_id"]),
            )
            if await cur.fetchone() is None:
                return None
    return {
        "household_id": str(household["household_id"]),
        "model_owner_user_id": str(household["model_owner_user_id"]),
    }


async def verify_household_model_owner(household_id: str, user_id: str) -> bool:
    """Return whether user_id is the household's parent model owner."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT 1
                FROM education_households AS households
                JOIN education_memberships AS memberships
                  ON memberships.household_id = households.household_id
                 AND memberships.user_id = households.model_owner_user_id
                 AND memberships.role = 'parent'
                WHERE households.household_id = %s
                  AND households.model_owner_user_id = %s
                """,
                (household_id, user_id),
            )
            return await cur.fetchone() is not None


async def get_student_model_preference(user_id: str, household_id: str) -> dict[str, Any] | None:
    """Read a student's public model preference."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT user_id, household_id, model_key, updated_at
                FROM student_llm_preferences
                WHERE user_id = %s AND household_id = %s
                """,
                (user_id, household_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def upsert_student_model_preference(
    user_id: str, household_id: str, model_key: str
) -> dict[str, Any]:
    """Persist a public model key after confirming household membership."""
    normalized_key = model_key.strip()
    if not normalized_key:
        raise ValueError("model_key must not be empty")
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    INSERT INTO student_llm_preferences
                        (user_id, household_id, model_key, updated_at)
                    SELECT %s, %s, %s, NOW()
                    WHERE EXISTS (
                        SELECT 1
                        FROM education_memberships
                        WHERE household_id = %s AND user_id = %s
                    )
                    ON CONFLICT (user_id) DO UPDATE
                    SET household_id = EXCLUDED.household_id,
                        model_key = EXCLUDED.model_key,
                        updated_at = NOW()
                    RETURNING user_id, household_id, model_key, updated_at
                    """,
                    (user_id, household_id, normalized_key, household_id, user_id),
                )
                try:
                    row = await cur.fetchone()
                except StopAsyncIteration:
                    row = None
                if row is None:
                    raise HouseholdMembershipError("User is not a member of this household")
    return dict(row) if row else {
        "user_id": user_id,
        "household_id": household_id,
        "model_key": normalized_key,
    }


async def clear_student_model_preference(user_id: str, household_id: str) -> bool:
    """Clear a student's model preference."""
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM student_llm_preferences WHERE user_id = %s AND household_id = %s",
                (user_id, household_id),
            )
            return cur.rowcount == 1


__all__ = [
    "HouseholdMembershipError",
    "clear_student_model_preference",
    "get_household_model_owner",
    "get_household_owner",
    "get_household_owner_for_user",
    "get_student_model_preference",
    "list_household_membership_context",
    "upsert_student_model_preference",
    "verify_household_model_owner",
]
