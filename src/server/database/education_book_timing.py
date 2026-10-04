"""Durable education-only attempt measurements; PG owns all fences."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from psycopg.rows import dict_row

from src.server.database.pool import get_db_connection


def _timing_projection(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "attempt": row["attempt"],
        "request_round": row["request_round"],
        "status": row["timing_status"],
        "queued_at": row["queued_at"],
        "claimed_at": row["claimed_at"],
        "terminal_at": row["terminal_at"],
        "total_ms": row["total_ms"],
        "phases": row.get("phases") or [],
    }


async def get_current_attempt_summaries(
    *, job_id: str | UUID
) -> dict[str, dict[str, Any]]:
    """One query for all current attempts, without exposing execution identities."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT a.* FROM education_book_job_attempts a
                JOIN education_book_job_items i ON i.item_id=a.item_id
                  AND i.attempt_token=a.attempt_token
                WHERE i.job_id=%s
                """,
                (job_id,),
            )
            rows = await cur.fetchall()
    return {
        str(row["item_id"]): {
            "timing": _timing_projection(dict(row)),
            "progress": {
                "total_resources": row["total_resources"],
                "verified_resources": row["verified_resources"],
            },
        }
        for row in rows
    }


async def list_attempt_statistics(
    *,
    job_id: str | UUID,
    parent_user_id: str,
    after: tuple[UUID, int] | None = None,
    limit: int = 50,
) -> list[dict[str, Any]] | None:
    """Stable item/attempt cursor. ACL applies even to an empty page."""
    if not 1 <= limit <= 100:
        raise ValueError("statistics limit must be between 1 and 100")
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """SELECT 1 FROM education_book_jobs j
                JOIN education_textbooks b ON b.textbook_id=j.textbook_id
                JOIN education_memberships m ON m.household_id=b.household_id
                WHERE j.job_id=%s AND m.user_id=%s AND m.role='parent'""",
                (job_id, parent_user_id),
            )
            if await cur.fetchone() is None:
                return None
            await cur.execute(
                """SELECT a.*, i.kind, p.title AS knowledge_point_title
                FROM education_book_job_attempts a
                JOIN education_book_job_items i ON i.item_id=a.item_id
                LEFT JOIN education_book_knowledge_points p ON p.knowledge_point_id=i.knowledge_point_id
                WHERE i.job_id=%s AND (%s::uuid IS NULL OR (a.item_id,a.attempt)>(%s::uuid,%s))
                ORDER BY a.item_id,a.attempt LIMIT %s""",
                (
                    job_id,
                    after[0] if after else None,
                    after[0] if after else None,
                    after[1] if after else 0,
                    limit,
                ),
            )
            rows = await cur.fetchall()
    return [
        {
            "item_id": row["item_id"],
            "kind": row["kind"],
            "status": row["status"],
            "knowledge_point_title": row["knowledge_point_title"],
            "timing": _timing_projection(dict(row)),
        }
        for row in rows
    ]
