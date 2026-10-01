"""PostgreSQL persistence for more-to-skills textbooks and structures."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.server.database.pool import get_db_connection

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
) -> dict[str, Any]:
    """Create one source-bound textbook and its structure job atomically."""

    textbook_id = UUID(str(textbook_id))
    job_id = uuid4()
    item_id = uuid4()
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
                    requested_by_user_id, total_items
                ) VALUES (
                    %s, %s, 'structure', 'queued', %s, %s, %s, %s, %s, 1
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
            await cur.execute(
                """
                SELECT items.status AS item_status, items.attempt_token,
                       jobs.status AS job_status, jobs.textbook_id,
                       jobs.more_to_skills_version, jobs.skill_sha256,
                       jobs.schema_sha256,
                       textbooks.current_structure_id,
                       textbooks.source_content_sha256
                FROM education_book_job_items AS items
                JOIN education_book_jobs AS jobs ON jobs.job_id = items.job_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = jobs.textbook_id
                WHERE items.item_id = %s AND jobs.job_id = %s
                  AND textbooks.textbook_id = %s
                  AND jobs.kind = 'structure' AND items.kind = 'structure'
                FOR UPDATE OF items, jobs, textbooks
                """,
                (item_id, job_id, textbook_id),
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
                    high_water_seq = high_water_seq + 1,
                    finished_at = NOW(), updated_at = NOW()
                WHERE job_id = %s
                RETURNING high_water_seq
                """,
                (job_id,),
            )
            event_seq = (await cur.fetchone())["high_water_seq"]
            await cur.execute(
                """
                INSERT INTO education_book_activity_events (
                    job_id, seq, dedupe_key, item_id, kind, status, message
                ) VALUES (%s, %s, 'structure-committed', %s,
                          'structure', 'succeeded', 'Structure imported')
                ON CONFLICT (job_id, dedupe_key) DO NOTHING
                """,
                (job_id, event_seq, item_id),
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
