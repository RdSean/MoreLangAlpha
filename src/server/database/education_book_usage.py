"""Durable, attempt-fenced provider usage snapshots."""

from typing import Any
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.server.database.pool import get_db_connection


async def record_book_usage(
    *, item_id: UUID, attempt_token: UUID, usage: dict[str, Any]
) -> bool:
    from src.server.app.education.book_models import BookTokenUsageResponse
    from src.server.database.education_book_jobs import _lock_book_job_for_item

    snapshot = BookTokenUsageResponse.model_validate(usage).model_dump()
    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await _lock_book_job_for_item(cur, item_id=item_id)
            await cur.execute(
                """UPDATE education_book_job_attempts a SET token_usage=%s
                FROM education_book_job_items i
                WHERE i.item_id=%s AND i.attempt_token=%s
                  AND a.item_id=i.item_id AND a.attempt_token=i.attempt_token
                  AND a.token_usage IS NULL RETURNING a.attempt_id""",
                (Jsonb(snapshot), item_id, attempt_token),
            )
            return await cur.fetchone() is not None


async def get_book_usage(*, job_id: str | UUID, conn=None) -> dict[str, Any] | None:
    async with get_db_connection(conn) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """SELECT a.token_usage FROM education_book_job_attempts a
                JOIN education_book_job_items i ON i.item_id=a.item_id
                WHERE i.job_id=%s ORDER BY i.position,a.attempt""",
                (job_id,),
            )
            rows = await cur.fetchall()
    recorded = [row["token_usage"] for row in rows if row["token_usage"] is not None]
    if not recorded:
        return None
    return {
        "status": "available"
        if len(recorded) == len(rows)
        and all(row["status"] == "available" for row in recorded)
        else "partial",
        **{
            key: sum(row[key] for row in recorded)
            for key in (
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "recorded_calls",
            )
        },
    }
