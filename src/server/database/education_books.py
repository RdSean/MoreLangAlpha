"""PostgreSQL persistence for more-to-skills textbooks and structures."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.server.database.pool import get_db_connection
from src.server.database.education_book_activity import append_terminal_activity

if TYPE_CHECKING:
    from src.server.services.education_book_structure import (
        MoreToSkillsIdentity,
        ParsedBookStructure,
    )


def _source_value(source: dict[str, Any], name: str) -> Any:
    value = source.get(name)
    if value is None or value == "":
        raise ValueError(f"source.{name} is required")
    return value


def _validated_follow_up_request(
    value: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if value is None:
        return None
    expected = {
        "operation",
        "depth",
        "requirements",
        "replace_existing",
        "include_supplementary",
    }
    if set(value) != expected:
        raise ValueError("Structure follow-up request fields are invalid")
    if value.get("operation") != "materials":
        raise ValueError("Structure follow-up operation must be materials")
    if value.get("depth") not in {"summary", "lesson", "deep"}:
        raise ValueError("Structure follow-up depth is invalid")
    requirements = value.get("requirements")
    if requirements is not None and not isinstance(requirements, str):
        raise ValueError("Structure follow-up requirements are invalid")
    if not isinstance(value.get("replace_existing"), bool) or not isinstance(
        value.get("include_supplementary"), bool
    ):
        raise ValueError("Structure follow-up flags are invalid")
    return dict(value)


async def get_owned_parse_job(
    *, owner_user_id: str, producer_job_id: str
) -> dict[str, Any] | None:
    """Return completed-bundle provenance through its owning document."""

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.job_id AS producer_job_id,
                       jobs.document_id, jobs.primary_artifact_id,
                       jobs.status, jobs.parser_id, jobs.parser_name,
                       jobs.parser_version, jobs.completed_at,
                       documents.original_filename, documents.media_type,
                       documents.document_format
                FROM document_parse_jobs AS jobs
                JOIN documents ON documents.document_id = jobs.document_id
                WHERE jobs.job_id = %s AND documents.owner_user_id = %s
                """,
                (producer_job_id, owner_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_existing_textbook_for_source(
    *,
    parent_user_id: str,
    household_id: str | UUID,
    source_parse_job_id: str,
    source_primary_artifact_id: str,
) -> dict[str, Any] | None:
    """Return an existing source-bound textbook without crossing household ACLs."""

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT textbooks.textbook_id, jobs.job_id, items.item_id
                FROM education_textbooks AS textbooks
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                 AND memberships.user_id = %s
                 AND memberships.role = 'parent'
                JOIN education_book_jobs AS jobs
                  ON jobs.textbook_id = textbooks.textbook_id
                 AND jobs.kind = 'structure'
                JOIN education_book_job_items AS items
                  ON items.job_id = jobs.job_id
                 AND items.kind = 'structure'
                WHERE textbooks.household_id = %s
                  AND textbooks.source_parse_job_id = %s
                  AND textbooks.source_primary_artifact_id = %s
                ORDER BY jobs.created_at, jobs.job_id
                LIMIT 1
                """,
                (
                    parent_user_id,
                    household_id,
                    source_parse_job_id,
                    source_primary_artifact_id,
                ),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def create_textbook_with_initial_job(
    *,
    textbook_id: str | UUID,
    parent_user_id: str,
    household_id: str,
    title: str,
    slug: str,
    source: dict[str, Any],
    idempotency_key: str,
    identity: MoreToSkillsIdentity,
    follow_up_request: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create one source-bound textbook and its structure job atomically."""

    textbook_id = UUID(str(textbook_id))
    job_id = uuid4()
    item_id = uuid4()
    follow_up_request = _validated_follow_up_request(follow_up_request)
    source_parse_job_id = str(_source_value(source, "parse_job_id"))
    primary_artifact_id = str(_source_value(source, "primary_artifact_id"))
    expected_prefix = (
        f"education/{UUID(str(household_id))}/textbooks/{textbook_id}/source/"
    )
    snapshot_prefix = str(_source_value(source, "snapshot_prefix"))
    if snapshot_prefix != expected_prefix:
        raise ValueError("source.snapshot_prefix does not match the textbook identity")
    for field in ("markdown_key", "blocks_key", "report_key"):
        value = source.get(field)
        if value is not None and not str(value).startswith(expected_prefix):
            raise ValueError(f"source.{field} does not belong to the textbook snapshot")
    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO education_textbooks (
                    textbook_id, household_id, title, slug,
                    source_document_id, source_parse_job_id,
                    source_primary_artifact_id, source_filename,
                    source_media_type, source_format, source_parser_id,
                    source_parser_name, source_parser_version,
                    source_parse_completed_at, source_content_sha256,
                    source_size_bytes, source_snapshot_prefix,
                    source_markdown_key, source_blocks_key, source_report_key,
                    source_asset_manifest, source_snapshot, created_by_user_id
                )
                SELECT
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                FROM education_memberships AS memberships
                WHERE memberships.household_id = %s
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                ON CONFLICT (
                    household_id, source_parse_job_id,
                    source_primary_artifact_id
                ) DO NOTHING
                RETURNING textbook_id
                """,
                (
                    textbook_id,
                    household_id,
                    title,
                    slug,
                    _source_value(source, "document_id"),
                    source_parse_job_id,
                    primary_artifact_id,
                    _source_value(source, "filename"),
                    _source_value(source, "media_type"),
                    _source_value(source, "format"),
                    _source_value(source, "parser_id"),
                    _source_value(source, "parser_name"),
                    source.get("parser_version"),
                    _source_value(source, "parse_completed_at"),
                    _source_value(source, "content_sha256"),
                    _source_value(source, "size_bytes"),
                    snapshot_prefix,
                    _source_value(source, "markdown_key"),
                    source.get("blocks_key"),
                    source.get("report_key"),
                    Jsonb(source.get("asset_manifest") or []),
                    Jsonb(source.get("snapshot") or {}),
                    parent_user_id,
                    household_id,
                    parent_user_id,
                ),
            )
            inserted = await cur.fetchone()
            if inserted is None:
                await cur.execute(
                    """
                    SELECT textbooks.textbook_id, jobs.job_id, items.item_id
                    FROM education_textbooks AS textbooks
                    JOIN education_memberships AS memberships
                      ON memberships.household_id = textbooks.household_id
                     AND memberships.user_id = %s
                     AND memberships.role = 'parent'
                    JOIN education_book_jobs AS jobs
                      ON jobs.textbook_id = textbooks.textbook_id
                     AND jobs.kind = 'structure'
                    JOIN education_book_job_items AS items
                      ON items.job_id = jobs.job_id
                     AND items.kind = 'structure'
                    WHERE textbooks.household_id = %s
                      AND textbooks.source_parse_job_id = %s
                      AND textbooks.source_primary_artifact_id = %s
                    ORDER BY jobs.created_at, jobs.job_id
                    LIMIT 1
                    """,
                    (
                        parent_user_id,
                        household_id,
                        source_parse_job_id,
                        primary_artifact_id,
                    ),
                )
                existing = await cur.fetchone()
                if existing is None:
                    raise PermissionError(
                        "Parent membership is required to create a textbook"
                    )
                return dict(existing)

            await cur.execute(
                """
                INSERT INTO education_book_jobs (
                    job_id, textbook_id, kind, status, idempotency_key,
                    more_to_skills_version, skill_sha256, schema_sha256,
                    requested_by_user_id, total_items, follow_up_request
                ) VALUES (
                    %s, %s, 'structure', 'queued', %s, %s, %s, %s, %s, 1, %s
                )
                """,
                (
                    job_id,
                    textbook_id,
                    idempotency_key,
                    identity.version,
                    identity.skill_sha256,
                    identity.schema_sha256,
                    parent_user_id,
                    Jsonb(follow_up_request) if follow_up_request is not None else None,
                ),
            )
            await cur.execute(
                """
                INSERT INTO education_book_job_items (
                    item_id, job_id, position, kind, status
                ) VALUES (%s, %s, 1, 'structure', 'queued')
                """,
                (item_id, job_id),
            )
    return {"textbook_id": textbook_id, "job_id": job_id, "item_id": item_id}


async def _lock_structure_job(cur, *, job_id: str | UUID) -> UUID:
    """Lock a structure job before its item and textbook rows."""

    await cur.execute(
        """
        SELECT job_id, cancel_requested_at FROM education_book_jobs
        WHERE job_id = %s
        FOR UPDATE
        """,
        (job_id,),
    )
    row = await cur.fetchone()
    if row is None:
        raise LookupError("Structure job was not found")
    if row["cancel_requested_at"] is not None:
        raise RuntimeError("Textbook job cancellation was requested")
    return row["job_id"]


async def commit_book_structure(
    *,
    textbook_id: str | UUID,
    job_id: str | UUID,
    item_id: str | UUID,
    attempt_token: UUID,
    parsed: ParsedBookStructure,
    validated_identity: MoreToSkillsIdentity,
) -> dict[str, Any]:
    """Atomically import one immutable structure and all KP projections."""

    structure_id = uuid4()
    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            locked_job_id = await _lock_structure_job(cur, job_id=job_id)
            await cur.execute(
                """
                SELECT items.status AS item_status, items.attempt_token,
                       jobs.status AS job_status, jobs.textbook_id,
                       jobs.more_to_skills_version, jobs.skill_sha256,
                       jobs.schema_sha256, jobs.follow_up_request,
                       jobs.requested_by_user_id,
                       textbooks.current_structure_id,
                       textbooks.source_content_sha256
                FROM education_book_job_items AS items
                JOIN education_book_jobs AS jobs ON jobs.job_id = items.job_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = jobs.textbook_id
                WHERE items.item_id = %s AND jobs.job_id = %s
                  AND textbooks.textbook_id = %s
                  AND jobs.kind = 'structure' AND items.kind = 'structure'
                FOR UPDATE OF items, textbooks
                """,
                (item_id, locked_job_id, textbook_id),
            )
            context = await cur.fetchone()
            if context is None:
                raise LookupError("Structure job item was not found")
            frozen_identity = (
                context["more_to_skills_version"],
                context["skill_sha256"],
                context["schema_sha256"],
            )
            actual_identity = (
                validated_identity.version,
                validated_identity.skill_sha256,
                validated_identity.schema_sha256,
            )
            if actual_identity != frozen_identity:
                raise ValueError(
                    "Validated structure identity does not match the frozen job"
                )
            if context["item_status"] == "succeeded":
                await cur.execute(
                    """
                    SELECT structure_id FROM education_book_structures
                    WHERE created_by_job_id = %s
                    """,
                    (job_id,),
                )
                existing = await cur.fetchone()
                if existing is None:
                    raise RuntimeError("Succeeded structure item has no structure")
                return dict(existing)
            if (
                context["item_status"] != "running"
                or context["attempt_token"] != attempt_token
            ):
                raise RuntimeError("Structure attempt is stale")

            if context["current_structure_id"] is not None:
                await cur.execute(
                    """
                    UPDATE education_book_structures
                    SET status = 'superseded'
                    WHERE structure_id = %s
                    """,
                    (context["current_structure_id"],),
                )
            await cur.execute(
                """
                INSERT INTO education_book_structures (
                    structure_id, textbook_id, schema_version,
                    more_to_skills_version, skill_sha256, schema_sha256,
                    source_content_sha256, structure_json,
                    validation_warnings, created_by_job_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    structure_id,
                    textbook_id,
                    str(parsed.document["schema_version"]),
                    context["more_to_skills_version"],
                    context["skill_sha256"],
                    context["schema_sha256"],
                    context["source_content_sha256"],
                    Jsonb(parsed.document),
                    Jsonb(list(parsed.warnings)),
                    job_id,
                ),
            )
            knowledge_point_rows = []
            for projection in parsed.knowledge_points:
                knowledge_point_rows.append(
                    (
                        uuid4(),
                        textbook_id,
                        structure_id,
                        projection["skill_kp_id"],
                        projection["position"],
                        projection["title"],
                        projection.get("unit_skill_node_id"),
                        Jsonb(list(projection.get("node_skill_ids") or ())),
                        projection["start_line"],
                        projection["end_line"],
                        Jsonb(projection["raw"]),
                    )
                )
            if knowledge_point_rows:
                await cur.executemany(
                    """
                    INSERT INTO education_book_knowledge_points (
                        knowledge_point_id, textbook_id, structure_id, skill_kp_id,
                        position, title, unit_skill_node_id, node_skill_ids,
                        start_line, end_line, knowledge_point_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    knowledge_point_rows,
                )
            await cur.execute(
                """
                UPDATE education_textbooks
                SET current_structure_id = %s, updated_at = NOW()
                WHERE textbook_id = %s
                """,
                (structure_id, textbook_id),
            )
            await cur.execute(
                """
                UPDATE education_book_job_items
                SET status = 'succeeded', finished_at = NOW(), updated_at = NOW()
                WHERE item_id = %s
                """,
                (item_id,),
            )
            await cur.execute(
                """
                UPDATE education_book_jobs
                SET status = 'succeeded', succeeded_items = 1,
                    finished_at = NOW(), updated_at = NOW()
                WHERE job_id = %s
                RETURNING job_id
                """,
                (job_id,),
            )
            await cur.fetchone()
            follow_up = context["follow_up_request"]
            if follow_up is not None:
                if (
                    not isinstance(follow_up, dict)
                    or follow_up.get("operation") != "materials"
                    or follow_up.get("depth") not in {"summary", "lesson", "deep"}
                ):
                    raise ValueError("Structure follow-up request is invalid")
                follow_up_job_id = uuid4()
                knowledge_point_ids = [row[0] for row in knowledge_point_rows]
                include_supplementary = bool(
                    follow_up.get("include_supplementary", False)
                )
                total_items = len(knowledge_point_ids) + int(include_supplementary)
                await cur.execute(
                    """
                    INSERT INTO education_book_jobs (
                        job_id, textbook_id, kind, status, idempotency_key,
                        target_knowledge_point_ids, depth, requirements,
                        replace_existing, include_supplementary,
                        more_to_skills_version, skill_sha256, schema_sha256,
                        requested_by_user_id, total_items
                    ) SELECT
                        %s, %s, 'materials', 'queued', %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s
                    WHERE %s > 0
                    """,
                    (
                        follow_up_job_id,
                        textbook_id,
                        f"follow-up:{job_id}",
                        Jsonb([str(value) for value in knowledge_point_ids]),
                        follow_up["depth"],
                        follow_up.get("requirements"),
                        bool(follow_up.get("replace_existing", False)),
                        include_supplementary,
                        context["more_to_skills_version"],
                        context["skill_sha256"],
                        context["schema_sha256"],
                        context["requested_by_user_id"],
                        total_items,
                        total_items,
                    ),
                )
                follow_up_items = [
                    (
                        uuid4(),
                        follow_up_job_id,
                        position,
                        "material",
                        knowledge_point_id,
                    )
                    for position, knowledge_point_id in enumerate(
                        knowledge_point_ids, start=1
                    )
                ]
                if include_supplementary:
                    follow_up_items.append(
                        (
                            uuid4(),
                            follow_up_job_id,
                            len(follow_up_items) + 1,
                            "supplementary",
                            None,
                        )
                    )
                if follow_up_items:
                    await cur.executemany(
                        """
                        INSERT INTO education_book_job_items (
                            item_id, job_id, position, kind,
                            knowledge_point_id, status
                        ) VALUES (%s, %s, %s, %s, %s, 'queued')
                        """,
                        follow_up_items,
                    )
            await append_terminal_activity(
                cur,
                job_id=UUID(str(job_id)),
                dedupe_key="structure-committed",
                item_id=UUID(str(item_id)),
                kind="structure",
                status="succeeded",
                message="Structure imported",
            )
            await append_terminal_activity(
                cur,
                job_id=UUID(str(job_id)),
                dedupe_key=f"job-terminal:{job_id}",
                item_id=None,
                kind="job",
                status="succeeded",
                message="Job completed",
            )
    return {"structure_id": structure_id}


async def get_current_structure(*, textbook_id: str | UUID) -> dict[str, Any] | None:
    """Return immutable semantics and query projections for the current structure."""

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT structures.*
                FROM education_textbooks AS textbooks
                JOIN education_book_structures AS structures
                  ON structures.structure_id = textbooks.current_structure_id
                WHERE textbooks.textbook_id = %s
                """,
                (textbook_id,),
            )
            structure = await cur.fetchone()
            if structure is None:
                return None
            await cur.execute(
                """
                SELECT points.*, materials.content_key,
                       materials.content_sha256, materials.updated_at AS material_updated_at
                FROM education_book_knowledge_points AS points
                LEFT JOIN education_book_materials AS materials
                  ON materials.knowledge_point_id = points.knowledge_point_id
                WHERE points.structure_id = %s
                ORDER BY points.position
                """,
                (structure["structure_id"],),
            )
            points = [dict(row) for row in await cur.fetchall()]
    result = dict(structure)
    result["knowledge_points"] = points
    return result


async def list_book_source_candidates_for_parent(
    *, parent_user_id: str
) -> list[dict[str, Any]]:
    """List completed Markdown parse bundles owned by a household parent."""

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT documents.document_id,
                       jobs.job_id AS parse_job_id,
                       jobs.primary_artifact_id,
                       documents.original_filename AS filename,
                       documents.media_type,
                       jobs.parser_id,
                       jobs.parser_name,
                       jobs.completed_at,
                       documents.source_sha256 AS content_sha256,
                       documents.source_size_bytes AS size_bytes,
                       COALESCE(images.image_count, 0)::int AS image_count
                FROM document_parse_jobs AS jobs
                JOIN documents ON documents.document_id = jobs.document_id
                JOIN document_artifacts AS primary_artifacts
                  ON primary_artifacts.artifact_id = jobs.primary_artifact_id
                 AND primary_artifacts.producer_job_id = jobs.job_id
                 AND primary_artifacts.artifact_kind = 'primary_document'
                 AND LOWER(SPLIT_PART(primary_artifacts.media_type, ';', 1))
                     = 'text/markdown'
                 AND LOWER(primary_artifacts.format) IN ('gfm', 'markdown')
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) AS image_count
                    FROM document_artifacts AS artifacts
                    WHERE artifacts.producer_job_id = jobs.job_id
                      AND artifacts.artifact_kind = 'embedded_image'
                ) AS images ON TRUE
                WHERE jobs.status = 'completed'
                  AND jobs.primary_artifact_id IS NOT NULL
                  AND documents.owner_user_id = %s
                  AND EXISTS (
                      SELECT 1 FROM education_memberships AS memberships
                      WHERE memberships.user_id = %s
                        AND memberships.role = 'parent'
                  )
                ORDER BY jobs.completed_at DESC NULLS LAST, jobs.job_id DESC
                """,
                (parent_user_id, parent_user_id),
            )
            return [dict(row) for row in await cur.fetchall()]


_MANAGED_JOB_SUMMARY_SQL = """
    jsonb_build_object(
        'job_id', jobs.job_id,
        'kind', jobs.kind,
        'status', jobs.status,
        'total_items', jobs.total_items,
        'succeeded_items', jobs.succeeded_items,
        'failed_items', jobs.failed_items,
        'cancelled_items', jobs.cancelled_items,
        'not_run_items', jobs.not_run_items,
        'high_water_seq', jobs.high_water_seq,
        'activity_status', jobs.activity_status,
        'created_at', jobs.created_at,
        'started_at', jobs.started_at,
        'finished_at', jobs.finished_at,
        'safe_error', jobs.safe_error
    )
"""


async def _managed_textbook_rows(
    *, parent_user_id: str, textbook_id: UUID | None = None
) -> list[dict[str, Any]]:
    textbook_filter = "AND textbooks.textbook_id = %s" if textbook_id else ""
    query = f"""
        SELECT textbooks.textbook_id, textbooks.title,
               CASE
                   WHEN textbooks.current_structure_id IS NOT NULL THEN 'ready'
                   WHEN recent_structure.status IN ('queued', 'running')
                       THEN recent_structure.status
                   WHEN recent_structure.status IS NULL THEN 'queued'
                   ELSE 'failed'
               END AS structure_status,
               COALESCE(material_counts.total, 0)::int AS material_total,
               COALESCE(material_counts.ready, 0)::int AS material_ready,
               current_job.summary AS current_job,
               recent_job.summary AS recent_job,
               textbooks.updated_at,
               textbooks.current_structure_id,
               textbooks.source_document_id AS document_id,
               textbooks.source_parse_job_id AS parse_job_id,
               textbooks.source_primary_artifact_id AS primary_artifact_id,
               textbooks.source_filename AS filename,
               textbooks.source_media_type AS media_type,
               textbooks.source_parser_id AS parser_id,
               textbooks.source_parser_name AS parser_name,
               textbooks.source_parse_completed_at AS completed_at,
               textbooks.source_content_sha256 AS content_sha256,
               textbooks.source_size_bytes AS size_bytes,
               textbooks.created_at AS frozen_at,
               COALESCE(source_counts.image_count, 0)::int AS image_count,
               COALESCE(assignments.assigned_student_count, 0)::int
                   AS assigned_student_count
        FROM education_textbooks AS textbooks
        JOIN education_memberships AS memberships
          ON memberships.household_id = textbooks.household_id
         AND memberships.user_id = %s
         AND memberships.role = 'parent'
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS total,
                   COUNT(materials.material_id) AS ready
            FROM education_book_knowledge_points AS points
            LEFT JOIN education_book_materials AS materials
              ON materials.knowledge_point_id = points.knowledge_point_id
            WHERE points.structure_id = textbooks.current_structure_id
        ) AS material_counts ON TRUE
        LEFT JOIN LATERAL (
            SELECT {_MANAGED_JOB_SUMMARY_SQL} AS summary
            FROM education_book_jobs AS jobs
            WHERE jobs.textbook_id = textbooks.textbook_id
              AND jobs.status IN ('queued', 'running')
            ORDER BY jobs.created_at DESC, jobs.job_id DESC
            LIMIT 1
        ) AS current_job ON TRUE
        LEFT JOIN LATERAL (
            SELECT {_MANAGED_JOB_SUMMARY_SQL} AS summary
            FROM education_book_jobs AS jobs
            WHERE jobs.textbook_id = textbooks.textbook_id
            ORDER BY jobs.created_at DESC, jobs.job_id DESC
            LIMIT 1
        ) AS recent_job ON TRUE
        LEFT JOIN LATERAL (
            SELECT jobs.status
            FROM education_book_jobs AS jobs
            WHERE jobs.textbook_id = textbooks.textbook_id
              AND jobs.kind = 'structure'
            ORDER BY jobs.created_at DESC, jobs.job_id DESC
            LIMIT 1
        ) AS recent_structure ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS image_count
            FROM jsonb_array_elements(textbooks.source_asset_manifest) AS asset
            WHERE asset->>'artifact_kind' = 'embedded_image'
        ) AS source_counts ON TRUE
        LEFT JOIN LATERAL (
            SELECT COUNT(*) AS assigned_student_count
            FROM education_textbook_assignments AS assignment
            WHERE assignment.textbook_id = textbooks.textbook_id
        ) AS assignments ON TRUE
        WHERE TRUE {textbook_filter}
        ORDER BY textbooks.updated_at DESC, textbooks.textbook_id
    """
    params: tuple[Any, ...] = (
        (parent_user_id, textbook_id) if textbook_id is not None else (parent_user_id,)
    )
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(query, params)
            return [dict(row) for row in await cur.fetchall()]


async def list_managed_textbooks_for_parent(
    *, parent_user_id: str
) -> list[dict[str, Any]]:
    return await _managed_textbook_rows(parent_user_id=parent_user_id)


async def get_managed_textbook_for_parent(
    *, parent_user_id: str, textbook_id: str | UUID
) -> dict[str, Any] | None:
    rows = await _managed_textbook_rows(
        parent_user_id=parent_user_id,
        textbook_id=UUID(str(textbook_id)),
    )
    return rows[0] if rows else None


async def get_managed_structure_for_user(
    *, user_id: str, textbook_id: str | UUID
) -> dict[str, Any] | None:
    """Read the current structure for a household parent or assigned student."""

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT structures.*
                FROM education_textbooks AS textbooks
                JOIN education_book_structures AS structures
                  ON structures.structure_id = textbooks.current_structure_id
                WHERE textbooks.textbook_id = %s
                  AND (
                      EXISTS (
                          SELECT 1 FROM education_memberships AS memberships
                          WHERE memberships.household_id = textbooks.household_id
                            AND memberships.user_id = %s
                            AND memberships.role = 'parent'
                      )
                      OR EXISTS (
                          SELECT 1 FROM education_textbook_assignments AS assignments
                          WHERE assignments.textbook_id = textbooks.textbook_id
                            AND assignments.student_user_id = %s
                      )
                  )
                """,
                (textbook_id, user_id, user_id),
            )
            structure = await cur.fetchone()
            if structure is None:
                return None
            await cur.execute(
                """
                SELECT points.knowledge_point_id, points.skill_kp_id,
                       points.position, points.title, points.unit_skill_node_id,
                       points.node_skill_ids, points.start_line, points.end_line,
                       materials.content_key
                FROM education_book_knowledge_points AS points
                LEFT JOIN education_book_materials AS materials
                  ON materials.knowledge_point_id = points.knowledge_point_id
                WHERE points.structure_id = %s
                ORDER BY points.position
                """,
                (structure["structure_id"],),
            )
            points = [dict(row) for row in await cur.fetchall()]
    result = dict(structure)
    result["knowledge_points"] = points
    return result


async def get_managed_structure_for_parent(
    *, parent_user_id: str, textbook_id: str | UUID
) -> dict[str, Any] | None:
    return await get_managed_structure_for_user(
        user_id=parent_user_id,
        textbook_id=textbook_id,
    )


async def get_managed_source_for_user(
    *, user_id: str, textbook_id: str | UUID
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT textbooks.textbook_id, textbooks.source_snapshot_prefix,
                       textbooks.source_markdown_key,
                       textbooks.source_content_sha256,
                       textbooks.source_size_bytes,
                       textbooks.source_asset_manifest
                FROM education_textbooks AS textbooks
                WHERE textbooks.textbook_id = %s
                  AND (
                      EXISTS (
                          SELECT 1 FROM education_memberships AS memberships
                          WHERE memberships.household_id = textbooks.household_id
                            AND memberships.user_id = %s
                            AND memberships.role = 'parent'
                      )
                      OR EXISTS (
                          SELECT 1 FROM education_textbook_assignments AS assignments
                          WHERE assignments.textbook_id = textbooks.textbook_id
                            AND assignments.student_user_id = %s
                      )
                  )
                """,
                (textbook_id, user_id, user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_managed_source_for_parent(
    *, parent_user_id: str, textbook_id: str | UUID
) -> dict[str, Any] | None:
    return await get_managed_source_for_user(
        user_id=parent_user_id,
        textbook_id=textbook_id,
    )


async def get_managed_material_for_user(
    *,
    user_id: str,
    textbook_id: str | UUID,
    knowledge_point_id: str | UUID,
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT textbooks.textbook_id, textbooks.household_id,
                       textbooks.source_asset_manifest,
                       points.knowledge_point_id, points.skill_kp_id,
                       materials.content_key, materials.content_sha256,
                       materials.size_bytes, materials.depth,
                       materials.requirements, materials.updated_at
                FROM education_textbooks AS textbooks
                JOIN education_book_knowledge_points AS points
                  ON points.structure_id = textbooks.current_structure_id
                 AND points.knowledge_point_id = %s
                LEFT JOIN education_book_materials AS materials
                  ON materials.knowledge_point_id = points.knowledge_point_id
                WHERE textbooks.textbook_id = %s
                  AND (
                      EXISTS (
                          SELECT 1 FROM education_memberships AS memberships
                          WHERE memberships.household_id = textbooks.household_id
                            AND memberships.user_id = %s
                            AND memberships.role = 'parent'
                      )
                      OR EXISTS (
                          SELECT 1 FROM education_textbook_assignments AS assignments
                          WHERE assignments.textbook_id = textbooks.textbook_id
                            AND assignments.student_user_id = %s
                      )
                  )
                """,
                (knowledge_point_id, textbook_id, user_id, user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_managed_material_for_parent(
    *,
    parent_user_id: str,
    textbook_id: str | UUID,
    knowledge_point_id: str | UUID,
) -> dict[str, Any] | None:
    return await get_managed_material_for_user(
        user_id=parent_user_id,
        textbook_id=textbook_id,
        knowledge_point_id=knowledge_point_id,
    )


async def get_managed_asset_for_user(
    *, user_id: str, textbook_id: str | UUID, asset_id: str
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT textbooks.textbook_id, textbooks.source_snapshot_prefix,
                       asset AS manifest_entry
                FROM education_textbooks AS textbooks
                CROSS JOIN LATERAL
                    jsonb_array_elements(textbooks.source_asset_manifest) AS asset
                WHERE textbooks.textbook_id = %s
                  AND asset->>'artifact_id' = %s
                  AND (
                      EXISTS (
                          SELECT 1 FROM education_memberships AS memberships
                          WHERE memberships.household_id = textbooks.household_id
                            AND memberships.user_id = %s
                            AND memberships.role = 'parent'
                      )
                      OR EXISTS (
                          SELECT 1 FROM education_textbook_assignments AS assignments
                          WHERE assignments.textbook_id = textbooks.textbook_id
                            AND assignments.student_user_id = %s
                      )
                  )
                LIMIT 1
                """,
                (textbook_id, asset_id, user_id, user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_managed_asset_for_parent(
    *, parent_user_id: str, textbook_id: str | UUID, asset_id: str
) -> dict[str, Any] | None:
    return await get_managed_asset_for_user(
        user_id=parent_user_id,
        textbook_id=textbook_id,
        asset_id=asset_id,
    )
