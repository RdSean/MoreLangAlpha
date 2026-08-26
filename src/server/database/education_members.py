"""Education household membership queries shared by first-party modules."""

from typing import Any

from psycopg.rows import dict_row

from src.server.database.pool import get_db_connection


async def get_membership_for_user(user_id: str) -> dict[str, Any] | None:
    """Return the user's single household role and household identifier."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT memberships.household_id, memberships.user_id,
                       memberships.role, memberships.display_name,
                       households.model_owner_user_id, households.timezone
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


async def get_household_membership_context(user_id: str) -> dict[str, Any] | None:
    """Return membership and the household's designated model owner."""
    return await get_membership_for_user(user_id)


async def list_household_membership_context(household_id: str) -> list[dict[str, Any]]:
    """Return all member roles plus the shared model owner identifier."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT memberships.household_id, memberships.user_id,
                       memberships.role, memberships.display_name,
                       households.model_owner_user_id, households.timezone
                FROM education_memberships AS memberships
                JOIN education_households AS households
                  ON households.household_id = memberships.household_id
                WHERE memberships.household_id = %s
                ORDER BY memberships.role ASC, memberships.created_at ASC
                """,
                (household_id,),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]
