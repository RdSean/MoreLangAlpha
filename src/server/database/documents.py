"""Ownership-safe PostgreSQL persistence for the document library."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.server.database.pool import get_db_connection


@dataclass(frozen=True, slots=True)
class DocumentListFilter:
    query: str | None = None
    dataset_id: str | None = None
    tag_ids: tuple[str, ...] = ()
    media_type: str | None = None
    classification: str | None = None
    parse_status: str | None = None
    limit: int = 50
    offset: int = 0


async def create_dataset(
    *,
    owner_user_id: str,
    dataset_id: str,
    name: str,
    description: str | None = None,
) -> dict[str, Any]:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO document_datasets (
                    dataset_id, owner_user_id, name, description
                ) VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (dataset_id, owner_user_id, name, description),
            )
            row = await cur.fetchone()
    if row is None:
        raise RuntimeError("Dataset insert did not return a row")
    return dict(row)


async def get_dataset(
    *,
    owner_user_id: str,
    dataset_id: str,
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT document_datasets.*,
                       COUNT(document_dataset_items.document_id) AS document_count
                FROM document_datasets
                LEFT JOIN document_dataset_items
                  ON document_dataset_items.dataset_id = document_datasets.dataset_id
                 AND document_dataset_items.owner_user_id =
                     document_datasets.owner_user_id
                WHERE document_datasets.dataset_id = %s
                  AND document_datasets.owner_user_id = %s
                GROUP BY document_datasets.dataset_id
                """,
                (dataset_id, owner_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def list_datasets(
    *,
    owner_user_id: str,
    query: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    clauses = ["document_datasets.owner_user_id = %s"]
    params: list[object] = [owner_user_id]
    if query:
        clauses.append("document_datasets.name ILIKE %s")
        params.append(f"%{query}%")
    where_sql = " AND ".join(clauses)

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM document_datasets
                WHERE {where_sql}
                """,
                tuple(params),
            )
            count_row = await cur.fetchone()
            total = int(count_row["total"]) if count_row else 0
            await cur.execute(
                f"""
                SELECT document_datasets.*,
                       COUNT(document_dataset_items.document_id) AS document_count
                FROM document_datasets
                LEFT JOIN document_dataset_items
                  ON document_dataset_items.dataset_id = document_datasets.dataset_id
                 AND document_dataset_items.owner_user_id =
                     document_datasets.owner_user_id
                WHERE {where_sql}
                GROUP BY document_datasets.dataset_id
                ORDER BY document_datasets.updated_at DESC,
                         document_datasets.dataset_id
                LIMIT %s OFFSET %s
                """,
                (*params, limit, offset),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows], total


async def count_datasets(
    *,
    owner_user_id: str,
    query: str | None = None,
) -> int:
    clauses = ["document_datasets.owner_user_id = %s"]
    params: list[object] = [owner_user_id]
    if query:
        clauses.append("document_datasets.name ILIKE %s")
        params.append(f"%{query}%")
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"""
                SELECT COUNT(*) AS total
                FROM document_datasets
                WHERE {' AND '.join(clauses)}
                """,
                tuple(params),
            )
            row = await cur.fetchone()
    return int(row["total"]) if row else 0


async def update_dataset(
    *,
    owner_user_id: str,
    dataset_id: str,
    name: str,
    description: str | None,
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE document_datasets
                SET name = %s, description = %s
                WHERE dataset_id = %s AND owner_user_id = %s
                RETURNING *
                """,
                (name, description, dataset_id, owner_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def delete_dataset(
    *,
    owner_user_id: str,
    dataset_id: str,
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                DELETE FROM document_datasets
                WHERE dataset_id = %s AND owner_user_id = %s
                RETURNING *
                """,
                (dataset_id, owner_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def create_document(
    *,
    owner_user_id: str,
    document_id: str,
    original_filename: str,
    media_type: str,
    document_format: str,
    source_storage_key: str,
    source_size_bytes: int,
    source_sha256: str,
    dataset_ids: tuple[str, ...] = (),
    tag_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Publish source metadata and owned collection relationships atomically."""
    unique_dataset_ids = tuple(dict.fromkeys(dataset_ids))
    unique_tag_ids = tuple(dict.fromkeys(tag_ids))

    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    INSERT INTO documents (
                        document_id, owner_user_id, original_filename, media_type,
                        document_format, source_storage_key, source_size_bytes,
                        source_sha256
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING *
                    """,
                    (
                        document_id,
                        owner_user_id,
                        original_filename,
                        media_type,
                        document_format,
                        source_storage_key,
                        source_size_bytes,
                        source_sha256,
                    ),
                )
                row = await cur.fetchone()
                if row is None:
                    raise RuntimeError("document insert did not return a row")

                await _insert_dataset_memberships(
                    cur,
                    owner_user_id=owner_user_id,
                    document_id=document_id,
                    dataset_ids=unique_dataset_ids,
                )
                await _insert_tag_assignments(
                    cur,
                    owner_user_id=owner_user_id,
                    document_id=document_id,
                    tag_ids=unique_tag_ids,
                )
                return dict(row)


async def get_document(
    *,
    owner_user_id: str,
    document_id: str,
) -> dict[str, Any] | None:
    """Return one Document only to its owner."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"""
                SELECT {_DOCUMENT_SELECT_COLUMNS}
                FROM documents
                WHERE documents.document_id = %s
                  AND documents.owner_user_id = %s
                """,
                (document_id, owner_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def update_document(
    *,
    owner_user_id: str,
    document_id: str,
    original_filename: str,
) -> dict[str, Any] | None:
    """Update mutable display metadata without changing the source object."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE documents
                SET original_filename = %s
                WHERE document_id = %s AND owner_user_id = %s
                RETURNING *
                """,
                (original_filename, document_id, owner_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def delete_document(
    *,
    owner_user_id: str,
    document_id: str,
) -> dict[str, Any] | None:
    """Delete owned metadata after the service has removed exact object keys."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                DELETE FROM documents
                WHERE document_id = %s AND owner_user_id = %s
                RETURNING *
                """,
                (document_id, owner_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def list_documents(
    *,
    owner_user_id: str,
    filters: DocumentListFilter,
) -> tuple[list[dict[str, Any]], int]:
    """Return an owner-scoped page without multiplying rows through joins."""
    where_sql, filter_params = _build_document_filter(
        owner_user_id=owner_user_id,
        filters=filters,
    )
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"SELECT COUNT(*) AS total FROM documents WHERE {where_sql}",
                tuple(filter_params),
            )
            count_row = await cur.fetchone()
            total = int(count_row["total"]) if count_row else 0

            await cur.execute(
                f"""
                SELECT {_DOCUMENT_SELECT_COLUMNS}
                FROM documents
                WHERE {where_sql}
                ORDER BY documents.updated_at DESC, documents.document_id
                LIMIT %s OFFSET %s
                """,
                (*filter_params, filters.limit, filters.offset),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows], total


async def replace_dataset_memberships(
    *,
    owner_user_id: str,
    document_id: str,
    dataset_ids: tuple[str, ...],
) -> None:
    """Replace an owned Document's flat Dataset membership atomically."""
    unique_ids = tuple(dict.fromkeys(dataset_ids))
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await _lock_owned_document(
                    cur,
                    owner_user_id=owner_user_id,
                    document_id=document_id,
                )
                await cur.execute(
                    """
                    DELETE FROM document_dataset_items
                    WHERE document_id = %s AND owner_user_id = %s
                    """,
                    (document_id, owner_user_id),
                )
                await _insert_dataset_memberships(
                    cur,
                    owner_user_id=owner_user_id,
                    document_id=document_id,
                    dataset_ids=unique_ids,
                )


async def replace_tag_assignments(
    *,
    owner_user_id: str,
    document_id: str,
    tag_ids: tuple[str, ...],
) -> None:
    """Replace an owned Document's tag assignments atomically."""
    unique_ids = tuple(dict.fromkeys(tag_ids))
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await _lock_owned_document(
                    cur,
                    owner_user_id=owner_user_id,
                    document_id=document_id,
                )
                await cur.execute(
                    """
                    DELETE FROM document_tag_assignments
                    WHERE document_id = %s AND owner_user_id = %s
                    """,
                    (document_id, owner_user_id),
                )
                await _insert_tag_assignments(
                    cur,
                    owner_user_id=owner_user_id,
                    document_id=document_id,
                    tag_ids=unique_ids,
                )


async def create_tag(
    *,
    owner_user_id: str,
    tag_id: str,
    name: str,
    normalized_name: str,
) -> dict[str, Any]:
    """Create an owner-local tag and let the unique constraint reject duplicates."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO document_tags (
                    tag_id, owner_user_id, name, normalized_name
                ) VALUES (%s, %s, %s, %s)
                RETURNING *
                """,
                (tag_id, owner_user_id, name, normalized_name),
            )
            row = await cur.fetchone()
    if row is None:
        raise RuntimeError("tag insert did not return a row")
    return dict(row)


async def get_tag(
    *,
    owner_user_id: str,
    tag_id: str,
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT * FROM document_tags
                WHERE tag_id = %s AND owner_user_id = %s
                """,
                (tag_id, owner_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def update_tag(
    *,
    owner_user_id: str,
    tag_id: str,
    name: str,
    normalized_name: str,
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE document_tags
                SET name = %s, normalized_name = %s
                WHERE tag_id = %s AND owner_user_id = %s
                RETURNING *
                """,
                (name, normalized_name, tag_id, owner_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def list_tags(*, owner_user_id: str) -> list[dict[str, Any]]:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT document_tags.*,
                       COUNT(document_tag_assignments.document_id) AS document_count
                FROM document_tags
                LEFT JOIN document_tag_assignments
                  ON document_tag_assignments.tag_id = document_tags.tag_id
                 AND document_tag_assignments.owner_user_id =
                     document_tags.owner_user_id
                WHERE document_tags.owner_user_id = %s
                GROUP BY document_tags.tag_id
                ORDER BY document_tags.name, document_tags.tag_id
                """,
                (owner_user_id,),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def delete_tag(
    *,
    owner_user_id: str,
    tag_id: str,
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                DELETE FROM document_tags
                WHERE tag_id = %s AND owner_user_id = %s
                RETURNING *
                """,
                (tag_id, owner_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def create_inspection(
    *,
    owner_user_id: str,
    inspection_id: str,
    document_id: str,
    inspector_id: str,
    inspector_name: str,
    inspector_version: str | None,
    status: str,
    detected_format: str | None,
    classification: str | None,
    summary: dict[str, object],
    details: dict[str, object],
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any] | None:
    """Create one inspection only when its Document belongs to the caller."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO document_inspections (
                    inspection_id, document_id, inspector_id, inspector_name,
                    inspector_version, status, detected_format, classification,
                    summary, details, error_code, error_message, completed_at
                )
                SELECT %s, documents.document_id, %s, %s, %s, %s, %s, %s,
                       %s, %s, %s, %s,
                       CASE WHEN %s IN ('completed', 'failed') THEN NOW() END
                FROM documents
                WHERE documents.document_id = %s
                  AND documents.owner_user_id = %s
                RETURNING *
                """,
                (
                    inspection_id,
                    inspector_id,
                    inspector_name,
                    inspector_version,
                    status,
                    detected_format,
                    classification,
                    Jsonb(summary),
                    Jsonb(details),
                    error_code,
                    error_message,
                    status,
                    document_id,
                    owner_user_id,
                ),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_inspection(
    *,
    owner_user_id: str,
    inspection_id: str,
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT document_inspections.*
                FROM document_inspections
                JOIN documents
                  ON documents.document_id = document_inspections.document_id
                WHERE document_inspections.inspection_id = %s
                  AND documents.owner_user_id = %s
                """,
                (inspection_id, owner_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def list_inspections(
    *,
    owner_user_id: str,
    document_id: str,
) -> list[dict[str, Any]]:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT document_inspections.*
                FROM document_inspections
                JOIN documents
                  ON documents.document_id = document_inspections.document_id
                WHERE document_inspections.document_id = %s
                  AND documents.owner_user_id = %s
                ORDER BY document_inspections.created_at DESC,
                         document_inspections.inspection_id DESC
                """,
                (document_id, owner_user_id),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_artifact(
    *,
    owner_user_id: str,
    artifact_id: str,
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT document_artifacts.*
                FROM document_artifacts
                JOIN documents
                  ON documents.document_id = document_artifacts.document_id
                WHERE document_artifacts.artifact_id = %s
                  AND documents.owner_user_id = %s
                """,
                (artifact_id, owner_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def list_artifacts(
    *,
    owner_user_id: str,
    document_id: str,
    producer_job_id: str | None = None,
) -> list[dict[str, Any]]:
    clauses = [
        "document_artifacts.document_id = %s",
        "documents.owner_user_id = %s",
    ]
    params: list[object] = [document_id, owner_user_id]
    if producer_job_id:
        clauses.append("document_artifacts.producer_job_id = %s")
        params.append(producer_job_id)
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"""
                SELECT document_artifacts.*
                FROM document_artifacts
                JOIN documents
                  ON documents.document_id = document_artifacts.document_id
                WHERE {' AND '.join(clauses)}
                ORDER BY document_artifacts.created_at,
                         document_artifacts.artifact_id
                """,
                tuple(params),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def list_parse_jobs(
    *,
    owner_user_id: str,
    document_id: str,
    limit: int = 50,
    offset: int = 0,
) -> list[dict[str, Any]]:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT document_parse_jobs.*
                FROM document_parse_jobs
                JOIN documents
                  ON documents.document_id = document_parse_jobs.document_id
                WHERE document_parse_jobs.document_id = %s
                  AND documents.owner_user_id = %s
                ORDER BY document_parse_jobs.created_at DESC,
                         document_parse_jobs.job_id DESC
                LIMIT %s OFFSET %s
                """,
                (document_id, owner_user_id, limit, offset),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def _insert_dataset_memberships(
    cur: Any,
    *,
    owner_user_id: str,
    document_id: str,
    dataset_ids: tuple[str, ...],
) -> None:
    if not dataset_ids:
        return
    await cur.execute(
        """
        INSERT INTO document_dataset_items (
            dataset_id, document_id, owner_user_id
        )
        SELECT document_datasets.dataset_id, documents.document_id, %s
        FROM document_datasets
        JOIN documents
          ON documents.document_id = %s
         AND documents.owner_user_id = %s
        WHERE document_datasets.owner_user_id = %s
          AND document_datasets.dataset_id = ANY(%s)
        """,
        (
            owner_user_id,
            document_id,
            owner_user_id,
            owner_user_id,
            list(dataset_ids),
        ),
    )
    if cur.rowcount != len(dataset_ids):
        raise ValueError("Dataset selection contains an unavailable Dataset")


async def _lock_owned_document(
    cur: Any,
    *,
    owner_user_id: str,
    document_id: str,
) -> None:
    await cur.execute(
        """
        SELECT document_id
        FROM documents
        WHERE document_id = %s AND owner_user_id = %s
        FOR UPDATE
        """,
        (document_id, owner_user_id),
    )
    if await cur.fetchone() is None:
        raise ValueError("Document is unavailable")


async def _insert_tag_assignments(
    cur: Any,
    *,
    owner_user_id: str,
    document_id: str,
    tag_ids: tuple[str, ...],
) -> None:
    if not tag_ids:
        return
    await cur.execute(
        """
        INSERT INTO document_tag_assignments (
            tag_id, document_id, owner_user_id
        )
        SELECT document_tags.tag_id, documents.document_id, %s
        FROM document_tags
        JOIN documents
          ON documents.document_id = %s
         AND documents.owner_user_id = %s
        WHERE document_tags.owner_user_id = %s
          AND document_tags.tag_id = ANY(%s)
        """,
        (
            owner_user_id,
            document_id,
            owner_user_id,
            owner_user_id,
            list(tag_ids),
        ),
    )
    if cur.rowcount != len(tag_ids):
        raise ValueError("Tag selection contains an unavailable tag")


def _build_document_filter(
    *,
    owner_user_id: str,
    filters: DocumentListFilter,
) -> tuple[str, list[object]]:
    clauses = ["documents.owner_user_id = %s"]
    params: list[object] = [owner_user_id]

    if filters.query:
        clauses.append("documents.original_filename ILIKE %s")
        params.append(f"%{filters.query}%")
    if filters.dataset_id:
        clauses.append(
            """
            EXISTS (
                SELECT 1
                FROM document_dataset_items
                WHERE document_dataset_items.document_id = documents.document_id
                  AND document_dataset_items.owner_user_id = %s
                  AND document_dataset_items.dataset_id = %s
            )
            """
        )
        params.extend((owner_user_id, filters.dataset_id))
    if filters.tag_ids:
        unique_tag_ids = tuple(dict.fromkeys(filters.tag_ids))
        clauses.append(
            """
            (
                SELECT COUNT(DISTINCT document_tag_assignments.tag_id)
                FROM document_tag_assignments
                WHERE document_tag_assignments.document_id = documents.document_id
                  AND document_tag_assignments.owner_user_id = %s
                  AND document_tag_assignments.tag_id = ANY(%s)
            ) = %s
            """
        )
        params.extend((owner_user_id, list(unique_tag_ids), len(unique_tag_ids)))
    if filters.media_type:
        clauses.append("documents.media_type = %s")
        params.append(filters.media_type)
    if filters.classification:
        clauses.append(
            """
            (
                SELECT document_inspections.classification
                FROM document_inspections
                WHERE document_inspections.document_id = documents.document_id
                  AND document_inspections.status = 'completed'
                ORDER BY document_inspections.created_at DESC,
                         document_inspections.inspection_id DESC
                LIMIT 1
            ) = %s
            """
        )
        params.append(filters.classification)
    if filters.parse_status:
        clauses.append(
            """
            (
                SELECT document_parse_jobs.status
                FROM document_parse_jobs
                WHERE document_parse_jobs.document_id = documents.document_id
                ORDER BY document_parse_jobs.created_at DESC,
                         document_parse_jobs.job_id DESC
                LIMIT 1
            ) = %s
            """
        )
        params.append(filters.parse_status)
    return " AND ".join(clauses), params


_DOCUMENT_SELECT_COLUMNS = """
    documents.document_id,
    documents.owner_user_id,
    documents.original_filename,
    documents.media_type,
    documents.document_format,
    documents.source_storage_key,
    documents.source_size_bytes,
    documents.source_sha256,
    documents.created_at,
    documents.updated_at,
    COALESCE((
        SELECT jsonb_agg(
            jsonb_build_object(
                'dataset_id', document_datasets.dataset_id,
                'name', document_datasets.name
            ) ORDER BY document_datasets.name, document_datasets.dataset_id
        )
        FROM document_dataset_items
        JOIN document_datasets
          ON document_datasets.dataset_id = document_dataset_items.dataset_id
         AND document_datasets.owner_user_id = document_dataset_items.owner_user_id
        WHERE document_dataset_items.document_id = documents.document_id
          AND document_dataset_items.owner_user_id = documents.owner_user_id
    ), '[]'::jsonb) AS datasets,
    COALESCE((
        SELECT jsonb_agg(
            jsonb_build_object(
                'tag_id', document_tags.tag_id,
                'name', document_tags.name
            ) ORDER BY document_tags.name, document_tags.tag_id
        )
        FROM document_tag_assignments
        JOIN document_tags
          ON document_tags.tag_id = document_tag_assignments.tag_id
         AND document_tags.owner_user_id = document_tag_assignments.owner_user_id
        WHERE document_tag_assignments.document_id = documents.document_id
          AND document_tag_assignments.owner_user_id = documents.owner_user_id
    ), '[]'::jsonb) AS tags,
    (
        SELECT document_inspections.classification
        FROM document_inspections
        WHERE document_inspections.document_id = documents.document_id
          AND document_inspections.status = 'completed'
        ORDER BY document_inspections.created_at DESC,
                 document_inspections.inspection_id DESC
        LIMIT 1
    ) AS classification,
    (
        SELECT document_parse_jobs.status
        FROM document_parse_jobs
        WHERE document_parse_jobs.document_id = documents.document_id
        ORDER BY document_parse_jobs.created_at DESC,
                 document_parse_jobs.job_id DESC
        LIMIT 1
    ) AS parse_status
"""
