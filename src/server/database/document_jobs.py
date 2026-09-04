"""Durable, fenced PostgreSQL operations for document parse jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.server.database.pool import get_db_connection
from src.server.documents.contracts import ArtifactKind, JsonValue


_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})
_PROGRESS_STAGES = frozenset({"preparing", "parsing", "storing"})


@dataclass(frozen=True, slots=True)
class ArtifactPublication:
    artifact_id: str
    artifact_kind: ArtifactKind
    format: str
    media_type: str
    relative_path: str
    storage_key: str
    schema_name: str | None = None
    schema_version: str | None = None
    locator: dict[str, JsonValue] | None = None
    metadata: dict[str, JsonValue] | None = None


async def create_job(
    *,
    owner_user_id: str,
    job_id: str,
    document_id: str,
    inspection_id: str,
    parser_id: str,
    parser_name: str,
    parser_version: str | None,
    parser_options: dict[str, JsonValue],
    request_mode: str,
) -> dict[str, Any] | None:
    """Create a fresh job from one completed inspection of an owned Document."""
    if request_mode not in {"sync", "async"}:
        raise ValueError("request_mode must be sync or async")

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO document_parse_jobs (
                    job_id, document_id, inspection_id, parser_id, parser_name,
                    parser_version, parser_options, request_mode
                )
                SELECT %s, documents.document_id,
                       document_inspections.inspection_id, %s, %s, %s, %s, %s
                FROM documents
                JOIN document_inspections
                  ON document_inspections.document_id = documents.document_id
                WHERE documents.document_id = %s
                  AND document_inspections.inspection_id = %s
                  AND document_inspections.status = 'completed'
                  AND documents.owner_user_id = %s
                RETURNING document_parse_jobs.*
                """,
                (
                    job_id,
                    parser_id,
                    parser_name,
                    parser_version,
                    Jsonb(parser_options),
                    request_mode,
                    document_id,
                    inspection_id,
                    owner_user_id,
                ),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_owned_job(
    *,
    owner_user_id: str,
    job_id: str,
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT document_parse_jobs.*
                FROM document_parse_jobs
                JOIN documents
                  ON documents.document_id = document_parse_jobs.document_id
                WHERE document_parse_jobs.job_id = %s
                  AND documents.owner_user_id = %s
                """,
                (job_id, owner_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def claim_next_job(
    *,
    claimed_by: str,
    lease_seconds: int,
) -> dict[str, Any] | None:
    """Atomically claim one queued or expired-running job across all workers."""
    _validate_lease(claimed_by=claimed_by, lease_seconds=lease_seconds)
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                WITH candidate AS (
                    SELECT jobs.job_id,
                           documents.source_storage_key,
                           documents.source_size_bytes,
                           documents.original_filename,
                           documents.media_type,
                           documents.document_format,
                           document_inspections.inspector_id,
                           document_inspections.inspector_name,
                           document_inspections.inspector_version,
                           document_inspections.status AS inspection_status,
                           document_inspections.detected_format,
                           document_inspections.classification,
                           document_inspections.summary AS inspection_summary,
                           document_inspections.details AS inspection_details
                    FROM document_parse_jobs AS jobs
                    JOIN documents
                      ON documents.document_id = jobs.document_id
                    JOIN document_inspections
                      ON document_inspections.inspection_id = jobs.inspection_id
                     AND document_inspections.document_id = jobs.document_id
                    WHERE jobs.cancellation_requested_at IS NULL
                      AND (
                        jobs.status = 'queued'
                        OR (
                            jobs.status = 'running'
                            AND jobs.lease_expires_at <= clock_timestamp()
                        )
                      )
                    ORDER BY jobs.created_at, jobs.job_id
                    LIMIT 1
                    FOR UPDATE OF jobs SKIP LOCKED
                )
                UPDATE document_parse_jobs
                SET status = 'running',
                    claimed_by = %s,
                    lease_expires_at = clock_timestamp()
                        + make_interval(secs => %s),
                    attempt_count = attempt_count + 1,
                    status_version = status_version + 1,
                    started_at = COALESCE(started_at, clock_timestamp()),
                    updated_at = clock_timestamp(),
                    error_code = NULL,
                    error_message = NULL
                FROM candidate
                WHERE document_parse_jobs.job_id = candidate.job_id
                RETURNING document_parse_jobs.*,
                          candidate.source_storage_key,
                          candidate.source_size_bytes,
                          candidate.original_filename,
                          candidate.media_type,
                          candidate.document_format,
                          candidate.inspector_id,
                          candidate.inspector_name,
                          candidate.inspector_version,
                          candidate.inspection_status,
                          candidate.detected_format,
                          candidate.classification,
                          candidate.inspection_summary,
                          candidate.inspection_details
                """,
                (claimed_by, lease_seconds),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def renew_lease(
    *,
    job_id: str,
    claimed_by: str,
    attempt_count: int,
    expected_status_version: int,
    lease_seconds: int,
) -> dict[str, Any] | None:
    """Extend only the current, live claim without creating a client event."""
    _validate_lease(claimed_by=claimed_by, lease_seconds=lease_seconds)
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE document_parse_jobs
                SET lease_expires_at = clock_timestamp()
                        + make_interval(secs => %s),
                    updated_at = clock_timestamp()
                WHERE status = 'running'
                  AND lease_expires_at > clock_timestamp()
                  AND job_id = %s
                  AND claimed_by = %s
                  AND attempt_count = %s
                  AND status_version = %s
                RETURNING *
                """,
                (
                    lease_seconds,
                    job_id,
                    claimed_by,
                    attempt_count,
                    expected_status_version,
                ),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def update_progress(
    *,
    job_id: str,
    claimed_by: str,
    attempt_count: int,
    expected_status_version: int,
    stage: str,
    percentage: int,
) -> dict[str, Any] | None:
    """Advance one active job with attempt and version fencing."""
    if stage not in _PROGRESS_STAGES:
        raise ValueError("stage must be preparing, parsing, or storing")
    if not 0 <= percentage <= 99:
        raise ValueError("active job percentage must be between 0 and 99")

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE document_parse_jobs
                SET stage = %s,
                    percentage = %s,
                    status_version = status_version + 1,
                    updated_at = clock_timestamp()
                WHERE status = 'running'
                  AND cancellation_requested_at IS NULL
                  AND lease_expires_at > clock_timestamp()
                  AND percentage <= %s
                  AND CASE document_parse_jobs.stage
                        WHEN 'queued' THEN 0
                        WHEN 'preparing' THEN 1
                        WHEN 'parsing' THEN 2
                        WHEN 'storing' THEN 3
                      END <= CASE %s
                        WHEN 'preparing' THEN 1
                        WHEN 'parsing' THEN 2
                        WHEN 'storing' THEN 3
                      END
                  AND job_id = %s
                  AND claimed_by = %s
                  AND attempt_count = %s
                  AND status_version = %s
                RETURNING *
                """,
                (
                    stage,
                    percentage,
                    percentage,
                    stage,
                    job_id,
                    claimed_by,
                    attempt_count,
                    expected_status_version,
                ),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def request_cancel(
    *,
    owner_user_id: str,
    job_id: str,
) -> dict[str, Any] | None:
    """Request running cancellation or immediately cancel an owned queued job."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT document_parse_jobs.*
                    FROM document_parse_jobs
                    JOIN documents
                      ON documents.document_id = document_parse_jobs.document_id
                    WHERE document_parse_jobs.job_id = %s
                      AND documents.owner_user_id = %s
                    FOR UPDATE OF document_parse_jobs
                    """,
                    (job_id, owner_user_id),
                )
                current = await cur.fetchone()
                if current is None:
                    return None
                if current["status"] in _TERMINAL_STATUSES:
                    return dict(current)

                await cur.execute(
                    """
                    UPDATE document_parse_jobs
                    SET cancellation_requested_at = COALESCE(
                            cancellation_requested_at,
                            clock_timestamp()
                        ),
                        status = 'cancelled',
                        stage = 'cancelled',
                        completed_at = clock_timestamp(),
                        claimed_by = NULL,
                        lease_expires_at = NULL,
                        status_version = status_version + 1,
                        updated_at = clock_timestamp()
                    WHERE job_id = %s
                      AND status_version = %s
                      AND status IN ('queued', 'running')
                    RETURNING *
                    """,
                    (job_id, current["status_version"]),
                )
                row = await cur.fetchone()
    return dict(row) if row else None


async def publish_artifacts(
    *,
    job_id: str,
    claimed_by: str,
    attempt_count: int,
    expected_status_version: int,
    artifacts: tuple[ArtifactPublication, ...],
    primary_artifact_id: str | None,
) -> dict[str, Any] | None:
    """Insert artifact metadata and complete its actively claimed job atomically."""
    artifact_ids = {artifact.artifact_id for artifact in artifacts}
    if len(artifact_ids) != len(artifacts):
        raise ValueError("artifact IDs must be unique")
    if primary_artifact_id is not None and primary_artifact_id not in artifact_ids:
        raise ValueError("primary artifact must be in the publication")

    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT document_id
                    FROM document_parse_jobs
                    WHERE job_id = %s
                      AND claimed_by = %s
                      AND attempt_count = %s
                      AND status_version = %s
                      AND status = 'running'
                      AND cancellation_requested_at IS NULL
                      AND lease_expires_at > clock_timestamp()
                    FOR UPDATE
                    """,
                    (
                        job_id,
                        claimed_by,
                        attempt_count,
                        expected_status_version,
                    ),
                )
                claim = await cur.fetchone()
                if claim is None:
                    return None

                if artifacts:
                    await cur.executemany(
                        """
                        INSERT INTO document_artifacts (
                            artifact_id, document_id, producer_job_id,
                            artifact_kind, format, media_type, schema_name,
                            schema_version, relative_path, storage_key,
                            locator, metadata
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        """,
                        [
                            (
                                artifact.artifact_id,
                                claim["document_id"],
                                job_id,
                                artifact.artifact_kind,
                                artifact.format,
                                artifact.media_type,
                                artifact.schema_name,
                                artifact.schema_version,
                                artifact.relative_path,
                                artifact.storage_key,
                                _optional_jsonb(artifact.locator),
                                _optional_jsonb(artifact.metadata),
                            )
                            for artifact in artifacts
                        ],
                    )

                await cur.execute(
                    """
                    UPDATE document_parse_jobs
                    SET status = 'completed',
                        stage = 'completed',
                        percentage = 100,
                        primary_artifact_id = %s,
                        claimed_by = NULL,
                        lease_expires_at = NULL,
                        status_version = status_version + 1,
                        completed_at = clock_timestamp(),
                        updated_at = clock_timestamp()
                    WHERE job_id = %s
                      AND claimed_by = %s
                      AND attempt_count = %s
                      AND status_version = %s
                      AND status = 'running'
                      AND cancellation_requested_at IS NULL
                      AND lease_expires_at > clock_timestamp()
                    RETURNING *
                    """,
                    (
                        primary_artifact_id,
                        job_id,
                        claimed_by,
                        attempt_count,
                        expected_status_version,
                    ),
                )
                row = await cur.fetchone()
                if row is None:
                    raise RuntimeError("Claim changed while publishing artifacts")
    return dict(row)


async def fail_job(
    *,
    job_id: str,
    claimed_by: str,
    attempt_count: int,
    expected_status_version: int,
    error_code: str,
    error_message: str,
) -> dict[str, Any] | None:
    """Fail only the active attempt represented by the supplied fence."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE document_parse_jobs
                SET status = 'failed',
                    stage = 'failed',
                    error_code = %s,
                    error_message = %s,
                    claimed_by = NULL,
                    lease_expires_at = NULL,
                    status_version = status_version + 1,
                    completed_at = clock_timestamp(),
                    updated_at = clock_timestamp()
                WHERE status = 'running'
                  AND lease_expires_at > clock_timestamp()
                  AND job_id = %s
                  AND claimed_by = %s
                  AND attempt_count = %s
                  AND status_version = %s
                RETURNING *
                """,
                (
                    error_code,
                    error_message,
                    job_id,
                    claimed_by,
                    attempt_count,
                    expected_status_version,
                ),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def recover_expired_jobs(*, limit: int = 100) -> list[dict[str, Any]]:
    """Release a bounded set of expired claims for retry or cancellation."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                WITH expired AS (
                    SELECT job_id
                    FROM document_parse_jobs
                    WHERE status = 'running'
                      AND lease_expires_at <= clock_timestamp()
                    ORDER BY lease_expires_at, job_id
                    LIMIT %s
                    FOR UPDATE SKIP LOCKED
                )
                UPDATE document_parse_jobs
                SET status = CASE
                        WHEN cancellation_requested_at IS NULL THEN 'queued'
                        ELSE 'cancelled'
                    END,
                    stage = CASE
                        WHEN cancellation_requested_at IS NULL THEN stage
                        ELSE 'cancelled'
                    END,
                    claimed_by = NULL,
                    lease_expires_at = NULL,
                    completed_at = CASE
                        WHEN cancellation_requested_at IS NULL THEN completed_at
                        ELSE clock_timestamp()
                    END,
                    status_version = status_version + 1,
                    updated_at = clock_timestamp()
                FROM expired
                WHERE document_parse_jobs.job_id = expired.job_id
                RETURNING document_parse_jobs.*
                """,
                (limit,),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


def _validate_lease(*, claimed_by: str, lease_seconds: int) -> None:
    if not claimed_by.strip():
        raise ValueError("claimed_by must not be empty")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")


def _optional_jsonb(value: dict[str, JsonValue] | None) -> Jsonb | None:
    return Jsonb(value) if value is not None else None
