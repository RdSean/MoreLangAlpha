"""PostgreSQL job, attempt and material fencing for managed textbooks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.server.database.pool import get_db_connection
from src.server.database.education_book_activity import append_terminal_activity

if TYPE_CHECKING:
    from src.server.services.education_book_structure import MoreToSkillsIdentity


async def claim_next_book_item(
    *, worker_id: str, lease_seconds: int, preparation_only: bool = False
) -> dict[str, Any] | None:
    """Atomically claim the next sequential item and fence its execution."""

    if not worker_id.strip():
        raise ValueError("worker_id is required")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    attempt_token = uuid4()
    execution_id = uuid4()
    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            if preparation_only:
                await cur.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended('book-source-capacity', 0))"
                )
                await cur.execute(
                    "SELECT 1 FROM education_book_job_items WHERE status='running' AND execution_phase='source_freezing' LIMIT 1"
                )
                if await cur.fetchone() is not None:
                    return None
            await cur.execute(
                """
                SELECT jobs.job_id
                FROM education_book_jobs AS jobs
                JOIN education_textbooks AS books ON books.textbook_id=jobs.textbook_id
                WHERE jobs.status IN ('queued', 'running')
                  AND jobs.cancel_requested_at IS NULL
                  AND ((%s AND jobs.kind='structure' AND books.source_status IN ('pending','failed','cancelled'))
                    OR (NOT %s AND books.source_status='ready'))
                  AND EXISTS (
                      SELECT 1
                      FROM education_book_job_items AS items
                      WHERE items.job_id = jobs.job_id
                        AND items.status = 'queued'
                        AND NOT EXISTS (
                            SELECT 1
                            FROM education_book_job_items AS earlier
                            WHERE earlier.job_id = items.job_id
                              AND earlier.position < items.position
                              AND earlier.status IN ('queued', 'running')
                        )
                  )
                ORDER BY jobs.created_at, jobs.job_id
                FOR UPDATE OF jobs SKIP LOCKED
                LIMIT 1
                """,
                (preparation_only, preparation_only),
            )
            candidate_job = await cur.fetchone()
            if candidate_job is None:
                return None
            await cur.execute(
                """
                SELECT items.item_id
                FROM education_book_job_items AS items
                WHERE items.job_id = %s AND items.status = 'queued'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM education_book_job_items AS earlier
                      WHERE earlier.job_id = items.job_id
                        AND earlier.position < items.position
                        AND earlier.status IN ('queued', 'running')
                  )
                ORDER BY items.position
                FOR UPDATE OF items
                LIMIT 1
                """,
                (candidate_job["job_id"],),
            )
            candidate = await cur.fetchone()
            if candidate is None:
                return None
            await cur.execute(
                """
                UPDATE education_book_job_items
                SET status = 'running', attempt = attempt + 1,
                    attempt_token = %s, execution_id = %s,
                    lease_owner = %s,
                    lease_expires_at = NOW() + make_interval(secs => %s),
                    started_at = NOW(), finished_at = NULL, safe_error = NULL,
                    execution_phase = %s,
                    updated_at = NOW()
                WHERE item_id = %s AND status = 'queued'
                RETURNING *
                """,
                (
                    attempt_token,
                    execution_id,
                    worker_id,
                    lease_seconds,
                    "source_freezing" if preparation_only else "runtime_queue",
                    candidate["item_id"],
                ),
            )
            item = await cur.fetchone()
            if item is None:
                return None
            if preparation_only:
                await cur.execute(
                    "UPDATE education_textbooks SET source_status='preparing',updated_at=NOW() WHERE textbook_id=(SELECT textbook_id FROM education_book_jobs WHERE job_id=%s) AND source_status<>'ready'",
                    (item["job_id"],),
                )
            await cur.execute(
                """
                UPDATE education_book_jobs
                SET status = 'running', started_at = COALESCE(started_at, NOW()),
                    finished_at = NULL, updated_at = NOW()
                WHERE job_id = %s
                  AND status IN ('queued', 'running', 'failed', 'not_run')
                """,
                (item["job_id"],),
            )
            await cur.execute(
                """
                SELECT items.*, jobs.textbook_id, jobs.kind AS job_kind,
                       jobs.depth, jobs.requirements, jobs.replace_existing,
                       jobs.include_supplementary, jobs.requested_by_user_id,
                       jobs.more_to_skills_version, jobs.skill_sha256,
                       jobs.schema_sha256, textbooks.household_id,
                       textbooks.slug, textbooks.source_markdown_key,
                       textbooks.source_blocks_key, textbooks.source_report_key,
                       textbooks.source_asset_manifest,
                       textbooks.source_snapshot_prefix,
                       textbooks.source_filename, textbooks.source_format,
                       textbooks.source_content_sha256,
                       textbooks.source_status, textbooks.preparation_descriptor,
                       textbooks.selected_source,
                       points.skill_kp_id, points.knowledge_point_json,
                       structures.structure_id, structures.structure_json,
                       CASE
                           WHEN items.kind = 'structure' THEN 'structure'
                           ELSE 'material'
                       END AS operation
                FROM education_book_job_items AS items
                JOIN education_book_jobs AS jobs ON jobs.job_id = items.job_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = jobs.textbook_id
                LEFT JOIN education_book_knowledge_points AS points
                  ON points.knowledge_point_id = items.knowledge_point_id
                LEFT JOIN education_book_structures AS structures
                  ON structures.structure_id = points.structure_id
                WHERE items.item_id = %s
                """,
                (item["item_id"],),
            )
            claimed = await cur.fetchone()
            return dict(claimed) if claimed is not None else None


async def request_book_job_cancel(*, job_id: str | UUID) -> dict[str, Any] | None:
    """Persist a business cancel fence and return the runtime now under it."""

    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE education_book_jobs
                SET cancel_requested_at = COALESCE(cancel_requested_at, NOW()),
                    updated_at = NOW()
                WHERE job_id = %s AND status IN ('queued', 'running')
                RETURNING job_id, cancel_requested_at
                """,
                (job_id,),
            )
            job = await cur.fetchone()
            if job is None:
                return None
            await cur.execute(
                """
                SELECT items.item_id, items.attempt_token,
                       items.managed_thread_id AS thread_id, items.run_id
                FROM education_book_job_items AS items
                WHERE items.job_id = %s AND items.status = 'running'
                ORDER BY items.position
                LIMIT 1
                """,
                (job_id,),
            )
            item = await cur.fetchone()
            return {
                **dict(job),
                "item_id": item["item_id"] if item is not None else None,
                "attempt_token": (item["attempt_token"] if item is not None else None),
                "thread_id": item["thread_id"] if item is not None else None,
                "run_id": item["run_id"] if item is not None else None,
            }


async def get_book_job_cancel_context(*, job_id: str | UUID) -> dict[str, Any] | None:
    """Load the active item and runtime identity used by cross-worker cancel."""

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.job_id, items.item_id, items.attempt_token,
                       items.managed_thread_id AS thread_id, items.run_id
                FROM education_book_jobs AS jobs
                LEFT JOIN education_book_job_items AS items
                  ON items.job_id = jobs.job_id AND items.status = 'running'
                WHERE jobs.job_id = %s AND jobs.status IN ('queued', 'running')
                ORDER BY items.position
                LIMIT 1
                """,
                (job_id,),
            )
            row = await cur.fetchone()
            return dict(row) if row is not None else None


async def bind_book_item_runtime(
    *,
    item_id: str | UUID,
    attempt_token: UUID,
    workspace_id: str | UUID,
    thread_id: str | UUID,
    run_id: str | UUID,
) -> dict[str, Any]:
    """Persist the normal root-run identities under the current attempt fence."""

    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE education_book_job_items
                SET managed_workspace_id = %s, managed_thread_id = %s,
                    run_id = %s, updated_at = NOW()
                WHERE item_id = %s AND status = 'running'
                  AND attempt_token = %s
                  AND (
                      run_id IS NULL OR (
                          managed_workspace_id = %s
                          AND managed_thread_id = %s
                          AND run_id = %s
                      )
                  )
                RETURNING *
                """,
                (
                    workspace_id,
                    thread_id,
                    run_id,
                    item_id,
                    attempt_token,
                    workspace_id,
                    thread_id,
                    run_id,
                ),
            )
            item = await cur.fetchone()
            if item is None:
                raise RuntimeError("Book item attempt is stale or already bound")
            return dict(item)


async def renew_book_item_lease(
    *,
    item_id: str | UUID,
    attempt_token: UUID,
    worker_id: str,
    lease_seconds: int,
) -> bool:
    """Extend a live attempt lease without changing its runtime identity."""

    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE education_book_job_items
                SET lease_owner = %s,
                    lease_expires_at = NOW() + make_interval(secs => %s),
                    updated_at = NOW()
                WHERE item_id = %s AND status = 'running'
                  AND attempt_token = %s
                """,
                (worker_id, lease_seconds, item_id, attempt_token),
            )
            return cur.rowcount == 1


async def list_book_items_for_recovery(*, limit: int = 100) -> list[dict[str, Any]]:
    """Return expired running attempts with all persisted recovery identity."""

    if limit <= 0:
        return []
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT items.*, jobs.textbook_id, jobs.kind AS job_kind,
                       jobs.depth, jobs.requirements, jobs.requested_by_user_id,
                       jobs.more_to_skills_version, jobs.skill_sha256,
                       jobs.schema_sha256, textbooks.household_id,
                       textbooks.slug, textbooks.source_snapshot_prefix,
                       textbooks.source_markdown_key, textbooks.source_blocks_key,
                       textbooks.source_report_key, textbooks.source_asset_manifest,
                       textbooks.source_filename, textbooks.source_format,
                       textbooks.source_content_sha256,
                       points.skill_kp_id, points.knowledge_point_json,
                       structures.structure_id, structures.structure_json,
                       CASE
                           WHEN items.kind = 'structure' THEN 'structure'
                           ELSE 'material'
                       END AS operation
                FROM education_book_job_items AS items
                JOIN education_book_jobs AS jobs ON jobs.job_id = items.job_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = jobs.textbook_id
                LEFT JOIN education_book_knowledge_points AS points
                  ON points.knowledge_point_id = items.knowledge_point_id
                LEFT JOIN education_book_structures AS structures
                  ON structures.structure_id = points.structure_id
                WHERE items.status = 'running'
                  AND jobs.cancel_requested_at IS NULL
                  AND (
                      items.lease_expires_at IS NULL
                      OR items.lease_expires_at <= NOW()
                  )
                ORDER BY items.updated_at, items.item_id
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in await cur.fetchall()]


async def list_book_jobs_pending_cancellation(
    *, limit: int = 100
) -> list[dict[str, Any]]:
    """Return active jobs whose durable business cancellation needs settling."""

    if limit <= 0:
        return []
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.job_id, items.item_id, items.attempt_token,
                       items.thread_id, items.run_id
                FROM education_book_jobs AS jobs
                LEFT JOIN LATERAL (
                    SELECT item_id, attempt_token,
                           managed_thread_id AS thread_id, run_id
                    FROM education_book_job_items
                    WHERE job_id = jobs.job_id AND status = 'running'
                    ORDER BY position
                    LIMIT 1
                ) AS items ON TRUE
                WHERE jobs.cancel_requested_at IS NOT NULL
                  AND jobs.status IN (
                      'queued', 'running', 'failed', 'partially_succeeded'
                  )
                ORDER BY jobs.cancel_requested_at, jobs.job_id
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in await cur.fetchall()]


async def list_book_items_for_terminal_cleanup(
    *, limit: int = 100
) -> list[dict[str, Any]]:
    """List settled attempts whose exact object or managed-runtime cleanup remains."""

    if limit <= 0:
        return []
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT items.item_id, items.attempt_token,
                       items.managed_workspace_id, items.managed_thread_id
                FROM education_book_job_items AS items
                LEFT JOIN workspaces
                  ON workspaces.workspace_id = items.managed_workspace_id
                LEFT JOIN conversation_threads AS threads
                  ON threads.conversation_thread_id = items.managed_thread_id
                WHERE items.status IN (
                    'succeeded', 'failed', 'cancelled', 'not_run'
                )
                  AND items.attempt_token IS NOT NULL
                  AND (
                      items.candidate_objects <> '[]'::jsonb
                      OR (
                          workspaces.workspace_id IS NOT NULL
                          AND workspaces.status <> 'deleted'
                      )
                      OR (
                          threads.conversation_thread_id IS NOT NULL
                          AND threads.archived_at IS NULL
                      )
                  )
                ORDER BY items.updated_at, items.item_id
                LIMIT %s
                """,
                (limit,),
            )
            return [dict(row) for row in await cur.fetchall()]


async def _lock_book_job_for_item(
    cur,
    *,
    item_id: str | UUID,
    reject_cancel_requested: bool = False,
) -> UUID:
    """Lock the owning job before any terminal item mutation."""

    await cur.execute(
        """
        SELECT jobs.job_id, jobs.cancel_requested_at
        FROM education_book_jobs AS jobs
        JOIN education_book_job_items AS items ON items.job_id = jobs.job_id
        WHERE items.item_id = %s
        FOR UPDATE OF jobs
        """,
        (item_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise LookupError("Book job item was not found")
    if reject_cancel_requested and row["cancel_requested_at"] is not None:
        raise RuntimeError("Textbook job cancellation was requested")
    return row["job_id"]


async def fail_book_item(
    *,
    item_id: str | UUID,
    attempt_token: UUID,
    safe_error: str,
    stop_remaining: bool,
) -> dict[str, Any]:
    """Fail the current attempt and optionally stop the remaining queue."""

    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            job_id = await _lock_book_job_for_item(cur, item_id=item_id)
            await cur.execute(
                """
                UPDATE education_book_job_items
                SET status = 'failed', safe_error = %s, finished_at = NOW(),
                    lease_owner = NULL, lease_expires_at = NULL,
                    updated_at = NOW()
                WHERE item_id = %s AND status = 'running'
                  AND attempt_token = %s
                RETURNING job_id
                """,
                (safe_error, item_id, attempt_token),
            )
            failed = await cur.fetchone()
            if failed is None:
                raise RuntimeError("Book item attempt is stale")
            if stop_remaining:
                await cur.execute(
                    """
                    UPDATE education_book_job_items
                    SET status = 'not_run', safe_error = %s,
                        finished_at = NOW(), updated_at = NOW()
                    WHERE job_id = %s AND status = 'queued'
                    RETURNING item_id
                    """,
                    ("Stopped after an infrastructure failure", job_id),
                )
                not_run_item_ids = [row["item_id"] for row in await cur.fetchall()]
            else:
                not_run_item_ids = []
            await cur.execute(
                """
                SELECT
                    count(*) FILTER (WHERE status = 'succeeded')::int AS succeeded,
                    count(*) FILTER (WHERE status = 'failed')::int AS failed,
                    count(*) FILTER (WHERE status = 'cancelled')::int AS cancelled,
                    count(*) FILTER (WHERE status = 'not_run')::int AS not_run,
                    count(*) FILTER (WHERE status IN ('queued', 'running'))::int AS active
                FROM education_book_job_items WHERE job_id = %s
                """,
                (job_id,),
            )
            counts = await cur.fetchone()
            terminal = counts["active"] == 0
            status = (
                "running"
                if not terminal
                else "partially_succeeded"
                if counts["succeeded"] > 0
                else "failed"
            )
            await cur.execute(
                """
                UPDATE education_book_jobs
                SET status = %s, succeeded_items = %s, failed_items = %s,
                    cancelled_items = %s, not_run_items = %s,
                    safe_error = %s,
                    finished_at = CASE WHEN %s THEN NOW() ELSE NULL END,
                    updated_at = NOW()
                WHERE job_id = %s
                RETURNING *
                """,
                (
                    status,
                    counts["succeeded"],
                    counts["failed"],
                    counts["cancelled"],
                    counts["not_run"],
                    safe_error,
                    terminal,
                    job_id,
                ),
            )
            job = await cur.fetchone()
            last_seq = await append_terminal_activity(
                cur,
                job_id=job_id,
                dedupe_key=f"item-failed:{item_id}:{attempt_token}",
                item_id=UUID(str(item_id)),
                kind="item",
                status="failed",
                message=safe_error,
            )
            for not_run_item_id in not_run_item_ids:
                last_seq = await append_terminal_activity(
                    cur,
                    job_id=job_id,
                    dedupe_key=f"item-not-run:{not_run_item_id}",
                    item_id=not_run_item_id,
                    kind="item",
                    status="not_run",
                    message="Item was not run after an infrastructure failure",
                )
            if terminal:
                last_seq = await append_terminal_activity(
                    cur,
                    job_id=job_id,
                    dedupe_key=f"job-terminal:{job_id}",
                    item_id=None,
                    kind="job",
                    status=status,
                    message=(
                        "Job completed with errors"
                        if status == "partially_succeeded"
                        else "Job failed"
                    ),
                )
            result = dict(job)
            if last_seq is not None:
                result["high_water_seq"] = last_seq
            return result


async def retry_book_job(
    *,
    source_job_id: str | UUID,
    requested_by_user_id: str,
    idempotency_key: str,
    identity: MoreToSkillsIdentity,
) -> dict[str, Any]:
    """Create a new job containing every unfinished source item."""

    new_job_id = uuid4()
    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.*
                FROM education_book_jobs AS jobs
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = jobs.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                 AND memberships.user_id = %s
                 AND memberships.role = 'parent'
                WHERE jobs.job_id = %s
                  AND jobs.status IN (
                      'failed', 'partially_succeeded', 'cancelled'
                  )
                FOR UPDATE OF jobs
                """,
                (requested_by_user_id, source_job_id),
            )
            source = await cur.fetchone()
            if source is None:
                raise LookupError("Retryable textbook job was not found")
            await cur.execute(
                """
                SELECT * FROM education_book_jobs
                WHERE textbook_id = %s AND idempotency_key = %s
                """,
                (source["textbook_id"], idempotency_key),
            )
            existing = await cur.fetchone()
            if existing is not None:
                return await _load_job_with_items(cur, job_id=existing["job_id"])
            await cur.execute(
                """
                SELECT *
                FROM education_book_job_items
                WHERE job_id = %s
                  AND status IN ('failed', 'not_run', 'cancelled')
                ORDER BY position
                """,
                (source_job_id,),
            )
            unfinished = [dict(row) for row in await cur.fetchall()]
            if not unfinished:
                raise ValueError("Textbook job has no unfinished items")
            target_ids = [
                str(item["knowledge_point_id"])
                for item in unfinished
                if item["knowledge_point_id"] is not None
            ]
            await cur.execute(
                """
                INSERT INTO education_book_jobs (
                    job_id, textbook_id, kind, status, idempotency_key,
                    target_knowledge_point_ids, depth, requirements,
                    replace_existing, include_supplementary,
                    more_to_skills_version, skill_sha256, schema_sha256,
                    requested_by_user_id, total_items, follow_up_request,
                    request_round, previous_job_id
                ) VALUES (
                    %s, %s, %s, 'queued', %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s
                )
                """,
                (
                    new_job_id,
                    source["textbook_id"],
                    source["kind"],
                    idempotency_key,
                    Jsonb(target_ids),
                    source["depth"],
                    source["requirements"],
                    source["replace_existing"],
                    source["include_supplementary"],
                    identity.version,
                    identity.skill_sha256,
                    identity.schema_sha256,
                    requested_by_user_id,
                    len(unfinished),
                    (
                        Jsonb(source["follow_up_request"])
                        if source["follow_up_request"] is not None
                        else None
                    ),
                    source["request_round"] + 1,
                    source["job_id"],
                ),
            )
            await cur.executemany(
                """
                INSERT INTO education_book_job_items (
                    item_id, job_id, position, kind,
                    knowledge_point_id, status
                ) VALUES (%s, %s, %s, %s, %s, 'queued')
                """,
                [
                    (
                        uuid4(),
                        new_job_id,
                        position,
                        item["kind"],
                        item["knowledge_point_id"],
                    )
                    for position, item in enumerate(unfinished, start=1)
                ],
            )
            return await _load_job_with_items(cur, job_id=new_job_id)


async def mark_book_job_cancelled(
    *,
    job_id: str | UUID,
    item_id: str | UUID | None,
    attempt_token: UUID | None,
) -> dict[str, Any]:
    """Atomically fence every live attempt and return their runtime identities."""

    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT job_id FROM education_book_jobs
                WHERE job_id = %s
                  AND status IN (
                      'queued', 'running', 'failed', 'partially_succeeded'
                  )
                FOR UPDATE
                """,
                (job_id,),
            )
            if await cur.fetchone() is None:
                raise RuntimeError("Textbook job is no longer active")
            await cur.execute(
                """
                SELECT item_id, status, attempt_token,
                       managed_thread_id AS thread_id, run_id
                FROM education_book_job_items
                WHERE job_id = %s
                  AND status IN ('queued', 'running', 'failed', 'not_run')
                ORDER BY position
                FOR UPDATE
                """,
                (job_id,),
            )
            cancelled_items = [dict(row) for row in await cur.fetchall()]
            runtime_contexts = [
                {
                    key: row[key]
                    for key in ("item_id", "attempt_token", "thread_id", "run_id")
                }
                for row in cancelled_items
                if row["status"] == "running"
            ]
            await cur.execute(
                """
                UPDATE education_book_job_items
                SET status = 'cancelled', finished_at = NOW(),
                    lease_owner = NULL, lease_expires_at = NULL,
                    updated_at = NOW()
                WHERE job_id = %s
                  AND status IN ('queued', 'running', 'failed', 'not_run')
                """,
                (job_id,),
            )
            await cur.execute(
                """
                SELECT
                    count(*) FILTER (WHERE status = 'succeeded')::int AS succeeded,
                    count(*) FILTER (WHERE status = 'failed')::int AS failed,
                    count(*) FILTER (WHERE status = 'cancelled')::int AS cancelled,
                    count(*) FILTER (WHERE status = 'not_run')::int AS not_run
                FROM education_book_job_items WHERE job_id = %s
                """,
                (job_id,),
            )
            counts = await cur.fetchone()
            await cur.execute(
                """
                UPDATE education_book_jobs
                SET status = 'cancelled', succeeded_items = %s,
                    failed_items = %s, cancelled_items = %s,
                    not_run_items = %s,
                    finished_at = NOW(), updated_at = NOW()
                WHERE job_id = %s
                  AND status IN (
                      'queued', 'running', 'failed', 'partially_succeeded'
                  )
                RETURNING *
                """,
                (
                    counts["succeeded"],
                    counts["failed"],
                    counts["cancelled"],
                    counts["not_run"],
                    job_id,
                ),
            )
            job = await cur.fetchone()
            if job is None:
                raise RuntimeError("Textbook job is no longer active")
            last_seq = None
            for cancelled_item in cancelled_items:
                last_seq = await append_terminal_activity(
                    cur,
                    job_id=UUID(str(job_id)),
                    dedupe_key=f"item-cancelled:{cancelled_item['item_id']}",
                    item_id=cancelled_item["item_id"],
                    kind="item",
                    status="cancelled",
                    message="Item cancelled",
                    supersede=True,
                )
            last_seq = await append_terminal_activity(
                cur,
                job_id=UUID(str(job_id)),
                dedupe_key=f"job-terminal:{job_id}",
                item_id=None,
                kind="job",
                status="cancelled",
                message="Job cancelled",
                supersede=True,
            )
            result = dict(job)
            if last_seq is not None:
                result["high_water_seq"] = last_seq
            result["runtime_contexts"] = runtime_contexts
            return result


def _material_result_snapshot(material: dict[str, Any]) -> dict[str, Any]:
    """Return the immutable result owned by one completed material item."""

    return {
        "material_id": str(material["material_id"]),
        "knowledge_point_id": str(material["knowledge_point_id"]),
        "generation": material["generation"],
        "content_key": material["content_key"],
        "content_sha256": material["content_sha256"],
        "size_bytes": material["size_bytes"],
        "format": material["format"],
        "depth": material["depth"],
        "requirements": material["requirements"],
        "generation_params": material["generation_params"],
        "source_job_id": str(material["source_job_id"]),
        "source_item_id": str(material["source_item_id"]),
    }


async def get_book_job_for_parent(
    *,
    job_id: str | UUID,
    parent_user_id: str,
) -> dict[str, Any] | None:
    """Return the public job snapshot when the user is a parent in its household."""

    job_id = UUID(str(job_id))
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.job_id, jobs.textbook_id, jobs.kind, jobs.status,
                       jobs.total_items, jobs.succeeded_items,
                       jobs.failed_items, jobs.cancelled_items,
                       jobs.not_run_items, jobs.high_water_seq,
                       jobs.activity_status, jobs.created_at, jobs.started_at,
                       jobs.finished_at, jobs.safe_error, jobs.depth,
                       jobs.requirements, jobs.replace_existing,
                       jobs.include_supplementary,
                       jobs.request_round, jobs.round_accepted_at, NOW() AS server_now,
                       COALESCE((
                           SELECT jsonb_agg(
                               jsonb_build_object(
                                   'item_id', items.item_id,
                                   'kind', items.kind,
                                   'position', items.position,
                                   'knowledge_point_id', items.knowledge_point_id,
                                   'skill_kp_id', points.skill_kp_id,
                                   'knowledge_point_title', CASE
                                       WHEN items.kind = 'material' THEN points.title
                                       ELSE NULL END,
                                   'status', items.status,
                                   'attempt', items.attempt,
                                   'safe_error', items.safe_error,
                                   'started_at', items.started_at,
                                   'finished_at', items.finished_at
                                   , 'execution_phase', items.execution_phase
                                   , 'queued_at', items.queued_at
                               ) ORDER BY items.position
                           )
                           FROM education_book_job_items AS items
                           LEFT JOIN education_book_knowledge_points AS points
                             ON points.knowledge_point_id = items.knowledge_point_id
                           WHERE items.job_id = jobs.job_id
                       ), '[]'::jsonb) AS items
                FROM education_book_jobs AS jobs
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = jobs.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                 AND memberships.user_id = %s
                 AND memberships.role = 'parent'
                WHERE jobs.job_id = %s
                """,
                (parent_user_id, job_id),
            )
            job = await cur.fetchone()
            if job is None:
                return None

    result = dict(job)
    result["job_id"] = str(result["job_id"])
    result["textbook_id"] = str(result["textbook_id"])
    result["items"] = [dict(item) for item in result["items"]]
    from src.server.database.education_book_timing import get_current_attempt_summaries

    timings = await get_current_attempt_summaries(job_id=job_id)
    for item in result["items"]:
        current = timings.get(str(item["item_id"]))
        item["timing_summary"] = current["timing"] if current else None
        item["preparation_progress"] = current["progress"] if current else None
    return result


async def _load_job_with_items(cur, *, job_id: UUID) -> dict[str, Any]:
    await cur.execute(
        "SELECT * FROM education_book_jobs WHERE job_id = %s",
        (job_id,),
    )
    job = await cur.fetchone()
    if job is None:
        raise RuntimeError("Idempotent book job was not found")
    await cur.execute(
        """
        SELECT * FROM education_book_job_items
        WHERE job_id = %s ORDER BY position
        """,
        (job_id,),
    )
    result = dict(job)
    result["items"] = [dict(row) for row in await cur.fetchall()]
    return result


def _assert_material_request_matches(
    job: dict[str, Any],
    *,
    knowledge_point_ids: list[UUID],
    depth: str,
    requirements: str | None,
    replace_existing: bool,
    include_supplementary: bool,
    identity: MoreToSkillsIdentity,
) -> None:
    expected_targets = [str(value) for value in knowledge_point_ids]
    matches = (
        job["kind"] == "materials"
        and list(job["target_knowledge_point_ids"] or []) == expected_targets
        and job["depth"] == depth
        and job["requirements"] == requirements
        and job["replace_existing"] is replace_existing
        and job["include_supplementary"] is include_supplementary
        and job["more_to_skills_version"] == identity.version
        and job["skill_sha256"] == identity.skill_sha256
        and job["schema_sha256"] == identity.schema_sha256
    )
    if not matches:
        raise ValueError("Idempotency key conflicts with a different book job request")


async def _load_matching_material_job(
    cur,
    *,
    job_id: UUID,
    knowledge_point_ids: list[UUID],
    depth: str,
    requirements: str | None,
    replace_existing: bool,
    include_supplementary: bool,
    identity: MoreToSkillsIdentity,
) -> dict[str, Any]:
    job = await _load_job_with_items(cur, job_id=job_id)
    _assert_material_request_matches(
        job,
        knowledge_point_ids=knowledge_point_ids,
        depth=depth,
        requirements=requirements,
        replace_existing=replace_existing,
        include_supplementary=include_supplementary,
        identity=identity,
    )
    return job


async def create_materials_job(
    *,
    textbook_id: str | UUID,
    requested_by_user_id: str,
    knowledge_point_ids: list[str | UUID],
    depth: str,
    requirements: str | None,
    replace_existing: bool,
    include_supplementary: bool,
    idempotency_key: str,
    identity: MoreToSkillsIdentity,
) -> dict[str, Any]:
    """Freeze a validated material target list and its queue items."""

    unique_ids = list(dict.fromkeys(UUID(str(value)) for value in knowledge_point_ids))
    if not unique_ids:
        raise ValueError("At least one knowledge point is required")
    job_id = uuid4()
    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.job_id
                FROM education_book_jobs AS jobs
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = jobs.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                 AND memberships.user_id = %s
                 AND memberships.role = 'parent'
                WHERE jobs.textbook_id = %s AND jobs.idempotency_key = %s
                """,
                (requested_by_user_id, textbook_id, idempotency_key),
            )
            existing = await cur.fetchone()
            if existing is not None:
                return await _load_matching_material_job(
                    cur,
                    job_id=existing["job_id"],
                    knowledge_point_ids=unique_ids,
                    depth=depth,
                    requirements=requirements,
                    replace_existing=replace_existing,
                    include_supplementary=include_supplementary,
                    identity=identity,
                )
            await cur.execute(
                """
                SELECT points.knowledge_point_id
                FROM education_textbooks AS textbooks
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                 AND memberships.user_id = %s
                 AND memberships.role = 'parent'
                JOIN education_book_knowledge_points AS points
                  ON points.structure_id = textbooks.current_structure_id
                WHERE textbooks.textbook_id = %s
                  AND points.knowledge_point_id = ANY(%s::uuid[])
                """,
                (requested_by_user_id, textbook_id, unique_ids),
            )
            found = {row["knowledge_point_id"] for row in await cur.fetchall()}
            if found != set(unique_ids):
                raise ValueError(
                    "Material targets must belong to the current structure"
                )
            await cur.execute(
                """
                INSERT INTO education_book_jobs (
                    job_id, textbook_id, kind, status, idempotency_key,
                    target_knowledge_point_ids, depth, requirements,
                    replace_existing, include_supplementary,
                    more_to_skills_version, skill_sha256, schema_sha256,
                    requested_by_user_id, total_items
                ) VALUES (
                    %s, %s, 'materials', 'queued', %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s
                )
                ON CONFLICT (textbook_id, idempotency_key) DO NOTHING
                RETURNING job_id
                """,
                (
                    job_id,
                    textbook_id,
                    idempotency_key,
                    Jsonb([str(value) for value in unique_ids]),
                    depth,
                    requirements,
                    replace_existing,
                    include_supplementary,
                    identity.version,
                    identity.skill_sha256,
                    identity.schema_sha256,
                    requested_by_user_id,
                    len(unique_ids) + int(include_supplementary),
                ),
            )
            inserted = await cur.fetchone()
            if inserted is None:
                await cur.execute(
                    """
                    SELECT job_id FROM education_book_jobs
                    WHERE textbook_id = %s AND idempotency_key = %s
                    """,
                    (textbook_id, idempotency_key),
                )
                existing = await cur.fetchone()
                if existing is None:
                    raise RuntimeError("Idempotent book job was not found")
                return await _load_matching_material_job(
                    cur,
                    job_id=existing["job_id"],
                    knowledge_point_ids=unique_ids,
                    depth=depth,
                    requirements=requirements,
                    replace_existing=replace_existing,
                    include_supplementary=include_supplementary,
                    identity=identity,
                )
            rows = [
                (uuid4(), job_id, position, "material", knowledge_point_id)
                for position, knowledge_point_id in enumerate(unique_ids, start=1)
            ]
            if include_supplementary:
                rows.append((uuid4(), job_id, len(rows) + 1, "supplementary", None))
            await cur.executemany(
                """
                INSERT INTO education_book_job_items (
                    item_id, job_id, position, kind,
                    knowledge_point_id, status
                ) VALUES (%s, %s, %s, %s, %s, 'queued')
                """,
                rows,
            )
            return await _load_job_with_items(cur, job_id=job_id)


async def start_item_attempt(
    *, item_id: str | UUID, attempt_token: UUID
) -> dict[str, Any]:
    """Fence a queued item to one current attempt token."""

    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            job_id = await _lock_book_job_for_item(cur, item_id=item_id)
            await cur.execute(
                """
                UPDATE education_book_job_items
                SET status = 'running', attempt = attempt + 1,
                    attempt_token = %s, started_at = NOW(),
                    execution_phase = 'runtime_queue',
                    finished_at = NULL, safe_error = NULL, updated_at = NOW()
                WHERE item_id = %s AND job_id = %s AND status = 'queued'
                RETURNING *
                """,
                (attempt_token, item_id, job_id),
            )
            item = await cur.fetchone()
            if item is None:
                raise RuntimeError("Book job item is not queued")
            await cur.execute(
                """
                UPDATE education_book_jobs
                SET status = 'running', started_at = COALESCE(started_at, NOW()),
                    updated_at = NOW()
                WHERE job_id = %s AND status = 'queued'
                """,
                (item["job_id"],),
            )
            return dict(item)


async def record_candidate_object(
    *, item_id: str | UUID, attempt_token: UUID, content_key: str
) -> None:
    """Persist an exact immutable object key before uploading its bytes."""

    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT candidate_objects FROM education_book_job_items
                WHERE item_id = %s AND status = 'running'
                  AND attempt_token = %s
                FOR UPDATE
                """,
                (item_id, attempt_token),
            )
            row = await cur.fetchone()
            if row is None:
                raise RuntimeError("Book material attempt is stale")
            candidates = list(row["candidate_objects"] or [])
            if content_key not in candidates:
                candidates.append(content_key)
                await cur.execute(
                    """
                    UPDATE education_book_job_items
                    SET candidate_objects = %s, updated_at = NOW()
                    WHERE item_id = %s
                    """,
                    (Jsonb(candidates), item_id),
                )


async def get_book_item_candidate_cleanup_context(
    *, item_id: str | UUID, attempt_token: UUID
) -> dict[str, Any] | None:
    """Load exact candidate keys after an attempt reaches a business terminal state."""

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT items.candidate_objects, items.result_snapshot,
                       items.kind, items.knowledge_point_id,
                       jobs.textbook_id, textbooks.household_id
                FROM education_book_job_items AS items
                JOIN education_book_jobs AS jobs ON jobs.job_id = items.job_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = jobs.textbook_id
                WHERE items.item_id = %s AND items.attempt_token = %s
                  AND items.status IN (
                      'succeeded', 'failed', 'cancelled', 'not_run'
                  )
                """,
                (item_id, attempt_token),
            )
            row = await cur.fetchone()
    return dict(row) if row is not None else None


async def forget_book_candidate_object(
    *, item_id: str | UUID, attempt_token: UUID, content_key: str
) -> bool:
    """Remove one settled candidate key without enumerating object storage."""

    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT candidate_objects
                FROM education_book_job_items
                WHERE item_id = %s AND attempt_token = %s
                  AND status IN ('succeeded', 'failed', 'cancelled', 'not_run')
                FOR UPDATE
                """,
                (item_id, attempt_token),
            )
            row = await cur.fetchone()
            if row is None:
                return False
            candidates = list(row["candidate_objects"] or [])
            if content_key not in candidates:
                return True
            candidates.remove(content_key)
            await cur.execute(
                """
                UPDATE education_book_job_items
                SET candidate_objects = %s, updated_at = NOW()
                WHERE item_id = %s
                """,
                (Jsonb(candidates), item_id),
            )
            return True


async def get_material_attempt_context(
    *, item_id: str | UUID, attempt_token: UUID
) -> dict[str, Any]:
    """Load storage identities and frozen request fields for one live attempt."""

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT textbooks.household_id, textbooks.textbook_id,
                       items.knowledge_point_id, jobs.depth, jobs.requirements,
                       jobs.more_to_skills_version, jobs.skill_sha256,
                       jobs.schema_sha256
                FROM education_book_job_items AS items
                JOIN education_book_jobs AS jobs ON jobs.job_id = items.job_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = jobs.textbook_id
                JOIN education_book_knowledge_points AS points
                  ON points.knowledge_point_id = items.knowledge_point_id
                JOIN education_book_structures AS structures
                  ON structures.structure_id = points.structure_id
                 AND structures.textbook_id = jobs.textbook_id
                WHERE items.item_id = %s
                  AND items.status = 'running'
                  AND items.attempt_token = %s
                  AND items.kind = 'material'
                """,
                (item_id, attempt_token),
            )
            row = await cur.fetchone()
    if row is None:
        raise RuntimeError("Book material attempt is stale")
    return dict(row)


async def get_supplementary_attempt_context(
    *, item_id: str | UUID, attempt_token: UUID
) -> dict[str, Any]:
    """Load object-storage identities for one live supplementary attempt."""

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT textbooks.household_id, textbooks.textbook_id
                FROM education_book_job_items AS items
                JOIN education_book_jobs AS jobs ON jobs.job_id = items.job_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = jobs.textbook_id
                WHERE items.item_id = %s AND items.status = 'running'
                  AND items.attempt_token = %s
                  AND items.kind = 'supplementary'
                """,
                (item_id, attempt_token),
            )
            row = await cur.fetchone()
    if row is None:
        raise RuntimeError("Book supplementary attempt is stale")
    return dict(row)


async def finalize_supplementary(
    *,
    item_id: str | UUID,
    attempt_token: UUID,
    result_snapshot: dict[str, Any],
) -> dict[str, Any]:
    """Commit the immutable supplementary object manifest and terminal state."""

    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            job_id = await _lock_book_job_for_item(
                cur,
                item_id=item_id,
                reject_cancel_requested=True,
            )
            await cur.execute(
                """
                SELECT * FROM education_book_job_items
                WHERE item_id = %s AND job_id = %s
                FOR UPDATE
                """,
                (item_id, job_id),
            )
            item = await cur.fetchone()
            if item is None:
                raise LookupError("Book supplementary item was not found")
            if item["status"] == "succeeded":
                if item["result_snapshot"] == result_snapshot:
                    return dict(result_snapshot)
                raise RuntimeError(
                    "Book supplementary item was already finalized differently"
                )
            if item["status"] != "running" or item["attempt_token"] != attempt_token:
                raise RuntimeError("Book supplementary attempt is stale")
            content_keys = {
                str(file["content_key"])
                for file in result_snapshot.get("files", [])
                if isinstance(file, dict) and file.get("content_key")
            }
            if not content_keys or not content_keys.issubset(
                set(item["candidate_objects"] or [])
            ):
                raise RuntimeError(
                    "Supplementary objects were not registered for this attempt"
                )
            await cur.execute(
                """
                UPDATE education_book_job_items
                SET status = 'succeeded', result_snapshot = %s,
                    finished_at = NOW(), lease_owner = NULL,
                    lease_expires_at = NULL, updated_at = NOW()
                WHERE item_id = %s
                """,
                (Jsonb(result_snapshot), item_id),
            )
            await cur.execute(
                """
                SELECT
                    count(*) FILTER (WHERE status = 'succeeded')::int AS succeeded,
                    count(*) FILTER (WHERE status = 'failed')::int AS failed,
                    count(*) FILTER (WHERE status = 'cancelled')::int AS cancelled,
                    count(*) FILTER (WHERE status = 'not_run')::int AS not_run,
                    count(*) FILTER (WHERE status IN ('queued', 'running'))::int AS active
                FROM education_book_job_items WHERE job_id = %s
                """,
                (item["job_id"],),
            )
            counts = await cur.fetchone()
            terminal = counts["active"] == 0
            status = (
                "running"
                if not terminal
                else "succeeded"
                if counts["failed"] == counts["cancelled"] == counts["not_run"] == 0
                else "partially_succeeded"
                if counts["succeeded"] > 0
                else "failed"
            )
            await cur.execute(
                """
                UPDATE education_book_jobs
                SET status = %s, succeeded_items = %s, failed_items = %s,
                    cancelled_items = %s, not_run_items = %s,
                    finished_at = CASE WHEN %s THEN NOW() ELSE NULL END,
                    updated_at = NOW()
                WHERE job_id = %s
                RETURNING job_id
                """,
                (
                    status,
                    counts["succeeded"],
                    counts["failed"],
                    counts["cancelled"],
                    counts["not_run"],
                    terminal,
                    item["job_id"],
                ),
            )
            await cur.fetchone()
            await append_terminal_activity(
                cur,
                job_id=item["job_id"],
                dedupe_key=f"supplementary-committed:{item_id}",
                item_id=UUID(str(item_id)),
                kind="supplementary",
                status="succeeded",
                message="Supplementary files committed",
            )
            if terminal:
                await append_terminal_activity(
                    cur,
                    job_id=item["job_id"],
                    dedupe_key=f"job-terminal:{item['job_id']}",
                    item_id=None,
                    kind="job",
                    status=status,
                    message=(
                        "Job completed"
                        if status == "succeeded"
                        else "Job completed with errors"
                    ),
                )
            return dict(result_snapshot)


async def finalize_material(
    *,
    item_id: str | UUID,
    attempt_token: UUID,
    content_key: str,
    content_sha256: str,
    size_bytes: int,
    generation_params: dict[str, Any],
) -> dict[str, Any]:
    """CAS the current material and item terminal state in one transaction."""

    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            job_id = await _lock_book_job_for_item(
                cur,
                item_id=item_id,
                reject_cancel_requested=True,
            )
            await cur.execute(
                """
                SELECT items.*, jobs.textbook_id, jobs.depth, jobs.requirements
                FROM education_book_job_items AS items
                JOIN education_book_jobs AS jobs ON jobs.job_id = items.job_id
                WHERE items.item_id = %s AND jobs.job_id = %s
                FOR UPDATE OF items
                """,
                (item_id, job_id),
            )
            item = await cur.fetchone()
            if item is None:
                raise LookupError("Book material item was not found")
            if item["status"] == "succeeded":
                prior_result = item["result_snapshot"]
                if (
                    prior_result is not None
                    and prior_result["content_key"] == content_key
                    and prior_result["content_sha256"] == content_sha256
                ):
                    return dict(prior_result)
                raise RuntimeError(
                    "Book material item was already finalized differently"
                )
            if item["status"] != "running" or item["attempt_token"] != attempt_token:
                raise RuntimeError("Book material attempt is stale")
            if content_key not in (item["candidate_objects"] or []):
                raise RuntimeError(
                    "Material object was not registered for this attempt"
                )
            if item["knowledge_point_id"] is None:
                raise RuntimeError("Material item has no knowledge point")

            await cur.execute(
                """
                SELECT * FROM education_book_materials
                WHERE knowledge_point_id = %s
                FOR UPDATE
                """,
                (item["knowledge_point_id"],),
            )
            current = await cur.fetchone()
            if current is None:
                material_id = uuid4()
                generation = 1
                await cur.execute(
                    """
                    INSERT INTO education_book_materials (
                        material_id, knowledge_point_id, generation,
                        content_key, content_sha256, size_bytes, depth,
                        requirements, generation_params,
                        source_job_id, source_item_id
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        material_id,
                        item["knowledge_point_id"],
                        generation,
                        content_key,
                        content_sha256,
                        size_bytes,
                        item["depth"],
                        item["requirements"],
                        Jsonb(generation_params),
                        item["job_id"],
                        item_id,
                    ),
                )
            else:
                await cur.execute(
                    """
                    UPDATE education_book_materials
                    SET generation = generation + 1, content_key = %s,
                        content_sha256 = %s, size_bytes = %s, depth = %s,
                        requirements = %s, generation_params = %s,
                        source_job_id = %s, source_item_id = %s,
                        updated_at = NOW()
                    WHERE material_id = %s
                    RETURNING *
                    """,
                    (
                        content_key,
                        content_sha256,
                        size_bytes,
                        item["depth"],
                        item["requirements"],
                        Jsonb(generation_params),
                        item["job_id"],
                        item_id,
                        current["material_id"],
                    ),
                )
            material = await cur.fetchone()
            if material is None:
                raise RuntimeError("Material finalization returned no row")
            result_snapshot = _material_result_snapshot(dict(material))
            await cur.execute(
                """
                UPDATE education_book_job_items
                SET status = 'succeeded', result_snapshot = %s,
                    finished_at = NOW(), updated_at = NOW()
                WHERE item_id = %s
                """,
                (Jsonb(result_snapshot), item_id),
            )
            await cur.execute(
                """
                SELECT
                    count(*) FILTER (WHERE status = 'succeeded')::int AS succeeded,
                    count(*) FILTER (WHERE status = 'failed')::int AS failed,
                    count(*) FILTER (WHERE status = 'cancelled')::int AS cancelled,
                    count(*) FILTER (WHERE status = 'not_run')::int AS not_run,
                    count(*) FILTER (WHERE status IN ('queued', 'running'))::int AS active
                FROM education_book_job_items WHERE job_id = %s
                """,
                (item["job_id"],),
            )
            counts = await cur.fetchone()
            terminal_status = "running"
            finished_at_sql = "NULL"
            if counts["active"] == 0:
                finished_at_sql = "NOW()"
                terminal_status = (
                    "succeeded"
                    if counts["failed"] == counts["cancelled"] == counts["not_run"] == 0
                    else "partially_succeeded"
                    if counts["succeeded"] > 0
                    else "failed"
                )
            await cur.execute(
                """
                UPDATE education_book_jobs
                SET status = %s, succeeded_items = %s, failed_items = %s,
                    cancelled_items = %s, not_run_items = %s,
                    finished_at = CASE WHEN %s THEN NOW() ELSE NULL END,
                    updated_at = NOW()
                WHERE job_id = %s
                RETURNING job_id
                """,
                (
                    terminal_status,
                    counts["succeeded"],
                    counts["failed"],
                    counts["cancelled"],
                    counts["not_run"],
                    finished_at_sql == "NOW()",
                    item["job_id"],
                ),
            )
            await cur.fetchone()
            await append_terminal_activity(
                cur,
                job_id=item["job_id"],
                dedupe_key=f"material-committed:{item_id}",
                item_id=UUID(str(item_id)),
                kind="material",
                status="succeeded",
                message="Material committed",
            )
            if counts["active"] == 0:
                await append_terminal_activity(
                    cur,
                    job_id=item["job_id"],
                    dedupe_key=f"job-terminal:{item['job_id']}",
                    item_id=None,
                    kind="job",
                    status=terminal_status,
                    message=(
                        "Job completed"
                        if terminal_status == "succeeded"
                        else "Job completed with errors"
                    ),
                )
            await cur.execute(
                """
                UPDATE education_textbooks SET updated_at = NOW()
                WHERE textbook_id = %s
                """,
                (item["textbook_id"],),
            )
            return result_snapshot
