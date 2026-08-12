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
                SELECT household_id, user_id, role, display_name
                FROM education_memberships
                WHERE user_id = %s
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (user_id,),
            )
            row = await cur.fetchone()
    return dict(row) if row else None
