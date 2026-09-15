"""Durable per-conversion usage: what a document parse actually cost.

One row per parse job, written by whichever provider incurred the cost. The
Usage surface aggregates these; nothing else reads them, and nothing here reads
another module's tables except for the foreign keys the migration declares.

Money is integer cents throughout. The providers report cents, the column is
cents, and the page formats — no floats on the way, because a float cent that
rounds the wrong way is a support ticket.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from psycopg.rows import dict_row

from src.server.database.pool import get_db_connection
from src.server.documents.ids import new_public_id


MAX_WINDOW_DAYS = 31
"""Longest span ``aggregate_usage`` will read.

The Usage page offers 7/14/30 days, so 31 is the page's own window plus the
inclusive-end slack. Anything wider is a bug or a caller probing the endpoint,
and the query is bounded rather than trusted.
"""


def _validate_window(*, start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise ValueError("usage window end_date must not precede start_date")
    if (end_date - start_date).days >= MAX_WINDOW_DAYS:
        raise ValueError(f"usage window cannot exceed {MAX_WINDOW_DAYS} days")


async def record_usage(
    *,
    job_id: str,
    owner_user_id: str,
    provider_id: str,
    pages: int,
    list_cost_cents: int | None,
    final_cost_cents: int,
) -> dict[str, Any] | None:
    """Upsert one job's usage.

    Upsert rather than insert because parse jobs are retried: the row must
    describe the job, not the attempt, or a retry would show up on the Usage
    page as a second conversion. ``created_at`` is left alone on conflict so the
    record keeps the day it was first earned.
    """
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO document_usage_records (
                    record_id, job_id, owner_user_id, provider_id,
                    pages, list_cost_cents, final_cost_cents
                ) VALUES (
                    %(record_id)s, %(job_id)s, %(owner_user_id)s, %(provider_id)s,
                    %(pages)s, %(list_cost_cents)s, %(final_cost_cents)s
                )
                ON CONFLICT (job_id) DO UPDATE SET
                    provider_id = EXCLUDED.provider_id,
                    pages = EXCLUDED.pages,
                    list_cost_cents = EXCLUDED.list_cost_cents,
                    final_cost_cents = EXCLUDED.final_cost_cents
                RETURNING record_id, job_id, owner_user_id, provider_id,
                          pages, list_cost_cents, final_cost_cents, created_at
                """,
                {
                    "record_id": new_public_id("usage"),
                    "job_id": job_id,
                    "owner_user_id": owner_user_id,
                    "provider_id": provider_id,
                    "pages": pages,
                    "list_cost_cents": list_cost_cents,
                    "final_cost_cents": final_cost_cents,
                },
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def aggregate_usage(
    *,
    owner_user_id: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Daily buckets of pages and cents for one owner.

    Days with no conversions are absent rather than zero-filled: the caller
    draws its own axis, and a sparse series is the honest input for that.
    """
    _validate_window(start_date=start_date, end_date=end_date)
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT (created_at AT TIME ZONE 'UTC')::date AS day,
                       SUM(pages)::int AS pages,
                       SUM(final_cost_cents)::int AS cost_cents,
                       COUNT(*)::int AS conversions
                FROM document_usage_records
                WHERE owner_user_id = %s
                  AND (created_at AT TIME ZONE 'UTC')::date BETWEEN %s AND %s
                GROUP BY 1
                ORDER BY 1 ASC
                """,
                (owner_user_id, start_date, end_date),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]
