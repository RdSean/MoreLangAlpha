"""PostgreSQL job, attempt and material fencing for managed textbooks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.server.database.pool import get_db_connection

if TYPE_CHECKING:
    from src.server.services.education_book_structure import MoreToSkillsIdentity


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
                    len(unique_ids),
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
                (uuid4(), job_id, position, knowledge_point_id)
                for position, knowledge_point_id in enumerate(unique_ids, start=1)
            ]
            await cur.executemany(
                """
                INSERT INTO education_book_job_items (
                    item_id, job_id, position, kind,
                    knowledge_point_id, status
                ) VALUES (%s, %s, %s, 'material', %s, 'queued')
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
            await cur.execute(
                """
                UPDATE education_book_job_items
                SET status = 'running', attempt = attempt + 1,
                    attempt_token = %s, started_at = NOW(),
                    finished_at = NULL, safe_error = NULL, updated_at = NOW()
                WHERE item_id = %s AND status = 'queued'
                RETURNING *
                """,
                (attempt_token, item_id),
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
            await cur.execute(
                """
                SELECT items.*, jobs.textbook_id, jobs.depth, jobs.requirements
                FROM education_book_job_items AS items
                JOIN education_book_jobs AS jobs ON jobs.job_id = items.job_id
                WHERE items.item_id = %s
                FOR UPDATE OF items, jobs
                """,
                (item_id,),
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
                SET high_water_seq = high_water_seq + 1,
                    status = %s, succeeded_items = %s, failed_items = %s,
                    cancelled_items = %s, not_run_items = %s,
                    finished_at = CASE WHEN %s THEN NOW() ELSE NULL END,
                    updated_at = NOW()
                WHERE job_id = %s
                RETURNING high_water_seq
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
            seq = (await cur.fetchone())["high_water_seq"]
            await cur.execute(
                """
                INSERT INTO education_book_activity_events (
                    job_id, seq, dedupe_key, item_id, kind, status, message
                ) VALUES (%s, %s, %s, %s, 'material', 'succeeded',
                          'Material committed')
                """,
                (item["job_id"], seq, f"material-committed:{item_id}", item_id),
            )
            await cur.execute(
                """
                UPDATE education_textbooks SET updated_at = NOW()
                WHERE textbook_id = %s
                """,
                (item["textbook_id"],),
            )
            return result_snapshot
