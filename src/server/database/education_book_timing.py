"""Durable education-only attempt measurements; PG owns all fences."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from psycopg.rows import dict_row

from src.server.database.pool import get_db_connection

PHASES = frozenset(
    {
        "initial_queue",
        "source_freezing",
        "runtime_queue",
        "sandbox_preparation",
        "input_staging",
        "ptc_execution",
        "finalization",
    }
)


async def begin_book_phase(*, item_id: UUID, attempt_token: UUID, phase: str) -> UUID:
    from src.server.database.education_book_jobs import _lock_book_job_for_item

    if phase not in PHASES or phase in {"initial_queue", "runtime_queue"}:
        raise ValueError("Unknown measured book phase")
    segment_id = uuid4()
    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await _lock_book_job_for_item(
                cur, item_id=item_id, reject_cancel_requested=True
            )
            await cur.execute(
                """UPDATE education_book_job_items SET execution_phase=%s,updated_at=NOW()
                WHERE item_id=%s AND attempt_token=%s AND status='running'
                  AND (run_id IS NOT NULL OR lease_expires_at>NOW()) RETURNING item_id""",
                (phase, item_id, attempt_token),
            )
            if await cur.fetchone() is None:
                raise RuntimeError("Book timing attempt is stale")
            await cur.execute(
                """UPDATE education_book_job_phase_spans SET status='interrupted',
                ended_at=GREATEST(started_at,clock_timestamp()) WHERE attempt_id=%s AND status='running'""",
                (attempt_token,),
            )
            await cur.execute(
                """INSERT INTO education_book_job_phase_spans (segment_id,attempt_id,phase,started_at,status)
                VALUES (%s,%s,%s,clock_timestamp(),'running')""",
                (segment_id, attempt_token, phase),
            )
    return segment_id


async def end_book_phase(
    *, segment_id: UUID, measured_ms: int | None, status: str
) -> None:
    if status not in {"succeeded", "failed", "cancelled"} or (
        measured_ms is not None and measured_ms < 0
    ):
        raise ValueError("Invalid measured book phase")
    async with get_db_connection() as conn:
        await conn.execute(
            """UPDATE education_book_job_phase_spans SET measured_ms=CASE WHEN clock_timestamp()>=started_at THEN %s END,
            ended_at=COALESCE(ended_at,GREATEST(started_at,clock_timestamp())),
            status=CASE WHEN clock_timestamp()<started_at THEN 'interrupted' WHEN status='running' THEN %s ELSE status END
            WHERE segment_id=%s AND measured_ms IS NULL AND status<>'interrupted'""",
            (measured_ms, status, segment_id),
        )


_PHASE_PROJECTION = """COALESCE((SELECT jsonb_agg(p.record ORDER BY p.first_start) FROM (
  SELECT min(started_at) AS first_start,jsonb_build_object(
    'phase',phase,'status',CASE WHEN count(*) FILTER (WHERE measured_ms IS NULL AND ended_at IS NOT NULL)>0 THEN 'partial' ELSE 'available' END,
    'started_at',COALESCE(max(started_at) FILTER (WHERE status='running'),min(started_at)),
    'ended_at',CASE WHEN bool_or(status='running') THEN NULL ELSE max(ended_at) END,
    'measured_ms',CASE WHEN count(*) FILTER (WHERE measured_ms IS NULL AND ended_at IS NOT NULL)>0 THEN NULL ELSE sum(measured_ms) END,
    'segment_count',count(*)) AS record
  FROM education_book_job_phase_spans s WHERE s.attempt_id=a.attempt_id GROUP BY phase
) p), '[]'::jsonb)"""


def _timing_projection(row: dict[str, Any]) -> dict[str, Any]:
    phases = row.get("phases") or []
    status = "unavailable"
    if phases or row["total_ms"] is not None:
        status = (
            "partial"
            if not phases or any(p["status"] != "available" for p in phases)
            else "available"
        )
        recorded = {p["phase"] for p in phases}
        if "initial_queue" in recorded and "source_freezing" not in recorded:
            status = "partial"
        if row["status"] == "succeeded" and not {
            "sandbox_preparation",
            "input_staging",
            "ptc_execution",
            "finalization",
        }.issubset(recorded):
            status = "partial"
        current = next(
            (p for p in phases if p["phase"] == row["execution_phase"]), None
        )
        if row["status"] == "running" and (
            current is None or current["ended_at"] is not None
        ):
            status = "partial"
        if row["status"] != "running" and row["total_ms"] is None:
            status = "partial"
    return {
        "attempt": row["attempt"],
        "request_round": row["request_round"],
        "status": status,
        "queued_at": row["queued_at"],
        "claimed_at": row["claimed_at"],
        "terminal_at": row["terminal_at"],
        "total_ms": row["total_ms"],
        "phases": phases,
    }


async def get_current_attempt_summaries(
    *, job_id: str | UUID, conn=None
) -> dict[str, dict[str, Any]]:
    """One query for all current attempts, without exposing execution identities."""
    async with get_db_connection(conn) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"""
                SELECT a.*, {_PHASE_PROJECTION} AS phases FROM education_book_job_attempts a
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
    conn=None,
) -> list[dict[str, Any]] | None:
    """Stable item/attempt cursor. ACL applies even to an empty page."""
    if not 1 <= limit <= 101:
        raise ValueError("statistics limit must be between 1 and 100")
    async with get_db_connection(conn) as conn:
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
                f"""WITH RECURSIVE chain AS (
                SELECT job_id,previous_job_id FROM education_book_jobs WHERE job_id=%s
                UNION ALL SELECT j.job_id,j.previous_job_id FROM education_book_jobs j JOIN chain c ON j.job_id=c.previous_job_id
                ) SELECT a.*, {_PHASE_PROJECTION} AS phases, i.kind, p.title AS knowledge_point_title
                FROM education_book_job_attempts a
                JOIN education_book_job_items i ON i.item_id=a.item_id
                LEFT JOIN education_book_knowledge_points p ON p.knowledge_point_id=i.knowledge_point_id
                WHERE i.job_id IN (SELECT job_id FROM chain) AND (%s::uuid IS NULL OR (a.item_id,a.attempt)>(%s::uuid,%s))
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


async def get_job_statistics_summary(
    *, job_id: UUID, parent_user_id: str, conn=None
) -> dict[str, Any] | None:
    async with get_db_connection(conn) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """SELECT j.job_id::text,j.request_round,NOW() AS server_now,
                CASE WHEN COALESCE(j.finished_at,NOW())>=j.round_accepted_at THEN
                  ROUND(EXTRACT(EPOCH FROM (COALESCE(j.finished_at,NOW())-j.round_accepted_at))*1000)::bigint END AS round_total_ms,
                count(a.attempt_id) FILTER (WHERE i.kind='material' AND a.status='succeeded' AND a.total_ms IS NOT NULL)::int AS material_sample_count,
                (percentile_cont(0.5) WITHIN GROUP (ORDER BY a.total_ms) FILTER (WHERE i.kind='material' AND a.status='succeeded'))::bigint AS material_median_ms,
                max(a.total_ms) FILTER (WHERE i.kind='material' AND a.status='succeeded') AS material_longest_ms
                ,count(a.attempt_id) FILTER (WHERE a.queued_at IS NULL OR (a.status<>'running' AND a.total_ms IS NULL)
                  OR (EXISTS (SELECT 1 FROM education_book_job_phase_spans s WHERE s.attempt_id=a.attempt_id AND s.phase='initial_queue')
                    AND NOT EXISTS (SELECT 1 FROM education_book_job_phase_spans s WHERE s.attempt_id=a.attempt_id AND s.phase='source_freezing'))
                  OR (a.status='running' AND NOT EXISTS (SELECT 1 FROM education_book_job_phase_spans s WHERE s.attempt_id=a.attempt_id AND s.phase=a.execution_phase AND s.status='running'))
                  OR (a.status='succeeded' AND (SELECT count(DISTINCT s.phase) FROM education_book_job_phase_spans s
                    WHERE s.attempt_id=a.attempt_id AND s.phase IN ('sandbox_preparation','input_staging','ptc_execution','finalization'))<4)
                  OR EXISTS (SELECT 1 FROM education_book_job_phase_spans s WHERE s.attempt_id=a.attempt_id AND s.measured_ms IS NULL AND s.ended_at IS NOT NULL)) AS incomplete_count
                FROM education_book_jobs j JOIN education_textbooks b ON b.textbook_id=j.textbook_id
                JOIN education_memberships m ON m.household_id=b.household_id AND m.user_id=%s AND m.role='parent'
                LEFT JOIN education_book_job_items i ON i.job_id=j.job_id
                LEFT JOIN education_book_job_attempts a ON a.item_id=i.item_id AND a.request_round=j.request_round
                WHERE j.job_id=%s GROUP BY j.job_id""",
                (parent_user_id, job_id),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            result = dict(row)
            incomplete = result.pop("incomplete_count")
            result["status"] = (
                ("partial" if incomplete else "available")
                if result["round_total_ms"] is not None
                else "unavailable"
            )
            await cur.execute(
                f"""SELECT a.*, {_PHASE_PROJECTION} AS phases,i.kind,p.title AS knowledge_point_title
                FROM education_book_job_attempts a JOIN education_book_job_items i ON i.item_id=a.item_id AND i.attempt_token=a.attempt_token
                LEFT JOIN education_book_knowledge_points p ON p.knowledge_point_id=i.knowledge_point_id
                WHERE i.job_id=%s AND i.kind='supplementary'""",
                (job_id,),
            )
            result["supplementary"] = [
                {
                    "item_id": r["item_id"],
                    "kind": r["kind"],
                    "status": r["status"],
                    "knowledge_point_title": r["knowledge_point_title"],
                    "timing": _timing_projection(dict(r)),
                }
                for r in await cur.fetchall()
            ]
            return result


async def get_statistics_snapshot(
    *, job_id: UUID, parent_user_id: str, after: tuple[UUID, int] | None, limit: int
) -> tuple[dict[str, Any], list[dict[str, Any]]] | None:
    async with get_db_connection() as conn, conn.transaction():
        await conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        summary = await get_job_statistics_summary(
            job_id=job_id, parent_user_id=parent_user_id, conn=conn
        )
        if summary is None:
            return None
        rows = await list_attempt_statistics(
            job_id=job_id,
            parent_user_id=parent_user_id,
            after=after,
            limit=limit,
            conn=conn,
        )
        return summary, rows or []


async def get_material_chain_progress(*, job_id: UUID, conn=None) -> dict[str, int]:
    async with get_db_connection(conn) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """WITH RECURSIVE chain AS (
                SELECT job_id,previous_job_id FROM education_book_jobs WHERE job_id=%s
                UNION ALL SELECT j.job_id,j.previous_job_id FROM education_book_jobs j JOIN chain c ON j.job_id=c.previous_job_id
                ) SELECT count(DISTINCT i.knowledge_point_id)::int AS total,
                  count(DISTINCT i.knowledge_point_id) FILTER (WHERE i.status='succeeded')::int AS completed
                FROM education_book_job_items i WHERE i.kind='material' AND i.job_id IN (SELECT job_id FROM chain)""",
                (job_id,),
            )
            return dict(await cur.fetchone())
