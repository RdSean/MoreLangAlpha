"""PostgreSQL-authoritative public activity for managed textbook jobs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.server.database.pool import get_db_connection


MAX_DETAIL_EVENTS = 1_000
MAX_DETAIL_BYTES = 1024 * 1024
MAX_EVENT_BYTES = 2 * 1024
MAX_MESSAGE_CHARS = 512
_BUDGET_SUMMARY_KEY = "activity-detail-budget"
_TERMINAL_JOB_STATUSES = frozenset(
    {"succeeded", "partially_succeeded", "failed", "cancelled"}
)


class BookActivityWriteError(RuntimeError):
    """A terminal activity write failed after business output was produced."""


def _activity_size(
    *,
    job_id: UUID,
    item_id: UUID | None,
    kind: str,
    status: str,
    message: str,
    metadata: Mapping[str, Any],
) -> int:
    payload = {
        "seq": 9_223_372_036_854_775_807,
        "job_id": str(job_id),
        "item_id": str(item_id) if item_id is not None else None,
        "kind": kind,
        "status": status,
        "message": message,
        "metadata": metadata,
        "created_at": "9999-12-31T23:59:59.999999+00:00",
    }
    return len(
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _validate_event(
    *,
    job_id: UUID,
    item_id: UUID | None,
    dedupe_key: str,
    kind: str,
    status: str,
    message: str,
    metadata: Mapping[str, Any],
) -> tuple[dict[str, Any], int]:
    if not dedupe_key or len(dedupe_key) > 255:
        raise ValueError("Book activity dedupe key is invalid")
    if not kind or len(kind) > 64 or not status or len(status) > 32:
        raise ValueError("Book activity classification is invalid")
    if not message or len(message) > MAX_MESSAGE_CHARS:
        raise ValueError("Book activity message is invalid")
    normalized = dict(metadata)
    normalized.pop("budget_class", None)
    normalized.pop("activity_bytes", None)
    activity_bytes = _activity_size(
        job_id=job_id,
        item_id=item_id,
        kind=kind,
        status=status,
        message=message,
        metadata=normalized,
    )
    if activity_bytes > MAX_EVENT_BYTES:
        raise ValueError("Book activity event exceeds the serialized size limit")
    return normalized, activity_bytes


async def append_terminal_activity(
    cur: Any,
    *,
    job_id: UUID,
    dedupe_key: str,
    item_id: UUID | None,
    kind: str,
    status: str,
    message: str,
    supersede: bool = False,
) -> int | None:
    """Append one budget-exempt terminal event inside the caller's transaction."""
    try:
        return await _append_terminal_activity(
            cur,
            job_id=job_id,
            dedupe_key=dedupe_key,
            item_id=item_id,
            kind=kind,
            status=status,
            message=message,
            supersede=supersede,
        )
    except BookActivityWriteError:
        raise
    except Exception as exc:
        raise BookActivityWriteError(
            "Could not persist terminal book activity"
        ) from exc


async def _append_terminal_activity(
    cur: Any,
    *,
    job_id: UUID,
    dedupe_key: str,
    item_id: UUID | None,
    kind: str,
    status: str,
    message: str,
    supersede: bool,
) -> int | None:
    message = message[:MAX_MESSAGE_CHARS]
    metadata, activity_bytes = _validate_event(
        job_id=job_id,
        item_id=item_id,
        dedupe_key=dedupe_key,
        kind=kind,
        status=status,
        message=message,
        metadata={},
    )
    metadata.update(
        budget_class="terminal",
        activity_bytes=activity_bytes,
    )
    if supersede:
        await cur.execute(
            """
            SELECT event_id, seq FROM education_book_activity_events
            WHERE job_id = %s
              AND item_id IS NOT DISTINCT FROM %s
              AND metadata->>'budget_class' = 'terminal'
            FOR UPDATE
            """,
            (job_id, item_id),
        )
    else:
        await cur.execute(
            """
            SELECT event_id, seq FROM education_book_activity_events
            WHERE job_id = %s AND dedupe_key = %s
            FOR UPDATE
            """,
            (job_id, dedupe_key),
        )
    existing = await cur.fetchone()
    if existing is not None and not supersede:
        return None
    await cur.execute(
        """
        UPDATE education_book_jobs
        SET high_water_seq = high_water_seq + 1, updated_at = NOW()
        WHERE job_id = %s
        RETURNING high_water_seq
        """,
        (job_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise LookupError("Book job was not found")
    seq = int(row["high_water_seq"])
    if existing is not None:
        await cur.execute(
            """
            UPDATE education_book_activity_events
            SET seq = %s, status = %s, message = %s, metadata = %s,
                created_at = NOW()
            WHERE event_id = %s
            """,
            (seq, status, message, Jsonb(metadata), existing["event_id"]),
        )
        return seq
    await cur.execute(
        """
        INSERT INTO education_book_activity_events (
            job_id, seq, dedupe_key, item_id, kind, status, message, metadata
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            job_id,
            seq,
            dedupe_key,
            item_id,
            kind,
            status,
            message,
            Jsonb(metadata),
        ),
    )
    return seq


async def append_book_activity_event(
    *,
    job_id: str | UUID,
    item_id: str | UUID,
    attempt_token: UUID,
    dedupe_key: str,
    kind: str,
    status: str,
    message: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    """Append one fenced detail event while enforcing per-job row and byte budgets."""
    job_id = UUID(str(job_id))
    item_id = UUID(str(item_id))
    normalized, activity_bytes = _validate_event(
        job_id=job_id,
        item_id=item_id,
        dedupe_key=dedupe_key,
        kind=kind,
        status=status,
        message=message,
        metadata=metadata,
    )
    normalized.update(
        budget_class="detail",
        activity_bytes=activity_bytes,
    )
    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.high_water_seq
                FROM education_book_jobs AS jobs
                JOIN education_book_job_items AS items
                  ON items.job_id = jobs.job_id
                WHERE jobs.job_id = %s AND items.item_id = %s
                  AND items.attempt_token = %s AND items.status = 'running'
                FOR UPDATE OF jobs, items
                """,
                (job_id, item_id, attempt_token),
            )
            job = await cur.fetchone()
            if job is None:
                return {"outcome": "stale", "high_water_seq": None}
            await cur.execute(
                """
                SELECT seq FROM education_book_activity_events
                WHERE job_id = %s AND dedupe_key = %s
                """,
                (job_id, dedupe_key),
            )
            existing = await cur.fetchone()
            if existing is not None:
                return {
                    "outcome": "duplicate",
                    "high_water_seq": int(existing["seq"]),
                }
            await cur.execute(
                """
                SELECT
                    count(*)::int AS event_count,
                    coalesce(sum((metadata->>'activity_bytes')::int), 0)::bigint
                        AS byte_count
                FROM education_book_activity_events
                WHERE job_id = %s
                  AND metadata->>'budget_class' = 'detail'
                """,
                (job_id,),
            )
            budget = await cur.fetchone()
            if (
                budget["event_count"] >= MAX_DETAIL_EVENTS
                or budget["byte_count"] + activity_bytes > MAX_DETAIL_BYTES
            ):
                summary_seq = await _record_budget_exhaustion(
                    cur,
                    job_id=job_id,
                    item_id=item_id,
                    dropped_count=1,
                )
                return {
                    "outcome": "budget_exhausted",
                    "high_water_seq": summary_seq,
                }
            await cur.execute(
                """
                UPDATE education_book_jobs
                SET high_water_seq = high_water_seq + 1, updated_at = NOW()
                WHERE job_id = %s
                RETURNING high_water_seq
                """,
                (job_id,),
            )
            seq = int((await cur.fetchone())["high_water_seq"])
            await cur.execute(
                """
                INSERT INTO education_book_activity_events (
                    job_id, seq, dedupe_key, item_id, kind, status,
                    message, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    job_id,
                    seq,
                    dedupe_key,
                    item_id,
                    kind,
                    status,
                    message,
                    Jsonb(normalized),
                ),
            )
            return {"outcome": "stored", "high_water_seq": seq}


async def _record_budget_exhaustion(
    cur: Any,
    *,
    job_id: UUID,
    item_id: UUID,
    dropped_count: int,
) -> int:
    await cur.execute(
        """
        SELECT event_id FROM education_book_activity_events
        WHERE job_id = %s AND dedupe_key = %s
        FOR UPDATE
        """,
        (job_id, _BUDGET_SUMMARY_KEY),
    )
    existing = await cur.fetchone()
    await cur.execute(
        """
        UPDATE education_book_jobs
        SET high_water_seq = high_water_seq + 1, updated_at = NOW()
        WHERE job_id = %s
        RETURNING high_water_seq
        """,
        (job_id,),
    )
    seq = int((await cur.fetchone())["high_water_seq"])
    if existing is not None:
        await cur.execute(
            """
            UPDATE education_book_activity_events
            SET seq = %s, metadata = jsonb_set(
                metadata,
                '{dropped_count}',
                to_jsonb(coalesce((metadata->>'dropped_count')::int, 0) + %s)
            ), created_at = NOW()
            WHERE event_id = %s
            """,
            (seq, dropped_count, existing["event_id"]),
        )
    else:
        await cur.execute(
            """
            INSERT INTO education_book_activity_events (
                job_id, seq, dedupe_key, item_id, kind, status, message, metadata
            ) VALUES (%s, %s, %s, %s, 'summary', 'truncated',
                      'Additional activity was omitted after reaching the limit', %s)
            """,
            (
                job_id,
                seq,
                _BUDGET_SUMMARY_KEY,
                item_id,
                Jsonb(
                    {
                        "budget_class": "summary",
                        "activity_bytes": 0,
                        "dropped_count": dropped_count,
                    }
                ),
            ),
        )
    return seq


async def record_book_activity_drops(
    *,
    job_id: str | UUID,
    item_id: str | UUID,
    attempt_token: UUID,
    dropped_count: int,
) -> dict[str, Any]:
    """Move the budget summary to a replayable seq with one coalesced count."""
    if dropped_count <= 0:
        raise ValueError("Dropped activity count must be positive")
    job_id = UUID(str(job_id))
    item_id = UUID(str(item_id))
    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.job_id
                FROM education_book_jobs AS jobs
                JOIN education_book_job_items AS items
                  ON items.job_id = jobs.job_id
                WHERE jobs.job_id = %s AND items.item_id = %s
                  AND items.attempt_token = %s AND items.status = 'running'
                FOR UPDATE OF jobs, items
                """,
                (job_id, item_id, attempt_token),
            )
            if await cur.fetchone() is None:
                return {"outcome": "stale", "high_water_seq": None}
            seq = await _record_budget_exhaustion(
                cur,
                job_id=job_id,
                item_id=item_id,
                dropped_count=dropped_count,
            )
            return {"outcome": "stored", "high_water_seq": seq}


async def mark_book_activity_unavailable(
    *,
    job_id: str | UUID,
    item_id: str | UUID,
    attempt_token: UUID,
) -> dict[str, Any]:
    """Expose an incomplete public timeline without changing business status."""

    job_id = UUID(str(job_id))
    item_id = UUID(str(item_id))
    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE education_book_jobs AS jobs
                SET activity_status = 'unavailable', updated_at = NOW()
                FROM education_book_job_items AS items
                WHERE jobs.job_id = %s
                  AND items.job_id = jobs.job_id
                  AND items.item_id = %s
                  AND items.attempt_token = %s
                RETURNING jobs.high_water_seq
                """,
                (job_id, item_id, attempt_token),
            )
            row = await cur.fetchone()
            if row is None:
                return {"outcome": "stale", "high_water_seq": None}
            return {
                "outcome": "stored",
                "high_water_seq": int(row["high_water_seq"]),
            }


async def get_book_activity_page(
    *,
    job_id: str | UUID,
    parent_user_id: str | None,
    after_seq: int,
    limit: int,
) -> dict[str, Any] | None:
    """Read a snapshot-bounded activity page from its durable home."""
    if after_seq < 0:
        raise ValueError("Book activity cursor cannot be negative")
    if limit <= 0 or limit > 2_100:
        raise ValueError("Book activity page limit is invalid")
    job_id = UUID(str(job_id))
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.job_id, jobs.status, jobs.activity_status,
                       jobs.high_water_seq
                FROM education_book_jobs AS jobs
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = jobs.textbook_id
                WHERE jobs.job_id = %s
                  AND (
                      %s::text IS NULL OR EXISTS (
                          SELECT 1 FROM education_memberships AS memberships
                          WHERE memberships.household_id = textbooks.household_id
                            AND memberships.user_id = %s
                            AND memberships.role = 'parent'
                      )
                  )
                """,
                (job_id, parent_user_id, parent_user_id),
            )
            job = await cur.fetchone()
            if job is None:
                return None
            high_water = int(job["high_water_seq"])
            cursor_expired = after_seq > high_water
            await cur.execute(
                """
                SELECT seq, job_id, item_id, kind, status, message,
                       metadata, created_at
                FROM education_book_activity_events
                WHERE job_id = %s AND seq > %s AND seq <= %s
                ORDER BY seq
                LIMIT %s
                """,
                (job_id, after_seq, high_water, limit + 1),
            )
            rows = [dict(row) for row in await cur.fetchall()]
    has_more = len(rows) > limit
    rows = rows[:limit]
    for row in rows:
        row["job_id"] = str(row["job_id"])
        metadata = dict(row.get("metadata") or {})
        metadata.pop("activity_bytes", None)
        metadata.pop("budget_class", None)
        row["metadata"] = metadata
    return {
        "job_id": str(job_id),
        "status": str(job["status"]),
        "activity_status": str(job["activity_status"]),
        "events": rows,
        "high_water_seq": high_water,
        "cursor_expired": cursor_expired,
        "has_more": has_more,
    }


def is_terminal_book_job_status(status: str) -> bool:
    return status in _TERMINAL_JOB_STATUSES
