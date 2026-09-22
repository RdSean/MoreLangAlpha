"""Raw PostgreSQL persistence for versioned family textbook learning."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Json

from src.server.database.pool import get_db_connection


_SAFE_PATH_COMPONENT = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,254}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_CHECKPOINT_BUNDLE_PREFIX = re.compile(
    r"^education/"
    r"[0-9A-Za-z][0-9A-Za-z._-]{0,79}/"
    r"[0-9A-Za-z][0-9A-Za-z._-]{0,79}/"
    r"v[1-9][0-9]*/book-pipeline-checkpoints/"
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}/"
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)
MAX_GENERATION_PROGRESS_EVENTS = 2_000
GENERIC_STRUCTURE_SCHEMAS = frozenset(
    {
        "langalpha-book-content-tree/v1",
        "langalpha-managed-book-package/v1",
    }
)


class TextbookQueueValidationError(ValueError):
    """A textbook queue request failed before any database write."""


class KnowledgePointCandidateNotFoundError(LookupError):
    """A generated knowledge-point candidate is absent or not owned."""


class KnowledgePointCandidateTransitionError(ValueError):
    """A generated knowledge-point candidate cannot take the requested state."""


class ProgressEventPersistenceOutcome(str, Enum):
    """Outcome of one idempotent semantic progress write."""

    INSERTED = "inserted"
    ALREADY_EXISTS = "already_exists"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class ProgressEventPersistenceResult:
    """Typed progress write result returned to the live collector."""

    outcome: ProgressEventPersistenceOutcome
    event: Mapping[str, Any] | None = None


def _validated_checkpoint_bundle_prefix(value: object) -> str:
    """Return one canonical private checkpoint prefix or reject it."""
    prefix = str(value or "").strip()
    if not prefix or not _CHECKPOINT_BUNDLE_PREFIX.fullmatch(prefix):
        raise ValueError("checkpoint bundle prefix is invalid")
    return prefix


def _progress_event_matches(
    row: Mapping[str, Any],
    event: Mapping[str, Any],
) -> bool:
    """Return whether one durable row is the same normalized event payload."""
    row_metadata = row.get("metadata")
    event_metadata = event.get("metadata")
    if row_metadata is None:
        row_metadata = {}
    if event_metadata is None:
        event_metadata = {}
    if row_metadata != event_metadata:
        return False
    return all(
        row.get(field) == event.get(field)
        for field in (
            "event_key",
            "stage",
            "substage",
            "status",
            "label",
            "detail",
            "node_key",
            "current_value",
            "total_value",
        )
    )


def _validated_path_component(value: str, label: str) -> str:
    """Return a single safe storage-path component or reject it."""
    if ".." in value or not _SAFE_PATH_COMPONENT.fullmatch(value):
        raise ValueError(f"{label} must be a safe path component")
    return value


def _validated_asset_manifest(value: object) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TextbookQueueValidationError("asset_manifest must be a list")
    normalized: list[dict[str, str]] = []
    relative_paths: set[str] = set()
    for entry in value:
        if not isinstance(entry, Mapping):
            raise TextbookQueueValidationError("asset_manifest entry is invalid")
        fields = {
            field: str(entry.get(field) or "")
            for field in (
                "artifact_id",
                "artifact_kind",
                "format",
                "media_type",
                "relative_path",
                "sha256",
            )
        }
        relative_path = fields["relative_path"]
        if (
            not all(fields[field] for field in fields if field != "relative_path")
            or not relative_path
            or "\\" in relative_path
            or relative_path.startswith("/")
            or any(part in {"", ".", ".."} for part in relative_path.split("/"))
        ):
            raise TextbookQueueValidationError("asset_manifest entry is invalid")
        if relative_path in relative_paths:
            raise TextbookQueueValidationError("asset_manifest paths must be unique")
        if not _SHA256.fullmatch(fields["sha256"]):
            raise TextbookQueueValidationError("asset_manifest sha256 is invalid")
        relative_paths.add(relative_path)
        normalized.append(fields)
    return normalized


async def list_document_teaching_usages(
    *, owner_user_id: str, document_id: str
) -> list[dict[str, Any]]:
    """Return safe artifact-backed textbook usages for one owned Document."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT documents.document_id,
                       sources.producer_job_id,
                       sources.primary_artifact_id,
                       textbooks.textbook_id,
                       textbooks.title AS textbook_title,
                       versions.version_id AS content_version_id,
                       versions.sequence AS content_version_sequence,
                       sources.position AS artifact_position,
                       structures.structure_id,
                       structures.sequence AS structure_sequence,
                       structures.status AS structure_status,
                       structures.book_asset_prefix,
                       publications.publication_id,
                       publications.publication_id IS NOT NULL AS is_published,
                       COALESCE(
                           structures.book_asset_manifest <> '{}'::jsonb,
                           FALSE
                       ) AS has_asset_manifest,
                       sources.created_at
                FROM documents
                JOIN education_textbook_artifact_sources AS sources
                  ON sources.document_id = documents.document_id
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = sources.version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                 AND memberships.user_id = documents.owner_user_id
                 AND memberships.role = 'parent'
                LEFT JOIN education_textbook_structures AS structures
                  ON structures.version_id = versions.version_id
                LEFT JOIN education_textbook_publications AS publications
                  ON publications.version_id = versions.version_id
                 AND publications.structure_id = structures.structure_id
                WHERE documents.document_id = %s
                  AND documents.owner_user_id = %s
                ORDER BY sources.created_at,
                         textbooks.created_at,
                         versions.sequence,
                         sources.position,
                         structures.sequence NULLS LAST,
                         structures.structure_id NULLS LAST
                """,
                (document_id, owner_user_id),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_document_teaching_usage_access(
    *, owner_user_id: str, document_id: str
) -> bool | None:
    """Authorize an owned Document in the households of its textbook usages."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                WITH usage_candidates AS (
                    SELECT textbooks.household_id
                    FROM documents
                    JOIN education_textbook_artifact_sources AS sources
                      ON sources.document_id = documents.document_id
                    JOIN education_textbook_versions AS versions
                      ON versions.version_id = sources.version_id
                    JOIN education_textbooks AS textbooks
                      ON textbooks.textbook_id = versions.textbook_id
                    WHERE documents.document_id = %s
                      AND documents.owner_user_id = %s
                )
                SELECT CASE
                    WHEN NOT EXISTS (SELECT 1 FROM usage_candidates)
                    THEN TRUE
                    ELSE EXISTS (
                        SELECT 1
                        FROM usage_candidates
                        JOIN education_memberships AS memberships
                          ON memberships.household_id =
                             usage_candidates.household_id
                         AND memberships.user_id = %s
                         AND memberships.role = 'parent'
                    )
                END AS can_read
                FROM documents
                WHERE documents.document_id = %s
                  AND documents.owner_user_id = %s
                """,
                (
                    document_id,
                    owner_user_id,
                    owner_user_id,
                    document_id,
                    owner_user_id,
                ),
            )
            row = await cur.fetchone()
    if row is None:
        return None
    return bool(row["can_read"])


async def get_or_create_student_learning_space(
    *, student_user_id: str, assignment_id: str
) -> dict[str, Any] | None:
    """Create exactly one canonical Flash thread for an assigned publication.

    The assignment row is locked before inspecting its mapping, so concurrent
    reader tabs cannot create two conversation threads for the same immutable
    publication snapshot.
    """
    from src.server.database.conversation import create_thread
    from src.server.database.workspace import get_or_create_flash_workspace

    thread_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT assignments.assignment_id, textbooks.title AS textbook_title
                    FROM education_textbook_assignments AS assignments
                    JOIN education_textbook_publications AS publications
                      ON publications.publication_id = assignments.publication_id
                    JOIN education_textbook_versions AS versions
                      ON versions.version_id = publications.version_id
                    JOIN education_textbooks AS textbooks
                      ON textbooks.textbook_id = versions.textbook_id
                    JOIN education_memberships AS memberships
                      ON memberships.user_id = assignments.student_user_id
                     AND memberships.household_id = textbooks.household_id
                    WHERE assignments.assignment_id = %s
                      AND assignments.student_user_id = %s
                      AND memberships.role = 'student'
                    FOR UPDATE OF assignments
                    """,
                    (assignment_id, student_user_id),
                )
                assignment = await cur.fetchone()
                if not assignment:
                    return None
                await cur.execute(
                    """
                    SELECT spaces.assignment_id, spaces.workspace_id,
                           spaces.conversation_thread_id, spaces.created_at
                    FROM education_learning_spaces AS spaces
                    WHERE spaces.assignment_id = %s
                    """,
                    (assignment_id,),
                )
                existing = await cur.fetchone()
                if existing:
                    return dict(existing)

                workspace = await get_or_create_flash_workspace(
                    student_user_id, conn=conn
                )
                await create_thread(
                    conversation_thread_id=thread_id,
                    workspace_id=str(workspace["workspace_id"]),
                    current_status="completed",
                    msg_type="flash",
                    title=f"{assignment['textbook_title']} 学习问答"[:255],
                    platform="education",
                    metadata={"education": {"assignment_id": assignment_id}},
                    conn=conn,
                )
                await cur.execute(
                    """
                    INSERT INTO education_learning_spaces (
                        assignment_id, workspace_id, conversation_thread_id
                    ) VALUES (%s, %s, %s)
                    RETURNING assignment_id, workspace_id, conversation_thread_id, created_at
                    """,
                    (assignment_id, workspace["workspace_id"], thread_id),
                )
                created = await cur.fetchone()
    return dict(created) if created else None


async def get_student_learning_space(
    *, student_user_id: str, assignment_id: str
) -> dict[str, Any] | None:
    """Read a student's assignment-scoped Flash thread without creating one."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT spaces.assignment_id, spaces.workspace_id,
                       spaces.conversation_thread_id, spaces.created_at
                FROM education_learning_spaces AS spaces
                JOIN education_textbook_assignments AS assignments
                  ON assignments.assignment_id = spaces.assignment_id
                JOIN education_textbook_publications AS publications
                  ON publications.publication_id = assignments.publication_id
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = publications.version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.user_id = assignments.student_user_id
                 AND memberships.household_id = textbooks.household_id
                WHERE spaces.assignment_id = %s
                  AND assignments.student_user_id = %s
                  AND memberships.role = 'student'
                """,
                (assignment_id, student_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_student_learning_space_for_thread(
    *, student_user_id: str, conversation_thread_id: str
) -> dict[str, Any] | None:
    """Resolve a mapped learning thread only when owned by the student."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT spaces.assignment_id, spaces.workspace_id,
                       spaces.conversation_thread_id
                FROM education_learning_spaces AS spaces
                JOIN education_textbook_assignments AS assignments
                  ON assignments.assignment_id = spaces.assignment_id
                JOIN education_textbook_publications AS publications
                  ON publications.publication_id = assignments.publication_id
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = publications.version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.user_id = assignments.student_user_id
                 AND memberships.household_id = textbooks.household_id
                WHERE spaces.conversation_thread_id = %s
                  AND assignments.student_user_id = %s
                  AND memberships.role = 'student'
                """,
                (conversation_thread_id, student_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_parent_learning_space(
    *, parent_user_id: str, assignment_id: str
) -> dict[str, Any] | None:
    """Return an assigned student's mapped Flash thread to an authorized parent."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT assignments.assignment_id, assignments.student_user_id,
                       textbooks.title AS textbook_title, spaces.workspace_id,
                       spaces.conversation_thread_id, spaces.created_at
                FROM education_textbook_assignments AS assignments
                JOIN education_textbook_publications AS publications
                  ON publications.publication_id = assignments.publication_id
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = publications.version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                LEFT JOIN education_learning_spaces AS spaces
                  ON spaces.assignment_id = assignments.assignment_id
                WHERE assignments.assignment_id = %s
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                """,
                (assignment_id, parent_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def create_textbook_record(
    *, household_id: str, parent_user_id: str, title: str, slug: str
) -> dict[str, Any]:
    textbook_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO education_textbooks (textbook_id, household_id, title, slug, created_by_user_id)
                SELECT %s, %s, %s, %s, %s
                WHERE EXISTS (
                    SELECT 1 FROM education_memberships
                    WHERE household_id = %s AND user_id = %s AND role = 'parent'
                )
                RETURNING textbook_id, household_id, title, slug, created_by_user_id, created_at
                """,
                (
                    textbook_id,
                    household_id,
                    title,
                    slug,
                    parent_user_id,
                    household_id,
                    parent_user_id,
                ),
            )
            row = await cur.fetchone()
    return dict(row) if row else {}


async def queue_textbook_structure(
    *,
    parent_user_id: str,
    content_version_id: str,
    processing_profile_id: str | None,
    processing_profile_sha256: str,
    input_manifest_sha256: str,
    source_revision: str,
    generation_job_id: str | None = None,
    structure_id: str | None = None,
) -> dict[str, Any] | None:
    """Create one reviewable structure and its queued generation job."""
    structure_id = str(structure_id or uuid4())
    generation_job_id = str(generation_job_id or uuid4())
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                # Serialize concurrent starts for one content version so a
                # double click cannot create two structure jobs.
                await cur.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    (f"education-structure:{content_version_id}",),
                )
                await cur.execute(
                    """
                    SELECT versions.version_id
                    FROM education_textbook_versions AS versions
                    JOIN education_textbooks AS textbooks
                      ON textbooks.textbook_id = versions.textbook_id
                    JOIN education_memberships AS memberships
                      ON memberships.household_id = textbooks.household_id
                    WHERE versions.version_id = %s
                      AND versions.status = 'review'
                      AND memberships.user_id = %s
                      AND memberships.role = 'parent'
                    FOR UPDATE OF versions
                    """,
                    (content_version_id, parent_user_id),
                )
                if not await cur.fetchone():
                    return None
                await cur.execute(
                    """
                    SELECT jobs.generation_job_id, jobs.version_id, jobs.scope,
                           jobs.structure_id, jobs.status, jobs.attempt_count,
                           structures.sequence AS structure_sequence,
                           structures.status AS structure_status
                    FROM education_generation_jobs AS jobs
                    LEFT JOIN education_textbook_structures AS structures
                      ON structures.structure_id = jobs.structure_id
                    WHERE jobs.version_id = %s
                      AND jobs.scope = 'structure'
                      AND jobs.status IN (
                          'queued', 'preparing', 'running', 'validating'
                      )
                    ORDER BY jobs.created_at DESC
                    LIMIT 1
                    """,
                    (content_version_id,),
                )
                active_job = await cur.fetchone()
                if active_job:
                    return dict(active_job)
                await cur.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence
                    FROM education_textbook_structures
                    WHERE version_id = %s
                    """,
                    (content_version_id,),
                )
                sequence = (await cur.fetchone())["sequence"]
                await cur.execute(
                    """
                    INSERT INTO education_textbook_structures (
                        structure_id, version_id, sequence, status, schema_version,
                        processing_profile_id, processing_profile_sha256,
                        input_manifest_sha256, source_revision, created_by_user_id
                    ) VALUES (
                        %s, %s, %s, 'queued',
                        'langalpha-managed-textbook-structure/v1',
                        %s, %s, %s, %s, %s
                    )
                    RETURNING structure_id, version_id, sequence, status
                    """,
                    (
                        structure_id,
                        content_version_id,
                        sequence,
                        processing_profile_id,
                        processing_profile_sha256,
                        input_manifest_sha256,
                        source_revision,
                        parent_user_id,
                    ),
                )
                structure = dict(await cur.fetchone())
                await cur.execute(
                    """
                    INSERT INTO education_generation_jobs (
                        generation_job_id, version_id, scope, structure_id, status,
                        processing_profile_sha256
                    ) VALUES (%s, %s, 'structure', %s, 'queued', %s)
                    RETURNING generation_job_id, scope, status
                    """,
                    (
                        generation_job_id,
                        content_version_id,
                        structure_id,
                        processing_profile_sha256,
                    ),
                )
                job = dict(await cur.fetchone())
    return {**structure, **job}


async def get_active_structure_generation_for_parent(
    *, parent_user_id: str, content_version_id: str
) -> dict[str, Any] | None:
    """Return the newest queued/running structure job for one content version.

    This is a best-effort fast path used before staging inputs. Correctness
    against concurrent double clicks is enforced by the advisory lock inside
    ``queue_textbook_structure``.
    """
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.generation_job_id, jobs.version_id, jobs.scope,
                       jobs.structure_id, jobs.status, jobs.attempt_count,
                       structures.sequence AS structure_sequence,
                       structures.status AS structure_status
                FROM education_generation_jobs AS jobs
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = jobs.version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                LEFT JOIN education_textbook_structures AS structures
                  ON structures.structure_id = jobs.structure_id
                WHERE jobs.version_id = %s
                  AND jobs.scope = 'structure'
                  AND jobs.status IN (
                      'queued', 'preparing', 'running', 'validating'
                  )
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                ORDER BY jobs.created_at DESC
                LIMIT 1
                """,
                (content_version_id, parent_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def queue_book_pipeline_job(
    *,
    parent_user_id: str,
    content_version_id: str,
    processing_profile_sha256: str,
    processing_brief: str = "",
    request_id: str | None = None,
    pause_after_chapter_analysis: bool = False,
) -> dict[str, Any] | None:
    """Create or reuse one active unified book pipeline for a content version."""
    generation_job_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT pg_advisory_xact_lock(hashtext(%s))",
                    (f"education-book-pipeline:{content_version_id}",),
                )
                await cur.execute(
                    """
                    SELECT versions.version_id
                    FROM education_textbook_versions AS versions
                    JOIN education_textbooks AS textbooks
                      ON textbooks.textbook_id = versions.textbook_id
                    JOIN education_memberships AS memberships
                      ON memberships.household_id = textbooks.household_id
                    WHERE versions.version_id = %s
                      AND versions.status = 'review'
                      AND memberships.user_id = %s
                      AND memberships.role = 'parent'
                    FOR UPDATE OF versions
                    """,
                    (content_version_id, parent_user_id),
                )
                if not await cur.fetchone():
                    return None
                if request_id is not None:
                    await cur.execute(
                        """
                        SELECT jobs.generation_job_id, jobs.version_id,
                               jobs.scope, jobs.structure_id,
                               jobs.knowledge_point_id, jobs.status,
                               jobs.attempt_count,
                               jobs.pause_after_chapter_analysis,
                               jobs.checkpoint_bundle_prefix,
                               jobs.error_code, jobs.error_message,
                               jobs.created_at, jobs.updated_at,
                               attempts.root_run_id, attempts.started_at,
                               attempts.heartbeat_at,
                               TRUE AS reused_existing_job
                        FROM education_generation_jobs AS jobs
                        LEFT JOIN education_generation_attempts AS attempts
                          ON attempts.attempt_id = jobs.latest_attempt_id
                        WHERE jobs.version_id = %s
                          AND jobs.request_id = %s
                          AND jobs.scope = 'book_pipeline'
                        ORDER BY jobs.created_at DESC
                        LIMIT 1
                        """,
                        (content_version_id, request_id),
                    )
                    request_job = await cur.fetchone()
                    if request_job:
                        return dict(request_job)
                await cur.execute(
                    """
                    SELECT jobs.generation_job_id, jobs.version_id, jobs.scope,
                           jobs.structure_id, jobs.knowledge_point_id,
                           jobs.status, jobs.attempt_count,
                           jobs.pause_after_chapter_analysis,
                           jobs.checkpoint_bundle_prefix,
                           jobs.error_code, jobs.error_message,
                           jobs.created_at, jobs.updated_at,
                           attempts.root_run_id, attempts.started_at,
                           attempts.heartbeat_at,
                           TRUE AS reused_existing_job
                    FROM education_generation_jobs AS jobs
                    LEFT JOIN education_generation_attempts AS attempts
                      ON attempts.attempt_id = jobs.latest_attempt_id
                    WHERE jobs.version_id = %s
                      AND jobs.scope = 'book_pipeline'
                      AND jobs.status IN (
                          'queued', 'preparing', 'running', 'validating',
                          'awaiting_review'
                      )
                    ORDER BY jobs.created_at DESC
                    LIMIT 1
                    """,
                    (content_version_id,),
                )
                active_job = await cur.fetchone()
                if active_job:
                    return dict(active_job)
                await cur.execute(
                    """
                    INSERT INTO education_generation_jobs (
                        generation_job_id, version_id, processing_brief,
                        request_id, scope, structure_id,
                        knowledge_point_id, status,
                        pause_after_chapter_analysis,
                        processing_profile_sha256
                    ) VALUES (
                        %s, %s, %s, %s, 'book_pipeline', NULL, NULL,
                        'queued', %s, %s
                    )
                    RETURNING generation_job_id, version_id, scope,
                              structure_id, knowledge_point_id, status,
                              attempt_count, pause_after_chapter_analysis,
                              checkpoint_bundle_prefix,
                              error_code, error_message, created_at, updated_at,
                              FALSE AS reused_existing_job
                    """,
                    (
                        generation_job_id,
                        content_version_id,
                        processing_brief,
                        request_id,
                        pause_after_chapter_analysis,
                        processing_profile_sha256,
                    ),
                )
                job = await cur.fetchone()
    return dict(job)


async def pause_book_pipeline_for_chapter_review(
    *,
    parent_user_id: str,
    generation_job_id: str,
    attempt_id: str,
    checkpoint_bundle_prefix: str,
) -> dict[str, Any] | None:
    """Finish one parent-owned checkpoint attempt and enter review state."""
    checkpoint_bundle_prefix = _validated_checkpoint_bundle_prefix(
        checkpoint_bundle_prefix
    )
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT attempts.attempt_id
                    FROM education_generation_attempts AS attempts
                    JOIN education_generation_jobs AS jobs
                      ON jobs.generation_job_id = attempts.generation_job_id
                    JOIN education_textbook_versions AS versions
                      ON versions.version_id = jobs.version_id
                    JOIN education_textbooks AS textbooks
                      ON textbooks.textbook_id = versions.textbook_id
                    JOIN education_memberships AS memberships
                      ON memberships.household_id = textbooks.household_id
                    WHERE attempts.generation_job_id = %s
                      AND attempts.attempt_id = %s
                      AND jobs.latest_attempt_id = %s
                      AND memberships.user_id = %s
                      AND memberships.role = 'parent'
                      AND jobs.scope = 'book_pipeline'
                      AND jobs.status = 'running'
                      AND jobs.pause_after_chapter_analysis IS TRUE
                    FOR UPDATE OF attempts
                    """,
                    (generation_job_id, attempt_id, attempt_id, parent_user_id),
                )
                if not await cur.fetchone():
                    return None
                await cur.execute(
                    """
                    UPDATE education_generation_attempts
                    SET status = 'completed', completed_at = NOW()
                    WHERE attempt_id = %s AND generation_job_id = %s
                      AND status = 'running'
                    RETURNING attempt_id
                    """,
                    (attempt_id, generation_job_id),
                )
                if not await cur.fetchone():
                    raise RuntimeError("Book pipeline checkpoint transition was lost")
                await cur.execute(
                    """
                    UPDATE education_generation_jobs AS jobs
                    SET status = 'awaiting_review', error_code = NULL,
                        error_message = NULL,
                        checkpoint_bundle_prefix = %s,
                        updated_at = NOW()
                    FROM education_textbook_versions AS versions,
                         education_textbooks AS textbooks,
                         education_memberships AS memberships
                    WHERE jobs.generation_job_id = %s
                      AND jobs.latest_attempt_id = %s
                      AND jobs.version_id = versions.version_id
                      AND versions.textbook_id = textbooks.textbook_id
                      AND textbooks.household_id = memberships.household_id
                      AND memberships.user_id = %s
                      AND memberships.role = 'parent'
                      AND jobs.scope = 'book_pipeline'
                      AND jobs.status = 'running'
                      AND jobs.pause_after_chapter_analysis IS TRUE
                    RETURNING jobs.generation_job_id, jobs.version_id,
                              jobs.scope, jobs.structure_id,
                              jobs.knowledge_point_id, jobs.status,
                              jobs.attempt_count,
                              jobs.pause_after_chapter_analysis,
                              jobs.checkpoint_bundle_prefix,
                              jobs.error_code, jobs.error_message,
                              jobs.created_at, jobs.updated_at
                    """,
                    (
                        checkpoint_bundle_prefix,
                        generation_job_id,
                        attempt_id,
                        parent_user_id,
                    ),
                )
                job = await cur.fetchone()
                if not job:
                    raise RuntimeError("Book pipeline checkpoint transition was lost")
    return dict(job)


async def resume_book_pipeline_job(
    *,
    parent_user_id: str,
    generation_job_id: str,
) -> dict[str, Any] | None:
    """Consume one parent-owned checkpoint and queue its continuation."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE education_generation_jobs AS jobs
                SET status = 'queued',
                    pause_after_chapter_analysis = FALSE,
                    error_code = NULL, error_message = NULL,
                    updated_at = NOW()
                FROM education_textbook_versions AS versions,
                     education_textbooks AS textbooks,
                     education_memberships AS memberships
                WHERE jobs.generation_job_id = %s
                  AND jobs.version_id = versions.version_id
                  AND versions.textbook_id = textbooks.textbook_id
                  AND textbooks.household_id = memberships.household_id
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                  AND jobs.scope = 'book_pipeline'
                  AND jobs.status = 'awaiting_review'
                  AND jobs.pause_after_chapter_analysis IS TRUE
                  AND jobs.checkpoint_bundle_prefix IS NOT NULL
                  AND btrim(jobs.checkpoint_bundle_prefix) <> ''
                RETURNING jobs.generation_job_id, jobs.version_id,
                          jobs.scope, jobs.structure_id,
                          jobs.knowledge_point_id, jobs.status,
                          jobs.attempt_count,
                          jobs.pause_after_chapter_analysis,
                          jobs.checkpoint_bundle_prefix,
                          jobs.error_code, jobs.error_message,
                          jobs.created_at, jobs.updated_at
                """,
                (generation_job_id, parent_user_id),
            )
            job = await cur.fetchone()
    return dict(job) if job else None


async def claim_book_pipeline_launch(
    *,
    parent_user_id: str,
    generation_job_id: str,
) -> dict[str, Any] | None:
    """Claim the queued→preparing launch fence for exactly one runtime owner."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE education_generation_jobs AS jobs
                    SET status = 'preparing', updated_at = NOW()
                    FROM education_textbook_versions AS versions,
                         education_textbooks AS textbooks,
                         education_memberships AS memberships
                    WHERE jobs.generation_job_id = %s
                      AND jobs.version_id = versions.version_id
                      AND versions.textbook_id = textbooks.textbook_id
                      AND textbooks.household_id = memberships.household_id
                      AND memberships.user_id = %s
                      AND memberships.role = 'parent'
                      AND jobs.scope = 'book_pipeline'
                      AND jobs.status = 'queued'
                    RETURNING jobs.generation_job_id, jobs.version_id,
                              jobs.scope, jobs.structure_id,
                              jobs.knowledge_point_id, jobs.status,
                              jobs.attempt_count, jobs.latest_attempt_id,
                              jobs.pause_after_chapter_analysis,
                              jobs.error_code, jobs.error_message,
                              jobs.created_at, jobs.updated_at
                    """,
                    (generation_job_id, parent_user_id),
                )
                claimed = await cur.fetchone()
    return dict(claimed) if claimed else None


async def fail_claimed_book_pipeline_launch(
    *,
    generation_job_id: str,
    expected_latest_attempt_id: str | None,
    error_code: str,
    error_message: str,
) -> dict[str, Any] | None:
    """Close a preparing launch claim when no attempt was created."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE education_generation_jobs AS jobs
                    SET status = 'failed', error_code = %s,
                        error_message = %s, updated_at = NOW()
                    WHERE jobs.generation_job_id = %s
                      AND jobs.scope = 'book_pipeline'
                      AND jobs.status = 'preparing'
                      AND jobs.latest_attempt_id IS NOT DISTINCT FROM %s
                    RETURNING generation_job_id, version_id, scope,
                              structure_id, knowledge_point_id, status,
                              attempt_count, pause_after_chapter_analysis,
                              error_code, error_message, created_at, updated_at
                    """,
                    (
                        error_code,
                        error_message,
                        generation_job_id,
                        expected_latest_attempt_id,
                    ),
                )
                failed = await cur.fetchone()
    return dict(failed) if failed else None


def _ordered_content_nodes(
    nodes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return a stable roots-before-children order for a validated tree."""
    by_key = {str(node["node_key"]): node for node in nodes}
    children: dict[str | None, list[dict[str, Any]]] = {}
    for node in nodes:
        parent = node.get("parent_key")
        children.setdefault(str(parent) if parent is not None else None, []).append(
            node
        )
    for siblings in children.values():
        siblings.sort(
            key=lambda node: (
                int(node.get("position") or 0),
                str(node.get("node_key") or ""),
            )
        )

    ordered: list[dict[str, Any]] = []
    stack = list(reversed(children.get(None, [])))
    while stack:
        node = stack.pop()
        ordered.append(node)
        key = str(node["node_key"])
        stack.extend(reversed(children.get(key, [])))
    if len(ordered) != len(by_key):
        raise TextbookQueueValidationError("content tree parent topology is invalid")
    return ordered


def _candidate_slug(candidate_key: str) -> str:
    slug = re.sub(r"[^0-9a-z]+", "-", candidate_key.casefold()).strip("-")
    slug = slug[:230] or "knowledge-point"
    return f"{slug}-{uuid4().hex[:8]}"


def _split_candidate_key(source_key: str, index: int) -> str:
    """Return a readable, deterministic key that fits VARCHAR(255)."""
    digest = hashlib.sha256(f"{source_key}\0{index}".encode("utf-8")).hexdigest()[:12]
    suffix = f"-split-{index + 1:02d}-{digest}"
    prefix = source_key[: max(1, 255 - len(suffix))]
    return f"{prefix}{suffix}"


async def complete_book_pipeline_import(
    *,
    parent_user_id: str,
    generation_job_id: str,
    attempt_id: str,
    package: Mapping[str, Any],
    bundle_prefix: str,
    bundle_manifest: Mapping[str, Any],
    asset_content_keys: Mapping[str, str],
    warnings: list[str] | None = None,
) -> dict[str, Any] | None:
    """Atomically persist one validated generic book package for review."""
    nodes = package.get("content_nodes")
    points = package.get("knowledge_points")
    assets = package.get("assets")
    if not isinstance(nodes, list) or not isinstance(points, list):
        raise TextbookQueueValidationError("book package content is invalid")
    if not isinstance(assets, list):
        raise TextbookQueueValidationError("book package assets are invalid")
    if (
        not isinstance(bundle_prefix, str)
        or not bundle_prefix.startswith("education/")
        or ".." in bundle_prefix
    ):
        raise TextbookQueueValidationError("book package bundle prefix is invalid")
    manifest_sha256 = hashlib.sha256(
        json.dumps(
            bundle_manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    structure_id = str(uuid4())
    node_ids = {str(node["node_key"]): str(uuid4()) for node in nodes}
    ordered_nodes = _ordered_content_nodes(nodes)

    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT jobs.generation_job_id, jobs.version_id,
                           jobs.processing_profile_sha256, jobs.structure_id,
                           jobs.status, attempts.attempt_id
                    FROM education_generation_attempts AS attempts
                    JOIN education_generation_jobs AS jobs
                      ON jobs.generation_job_id = attempts.generation_job_id
                    JOIN education_textbook_versions AS versions
                      ON versions.version_id = jobs.version_id
                    JOIN education_textbooks AS textbooks
                      ON textbooks.textbook_id = versions.textbook_id
                    JOIN education_memberships AS memberships
                      ON memberships.household_id = textbooks.household_id
                    WHERE attempts.attempt_id = %s
                      AND attempts.generation_job_id = %s
                      AND attempts.status = 'running'
                      AND jobs.latest_attempt_id = attempts.attempt_id
                      AND jobs.scope = 'book_pipeline'
                      AND jobs.status = 'running'
                      AND memberships.user_id = %s
                      AND memberships.role = 'parent'
                    FOR UPDATE OF attempts
                    """,
                    (attempt_id, generation_job_id, parent_user_id),
                )
                job = await cur.fetchone()
                if not job:
                    return None
                version_id = str(job["version_id"])
                await cur.execute(
                    """
                    SELECT version_id
                    FROM education_textbook_versions
                    WHERE version_id = %s
                    FOR UPDATE
                    """,
                    (version_id,),
                )
                if not await cur.fetchone():
                    raise RuntimeError("Book package version disappeared")
                await cur.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence
                    FROM education_textbook_structures
                    WHERE version_id = %s
                    """,
                    (version_id,),
                )
                sequence = int((await cur.fetchone())["sequence"])
                await cur.execute(
                    """
                    INSERT INTO education_textbook_structures (
                        structure_id, version_id, sequence, status,
                        schema_version, processing_profile_id,
                        processing_profile_sha256, input_manifest_sha256,
                        source_revision, bundle_prefix, validation_warnings,
                        created_by_user_id
                    ) VALUES (
                        %s, %s, %s, 'review', 'langalpha-book-content-tree/v1',
                        NULL, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING structure_id, version_id, sequence, status
                    """,
                    (
                        structure_id,
                        version_id,
                        sequence,
                        str(job["processing_profile_sha256"]),
                        manifest_sha256,
                        str(package.get("source_revision") or ""),
                        bundle_prefix,
                        Json(warnings or []),
                        parent_user_id,
                    ),
                )
                structure = await cur.fetchone()
                if not structure:
                    raise RuntimeError("Book package structure was not created")

                for index, node in enumerate(ordered_nodes, start=1):
                    node_key = str(node["node_key"])
                    parent_key = node.get("parent_key")
                    await cur.execute(
                        """
                        INSERT INTO education_content_nodes (
                            node_id, structure_id, parent_node_id, node_key,
                            node_type, label, position, slug, title, summary,
                            source_refs, metadata
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                        )
                        """,
                        (
                            node_ids[node_key],
                            structure_id,
                            node_ids.get(str(parent_key)) if parent_key else None,
                            node_key,
                            str(node["node_type"]),
                            node.get("label"),
                            int(node["position"]),
                            str(node.get("slug") or f"node-{index}"),
                            str(node["title"]),
                            str(node.get("summary") or ""),
                            Json(node.get("source_refs") or []),
                            Json(node.get("metadata") or {}),
                        ),
                    )

                for asset in assets:
                    relative_path = str(asset.get("path") or "")
                    content_key = asset_content_keys.get(relative_path)
                    if not content_key:
                        raise TextbookQueueValidationError(
                            "book package asset is not archived"
                        )
                    await cur.execute(
                        """
                        INSERT INTO education_content_assets (
                            asset_id, structure_id, node_id, asset_type,
                            content_key, content_sha256, size_bytes, metadata
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            str(uuid4()),
                            structure_id,
                            node_ids[str(asset["node_key"])],
                            str(asset["kind"]),
                            content_key,
                            str(asset["content_sha256"]),
                            int(asset["size_bytes"]),
                            Json(asset.get("metadata") or {}),
                        ),
                    )

                for position, point in enumerate(points, start=1):
                    candidate_key = str(point["candidate_key"])
                    await cur.execute(
                        """
                        INSERT INTO education_structure_knowledge_points (
                            knowledge_point_id, unit_id, content_structure_id,
                            content_node_id, candidate_key, point_type, origin,
                            candidate_status, position, slug, title, summary,
                            source_refs, confidence, status
                        ) VALUES (
                            %s, NULL, %s, %s, %s, %s, 'generated',
                            'pending', %s, %s, %s, %s, %s, %s, 'review'
                        )
                        """,
                        (
                            str(uuid4()),
                            structure_id,
                            node_ids[str(point["node_key"])],
                            candidate_key,
                            str(point["point_type"]),
                            position,
                            _candidate_slug(candidate_key),
                            str(point["title"]),
                            str(point.get("summary") or ""),
                            Json(point.get("source_refs") or []),
                            float(point["confidence"]),
                        ),
                    )

                await cur.execute(
                    """
                    UPDATE education_generation_attempts
                    SET status = 'completed', completed_at = NOW()
                    WHERE attempt_id = %s AND generation_job_id = %s
                      AND status = 'running'
                    RETURNING attempt_id
                    """,
                    (attempt_id, generation_job_id),
                )
                if not await cur.fetchone():
                    raise RuntimeError("Book pipeline attempt completion was lost")
                await cur.execute(
                    """
                    UPDATE education_generation_jobs
                    SET status = 'completed', structure_id = %s,
                        checkpoint_bundle_prefix = NULL,
                        error_code = NULL, error_message = NULL,
                        updated_at = NOW()
                    WHERE generation_job_id = %s
                      AND latest_attempt_id = %s
                      AND status = 'running'
                    RETURNING generation_job_id, status
                    """,
                    (structure_id, generation_job_id, attempt_id),
                )
                completed = await cur.fetchone()
                if not completed:
                    raise RuntimeError("Book pipeline job completion was lost")
    return {
        **dict(structure),
        "generation_job_id": completed["generation_job_id"],
        "job_status": completed["status"],
        "bundle_prefix": bundle_prefix,
        "node_count": len(nodes),
        "knowledge_point_count": len(points),
        "asset_count": len(assets),
    }


async def get_active_lesson_generation_for_parent(
    *, parent_user_id: str, knowledge_point_id: str
) -> dict[str, Any] | None:
    """Return the newest queued/running lesson job for one knowledge point."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.generation_job_id, jobs.version_id, jobs.scope,
                       jobs.knowledge_point_id, jobs.status, jobs.attempt_count,
                       jobs.auto_grading, jobs.error_code, jobs.error_message,
                       jobs.created_at, jobs.updated_at,
                       attempts.root_run_id, attempts.started_at,
                       attempts.heartbeat_at
                FROM education_generation_jobs AS jobs
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = jobs.version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                LEFT JOIN education_generation_attempts AS attempts
                  ON attempts.attempt_id = jobs.latest_attempt_id
                WHERE jobs.knowledge_point_id = %s
                  AND jobs.scope = 'lesson'
                  AND jobs.status IN (
                      'queued', 'preparing', 'running', 'validating'
                  )
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                ORDER BY jobs.created_at DESC
                LIMIT 1
                """,
                (knowledge_point_id, parent_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def create_processing_profile(
    *,
    parent_user_id: str,
    version_id: str,
    subject: str,
    grade_band: str,
    language: str,
    depth: str,
    question_types: list[str],
    prompt_fragment: str,
    allowed_skills: list[str],
    profile_sha256: str,
) -> dict[str, Any] | None:
    """Create a new immutable profile revision for one parent-owned version."""
    profile_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT versions.version_id, textbooks.household_id
                    FROM education_textbook_versions AS versions
                    JOIN education_textbooks AS textbooks
                      ON textbooks.textbook_id = versions.textbook_id
                    JOIN education_memberships AS memberships
                      ON memberships.household_id = textbooks.household_id
                    WHERE versions.version_id = %s
                      AND memberships.user_id = %s
                      AND memberships.role = 'parent'
                    FOR UPDATE OF versions
                    """,
                    (version_id, parent_user_id),
                )
                version = await cur.fetchone()
                if not version:
                    return None
                await cur.execute(
                    """
                    SELECT COALESCE(MAX(version), 0) + 1 AS version
                    FROM education_processing_profiles
                    WHERE version_id = %s
                    """,
                    (version_id,),
                )
                profile_version = (await cur.fetchone())["version"]
                await cur.execute(
                    """
                    INSERT INTO education_processing_profiles (
                        profile_id, household_id, version_id, version, subject,
                        grade_band, language, depth, question_types,
                        prompt_fragment, allowed_skills, profile_sha256,
                        created_by_user_id
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING profile_id, household_id, version_id, version,
                              subject, grade_band, language, depth,
                              question_types, prompt_fragment, allowed_skills,
                              profile_sha256, created_at
                    """,
                    (
                        profile_id,
                        version["household_id"],
                        version_id,
                        profile_version,
                        subject,
                        grade_band,
                        language,
                        depth,
                        Json(question_types),
                        prompt_fragment,
                        Json(allowed_skills),
                        profile_sha256,
                        parent_user_id,
                    ),
                )
                row = dict(await cur.fetchone())
    return row


async def get_processing_profile_for_parent(
    *, parent_user_id: str, profile_id: str
) -> dict[str, Any] | None:
    """Read one profile revision for its owning parent."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT profiles.profile_id, profiles.household_id,
                       profiles.version_id, profiles.version, profiles.subject,
                       profiles.grade_band, profiles.language, profiles.depth,
                       profiles.question_types, profiles.prompt_fragment,
                       profiles.allowed_skills, profiles.profile_sha256,
                       profiles.created_at
                FROM education_processing_profiles AS profiles
                JOIN education_textbooks AS textbooks
                  ON textbooks.household_id = profiles.household_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                WHERE profiles.profile_id = %s
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                """,
                (profile_id, parent_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_textbook_structure_for_parent(
    *, parent_user_id: str, structure_id: str
) -> dict[str, Any] | None:
    """Read one structure with its Unit and knowledge-point projection."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT structures.structure_id, structures.version_id,
                       structures.sequence, structures.status,
                       structures.schema_version, structures.processing_profile_id,
                       structures.processing_profile_sha256,
                       structures.input_manifest_sha256, structures.source_revision,
                       structures.created_at, structures.reviewed_at,
                       structures.book_asset_prefix,
                       structures.book_asset_manifest,
                       structures.validation_warnings
                FROM education_textbook_structures AS structures
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = structures.version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                WHERE structures.structure_id = %s
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                """,
                (structure_id, parent_user_id),
            )
            structure = await cur.fetchone()
            if not structure:
                return None
            result = dict(structure)
            await cur.execute(
                """
                SELECT unit_id, position, slug, title, summary, unit_type,
                       source_refs, confidence, status
                FROM education_structure_units
                WHERE structure_id = %s
                ORDER BY position
                """,
                (structure_id,),
            )
            units = [dict(row) for row in await cur.fetchall()]
            await cur.execute(
                """
                SELECT scopes.unit_id, scopes.slot, scopes.title, scopes.summary,
                       scopes.reading_skill, scopes.vocabulary_building,
                       scopes.critical_thinking, scopes.source_id,
                       scopes.line_start, scopes.line_end,
                       scopes.char_start, scopes.char_end
                FROM education_textbook_scopes AS scopes
                JOIN education_structure_units AS units
                  ON units.unit_id = scopes.unit_id
                WHERE units.structure_id = %s
                ORDER BY units.position, scopes.line_start
                """,
                (structure_id,),
            )
            scopes = [dict(row) for row in await cur.fetchall()]
            scopes_by_unit: dict[str, list[dict[str, Any]]] = {}
            for scope in scopes:
                scope["verified"] = True
                scopes_by_unit.setdefault(str(scope["unit_id"]), []).append(scope)
            await cur.execute(
                """
                SELECT knowledge_points.knowledge_point_id,
                       knowledge_points.unit_id,
                       knowledge_points.position,
                       knowledge_points.slug,
                       knowledge_points.title,
                       knowledge_points.summary,
                       knowledge_points.scope_slot,
                       knowledge_points.source_refs,
                       knowledge_points.confidence,
                       knowledge_points.status,
                       lessons.status AS lesson_status,
                       lessons.latest_revision_id AS lesson_revision_id
                FROM education_structure_knowledge_points AS knowledge_points
                JOIN education_structure_units AS units
                  ON units.unit_id = knowledge_points.unit_id
                LEFT JOIN education_kp_lessons AS lessons
                  ON lessons.knowledge_point_id =
                     knowledge_points.knowledge_point_id
                WHERE units.structure_id = %s
                ORDER BY units.position, knowledge_points.position
                """,
                (structure_id,),
            )
            knowledge_points = [dict(row) for row in await cur.fetchall()]
            by_unit: dict[str, list[dict[str, Any]]] = {}
            for knowledge_point in knowledge_points:
                by_unit.setdefault(str(knowledge_point["unit_id"]), []).append(
                    knowledge_point
                )
            for unit in units:
                unit["scopes"] = scopes_by_unit.get(str(unit["unit_id"]), [])
                unit["knowledge_points"] = by_unit.get(str(unit["unit_id"]), [])
            result["units"] = units
            if str(structure.get("schema_version") or "") in GENERIC_STRUCTURE_SCHEMAS:
                await cur.execute(
                    """
                    SELECT COUNT(*) FILTER (
                               WHERE candidate.candidate_status IN (
                                   'pending', 'accepted'
                               )
                           ) AS total,
                           COUNT(*) FILTER (
                               WHERE candidate.candidate_status = 'accepted'
                           ) AS accepted,
                           COUNT(lessons.lesson_id) FILTER (
                               WHERE candidate.candidate_status = 'accepted'
                                 AND lessons.latest_revision_id IS NOT NULL
                           ) AS generated,
                           COUNT(*) FILTER (
                               WHERE candidate.candidate_status = 'accepted'
                                 AND lessons.status = 'approved'
                                 AND lessons.latest_revision_id IS NOT NULL
                           ) AS approved
                    FROM education_structure_knowledge_points AS candidate
                    LEFT JOIN education_kp_lessons AS lessons
                      ON lessons.knowledge_point_id =
                         candidate.knowledge_point_id
                    WHERE candidate.content_structure_id = %s
                      AND candidate.origin = 'generated'
                      AND candidate.content_node_id IS NOT NULL
                    """,
                    (structure_id,),
                )
            else:
                await cur.execute(
                    """
                    SELECT COUNT(*) AS total,
                           COUNT(*) FILTER (
                               WHERE knowledge_points.status = 'accepted'
                           ) AS accepted,
                           COUNT(lessons.lesson_id) FILTER (
                               WHERE lessons.latest_revision_id IS NOT NULL
                           ) AS generated,
                           COUNT(*) FILTER (
                               WHERE lessons.status = 'approved'
                                 AND lessons.latest_revision_id IS NOT NULL
                           ) AS approved
                    FROM education_structure_units AS units
                    JOIN education_structure_knowledge_points AS knowledge_points
                      ON knowledge_points.unit_id = units.unit_id
                    LEFT JOIN education_kp_lessons AS lessons
                      ON lessons.knowledge_point_id =
                         knowledge_points.knowledge_point_id
                    WHERE units.structure_id = %s
                    """,
                    (structure_id,),
                )
            result["lesson_summary"] = dict(await cur.fetchone())
            await cur.execute(
                """
                SELECT jobs.generation_job_id, jobs.status, jobs.attempt_count,
                       jobs.error_message, jobs.created_at, jobs.updated_at,
                       attempts.root_run_id, attempts.started_at,
                       attempts.heartbeat_at
                FROM education_generation_jobs AS jobs
                LEFT JOIN education_generation_attempts AS attempts
                  ON attempts.attempt_id = jobs.latest_attempt_id
                WHERE jobs.structure_id = %s
                ORDER BY jobs.created_at DESC
                LIMIT 1
                """,
                (structure_id,),
            )
            latest_generation_job = await cur.fetchone()
            result["latest_generation_job_id"] = (
                latest_generation_job["generation_job_id"]
                if latest_generation_job
                else None
            )
            result["latest_generation_job_status"] = (
                latest_generation_job["status"] if latest_generation_job else None
            )
            result["latest_generation_job_created_at"] = (
                latest_generation_job["created_at"] if latest_generation_job else None
            )
            result["latest_generation_job_updated_at"] = (
                latest_generation_job["updated_at"] if latest_generation_job else None
            )
            result["latest_generation_job"] = (
                dict(latest_generation_job) if latest_generation_job else None
            )
    return result


async def list_knowledge_point_candidates_for_parent(
    *,
    parent_user_id: str,
    structure_id: str,
) -> dict[str, Any] | None:
    """Return one owned generic content tree with generated candidates."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT structures.structure_id, structures.version_id
                FROM education_textbook_structures AS structures
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = structures.version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                WHERE structures.structure_id = %s
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                """,
                (structure_id, parent_user_id),
            )
            structure = await cur.fetchone()
            if not structure:
                return None

            await cur.execute(
                """
                WITH RECURSIVE ordered_nodes AS (
                    SELECT nodes.node_id, nodes.structure_id,
                           nodes.parent_node_id, nodes.node_key,
                           nodes.node_type, nodes.label, nodes.position,
                           nodes.slug, nodes.title, nodes.summary,
                           nodes.source_refs,
                           ARRAY[nodes.position]::INTEGER[] AS sort_path
                    FROM education_content_nodes AS nodes
                    WHERE nodes.structure_id = %s
                      AND nodes.parent_node_id IS NULL
                    UNION ALL
                    SELECT child.node_id, child.structure_id,
                           child.parent_node_id, child.node_key,
                           child.node_type, child.label, child.position,
                           child.slug, child.title, child.summary,
                           child.source_refs,
                           parent.sort_path || child.position
                    FROM education_content_nodes AS child
                    JOIN ordered_nodes AS parent
                      ON parent.node_id = child.parent_node_id
                    WHERE child.structure_id = %s
                )
                SELECT node_id, structure_id, parent_node_id, node_key,
                       node_type, label, position, slug, title, summary,
                       source_refs
                FROM ordered_nodes
                ORDER BY sort_path, node_key
                """,
                (structure_id, structure_id),
            )
            nodes = [dict(row) for row in await cur.fetchall()]

            await cur.execute(
                """
                SELECT candidate.knowledge_point_id,
                       candidate.content_structure_id,
                       candidate.content_node_id,
                       candidate.candidate_key,
                       candidate.point_type,
                       candidate.origin,
                       candidate.candidate_status,
                       candidate.position,
                       candidate.slug,
                       candidate.title,
                       candidate.summary,
                       candidate.source_refs,
                       candidate.confidence,
                       candidate.status,
                       candidate.created_at
                FROM education_structure_knowledge_points AS candidate
                WHERE candidate.content_structure_id = %s
                  AND candidate.origin = 'generated'
                  AND candidate.content_node_id IS NOT NULL
                ORDER BY candidate.position, candidate.created_at,
                         candidate.knowledge_point_id
                """,
                (structure_id,),
            )
            candidates_by_node: dict[str, list[dict[str, Any]]] = {}
            for row in await cur.fetchall():
                candidate = dict(row)
                candidates_by_node.setdefault(
                    str(candidate["content_node_id"]), []
                ).append(candidate)
            for node in nodes:
                node["candidates"] = candidates_by_node.get(str(node["node_id"]), [])

    return {
        "structure_id": structure["structure_id"],
        "version_id": structure["version_id"],
        "nodes": nodes,
    }


async def _lock_owned_generated_candidates(
    cur: Any,
    *,
    parent_user_id: str,
    candidate_ids: list[str],
) -> list[dict[str, Any]]:
    """Lock generated candidates that belong to one parent's household."""
    await cur.execute(
        """
        SELECT candidate.knowledge_point_id,
               candidate.content_structure_id,
               candidate.content_node_id,
               candidate.candidate_key,
               candidate.point_type,
               candidate.origin,
               candidate.candidate_status,
               candidate.position,
               candidate.slug,
               candidate.title,
               candidate.summary,
               candidate.source_refs,
               candidate.confidence,
               candidate.status,
               candidate.created_at
        FROM education_structure_knowledge_points AS candidate
        JOIN education_textbook_structures AS structures
          ON structures.structure_id = candidate.content_structure_id
        JOIN education_textbook_versions AS versions
          ON versions.version_id = structures.version_id
        JOIN education_textbooks AS textbooks
          ON textbooks.textbook_id = versions.textbook_id
        JOIN education_memberships AS memberships
          ON memberships.household_id = textbooks.household_id
        WHERE candidate.knowledge_point_id = ANY(%s::uuid[])
          AND candidate.origin = 'generated'
          AND candidate.content_structure_id IS NOT NULL
          AND candidate.content_node_id IS NOT NULL
          AND memberships.user_id = %s
          AND memberships.role = 'parent'
        ORDER BY candidate.knowledge_point_id
        FOR UPDATE OF candidate
        """,
        (candidate_ids, parent_user_id),
    )
    rows = [dict(row) for row in await cur.fetchall()]
    if len(rows) != len(candidate_ids):
        raise KnowledgePointCandidateNotFoundError(
            "Generated knowledge-point candidate not found"
        )
    return rows


async def _lock_owned_candidate_content_nodes(
    cur: Any,
    *,
    parent_user_id: str,
    candidate_ids: list[str],
) -> list[str]:
    """Lock content-node rows before any candidate mutation."""
    await cur.execute(
        """
        SELECT nodes.node_id
        FROM education_content_nodes AS nodes
        JOIN education_textbook_structures AS structures
          ON structures.structure_id = nodes.structure_id
        JOIN education_textbook_versions AS versions
          ON versions.version_id = structures.version_id
        JOIN education_textbooks AS textbooks
          ON textbooks.textbook_id = versions.textbook_id
        JOIN education_memberships AS memberships
          ON memberships.household_id = textbooks.household_id
        WHERE nodes.node_id IN (
            SELECT candidate.content_node_id
            FROM education_structure_knowledge_points AS candidate
            WHERE candidate.knowledge_point_id = ANY(%s::uuid[])
              AND candidate.origin = 'generated'
              AND candidate.content_node_id IS NOT NULL
        )
          AND memberships.user_id = %s
          AND memberships.role = 'parent'
        ORDER BY nodes.node_id
        FOR UPDATE OF nodes
        """,
        (candidate_ids, parent_user_id),
    )
    return [str(row["node_id"]) for row in await cur.fetchall()]


def _candidate_by_id(
    rows: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    return {str(row["knowledge_point_id"]): row for row in rows}


async def update_knowledge_point_candidate_for_parent(
    *,
    parent_user_id: str,
    candidate_id: str,
    title: str | None,
    summary: str | None,
    point_type: str | None,
) -> dict[str, Any] | None:
    """Update only descriptive fields on one generated candidate."""
    if title is None and summary is None and point_type is None:
        raise TextbookQueueValidationError(
            "At least one candidate field must be updated"
        )
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT candidate.knowledge_point_id
                    FROM education_structure_knowledge_points AS candidate
                    JOIN education_textbook_structures AS structures
                      ON structures.structure_id = candidate.content_structure_id
                    JOIN education_textbook_versions AS versions
                      ON versions.version_id = structures.version_id
                    JOIN education_textbooks AS textbooks
                      ON textbooks.textbook_id = versions.textbook_id
                    JOIN education_memberships AS memberships
                      ON memberships.household_id = textbooks.household_id
                    WHERE candidate.knowledge_point_id = %s
                      AND candidate.origin = 'generated'
                      AND candidate.content_structure_id IS NOT NULL
                      AND candidate.content_node_id IS NOT NULL
                      AND memberships.user_id = %s
                      AND memberships.role = 'parent'
                    FOR UPDATE OF candidate
                    """,
                    (candidate_id, parent_user_id),
                )
                if not await cur.fetchone():
                    return None
                await cur.execute(
                    """
                    UPDATE education_structure_knowledge_points
                    SET title = COALESCE(%s, title),
                        summary = COALESCE(%s, summary),
                        point_type = COALESCE(%s, point_type)
                    WHERE knowledge_point_id = %s
                    RETURNING knowledge_point_id, content_structure_id,
                              content_node_id, candidate_key, point_type,
                              origin, candidate_status, position, slug,
                              title, summary, source_refs, confidence,
                              status, created_at
                    """,
                    (title, summary, point_type, candidate_id),
                )
                row = await cur.fetchone()
    return dict(row) if row else None


async def _transition_generated_candidates(
    *,
    parent_user_id: str,
    candidate_ids: list[str],
    target_status: str,
    target_legacy_status: str,
) -> list[dict[str, Any]]:
    """Idempotently apply accept or reject to an ordered candidate set."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                rows = await _lock_owned_generated_candidates(
                    cur,
                    parent_user_id=parent_user_id,
                    candidate_ids=candidate_ids,
                )
                by_id = _candidate_by_id(rows)
                for candidate_id in candidate_ids:
                    row = by_id[candidate_id]
                    current = str(row["candidate_status"])
                    if current == target_status:
                        continue
                    if current != "pending":
                        raise KnowledgePointCandidateTransitionError(
                            "Generated knowledge-point candidate transition "
                            f"from {current} to {target_status} is not allowed"
                        )
                    await cur.execute(
                        """
                        UPDATE education_structure_knowledge_points
                        SET candidate_status = %s, status = %s
                        WHERE knowledge_point_id = %s
                        """,
                        (target_status, target_legacy_status, candidate_id),
                    )
                    row["candidate_status"] = target_status
                    row["status"] = target_legacy_status
    return [by_id[candidate_id] for candidate_id in candidate_ids]


async def accept_knowledge_point_candidates_for_parent(
    *,
    parent_user_id: str,
    candidate_ids: list[str],
) -> list[dict[str, Any]]:
    """Accept pending generated candidates; repeated accepts are idempotent."""
    return await _transition_generated_candidates(
        parent_user_id=parent_user_id,
        candidate_ids=candidate_ids,
        target_status="accepted",
        target_legacy_status="accepted",
    )


async def reject_knowledge_point_candidates_for_parent(
    *,
    parent_user_id: str,
    candidate_ids: list[str],
) -> list[dict[str, Any]]:
    """Reject pending generated candidates; repeated rejects are idempotent."""
    return await _transition_generated_candidates(
        parent_user_id=parent_user_id,
        candidate_ids=candidate_ids,
        target_status="rejected",
        target_legacy_status="blocked",
    )


def _combined_candidate_source_refs(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    combined: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        refs = row.get("source_refs")
        if not isinstance(refs, list):
            continue
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            key = json.dumps(
                ref,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            if key in seen:
                continue
            seen.add(key)
            combined.append(ref)
    return combined


async def merge_knowledge_point_candidates_for_parent(
    *,
    parent_user_id: str,
    source_ids: list[str],
    target_id: str | None,
    title: str | None,
    summary: str | None,
    point_type: str | None,
    accept: bool,
) -> list[dict[str, Any]]:
    """Merge pending candidates under one content node in one transaction."""
    if target_id is None and accept:
        raise KnowledgePointCandidateTransitionError(
            "A new merged candidate must remain pending"
        )
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await _lock_owned_candidate_content_nodes(
                    cur,
                    parent_user_id=parent_user_id,
                    candidate_ids=source_ids,
                )
                rows = await _lock_owned_generated_candidates(
                    cur,
                    parent_user_id=parent_user_id,
                    candidate_ids=source_ids,
                )
                if any(str(row["candidate_status"]) != "pending" for row in rows):
                    raise KnowledgePointCandidateTransitionError(
                        "Only pending generated candidates can be merged"
                    )
                structure_ids = {str(row["content_structure_id"]) for row in rows}
                node_ids = {str(row["content_node_id"]) for row in rows}
                if len(structure_ids) != 1 or len(node_ids) != 1:
                    raise KnowledgePointCandidateTransitionError(
                        "Candidates can only be merged within one content node"
                    )
                by_id = _candidate_by_id(rows)
                if target_id is not None and target_id not in by_id:
                    raise KnowledgePointCandidateTransitionError(
                        "Merge target must be one of the source candidates"
                    )
                source_refs = _combined_candidate_source_refs(rows)
                final_status = "accepted" if accept else "pending"
                legacy_status = "accepted" if accept else "review"

                if target_id is None:
                    await cur.execute(
                        """
                        SELECT COALESCE(MAX(position), 0) + 1 AS position
                        FROM education_structure_knowledge_points
                        WHERE content_node_id = %s
                        """,
                        (next(iter(node_ids)),),
                    )
                    position = int((await cur.fetchone())["position"])
                    candidate_key = f"merge-{uuid4().hex}"
                    await cur.execute(
                        """
                        INSERT INTO education_structure_knowledge_points (
                            knowledge_point_id, unit_id, content_structure_id,
                            content_node_id, candidate_key, point_type, origin,
                            candidate_status, position, slug, title, summary,
                            source_refs, confidence, status
                        ) VALUES (
                            %s, NULL, %s, %s, %s, %s, 'generated', %s, %s,
                            %s, %s, %s, %s, %s, %s
                        )
                        RETURNING knowledge_point_id, content_structure_id,
                                  content_node_id, candidate_key, point_type,
                                  origin, candidate_status, position, slug,
                                  title, summary, source_refs, confidence,
                                  status, created_at
                        """,
                        (
                            str(uuid4()),
                            next(iter(structure_ids)),
                            next(iter(node_ids)),
                            candidate_key,
                            point_type,
                            final_status,
                            position,
                            _candidate_slug(candidate_key),
                            title,
                            summary or "",
                            Json(source_refs),
                            max(float(row["confidence"]) for row in rows),
                            legacy_status,
                        ),
                    )
                    target = dict(await cur.fetchone())
                    target_id = str(target["knowledge_point_id"])
                else:
                    target = by_id[target_id]
                    await cur.execute(
                        """
                        UPDATE education_structure_knowledge_points
                        SET title = COALESCE(%s, title),
                            summary = COALESCE(%s, summary),
                            point_type = COALESCE(%s, point_type),
                            source_refs = %s,
                            candidate_status = %s,
                            status = %s
                        WHERE knowledge_point_id = %s
                        RETURNING knowledge_point_id, content_structure_id,
                                  content_node_id, candidate_key, point_type,
                                  origin, candidate_status, position, slug,
                                  title, summary, source_refs, confidence,
                                  status, created_at
                        """,
                        (
                            title,
                            summary,
                            point_type,
                            Json(source_refs),
                            final_status,
                            legacy_status,
                            target_id,
                        ),
                    )
                    target = dict(await cur.fetchone())

                merged_ids = [
                    candidate_id
                    for candidate_id in source_ids
                    if candidate_id != target_id
                ]
                if merged_ids:
                    await cur.execute(
                        """
                        UPDATE education_structure_knowledge_points
                        SET candidate_status = 'merged', status = 'blocked'
                        WHERE knowledge_point_id = ANY(%s::uuid[])
                        """,
                        (merged_ids,),
                    )
                for candidate_id in merged_ids:
                    by_id[candidate_id]["candidate_status"] = "merged"
                    by_id[candidate_id]["status"] = "blocked"
    return [target, *[by_id[candidate_id] for candidate_id in merged_ids]]


async def split_knowledge_point_candidate_for_parent(
    *,
    parent_user_id: str,
    candidate_id: str,
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Replace one pending candidate with two or more pending candidates."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await _lock_owned_candidate_content_nodes(
                    cur,
                    parent_user_id=parent_user_id,
                    candidate_ids=[candidate_id],
                )
                rows = await _lock_owned_generated_candidates(
                    cur,
                    parent_user_id=parent_user_id,
                    candidate_ids=[candidate_id],
                )
                source = rows[0]
                if source["candidate_status"] != "pending":
                    raise KnowledgePointCandidateTransitionError(
                        "Only a pending generated candidate can be split"
                    )
                await cur.execute(
                    """
                    SELECT COALESCE(MAX(position), 0) + 1 AS position
                    FROM education_structure_knowledge_points
                    WHERE content_node_id = %s
                    """,
                    (source["content_node_id"],),
                )
                next_position = int((await cur.fetchone())["position"])
                await cur.execute(
                    """
                    UPDATE education_structure_knowledge_points
                    SET candidate_status = 'split', status = 'blocked'
                    WHERE knowledge_point_id = %s
                    """,
                    (candidate_id,),
                )
                source["candidate_status"] = "split"
                source["status"] = "blocked"

                created: list[dict[str, Any]] = []
                for index, item in enumerate(items):
                    candidate_key = _split_candidate_key(
                        str(source["candidate_key"]),
                        index,
                    )
                    await cur.execute(
                        """
                        INSERT INTO education_structure_knowledge_points (
                            knowledge_point_id, unit_id, content_structure_id,
                            content_node_id, candidate_key, point_type, origin,
                            candidate_status, position, slug, title, summary,
                            source_refs, confidence, status
                        ) VALUES (
                            %s, NULL, %s, %s, %s, %s, 'generated', 'pending',
                            %s, %s, %s, %s, %s, %s, 'review'
                        )
                        RETURNING knowledge_point_id, content_structure_id,
                                  content_node_id, candidate_key, point_type,
                                  origin, candidate_status, position, slug,
                                  title, summary, source_refs, confidence,
                                  status, created_at
                        """,
                        (
                            str(uuid4()),
                            source["content_structure_id"],
                            source["content_node_id"],
                            candidate_key,
                            item["point_type"],
                            next_position + index,
                            _candidate_slug(candidate_key),
                            item["title"],
                            item.get("summary") or "",
                            Json(source.get("source_refs") or []),
                            source["confidence"],
                        ),
                    )
                    created.append(dict(await cur.fetchone()))
    return [source, *created]


async def get_latest_textbook_structure_for_parent(
    *, parent_user_id: str, content_version_id: str
) -> dict[str, Any] | None:
    """Return the newest structure for one version, if the parent owns it.

    A structure still being generated is returned as ``queued``/``running``
    so callers can render live progress before the reviewable Units exist.
    """
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT structures.structure_id, structures.status,
                       jobs.status AS job_status,
                       jobs.generation_job_id
                FROM education_textbook_structures AS structures
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = structures.version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                LEFT JOIN LATERAL (
                    SELECT generation_job_id, status
                    FROM education_generation_jobs
                    WHERE structure_id = structures.structure_id
                      AND scope = 'structure'
                    ORDER BY created_at DESC
                    LIMIT 1
                ) AS jobs ON TRUE
                WHERE structures.version_id = %s
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                ORDER BY structures.sequence DESC
                LIMIT 1
                """,
                (content_version_id, parent_user_id),
            )
            row = await cur.fetchone()
    if not row:
        return None
    structure = await get_textbook_structure_for_parent(
        parent_user_id=parent_user_id,
        structure_id=str(row["structure_id"]),
    )
    if not structure:
        return None
    if row.get("job_status") in ("queued", "preparing", "running", "validating"):
        structure["latest_generation_job_id"] = row.get("generation_job_id")
        if row["status"] in ("queued", "running"):
            structure["status"] = row["status"]
    return structure


async def get_generation_job_for_parent(
    *, parent_user_id: str, generation_job_id: str
) -> dict[str, Any] | None:
    """Read one generation job with the frozen context required to dispatch it."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.generation_job_id, jobs.version_id, jobs.scope,
                       jobs.structure_id, jobs.knowledge_point_id, jobs.status,
                       jobs.attempt_count, jobs.latest_attempt_id,
                       jobs.auto_grading, jobs.pause_after_chapter_analysis,
                       jobs.checkpoint_bundle_prefix,
                       jobs.processing_brief, jobs.request_id,
                       jobs.processing_profile_sha256, jobs.error_code,
                       jobs.error_message, jobs.created_at, jobs.updated_at,
                       attempts.root_run_id, attempts.started_at,
                       attempts.heartbeat_at,
                       versions.sequence AS content_version_sequence,
                       textbooks.textbook_id, textbooks.household_id,
                       textbooks.slug, textbooks.title,
                       knowledge_points.unit_id,
                       knowledge_points.position AS knowledge_point_position,
                       knowledge_points.slug AS knowledge_point_slug,
                       knowledge_points.title AS knowledge_point_title,
                       knowledge_points.summary AS knowledge_point_summary,
                       knowledge_points.scope_slot AS knowledge_point_scope_slot,
                       knowledge_points.source_refs AS knowledge_point_source_refs,
                       units.unit_id,
                       units.position AS unit_position,
                       units.slug AS unit_slug,
                       units.title AS unit_title,
                       structures.sequence AS structure_sequence,
                       structures.status AS structure_status,
                       structures.bundle_prefix AS structure_bundle_prefix,
                       structures.book_asset_prefix,
                       structures.book_asset_manifest,
                       profiles.profile_id AS processing_profile_id,
                       profiles.subject AS processing_profile_subject,
                       profiles.grade_band AS processing_profile_grade_band,
                       profiles.language AS processing_profile_language,
                       profiles.depth AS processing_profile_depth,
                       profiles.question_types AS processing_profile_question_types,
                       profiles.prompt_fragment AS processing_profile_prompt_fragment,
                       profiles.allowed_skills AS processing_profile_allowed_skills
                FROM education_generation_jobs AS jobs
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = jobs.version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                LEFT JOIN education_structure_knowledge_points AS knowledge_points
                  ON knowledge_points.knowledge_point_id =
                     jobs.knowledge_point_id
                LEFT JOIN education_structure_units AS units
                  ON units.unit_id = knowledge_points.unit_id
                LEFT JOIN education_textbook_structures AS structures
                  ON structures.structure_id =
                     COALESCE(jobs.structure_id, units.structure_id)
                LEFT JOIN education_processing_profiles AS profiles
                  ON profiles.profile_id = structures.processing_profile_id
                LEFT JOIN education_generation_attempts AS attempts
                  ON attempts.attempt_id = jobs.latest_attempt_id
                WHERE jobs.generation_job_id = %s
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                """,
                (generation_job_id, parent_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def persist_generation_progress_event(
    *,
    generation_job_id: str,
    attempt_id: str,
    run_id: str | None,
    sequence: int,
    event: Mapping[str, Any],
) -> ProgressEventPersistenceResult:
    """Persist one collector event idempotently under its attempt ownership."""
    metadata = event.get("metadata")
    if metadata is None:
        metadata = {}
    if not isinstance(metadata, Mapping):
        raise ValueError("generation progress metadata must be an object")
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT generation_job_id, attempt_id, root_run_id, status
                    FROM education_generation_attempts
                    WHERE generation_job_id = %s
                      AND attempt_id = %s
                      AND status IN ('preparing', 'running')
                      AND (%s::uuid IS NULL OR root_run_id = %s::uuid)
                    FOR UPDATE
                    """,
                    (generation_job_id, attempt_id, run_id, run_id),
                )
                if not await cur.fetchone():
                    return ProgressEventPersistenceResult(
                        outcome=ProgressEventPersistenceOutcome.REJECTED
                    )

                await cur.execute(
                    """
                    SELECT event_id, generation_job_id, attempt_id, run_id,
                           sequence, event_key, stage, substage, status, label,
                           detail, node_key, current_value, total_value,
                           metadata, created_at
                    FROM education_generation_progress_events
                    WHERE generation_job_id = %s
                      AND attempt_id = %s
                      AND sequence = %s
                    FOR UPDATE
                    """,
                    (generation_job_id, attempt_id, sequence),
                )
                existing = await cur.fetchone()
                if existing is not None:
                    existing_row = dict(existing)
                    if not _progress_event_matches(existing_row, event):
                        return ProgressEventPersistenceResult(
                            outcome=ProgressEventPersistenceOutcome.REJECTED
                        )
                    return ProgressEventPersistenceResult(
                        outcome=ProgressEventPersistenceOutcome.ALREADY_EXISTS,
                        event=existing_row,
                    )

                await cur.execute(
                    """
                    INSERT INTO education_generation_progress_events (
                        generation_job_id, attempt_id, run_id, sequence,
                        event_key, stage, substage, status, label, detail,
                        node_key, current_value, total_value, metadata
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    RETURNING event_id, generation_job_id, attempt_id, run_id,
                              sequence, event_key, stage, substage, status,
                              label, detail, node_key, current_value,
                              total_value, metadata, created_at
                    """,
                    (
                        generation_job_id,
                        attempt_id,
                        run_id,
                        sequence,
                        str(event["event_key"]),
                        str(event["stage"]),
                        event.get("substage"),
                        str(event["status"]),
                        str(event["label"]),
                        event.get("detail"),
                        event.get("node_key"),
                        event.get("current_value"),
                        event.get("total_value"),
                        Json(dict(metadata)),
                    ),
                )
                inserted = await cur.fetchone()
                if inserted is None:
                    return ProgressEventPersistenceResult(
                        outcome=ProgressEventPersistenceOutcome.REJECTED
                    )
                return ProgressEventPersistenceResult(
                    outcome=ProgressEventPersistenceOutcome.INSERTED,
                    event=dict(inserted),
                )


async def list_generation_progress_events(
    *,
    generation_job_id: str,
    attempt_id: str | None = None,
) -> list[dict[str, Any]]:
    """Read a bounded progress window with latest/terminal stage context."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                WITH ordered_events AS (
                    SELECT progress.event_id, progress.generation_job_id,
                           progress.attempt_id, progress.run_id,
                           progress.sequence, progress.event_key,
                           progress.stage, progress.substage,
                           progress.status, progress.label, progress.detail,
                           progress.node_key, progress.current_value,
                           progress.total_value, progress.metadata,
                           progress.created_at,
                           attempts.started_at AS attempt_started_at,
                           ROW_NUMBER() OVER (
                               ORDER BY attempts.started_at,
                                        progress.attempt_id,
                                        progress.sequence
                           ) AS event_order,
                           ROW_NUMBER() OVER (
                               PARTITION BY progress.stage
                               ORDER BY attempts.started_at DESC,
                                        progress.attempt_id DESC,
                                        progress.sequence DESC
                           ) AS stage_latest_order,
                           ROW_NUMBER() OVER (
                               PARTITION BY progress.stage
                               ORDER BY CASE
                                   WHEN progress.status IN (
                                       'completed', 'failed', 'skipped'
                                   ) THEN 0
                                   ELSE 1
                               END,
                               attempts.started_at DESC,
                               progress.attempt_id DESC,
                               progress.sequence DESC
                           ) AS stage_terminal_order,
                           ROW_NUMBER() OVER (
                               PARTITION BY progress.stage
                               ORDER BY CASE
                                   WHEN progress.current_value IS NOT NULL
                                     OR progress.total_value IS NOT NULL
                                   THEN 0
                                   ELSE 1
                               END,
                               attempts.started_at DESC,
                               progress.attempt_id DESC,
                               progress.sequence DESC
                           ) AS stage_counted_order,
                           COUNT(*) OVER () AS total_event_count
                    FROM education_generation_progress_events AS progress
                    JOIN education_generation_attempts AS attempts
                      ON attempts.generation_job_id =
                         progress.generation_job_id
                     AND attempts.attempt_id = progress.attempt_id
                    WHERE progress.generation_job_id = %s
                      AND (
                          %s::uuid IS NULL
                          OR progress.attempt_id = %s::uuid
                      )
                ),
                bounded_events AS (
                    SELECT *
                    FROM ordered_events
                    WHERE event_order > GREATEST(total_event_count - %s, 0)
                       OR stage_latest_order = 1
                       OR (
                           stage_terminal_order = 1
                           AND status IN ('completed', 'failed', 'skipped')
                       )
                       OR (
                           stage_counted_order = 1
                           AND (
                               current_value IS NOT NULL
                               OR total_value IS NOT NULL
                           )
                       )
                )
                SELECT event_id, generation_job_id, attempt_id, run_id,
                       sequence, event_key, stage, substage, status, label,
                       detail, node_key, current_value, total_value,
                       metadata, created_at, attempt_started_at,
                       total_event_count,
                       total_event_count > %s AS progress_truncated
                FROM bounded_events
                ORDER BY event_order
                """,
                (
                    generation_job_id,
                    attempt_id,
                    attempt_id,
                    MAX_GENERATION_PROGRESS_EVENTS,
                    MAX_GENERATION_PROGRESS_EVENTS,
                ),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_run_id_for_generation_job(
    *, parent_user_id: str, generation_job_id: str
) -> dict[str, Any] | None:
    """Resolve a parent-owned generation job to its current run id."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.generation_job_id, jobs.status,
                       jobs.latest_attempt_id, attempts.root_run_id
                FROM education_generation_jobs AS jobs
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = jobs.version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                LEFT JOIN education_generation_attempts AS attempts
                  ON attempts.attempt_id = jobs.latest_attempt_id
                WHERE jobs.generation_job_id = %s
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                """,
                (generation_job_id, parent_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_run_sse_events(*, run_id: str) -> list[Any]:
    """Read one run's persisted SSE event blob."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT sse_events
                FROM conversation_responses
                WHERE conversation_response_id = %s
                """,
                (run_id,),
            )
            row = await cur.fetchone()
    if not row:
        return []
    events = row.get("sse_events")
    return list(events) if isinstance(events, list) else []


async def get_knowledge_point_for_parent(
    *, parent_user_id: str, knowledge_point_id: str
) -> dict[str, Any] | None:
    """Read one accepted knowledge point with its Unit and structure context."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT knowledge_points.knowledge_point_id,
                       knowledge_points.position AS knowledge_point_position,
                       knowledge_points.slug AS knowledge_point_slug,
                       knowledge_points.title AS knowledge_point_title,
                       knowledge_points.summary AS knowledge_point_summary,
                       knowledge_points.scope_slot,
                       knowledge_points.source_refs AS knowledge_point_source_refs,
                       units.unit_id,
                       units.position AS unit_position,
                       units.slug AS unit_slug,
                       units.title AS unit_title,
                       structures.structure_id,
                       structures.sequence AS structure_sequence,
                       structures.status AS structure_status,
                       versions.version_id,
                       versions.sequence AS content_version_sequence,
                       textbooks.textbook_id, textbooks.household_id,
                       textbooks.slug, textbooks.title
                FROM education_structure_knowledge_points AS knowledge_points
                JOIN education_structure_units AS units
                  ON units.unit_id = knowledge_points.unit_id
                JOIN education_textbook_structures AS structures
                  ON structures.structure_id = units.structure_id
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = structures.version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                WHERE knowledge_points.knowledge_point_id = %s
                  AND knowledge_points.status = 'accepted'
                  AND units.status = 'accepted'
                  AND structures.status = 'accepted'
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                """,
                (knowledge_point_id, parent_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_textbook_scopes_for_unit(
    *, parent_user_id: str, unit_id: str
) -> list[dict[str, Any]]:
    """Return the authoritative reading scopes for one reviewable unit."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT scopes.scope_id, scopes.slot, scopes.title, scopes.summary,
                       scopes.reading_skill, scopes.vocabulary_building,
                       scopes.critical_thinking, scopes.source_id,
                       scopes.line_start, scopes.line_end,
                       scopes.char_start, scopes.char_end
                FROM education_textbook_scopes AS scopes
                JOIN education_structure_units AS units
                  ON units.unit_id = scopes.unit_id
                JOIN education_textbook_structures AS structures
                  ON structures.structure_id = units.structure_id
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = structures.version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                WHERE scopes.unit_id = %s
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                ORDER BY scopes.line_start
                """,
                (unit_id, parent_user_id),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_knowledge_point_source_preview_for_parent(
    *, parent_user_id: str, knowledge_point_id: str
) -> dict[str, Any] | None:
    """Read one reviewable knowledge point without requiring accepted status."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT knowledge_points.knowledge_point_id,
                       knowledge_points.title AS knowledge_point_title,
                       knowledge_points.source_refs AS knowledge_point_source_refs,
                       units.unit_id,
                       units.title AS unit_title,
                       versions.version_id,
                       structures.structure_id
                FROM education_structure_knowledge_points AS knowledge_points
                JOIN education_structure_units AS units
                  ON units.unit_id = knowledge_points.unit_id
                JOIN education_textbook_structures AS structures
                  ON structures.structure_id = units.structure_id
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = structures.version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                WHERE knowledge_points.knowledge_point_id = %s
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                """,
                (knowledge_point_id, parent_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def replace_structure_contents(
    *,
    structure_id: str,
    units: list[dict[str, Any]],
    warnings: list[str] | None = None,
    scopes: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Replace a mutable structure projection with service-owned IDs."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT structure_id
                    FROM education_textbook_structures
                    WHERE structure_id = %s
                      AND status IN ('queued', 'running', 'failed', 'review')
                    FOR UPDATE
                    """,
                    (structure_id,),
                )
                if not await cur.fetchone():
                    raise ValueError("Textbook structure is not mutable")
                if warnings is not None:
                    await cur.execute(
                        """
                        UPDATE education_textbook_structures
                        SET validation_warnings = %s
                        WHERE structure_id = %s
                        """,
                        (Json(warnings), structure_id),
                    )
                await cur.execute(
                    """
                    SELECT units.unit_id, units.slug AS unit_slug,
                           knowledge_points.knowledge_point_id,
                           knowledge_points.slug AS knowledge_point_slug
                    FROM education_structure_units AS units
                    LEFT JOIN education_structure_knowledge_points AS knowledge_points
                      ON knowledge_points.unit_id = units.unit_id
                    WHERE units.structure_id = %s
                    """,
                    (structure_id,),
                )
                existing_rows = await cur.fetchall()
                existing_unit_ids = {
                    str(row["unit_slug"]): str(row["unit_id"]) for row in existing_rows
                }
                existing_knowledge_point_ids = {
                    (str(row["unit_id"]), str(row["knowledge_point_slug"])): str(
                        row["knowledge_point_id"]
                    )
                    for row in existing_rows
                    if row.get("knowledge_point_id") is not None
                    and row.get("knowledge_point_slug") is not None
                }
                preserved_scopes: dict[str, list[dict[str, Any]]] = {}
                if scopes is None:
                    await cur.execute(
                        """
                        SELECT scopes.unit_id, scopes.slot, scopes.title,
                               scopes.summary, scopes.reading_skill,
                               scopes.vocabulary_building,
                               scopes.critical_thinking, scopes.source_id,
                               scopes.line_start, scopes.line_end,
                               scopes.char_start, scopes.char_end
                        FROM education_textbook_scopes AS scopes
                        JOIN education_structure_units AS units
                          ON units.unit_id = scopes.unit_id
                        WHERE units.structure_id = %s
                        ORDER BY units.position, scopes.line_start
                        """,
                        (structure_id,),
                    )
                    for row in await cur.fetchall():
                        scope = dict(row)
                        if "slot" not in scope or "unit_id" not in scope:
                            continue
                        preserved_scopes.setdefault(str(scope["unit_id"]), []).append(
                            scope
                        )
                await cur.execute(
                    """
                    DELETE FROM education_structure_knowledge_points
                    WHERE unit_id IN (
                        SELECT unit_id
                        FROM education_structure_units
                        WHERE structure_id = %s
                    )
                    """,
                    (structure_id,),
                )
                await cur.execute(
                    """
                    DELETE FROM education_structure_units
                    WHERE structure_id = %s
                    """,
                    (structure_id,),
                )
                if scopes is not None:
                    await cur.execute(
                        """
                        DELETE FROM education_textbook_scopes
                        WHERE structure_id = %s
                        """,
                        (structure_id,),
                    )
                stored_units: list[dict[str, Any]] = []
                for unit_index, unit in enumerate(units):
                    unit_id = existing_unit_ids.get(str(unit["slug"]), str(uuid4()))
                    await cur.execute(
                        """
                        INSERT INTO education_structure_units (
                            unit_id, structure_id, position, slug, title, summary,
                            unit_type, source_refs, confidence, status
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING unit_id
                        """,
                        (
                            unit_id,
                            structure_id,
                            unit["position"],
                            unit["slug"],
                            unit["title"],
                            unit.get("summary", ""),
                            unit["unit_type"],
                            Json(unit.get("source_refs", [])),
                            unit["confidence"],
                            unit.get("status", "review"),
                        ),
                    )
                    await cur.fetchone()
                    stored_unit = {
                        **unit,
                        "unit_id": unit_id,
                        "knowledge_points": [],
                    }
                    for knowledge_point in unit.get("knowledge_points", []):
                        knowledge_point_id = existing_knowledge_point_ids.get(
                            (unit_id, str(knowledge_point["slug"])),
                            str(uuid4()),
                        )
                        await cur.execute(
                            """
                            INSERT INTO education_structure_knowledge_points (
                                    knowledge_point_id, unit_id, position, slug, title,
                                    summary, scope_slot, source_refs, confidence, status
                                ) VALUES (
                                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                                )
                                RETURNING knowledge_point_id
                                """,
                            (
                                knowledge_point_id,
                                unit_id,
                                knowledge_point["position"],
                                knowledge_point["slug"],
                                knowledge_point["title"],
                                knowledge_point.get("summary", ""),
                                knowledge_point.get("scope_slot"),
                                Json(knowledge_point.get("source_refs", [])),
                                knowledge_point["confidence"],
                                knowledge_point.get("status", "review"),
                            ),
                        )
                        await cur.fetchone()
                        stored_unit["knowledge_points"].append(
                            {
                                **knowledge_point,
                                "knowledge_point_id": knowledge_point_id,
                                "unit_id": unit_id,
                            }
                        )
                    stored_units.append(stored_unit)
                    unit_scopes: list[Mapping[str, Any]]
                    if scopes is not None:
                        unit_scopes = [
                            scope
                            for scope in scopes
                            if scope.get("unit_index") == unit_index
                        ]
                    else:
                        unit_scopes = preserved_scopes.get(unit_id, [])
                    for scope in unit_scopes:
                        await cur.execute(
                            """
                            INSERT INTO education_textbook_scopes (
                                scope_id, structure_id, unit_id, slot, title,
                                summary, reading_skill, vocabulary_building,
                                critical_thinking, source_id, line_start,
                                line_end, char_start, char_end
                            ) VALUES (
                                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                                %s, %s, %s, %s
                            )
                            """,
                            (
                                str(uuid4()),
                                structure_id,
                                unit_id,
                                scope["slot"],
                                scope["title"],
                                scope.get("summary", ""),
                                scope.get("reading_skill", ""),
                                scope.get("vocabulary_building", ""),
                                scope.get("critical_thinking", ""),
                                scope.get("source_id", ""),
                                scope["line_start"],
                                scope["line_end"],
                                scope["char_start"],
                                scope["char_end"],
                            ),
                        )
    return stored_units


async def create_generation_job(
    *,
    version_id: str,
    scope: str,
    structure_id: str | None,
    knowledge_point_id: str | None,
    processing_profile_sha256: str,
    auto_grading: bool = False,
) -> dict[str, Any]:
    """Queue one textbook generation job."""
    structure_target = str(structure_id) if structure_id is not None else None
    knowledge_point_target = (
        str(knowledge_point_id) if knowledge_point_id is not None else None
    )
    if scope in {"structure", "assets"}:
        valid_target = structure_target is not None and knowledge_point_target is None
    elif scope == "lesson":
        valid_target = structure_target is None and knowledge_point_target is not None
    elif scope == "book_pipeline":
        raise ValueError("book_pipeline jobs must use queue_book_pipeline_job()")
    else:
        valid_target = False
    if not valid_target:
        raise ValueError("generation job requires exactly one target")

    generation_job_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO education_generation_jobs (
                    generation_job_id, version_id, scope, structure_id,
                    knowledge_point_id, status, auto_grading,
                    processing_profile_sha256
                ) VALUES (%s, %s, %s, %s, %s, 'queued', %s, %s)
                RETURNING generation_job_id, version_id, scope, structure_id,
                          knowledge_point_id, status, auto_grading
                """,
                (
                    generation_job_id,
                    version_id,
                    scope,
                    structure_target,
                    knowledge_point_target,
                    auto_grading,
                    processing_profile_sha256,
                ),
            )
            row = await cur.fetchone()
    return dict(row)


async def claim_generation_job(
    *,
    generation_job_id: str,
    managed_workspace_id: str,
    managed_thread_id: str,
    expected_job_status: str = "queued",
) -> dict[str, Any] | None:
    """Reserve one queued generation attempt under the job's single-writer row."""
    if expected_job_status not in {"queued", "preparing"}:
        raise ValueError("Invalid expected generation job status")
    attempt_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    f"""
                    SELECT generation_job_id, version_id, scope, structure_id,
                           knowledge_point_id, latest_attempt_id AS previous_attempt_id
                    FROM education_generation_jobs
                    WHERE generation_job_id = %s
                      AND status = '{expected_job_status}'
                    FOR UPDATE
                    """,
                    (generation_job_id,),
                )
                job = await cur.fetchone()
                if not job:
                    return None
                await cur.execute(
                    """
                    INSERT INTO education_generation_attempts (
                        attempt_id, generation_job_id, previous_attempt_id,
                        managed_workspace_id, managed_thread_id, status
                    ) VALUES (%s, %s, %s, %s, %s, 'preparing')
                    RETURNING attempt_id, generation_job_id, previous_attempt_id,
                              managed_workspace_id, managed_thread_id, root_run_id
                    """,
                    (
                        attempt_id,
                        generation_job_id,
                        job["previous_attempt_id"],
                        managed_workspace_id,
                        managed_thread_id,
                    ),
                )
                attempt = dict(await cur.fetchone())
                await cur.execute(
                    f"""
                    UPDATE education_generation_jobs
                    SET status = 'preparing',
                        attempt_count = attempt_count + 1,
                        latest_attempt_id = %s,
                        updated_at = NOW()
                    WHERE generation_job_id = %s
                      AND status = '{expected_job_status}'
                    """,
                    (attempt_id, generation_job_id),
                )
    return {**dict(job), **attempt}


async def requeue_generation_job(*, generation_job_id: str) -> bool:
    """Requeue one failed generation job for another attempt without a new job."""
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE education_generation_jobs
                SET status = 'queued', error_code = NULL, error_message = NULL,
                    updated_at = NOW()
                WHERE generation_job_id = %s AND status = 'failed'
                  AND attempt_count < 3
                RETURNING generation_job_id
                """,
                (generation_job_id,),
            )
            return await cur.fetchone() is not None


async def requeue_structure_generation(*, generation_job_id: str) -> bool:
    """Requeue one failed structure job with its existing structure identity."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE education_generation_jobs
                    SET status = 'queued', error_code = NULL,
                        error_message = NULL, updated_at = NOW()
                    WHERE generation_job_id = %s
                      AND scope = 'structure'
                      AND status = 'failed'
                      AND attempt_count < 3
                    RETURNING structure_id
                    """,
                    (generation_job_id,),
                )
                job = await cur.fetchone()
                if not job or job.get("structure_id") is None:
                    return False
                await cur.execute(
                    """
                    UPDATE education_textbook_structures
                    SET status = 'queued', bundle_prefix = NULL
                    WHERE structure_id = %s AND status = 'failed'
                    """,
                    (job["structure_id"],),
                )
    return True


async def settle_generation_job(
    *,
    generation_job_id: str,
    attempt_id: str,
    status: str,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any] | None:
    """Settle one generation attempt and project its terminal product status."""
    if status not in {"completed", "failed", "cancelled", "worker_lost"}:
        raise ValueError("Invalid generation attempt status")
    job_status = "completed" if status == "completed" else status
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE education_generation_attempts
                    SET status = %s, error_code = %s, error_message = %s,
                        completed_at = NOW()
                    WHERE attempt_id = %s AND generation_job_id = %s
                      AND status IN ('preparing', 'running')
                    RETURNING attempt_id, generation_job_id, status
                    """,
                    (
                        status,
                        error_code,
                        error_message,
                        attempt_id,
                        generation_job_id,
                    ),
                )
                attempt = await cur.fetchone()
                if not attempt:
                    return None
                await cur.execute(
                    """
                    UPDATE education_generation_jobs
                    SET status = %s, error_code = %s, error_message = %s,
                        updated_at = NOW()
                    WHERE generation_job_id = %s AND latest_attempt_id = %s
                    RETURNING generation_job_id, version_id, scope, structure_id,
                              knowledge_point_id, status
                    """,
                    (
                        job_status,
                        error_code,
                        error_message,
                        generation_job_id,
                        attempt_id,
                    ),
                )
                job = await cur.fetchone()
    return dict(job) if job else None


async def mark_generation_attempt_running(
    *,
    generation_job_id: str,
    attempt_id: str,
    root_run_id: str,
) -> dict[str, Any] | None:
    """Bind the dispatched root run to its reserved generation attempt."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE education_generation_attempts
                    SET status = 'running', root_run_id = %s,
                        heartbeat_at = NOW()
                    WHERE attempt_id = %s AND generation_job_id = %s
                      AND status = 'preparing' AND root_run_id IS NULL
                    RETURNING attempt_id, generation_job_id, root_run_id, status
                    """,
                    (root_run_id, attempt_id, generation_job_id),
                )
                attempt = await cur.fetchone()
                if not attempt:
                    return None
                await cur.execute(
                    """
                    UPDATE education_generation_jobs
                    SET status = 'running', updated_at = NOW()
                    WHERE generation_job_id = %s
                      AND latest_attempt_id = %s
                      AND status = 'preparing'
                    RETURNING generation_job_id, scope, structure_id, status
                    """,
                    (generation_job_id, attempt_id),
                )
                job = await cur.fetchone()
                if (
                    job
                    and job.get("scope") == "structure"
                    and job.get("structure_id") is not None
                ):
                    await cur.execute(
                        """
                        UPDATE education_textbook_structures
                        SET status = 'running'
                        WHERE structure_id = %s AND status = 'queued'
                        """,
                        (job["structure_id"],),
                    )
    return {**dict(attempt), **dict(job)} if job else None


async def touch_generation_attempt(
    *, generation_job_id: str, attempt_id: str, root_run_id: str
) -> bool:
    """Refresh a running generation attempt without reviving stale runs."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE education_generation_attempts AS attempts
                SET heartbeat_at = NOW()
                FROM education_generation_jobs AS jobs
                WHERE attempts.attempt_id = %s
                  AND attempts.generation_job_id = %s
                  AND attempts.root_run_id = %s
                  AND attempts.status = 'running'
                  AND jobs.generation_job_id = attempts.generation_job_id
                  AND jobs.latest_attempt_id = attempts.attempt_id
                RETURNING attempts.attempt_id
                """,
                (attempt_id, generation_job_id, root_run_id),
            )
            return await cur.fetchone() is not None


async def complete_structure_generation(
    *,
    generation_job_id: str,
    attempt_id: str,
    structure_id: str,
    bundle_prefix: str,
) -> dict[str, Any] | None:
    """Atomically publish a validated structure projection into review."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE education_textbook_structures
                    SET status = 'review', bundle_prefix = %s
                    WHERE structure_id = %s AND status = 'running'
                    RETURNING structure_id, version_id, sequence, status,
                              bundle_prefix
                    """,
                    (bundle_prefix, structure_id),
                )
                structure = await cur.fetchone()
                if not structure:
                    return None
                await cur.execute(
                    """
                    UPDATE education_generation_attempts
                    SET status = 'completed', completed_at = NOW()
                    WHERE attempt_id = %s AND generation_job_id = %s
                      AND status = 'running'
                    RETURNING attempt_id
                    """,
                    (attempt_id, generation_job_id),
                )
                if not await cur.fetchone():
                    raise RuntimeError("Generation attempt completion was lost")
                await cur.execute(
                    """
                    UPDATE education_generation_jobs
                    SET status = 'completed', error_code = NULL,
                        error_message = NULL, updated_at = NOW()
                    WHERE generation_job_id = %s
                      AND latest_attempt_id = %s
                    RETURNING generation_job_id, status
                    """,
                    (generation_job_id, attempt_id),
                )
                job = await cur.fetchone()
    if not job:
        return None
    result = dict(structure)
    result["structure_status"] = result.pop("status")
    result["generation_job_id"] = job["generation_job_id"]
    result["job_status"] = job["status"]
    return result


async def complete_book_asset_generation(
    *,
    generation_job_id: str,
    attempt_id: str,
    structure_id: str,
    bundle_prefix: str,
    asset_manifest: dict[str, Any],
) -> dict[str, Any] | None:
    """Attach optional generated chapter assets to an existing structure."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE education_textbook_structures
                    SET book_asset_prefix = %s, book_asset_manifest = %s
                    WHERE structure_id = %s
                    RETURNING structure_id, version_id, sequence
                    """,
                    (bundle_prefix, Json(asset_manifest), structure_id),
                )
                structure = await cur.fetchone()
                if not structure:
                    return None
                await cur.execute(
                    """
                    UPDATE education_generation_attempts
                    SET status = 'completed', completed_at = NOW()
                    WHERE attempt_id = %s AND generation_job_id = %s
                      AND status = 'running'
                    RETURNING attempt_id
                    """,
                    (attempt_id, generation_job_id),
                )
                if not await cur.fetchone():
                    raise RuntimeError("Book asset attempt completion was lost")
                await cur.execute(
                    """
                    UPDATE education_generation_jobs
                    SET status = 'completed', error_code = NULL,
                        error_message = NULL, updated_at = NOW()
                    WHERE generation_job_id = %s
                      AND latest_attempt_id = %s
                    RETURNING generation_job_id, status
                    """,
                    (generation_job_id, attempt_id),
                )
                job = await cur.fetchone()
    if not job:
        return None
    return {
        **dict(structure),
        "generation_job_id": job["generation_job_id"],
        "job_status": job["status"],
        "book_asset_prefix": bundle_prefix,
        "book_asset_manifest": asset_manifest,
    }


async def accept_textbook_structure(
    *, parent_user_id: str, structure_id: str
) -> dict[str, Any] | None:
    """Accept one parent-owned structure and all of its reviewable children."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT structures.structure_id
                    FROM education_textbook_structures AS structures
                    JOIN education_textbook_versions AS versions
                      ON versions.version_id = structures.version_id
                    JOIN education_textbooks AS textbooks
                      ON textbooks.textbook_id = versions.textbook_id
                    JOIN education_memberships AS memberships
                      ON memberships.household_id = textbooks.household_id
                    WHERE structures.structure_id = %s
                      AND structures.status = 'review'
                      AND memberships.user_id = %s
                      AND memberships.role = 'parent'
                    FOR UPDATE OF structures
                    """,
                    (structure_id, parent_user_id),
                )
                if not await cur.fetchone():
                    return None
                await cur.execute(
                    """
                    UPDATE education_structure_knowledge_points
                    SET status = 'accepted'
                    WHERE unit_id IN (
                        SELECT unit_id
                        FROM education_structure_units
                        WHERE structure_id = %s
                    )
                    """,
                    (structure_id,),
                )
                await cur.execute(
                    """
                    UPDATE education_structure_units
                    SET status = 'accepted'
                    WHERE structure_id = %s
                    """,
                    (structure_id,),
                )
                await cur.execute(
                    """
                    UPDATE education_textbook_structures
                    SET status = 'accepted', reviewed_at = NOW()
                    WHERE structure_id = %s AND status = 'review'
                    RETURNING structure_id, version_id, sequence, status,
                              reviewed_at
                    """,
                    (structure_id,),
                )
                structure = await cur.fetchone()
    return dict(structure) if structure else None


async def create_kp_lesson_revision(
    *,
    knowledge_point_id: str,
    content_key: str,
    content_sha256: str,
    size_bytes: int,
    processing_profile_sha256: str,
    generation_job_id: str | None,
) -> dict[str, Any] | None:
    """Create an immutable Markdown revision for one knowledge point."""
    if not content_key.startswith("education/") or ".." in content_key:
        raise ValueError("Lesson content key is invalid")
    if not _SHA256.fullmatch(content_sha256):
        raise ValueError("Lesson content sha256 is invalid")
    if not _SHA256.fullmatch(processing_profile_sha256):
        raise ValueError("Lesson processing profile sha256 is invalid")
    if (
        not isinstance(size_bytes, int)
        or isinstance(size_bytes, bool)
        or size_bytes <= 0
    ):
        raise ValueError("Lesson content size is invalid")

    revision_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT knowledge_point_id
                    FROM education_structure_knowledge_points
                    WHERE knowledge_point_id = %s
                      AND status = 'accepted'
                    FOR UPDATE
                    """,
                    (knowledge_point_id,),
                )
                if not await cur.fetchone():
                    return None
                await cur.execute(
                    """
                    SELECT lesson_id, latest_revision_id, status
                    FROM education_kp_lessons
                    WHERE knowledge_point_id = %s
                    FOR UPDATE
                    """,
                    (knowledge_point_id,),
                )
                lesson = await cur.fetchone()
                if lesson:
                    lesson_id = str(lesson["lesson_id"])
                else:
                    lesson_id = str(uuid4())
                    await cur.execute(
                        """
                        INSERT INTO education_kp_lessons (
                            lesson_id, knowledge_point_id, status
                        ) VALUES (%s, %s, 'review')
                        """,
                        (lesson_id, knowledge_point_id),
                    )
                await cur.execute(
                    """
                    SELECT COALESCE(MAX(revision), 0) + 1 AS revision
                    FROM education_kp_lesson_revisions
                    WHERE lesson_id = %s
                    """,
                    (lesson_id,),
                )
                revision = (await cur.fetchone())["revision"]
                await cur.execute(
                    """
                    INSERT INTO education_kp_lesson_revisions (
                        revision_id, lesson_id, revision, format, content_key,
                        content_sha256, size_bytes, processing_profile_sha256,
                        generation_job_id
                    ) VALUES (
                        %s, %s, %s, 'markdown', %s, %s, %s, %s, %s
                    )
                    RETURNING revision_id
                    """,
                    (
                        revision_id,
                        lesson_id,
                        revision,
                        content_key,
                        content_sha256,
                        size_bytes,
                        processing_profile_sha256,
                        generation_job_id,
                    ),
                )
                await cur.fetchone()
                await cur.execute(
                    """
                    UPDATE education_kp_lessons
                    SET latest_revision_id = %s,
                        status = 'review',
                        reviewed_at = NULL
                    WHERE lesson_id = %s
                    RETURNING lesson_id, knowledge_point_id,
                              latest_revision_id, status
                    """,
                    (revision_id, lesson_id),
                )
                updated = dict(await cur.fetchone())
    return {
        **updated,
        "revision_id": revision_id,
        "revision": revision,
        "content_key": content_key,
        "content_sha256": content_sha256,
        "size_bytes": size_bytes,
    }


async def get_kp_lesson_for_parent(
    *, parent_user_id: str, lesson_id: str
) -> dict[str, Any] | None:
    """Read one stable lesson identity and its immutable revisions."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT lessons.lesson_id, lessons.status,
                       lessons.latest_revision_id, lessons.created_at,
                       lessons.reviewed_at,
                       knowledge_points.knowledge_point_id,
                       knowledge_points.position AS knowledge_point_position,
                       knowledge_points.slug AS knowledge_point_slug,
                       knowledge_points.title AS knowledge_point_title,
                       units.unit_id,
                       units.position AS unit_position,
                       units.slug AS unit_slug,
                       units.title AS unit_title,
                       structures.structure_id,
                       structures.sequence AS structure_sequence,
                       versions.version_id,
                       versions.sequence AS content_version_sequence,
                       textbooks.textbook_id, textbooks.household_id,
                       textbooks.slug, textbooks.title
                FROM education_kp_lessons AS lessons
                JOIN education_structure_knowledge_points AS knowledge_points
                  ON knowledge_points.knowledge_point_id =
                     lessons.knowledge_point_id
                JOIN education_structure_units AS units
                  ON units.unit_id = knowledge_points.unit_id
                JOIN education_textbook_structures AS structures
                  ON structures.structure_id = units.structure_id
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = structures.version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                WHERE lessons.lesson_id = %s
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                """,
                (lesson_id, parent_user_id),
            )
            lesson = await cur.fetchone()
            if not lesson:
                return None
            result = dict(lesson)
            await cur.execute(
                """
                SELECT revision_id, revision, format, content_key,
                       content_sha256, size_bytes,
                       processing_profile_sha256, created_at
                FROM education_kp_lesson_revisions
                WHERE lesson_id = %s
                ORDER BY revision DESC
                """,
                (lesson_id,),
            )
            result["revisions"] = [dict(row) for row in await cur.fetchall()]
    return result


async def get_kp_lesson_by_knowledge_point_for_parent(
    *, parent_user_id: str, knowledge_point_id: str
) -> dict[str, Any] | None:
    """Return the stable lesson identity for one accepted knowledge point."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT lessons.lesson_id
                FROM education_kp_lessons AS lessons
                JOIN education_structure_knowledge_points AS knowledge_points
                  ON knowledge_points.knowledge_point_id =
                     lessons.knowledge_point_id
                JOIN education_structure_units AS units
                  ON units.unit_id = knowledge_points.unit_id
                JOIN education_textbook_structures AS structures
                  ON structures.structure_id = units.structure_id
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = structures.version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                WHERE lessons.knowledge_point_id = %s
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                """,
                (knowledge_point_id, parent_user_id),
            )
            row = await cur.fetchone()
    if not row:
        return None
    return await get_kp_lesson_for_parent(
        parent_user_id=parent_user_id,
        lesson_id=str(row["lesson_id"]),
    )


async def approve_kp_lesson_revision(
    *, parent_user_id: str, lesson_id: str, revision_id: str
) -> dict[str, Any] | None:
    """Approve one exact revision without mutating its content."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT lessons.lesson_id
                    FROM education_kp_lessons AS lessons
                    JOIN education_structure_knowledge_points AS knowledge_points
                      ON knowledge_points.knowledge_point_id =
                         lessons.knowledge_point_id
                    JOIN education_structure_units AS units
                      ON units.unit_id = knowledge_points.unit_id
                    JOIN education_textbook_structures AS structures
                      ON structures.structure_id = units.structure_id
                    JOIN education_textbook_versions AS versions
                      ON versions.version_id = structures.version_id
                    JOIN education_textbooks AS textbooks
                      ON textbooks.textbook_id = versions.textbook_id
                    JOIN education_memberships AS memberships
                      ON memberships.household_id = textbooks.household_id
                    WHERE lessons.lesson_id = %s
                      AND memberships.user_id = %s
                      AND memberships.role = 'parent'
                    FOR UPDATE OF lessons
                    """,
                    (lesson_id, parent_user_id),
                )
                if not await cur.fetchone():
                    return None
                await cur.execute(
                    """
                    SELECT revision_id
                    FROM education_kp_lesson_revisions
                    WHERE revision_id = %s AND lesson_id = %s
                    """,
                    (revision_id, lesson_id),
                )
                if not await cur.fetchone():
                    return None
                await cur.execute(
                    """
                    UPDATE education_kp_lessons
                    SET latest_revision_id = %s, status = 'approved',
                        reviewed_at = NOW()
                    WHERE lesson_id = %s
                    RETURNING lesson_id, knowledge_point_id,
                              latest_revision_id, status, reviewed_at
                    """,
                    (revision_id, lesson_id),
                )
                approved = await cur.fetchone()
    return dict(approved) if approved else None


async def freeze_publication_lessons(
    *,
    publication_id: str,
    lessons: list[dict[str, str]],
) -> bool:
    """Freeze exact approved lesson revisions into one publication snapshot."""
    if not lessons:
        return False
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT publications.publication_id, publications.version_id
                    FROM education_textbook_publications AS publications
                    WHERE publications.publication_id = %s
                    FOR UPDATE
                    """,
                    (publication_id,),
                )
                publication = await cur.fetchone()
                if not publication:
                    return False
                for lesson in lessons:
                    knowledge_point_id = str(lesson.get("knowledge_point_id") or "")
                    lesson_revision_id = str(lesson.get("lesson_revision_id") or "")
                    if not knowledge_point_id or not lesson_revision_id:
                        return False
                    await cur.execute(
                        """
                        SELECT revisions.revision_id
                        FROM education_kp_lesson_revisions AS revisions
                        JOIN education_kp_lessons AS lessons
                          ON lessons.lesson_id = revisions.lesson_id
                        JOIN education_structure_knowledge_points AS knowledge_points
                          ON knowledge_points.knowledge_point_id =
                             lessons.knowledge_point_id
                        JOIN education_structure_units AS units
                          ON units.unit_id = knowledge_points.unit_id
                        JOIN education_textbook_structures AS structures
                          ON structures.structure_id = units.structure_id
                        WHERE revisions.revision_id = %s
                          AND lessons.knowledge_point_id = %s
                          AND lessons.status = 'approved'
                          AND structures.version_id = %s
                        FOR UPDATE OF revisions, lessons
                        """,
                        (
                            lesson_revision_id,
                            knowledge_point_id,
                            publication["version_id"],
                        ),
                    )
                    if not await cur.fetchone():
                        return False
                    await cur.execute(
                        """
                        INSERT INTO education_publication_kp_lessons (
                            publication_id, knowledge_point_id,
                            lesson_revision_id
                        ) VALUES (%s, %s, %s)
                        """,
                        (
                            publication_id,
                            knowledge_point_id,
                            lesson_revision_id,
                        ),
                    )
    return True


async def fail_structure_generation(
    *,
    generation_job_id: str,
    attempt_id: str,
    structure_id: str,
    status: str,
    error_code: str,
    error_message: str | None,
) -> dict[str, Any] | None:
    """Fail one structure attempt without touching completed structures."""
    if status not in {"failed", "cancelled"}:
        raise ValueError("Invalid structure generation failure status")
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE education_generation_attempts
                    SET status = %s, error_code = %s, error_message = %s,
                        completed_at = NOW()
                    WHERE attempt_id = %s AND generation_job_id = %s
                      AND status IN ('preparing', 'running')
                    RETURNING attempt_id
                    """,
                    (
                        status,
                        error_code,
                        error_message,
                        attempt_id,
                        generation_job_id,
                    ),
                )
                if not await cur.fetchone():
                    return None
                await cur.execute(
                    """
                    UPDATE education_generation_jobs
                    SET status = %s, error_code = %s, error_message = %s,
                        updated_at = NOW()
                    WHERE generation_job_id = %s
                      AND latest_attempt_id = %s
                    RETURNING generation_job_id, status
                    """,
                    (
                        status,
                        error_code,
                        error_message,
                        generation_job_id,
                        attempt_id,
                    ),
                )
                job = await cur.fetchone()
                await cur.execute(
                    """
                    UPDATE education_textbook_structures
                    SET status = %s
                    WHERE structure_id = %s AND status IN ('queued', 'running')
                    RETURNING structure_id, status
                    """,
                    (status, structure_id),
                )
                structure = await cur.fetchone()
    if not job:
        return None
    result = dict(job)
    if structure:
        result.update(dict(structure))
    return result


async def get_teaching_input_for_parent(
    *, parent_user_id: str, content_version_id: str
) -> dict[str, Any] | None:
    """Read only reviewable frozen Markdown for deterministic job provenance."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT versions.version_id AS content_version_id,
                       versions.sequence AS content_version_sequence,
                       textbooks.household_id, textbooks.slug, textbooks.title,
                       EXISTS (
                           SELECT 1
                           FROM education_textbook_artifact_sources AS artifact_sources
                           WHERE artifact_sources.version_id = versions.version_id
                       ) AS artifact_backed
                FROM education_textbook_versions AS versions
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                WHERE versions.version_id = %s
                  AND versions.status = 'review'
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                """,
                (content_version_id, parent_user_id),
            )
            version = await cur.fetchone()
            if not version:
                return None
            result = dict(version)
            artifact_backed = bool(result.pop("artifact_backed", False))
            await cur.execute(
                """
                SELECT chapters.chapter_id AS content_chapter_id,
                       artifact_sources.producer_job_id,
                       artifact_sources.document_id,
                       artifact_sources.snapshot_prefix,
                       artifact_sources.asset_manifest,
                       chapters.position, chapters.slug, chapters.title, chapters.markdown
                FROM education_textbook_chapters AS chapters
                LEFT JOIN education_textbook_artifact_sources AS artifact_sources
                  ON artifact_sources.version_id = chapters.version_id
                 AND artifact_sources.position = chapters.position
                WHERE chapters.version_id = %s
                ORDER BY chapters.position
                """,
                (content_version_id,),
            )
            rows = [dict(row) for row in await cur.fetchall()]
            if artifact_backed:
                result["sources"] = [
                    {
                        "source_id": str(
                            row.get("producer_job_id") or row["content_chapter_id"]
                        ),
                        "content_chapter_id": str(row["content_chapter_id"]),
                        "document_id": (
                            str(row["document_id"])
                            if row.get("document_id") is not None
                            else None
                        ),
                        "snapshot_prefix": row.get("snapshot_prefix"),
                        "asset_manifest": row.get("asset_manifest") or [],
                        "position": row["position"],
                        "slug": row["slug"],
                        "title": row["title"],
                        "content_sha256": hashlib.sha256(
                            str(row["markdown"]).encode("utf-8")
                        ).hexdigest(),
                        "markdown": row["markdown"],
                    }
                    for row in rows
                ]
            else:
                result["chapters"] = [
                    {
                        "content_chapter_id": row["content_chapter_id"],
                        "position": row["position"],
                        "slug": row["slug"],
                        "title": row["title"],
                        "markdown": row["markdown"],
                    }
                    for row in rows
                ]
    return result


async def queue_textbook_processing(
    *,
    parent_user_id: str,
    household_id: str,
    textbook_id: str,
    source_asset_ids: list[str],
    extractor_name: str,
    extractor_version: str,
) -> dict[str, Any] | None:
    """Freeze eligible source assets into a fresh processing version and queue one job."""
    version_id = str(uuid4())
    job_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT textbook_id FROM education_textbooks
                    WHERE textbook_id = %s AND household_id = %s
                    FOR UPDATE
                    """,
                    (textbook_id, household_id),
                )
                if not await cur.fetchone():
                    return None
                await cur.execute(
                    """
                    SELECT COUNT(*) AS source_count FROM education_assets
                    WHERE household_id = %s AND asset_id = ANY(%s::uuid[])
                    """,
                    (household_id, source_asset_ids),
                )
                if (await cur.fetchone())["source_count"] != len(set(source_asset_ids)):
                    raise ValueError(
                        "One or more textbook sources are outside the household"
                    )
                await cur.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence FROM education_textbook_versions WHERE textbook_id = %s",
                    (textbook_id,),
                )
                sequence = (await cur.fetchone())["sequence"]
                await cur.execute(
                    """
                    INSERT INTO education_textbook_versions (
                        version_id, textbook_id, sequence, status, extractor_name, extractor_version, created_by_user_id
                    ) VALUES (%s, %s, %s, 'processing', %s, %s, %s)
                    """,
                    (
                        version_id,
                        textbook_id,
                        sequence,
                        extractor_name,
                        extractor_version,
                        parent_user_id,
                    ),
                )
                await cur.executemany(
                    "INSERT INTO education_textbook_sources (version_id, asset_id, position) VALUES (%s, %s, %s)",
                    [
                        (version_id, asset_id, index)
                        for index, asset_id in enumerate(source_asset_ids, start=1)
                    ],
                )
                await cur.execute(
                    """
                    INSERT INTO education_processing_jobs (job_id, version_id, status)
                    VALUES (%s, %s, 'queued')
                    RETURNING job_id, version_id, status, attempt_count, created_at
                    """,
                    (job_id, version_id),
                )
                job = dict(await cur.fetchone())
    return job


async def queue_textbook_processing_from_artifacts(
    *,
    parent_user_id: str,
    household_id: str,
    textbook_id: str,
    sources: list[dict[str, Any]],
    extractor_name: str,
    extractor_version: str,
    version_id: str | None = None,
    job_id: str | None = None,
) -> dict[str, Any] | None:
    """Freeze completed library parse bundles into a fresh processing version.

    ``snapshot_prefix`` is deliberately not an input. This service boundary is
    the only writer and derives it from the locked textbook identity, the
    pre-generated version ID when supplied, and each source position.
    ``primary_sha256`` is the service-computed digest of the frozen primary
    artifact.
    """
    if not sources:
        raise TextbookQueueValidationError("At least one parse job source is required")

    try:
        household_component = _validated_path_component(
            str(household_id), "household_id"
        )
    except ValueError as exc:
        raise TextbookQueueValidationError(str(exc)) from exc
    producer_job_ids = [str(source.get("producer_job_id") or "") for source in sources]
    if any(not job_id for job_id in producer_job_ids):
        raise TextbookQueueValidationError("Every source requires a producer_job_id")
    if len(set(producer_job_ids)) != len(producer_job_ids):
        raise TextbookQueueValidationError(
            "Duplicate producer_job_id sources are not allowed"
        )
    for source in sources:
        if not str(source.get("document_id") or ""):
            raise TextbookQueueValidationError("Every source requires a document_id")
        if not str(source.get("primary_artifact_id") or ""):
            raise TextbookQueueValidationError(
                "Every source requires a primary_artifact_id"
            )
        if not _SHA256.fullmatch(str(source.get("primary_sha256") or "")):
            raise TextbookQueueValidationError(
                "primary_sha256 must be 64 lowercase hex characters"
            )
    asset_manifests = {
        str(source["producer_job_id"]): _validated_asset_manifest(
            source.get("asset_manifest")
        )
        for source in sources
    }

    try:
        version_id = str(UUID(version_id)) if version_id else str(uuid4())
        job_id = str(UUID(job_id)) if job_id else str(uuid4())
    except ValueError as exc:
        raise TextbookQueueValidationError(
            "version_id and job_id must be UUIDs"
        ) from exc
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT textbook_id, slug FROM education_textbooks
                    WHERE textbook_id = %s AND household_id = %s
                    FOR UPDATE
                    """,
                    (textbook_id, household_id),
                )
                textbook = await cur.fetchone()
                if not textbook:
                    raise TextbookQueueValidationError("Textbook not found")
                try:
                    textbook_component = _validated_path_component(
                        str(textbook["slug"]), "textbook slug"
                    )
                except ValueError as exc:
                    raise TextbookQueueValidationError(str(exc)) from exc

                await cur.execute(
                    """
                    SELECT jobs.job_id AS producer_job_id,
                           jobs.document_id,
                           jobs.primary_artifact_id,
                           documents.original_filename AS source_filename,
                           documents.media_type AS source_media_type,
                           documents.document_format AS source_format,
                           jobs.parser_id,
                           jobs.parser_name,
                           jobs.parser_version,
                           jobs.completed_at AS parse_completed_at
                    FROM document_parse_jobs AS jobs
                    JOIN documents ON documents.document_id = jobs.document_id
                    JOIN document_artifacts AS artifacts
                      ON artifacts.artifact_id = jobs.primary_artifact_id
                     AND artifacts.producer_job_id = jobs.job_id
                    WHERE jobs.job_id = ANY(%s::varchar[])
                      AND jobs.status = 'completed'
                      AND jobs.primary_artifact_id IS NOT NULL
                      AND artifacts.artifact_kind = 'primary_document'
                      AND documents.owner_user_id = %s
                    FOR SHARE OF jobs, documents, artifacts
                    """,
                    (producer_job_ids, parent_user_id),
                )
                available = {
                    str(row["producer_job_id"]): dict(row)
                    for row in await cur.fetchall()
                }
                for source in sources:
                    row = available.get(str(source["producer_job_id"]))
                    if row is None or (
                        str(row["document_id"]),
                        str(row["primary_artifact_id"]),
                    ) != (
                        str(source["document_id"]),
                        str(source["primary_artifact_id"]),
                    ):
                        raise TextbookQueueValidationError(
                            "One or more parse job sources are unavailable "
                            "or not owned by the parent"
                        )

                await cur.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence "
                    "FROM education_textbook_versions WHERE textbook_id = %s",
                    (textbook_id,),
                )
                sequence = (await cur.fetchone())["sequence"]
                await cur.execute(
                    """
                    INSERT INTO education_textbook_versions (
                        version_id, textbook_id, sequence, status, extractor_name, extractor_version, created_by_user_id
                    ) VALUES (%s, %s, %s, 'processing', %s, %s, %s)
                    """,
                    (
                        version_id,
                        textbook_id,
                        sequence,
                        extractor_name,
                        extractor_version,
                        parent_user_id,
                    ),
                )
                source_rows: list[tuple[Any, ...]] = []
                for index, source in enumerate(sources, start=1):
                    row = available[str(source["producer_job_id"])]
                    source_rows.append(
                        (
                            version_id,
                            str(row["document_id"]),
                            str(row["producer_job_id"]),
                            str(row["primary_artifact_id"]),
                            index,
                            str(row["source_filename"]),
                            str(row["source_media_type"]),
                            str(row["source_format"]),
                            str(row["parser_id"]),
                            str(row["parser_name"]),
                            (
                                str(row["parser_version"])
                                if row["parser_version"] is not None
                                else None
                            ),
                            row["parse_completed_at"],
                            str(source["primary_sha256"]),
                            (
                                f"education/{household_component}/{textbook_component}/"
                                f"source-bundles/{version_id}/{index:02d}/"
                            ),
                            Json(asset_manifests[str(source["producer_job_id"])]),
                        )
                    )
                await cur.executemany(
                    """
                    INSERT INTO education_textbook_artifact_sources (
                        version_id, document_id, producer_job_id, primary_artifact_id,
                        position, source_filename, source_media_type, source_format,
                        parser_id, parser_name, parser_version, parse_completed_at,
                        primary_sha256, snapshot_prefix, asset_manifest
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    """,
                    source_rows,
                )
                await cur.execute(
                    """
                    INSERT INTO education_processing_jobs (job_id, version_id, status)
                    VALUES (%s, %s, 'queued')
                    RETURNING job_id, version_id, status, attempt_count, created_at
                    """,
                    (job_id, version_id),
                )
                job = dict(await cur.fetchone())
    return job


async def get_owned_parse_job(
    *, owner_user_id: str, producer_job_id: str
) -> dict[str, Any] | None:
    """Return exact parse-job provenance only when its Document is owner-scoped."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.job_id AS producer_job_id,
                       jobs.document_id,
                       jobs.primary_artifact_id,
                       jobs.status,
                       jobs.parser_id,
                       jobs.parser_name,
                       jobs.parser_version,
                       jobs.completed_at,
                       documents.original_filename,
                       documents.media_type,
                       documents.document_format
                FROM document_parse_jobs AS jobs
                JOIN documents ON documents.document_id = jobs.document_id
                WHERE jobs.job_id = %s
                  AND documents.owner_user_id = %s
                """,
                (producer_job_id, owner_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


_PARSE_JOB_CANDIDATE_FIELDS = (
    "producer_job_id",
    "document_id",
    "primary_artifact_id",
    "filename",
    "media_type",
    "format",
    "parser_id",
    "parser_name",
    "parser_version",
    "parse_completed_at",
    "size_bytes",
    "artifact_count",
)


def _safe_completed_parse_job_candidates(
    rows: list[dict[str, Any]], *, parent_user_id: str
) -> list[dict[str, Any]]:
    """Apply an explicit repository-boundary filter and safe projection."""
    return [
        {field: row.get(field) for field in _PARSE_JOB_CANDIDATE_FIELDS}
        for row in rows
        if row.get("status") == "completed"
        and str(row.get("owner_user_id") or "") == str(parent_user_id)
        and bool(row.get("primary_artifact_id"))
    ]


async def list_completed_parse_jobs_for_parent(
    *, parent_user_id: str
) -> list[dict[str, Any]]:
    """Return safe completed Markdown bundles owned by one parent."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.job_id AS producer_job_id,
                       jobs.document_id,
                       jobs.primary_artifact_id,
                       jobs.status,
                       documents.owner_user_id,
                       documents.original_filename AS filename,
                       documents.media_type,
                       documents.document_format AS format,
                       jobs.parser_id,
                       jobs.parser_name,
                       jobs.parser_version,
                       jobs.completed_at AS parse_completed_at,
                       documents.source_size_bytes AS size_bytes,
                       COALESCE(artifact_counts.artifact_count, 0)::int
                           AS artifact_count
                FROM document_parse_jobs AS jobs
                JOIN documents
                  ON documents.document_id = jobs.document_id
                JOIN document_artifacts AS primary_artifacts
                  ON primary_artifacts.artifact_id = jobs.primary_artifact_id
                 AND primary_artifacts.producer_job_id = jobs.job_id
                 AND primary_artifacts.artifact_kind = 'primary_document'
                 AND LOWER(
                     SPLIT_PART(primary_artifacts.media_type, ';', 1)
                 ) = 'text/markdown'
                 AND LOWER(primary_artifacts.format) IN ('gfm', 'markdown')
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) AS artifact_count
                    FROM document_artifacts AS artifacts
                    WHERE artifacts.producer_job_id = jobs.job_id
                ) AS artifact_counts ON TRUE
                WHERE jobs.status = 'completed'
                  AND jobs.primary_artifact_id IS NOT NULL
                  AND documents.owner_user_id = %s
                ORDER BY jobs.completed_at DESC NULLS LAST,
                         jobs.job_id DESC
                """,
                (parent_user_id,),
            )
            rows = await cur.fetchall()
    return _safe_completed_parse_job_candidates(
        [dict(row) for row in rows],
        parent_user_id=parent_user_id,
    )


async def claim_textbook_processing_job(*, job_id: str) -> dict[str, Any] | None:
    """Claim exactly one queued job with a row lock; a future PTC worker uses the same contract."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT jobs.job_id, jobs.version_id, versions.sequence AS version_sequence,
                           textbooks.textbook_id, textbooks.household_id, textbooks.title, textbooks.slug
                    FROM education_processing_jobs AS jobs
                    JOIN education_textbook_versions AS versions ON versions.version_id = jobs.version_id
                    JOIN education_textbooks AS textbooks ON textbooks.textbook_id = versions.textbook_id
                    WHERE jobs.job_id = %s AND jobs.status = 'queued'
                    FOR UPDATE SKIP LOCKED
                    """,
                    (job_id,),
                )
                job = await cur.fetchone()
                if not job:
                    return None
                await cur.execute(
                    """
                    UPDATE education_processing_jobs
                    SET status = 'processing', attempt_count = attempt_count + 1,
                        claimed_at = NOW(), claim_expires_at = NOW() + INTERVAL '15 minutes',
                        updated_at = NOW()
                    WHERE job_id = %s
                    RETURNING attempt_count
                    """,
                    (job_id,),
                )
                claimed_attempt = await cur.fetchone()
                await cur.execute(
                    """
                    SELECT sources.document_id, sources.producer_job_id,
                           sources.primary_artifact_id, sources.position,
                           sources.source_filename, sources.source_media_type,
                           sources.source_format, sources.parser_id,
                           sources.parser_name, sources.parser_version,
                           sources.parse_completed_at, sources.primary_sha256,
                           sources.snapshot_prefix, sources.asset_manifest
                    FROM education_textbook_artifact_sources AS sources
                    WHERE sources.version_id = %s
                    ORDER BY sources.position
                    """,
                    (job["version_id"],),
                )
                sources = [dict(row) for row in await cur.fetchall()]
                if sources:
                    result = dict(job)
                    result["attempt_count"] = claimed_attempt["attempt_count"]
                    result["sources"] = sources
                    return result

                await cur.execute(
                    """
                    SELECT assets.asset_id, assets.storage_key, assets.original_filename, assets.content_type, assets.size_bytes
                    FROM education_textbook_sources AS sources
                    JOIN education_assets AS assets ON assets.asset_id = sources.asset_id
                    WHERE sources.version_id = %s
                    ORDER BY sources.position
                    """,
                    (job["version_id"],),
                )
                sources = [dict(row) for row in await cur.fetchall()]
    result = dict(job)
    result["attempt_count"] = claimed_attempt["attempt_count"]
    result["sources"] = sources
    return result


async def complete_textbook_processing_job(
    *,
    job_id: str,
    version_id: str,
    attempt_count: int,
    bundle_prefix: str,
    extractor: dict[str, str],
    chapters: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Persist reviewed candidate material only while the claimed job is still processing."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT 1 FROM education_processing_jobs
                    WHERE job_id = %s AND version_id = %s AND status = 'processing'
                      AND attempt_count = %s
                    FOR UPDATE
                    """,
                    (job_id, version_id, attempt_count),
                )
                if not await cur.fetchone():
                    return None
                for chapter in chapters:
                    chapter_id = str(uuid4())
                    await cur.execute(
                        """
                        INSERT INTO education_textbook_chapters (
                            chapter_id, version_id, position, slug, title,
                            page_start, page_end, markdown, markdown_key
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            chapter_id,
                            version_id,
                            chapter["position"],
                            chapter["slug"],
                            chapter["title"],
                            chapter.get("page_start"),
                            chapter.get("page_end"),
                            chapter["markdown"],
                            chapter["markdown_key"],
                        ),
                    )
                await cur.execute(
                    """
                    UPDATE education_textbook_versions
                    SET status = 'review', bundle_prefix = %s, processing_error = NULL,
                        extractor_name = %s, extractor_version = %s, reviewed_at = NOW()
                    WHERE version_id = %s AND status = 'processing'
                    """,
                    (
                        bundle_prefix,
                        extractor["name"],
                        extractor["version"],
                        version_id,
                    ),
                )
                await cur.execute(
                    """
                    UPDATE education_processing_jobs
                    SET status = 'completed', completed_at = NOW(), claim_expires_at = NULL,
                        updated_at = NOW(), error_message = NULL
                    WHERE job_id = %s AND version_id = %s AND status = 'processing'
                      AND attempt_count = %s
                    RETURNING job_id, version_id, status, attempt_count, completed_at
                    """,
                    (job_id, version_id, attempt_count),
                )
                row = await cur.fetchone()
    return dict(row) if row else None


async def fail_textbook_processing_job(
    *, job_id: str, version_id: str, attempt_count: int, error_message: str
) -> None:
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE education_processing_jobs
                    SET status = 'failed', error_message = %s, claim_expires_at = NULL,
                        updated_at = NOW()
                    WHERE job_id = %s AND version_id = %s AND status = 'processing'
                      AND attempt_count = %s
                    """,
                    (error_message[:10_000], job_id, version_id, attempt_count),
                )
                await cur.execute(
                    """
                    UPDATE education_textbook_versions AS versions
                    SET status = 'failed', processing_error = %s
                    FROM education_processing_jobs AS jobs
                    WHERE versions.version_id = %s AND versions.status = 'processing'
                      AND jobs.job_id = %s AND jobs.version_id = versions.version_id
                      AND jobs.status = 'failed' AND jobs.attempt_count = %s
                    """,
                    (error_message[:10_000], version_id, job_id, attempt_count),
                )


async def retry_textbook_processing_job(
    *, parent_user_id: str, job_id: str
) -> dict[str, Any] | None:
    """Requeue only the parent's failed job; its frozen version and sources remain unchanged."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE education_processing_jobs AS jobs
                    SET status = 'queued', error_message = NULL, claimed_at = NULL,
                        claim_expires_at = NULL, completed_at = NULL, updated_at = NOW()
                    FROM education_textbook_versions AS versions
                    JOIN education_textbooks AS textbooks ON textbooks.textbook_id = versions.textbook_id
                    JOIN education_memberships AS memberships ON memberships.household_id = textbooks.household_id
                    WHERE jobs.job_id = %s AND jobs.version_id = versions.version_id
                      AND memberships.user_id = %s AND memberships.role = 'parent'
                      AND (
                        (jobs.status = 'failed' AND versions.status = 'failed')
                        OR (
                          jobs.status = 'processing' AND versions.status = 'processing'
                          AND jobs.claim_expires_at <= NOW()
                        )
                      )
                    RETURNING jobs.job_id, jobs.version_id, jobs.status, jobs.attempt_count, jobs.created_at
                    """,
                    (job_id, parent_user_id),
                )
                job = await cur.fetchone()
                if not job:
                    return None
                await cur.execute(
                    """
                    UPDATE education_textbook_versions
                    SET status = 'processing', processing_error = NULL
                    WHERE version_id = %s AND status IN ('failed', 'processing')
                    """,
                    (job["version_id"],),
                )
    return dict(job)


async def list_textbooks_for_parent(user_id: str) -> list[dict[str, Any]]:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT textbooks.textbook_id, textbooks.household_id, textbooks.title, textbooks.slug,
                       textbooks.created_by_user_id, textbooks.created_at,
                       latest.version_id AS latest_version_id, latest.sequence AS latest_version_sequence,
                       latest.status AS latest_version_status,
                       COALESCE(latest.chapter_count, 0) AS chapter_count,
                       COALESCE(latest.assignment_count, 0) AS assignment_count
                FROM education_textbooks AS textbooks
                JOIN education_memberships AS memberships ON memberships.household_id = textbooks.household_id
                LEFT JOIN LATERAL (
                    SELECT versions.version_id, versions.sequence, versions.status,
                           (SELECT COUNT(*) FROM education_textbook_chapters WHERE version_id = versions.version_id) AS chapter_count,
                           (SELECT COUNT(*) FROM education_textbook_assignments AS assignments
                            JOIN education_textbook_publications AS publications ON publications.publication_id = assignments.publication_id
                            WHERE publications.version_id = versions.version_id) AS assignment_count
                    FROM education_textbook_versions AS versions
                    WHERE versions.textbook_id = textbooks.textbook_id
                    ORDER BY versions.sequence DESC
                    LIMIT 1
                ) AS latest ON TRUE
                WHERE memberships.user_id = %s AND memberships.role = 'parent'
                ORDER BY textbooks.created_at DESC
                """,
                (user_id,),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_textbook_for_parent(
    *, parent_user_id: str, textbook_id: str
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT textbooks.textbook_id, textbooks.household_id, textbooks.title, textbooks.slug,
                       textbooks.created_by_user_id, textbooks.created_at
                FROM education_textbooks AS textbooks
                JOIN education_memberships AS memberships ON memberships.household_id = textbooks.household_id
                WHERE textbooks.textbook_id = %s AND memberships.user_id = %s AND memberships.role = 'parent'
                """,
                (textbook_id, parent_user_id),
            )
            textbook = await cur.fetchone()
            if not textbook:
                return None
            await cur.execute(
                """
                SELECT versions.version_id, versions.sequence, versions.status, versions.extractor_name,
                       versions.extractor_version, versions.processing_error, versions.created_at,
                       versions.reviewed_at, versions.published_at,
                       publications.publication_id,
                       COALESCE(jobs.job_id::text, '') AS processing_job_id,
                       jobs.status AS processing_job_status, jobs.attempt_count AS processing_attempt_count,
                       jobs.error_message AS processing_error_message,
                       COALESCE((SELECT COUNT(*) FROM education_textbook_chapters WHERE version_id = versions.version_id), 0) AS chapter_count,
                       publications.publication_id IS NOT NULL AS is_published
                FROM education_textbook_versions AS versions
                LEFT JOIN education_processing_jobs AS jobs ON jobs.version_id = versions.version_id
                LEFT JOIN education_textbook_publications AS publications ON publications.version_id = versions.version_id
                WHERE versions.textbook_id = %s
                ORDER BY versions.sequence DESC
                """,
                (textbook["textbook_id"],),
            )
            versions = [dict(row) for row in await cur.fetchall()]
            for version in versions:
                await cur.execute(
                    """
                    SELECT sources.position,
                           sources.document_id,
                           sources.producer_job_id,
                           sources.primary_artifact_id,
                           sources.source_filename AS filename,
                           sources.source_media_type AS media_type,
                           sources.source_format AS format,
                           sources.parser_id,
                           sources.parser_name,
                           sources.parser_version,
                           sources.parse_completed_at,
                           sources.primary_sha256,
                           COALESCE(
                               documents.owner_user_id = %s,
                               FALSE
                           ) AS document_accessible,
                           documents.document_id IS NULL AS document_deleted,
                           FALSE AS legacy,
                           NULL::uuid AS asset_id,
                           NULL::varchar AS original_filename,
                           NULL::varchar AS content_type,
                           NULL::bigint AS size_bytes
                    FROM education_textbook_artifact_sources AS sources
                    LEFT JOIN documents
                      ON documents.document_id = sources.document_id
                    WHERE sources.version_id = %s
                    ORDER BY sources.position
                    """,
                    (
                        parent_user_id,
                        version["version_id"],
                    ),
                )
                version["sources"] = [dict(row) for row in await cur.fetchall()]
                await cur.execute(
                    """
                    SELECT chapters.chapter_id, chapters.position, chapters.slug, chapters.title,
                           chapters.page_start, chapters.page_end, chapters.markdown
                    FROM education_textbook_chapters AS chapters
                    WHERE chapters.version_id = %s ORDER BY chapters.position
                    """,
                    (version["version_id"],),
                )
                chapters = [dict(row) for row in await cur.fetchall()]
                for chapter in chapters:
                    chapter["questions"] = []
                version["chapters"] = chapters
                if version["publication_id"]:
                    await cur.execute(
                        """
                        SELECT assignments.assignment_id, assignments.student_user_id, assignments.created_at,
                               student_memberships.display_name AS student_name
                        FROM education_textbook_assignments AS assignments
                        JOIN education_memberships AS student_memberships
                          ON student_memberships.user_id = assignments.student_user_id
                         AND student_memberships.household_id = %s
                         AND student_memberships.role = 'student'
                        WHERE assignments.publication_id = %s ORDER BY assignments.created_at
                        """,
                        (textbook["household_id"], version["publication_id"]),
                    )
                    version["assignments"] = [dict(row) for row in await cur.fetchall()]
                else:
                    version["assignments"] = []
    result = dict(textbook)
    result["versions"] = versions
    return result


async def get_processing_job_for_parent(
    *, parent_user_id: str, job_id: str
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.job_id, jobs.version_id, jobs.status
                FROM education_processing_jobs AS jobs
                JOIN education_textbook_versions AS versions ON versions.version_id = jobs.version_id
                JOIN education_textbooks AS textbooks ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships ON memberships.household_id = textbooks.household_id
                WHERE jobs.job_id = %s AND memberships.user_id = %s AND memberships.role = 'parent'
                """,
                (job_id, parent_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def publish_textbook_structure(
    *,
    parent_user_id: str,
    version_id: str,
    structure_id: str,
) -> dict[str, Any] | None:
    """Freeze one accepted structure and every approved lesson revision."""
    publication_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT versions.version_id, structures.structure_id
                    FROM education_textbook_structures AS structures
                    JOIN education_textbook_versions AS versions
                      ON versions.version_id = structures.version_id
                    JOIN education_textbooks AS textbooks
                      ON textbooks.textbook_id = versions.textbook_id
                    JOIN education_memberships AS memberships
                      ON memberships.household_id = textbooks.household_id
                    WHERE versions.version_id = %s
                      AND structures.structure_id = %s
                      AND structures.status = 'accepted'
                      AND versions.status = 'review'
                      AND memberships.user_id = %s
                      AND memberships.role = 'parent'
                    FOR UPDATE OF versions, structures
                    """,
                    (
                        version_id,
                        structure_id,
                        parent_user_id,
                    ),
                )
                if not await cur.fetchone():
                    return None
                await cur.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM education_structure_knowledge_points AS knowledge_points
                    JOIN education_structure_units AS units
                      ON units.unit_id = knowledge_points.unit_id
                    WHERE units.structure_id = %s
                    """,
                    (structure_id,),
                )
                total_count = int((await cur.fetchone())["count"])
                if total_count <= 0:
                    return None
                await cur.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM education_structure_knowledge_points AS knowledge_points
                    JOIN education_structure_units AS units
                      ON units.unit_id = knowledge_points.unit_id
                    JOIN education_kp_lessons AS lessons
                      ON lessons.knowledge_point_id =
                         knowledge_points.knowledge_point_id
                    JOIN education_kp_lesson_revisions AS revisions
                      ON revisions.revision_id = lessons.latest_revision_id
                    WHERE units.structure_id = %s
                      AND knowledge_points.status = 'accepted'
                      AND lessons.status = 'approved'
                    """,
                    (structure_id,),
                )
                approved_count = int((await cur.fetchone())["count"])
                if approved_count != total_count:
                    return None
                await cur.execute(
                    """
                    SELECT knowledge_points.knowledge_point_id,
                           lessons.latest_revision_id AS lesson_revision_id
                    FROM education_structure_knowledge_points AS knowledge_points
                    JOIN education_structure_units AS units
                      ON units.unit_id = knowledge_points.unit_id
                    JOIN education_kp_lessons AS lessons
                      ON lessons.knowledge_point_id =
                         knowledge_points.knowledge_point_id
                    WHERE units.structure_id = %s
                      AND knowledge_points.status = 'accepted'
                      AND lessons.status = 'approved'
                    ORDER BY units.position, knowledge_points.position
                    """,
                    (structure_id,),
                )
                lessons = [dict(row) for row in await cur.fetchall()]
                await cur.execute(
                    """
                    INSERT INTO education_textbook_publications (
                        publication_id, version_id, structure_id,
                        published_by_user_id
                    ) VALUES (%s, %s, %s, %s)
                    RETURNING publication_id, version_id, structure_id,
                              published_by_user_id, created_at
                    """,
                    (
                        publication_id,
                        version_id,
                        structure_id,
                        parent_user_id,
                    ),
                )
                publication = dict(await cur.fetchone())
                for lesson in lessons:
                    await cur.execute(
                        """
                        INSERT INTO education_publication_kp_lessons (
                            publication_id, knowledge_point_id,
                            lesson_revision_id
                        ) VALUES (%s, %s, %s)
                        """,
                        (
                            publication_id,
                            lesson["knowledge_point_id"],
                            lesson["lesson_revision_id"],
                        ),
                    )
                await cur.execute(
                    """
                    UPDATE education_textbook_versions
                    SET status = 'published', published_at = NOW()
                    WHERE version_id = %s AND status = 'review'
                    """,
                    (version_id,),
                )
    return publication


async def assign_textbook_publication(
    *, parent_user_id: str, publication_id: str, student_user_id: str
) -> dict[str, Any] | None:
    assignment_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT publications.publication_id, textbooks.household_id
                    FROM education_textbook_publications AS publications
                    JOIN education_textbook_versions AS versions ON versions.version_id = publications.version_id
                    JOIN education_textbooks AS textbooks ON textbooks.textbook_id = versions.textbook_id
                    JOIN education_memberships AS parent_memberships ON parent_memberships.household_id = textbooks.household_id
                    JOIN education_memberships AS student_memberships ON student_memberships.household_id = textbooks.household_id
                    WHERE publications.publication_id = %s AND parent_memberships.user_id = %s
                      AND parent_memberships.role = 'parent' AND student_memberships.user_id = %s
                      AND student_memberships.role = 'student'
                    """,
                    (publication_id, parent_user_id, student_user_id),
                )
                if not await cur.fetchone():
                    return None
                await cur.execute(
                    """
                    INSERT INTO education_textbook_assignments (
                        assignment_id, publication_id, student_user_id, assigned_by_user_id
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (publication_id, student_user_id) DO UPDATE SET assigned_by_user_id = EXCLUDED.assigned_by_user_id
                    RETURNING assignment_id, publication_id, student_user_id, assigned_by_user_id, created_at
                    """,
                    (assignment_id, publication_id, student_user_id, parent_user_id),
                )
                row = await cur.fetchone()
    return dict(row) if row else None


async def list_student_assignments(student_user_id: str) -> list[dict[str, Any]]:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT assignments.assignment_id, assignments.publication_id, assignments.created_at,
                       textbooks.title AS textbook_title, textbooks.slug AS textbook_slug,
                       versions.sequence AS version_sequence,
                       COALESCE((
                           SELECT COUNT(*)
                           FROM education_structure_knowledge_points AS knowledge_points
                           JOIN education_structure_units AS units
                             ON units.unit_id = knowledge_points.unit_id
                           WHERE units.structure_id = publications.structure_id
                       ), 0) AS chapter_count,
                       COALESCE((SELECT COUNT(*) FROM education_learning_kp_progress AS progress
                                 WHERE progress.assignment_id = assignments.assignment_id
                                   AND progress.status = 'read'), 0) AS completed_chapter_count
                FROM education_textbook_assignments AS assignments
                JOIN education_textbook_publications AS publications ON publications.publication_id = assignments.publication_id
                JOIN education_textbook_versions AS versions ON versions.version_id = publications.version_id
                JOIN education_textbooks AS textbooks ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.user_id = assignments.student_user_id
                 AND memberships.household_id = textbooks.household_id
                WHERE assignments.student_user_id = %s AND memberships.role = 'student'
                ORDER BY assignments.created_at DESC
                """,
                (student_user_id,),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_student_published_structure(
    *, student_user_id: str, assignment_id: str
) -> dict[str, Any] | None:
    """Return only the structure frozen by the student's assignment publication."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT assignments.assignment_id,
                       assignments.publication_id,
                       textbooks.textbook_id,
                       textbooks.title AS textbook_title,
                       textbooks.slug AS textbook_slug,
                       versions.sequence AS version_sequence,
                       structures.structure_id,
                       structures.sequence AS structure_sequence
                FROM education_textbook_assignments AS assignments
                JOIN education_textbook_publications AS publications
                  ON publications.publication_id = assignments.publication_id
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = publications.version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_textbook_structures AS structures
                  ON structures.structure_id = publications.structure_id
                JOIN education_memberships AS memberships
                  ON memberships.user_id = assignments.student_user_id
                 AND memberships.household_id = textbooks.household_id
                WHERE assignments.assignment_id = %s
                  AND assignments.student_user_id = %s
                  AND memberships.role = 'student'
                """,
                (assignment_id, student_user_id),
            )
            assignment = await cur.fetchone()
            if not assignment:
                return None
            result = dict(assignment)
            await cur.execute(
                """
                SELECT units.unit_id, units.position, units.slug, units.title,
                       units.summary, units.unit_type
                FROM education_structure_units AS units
                WHERE units.structure_id = %s
                ORDER BY units.position
                """,
                (result["structure_id"],),
            )
            units = [dict(row) for row in await cur.fetchall()]
            await cur.execute(
                """
                SELECT knowledge_points.knowledge_point_id,
                       knowledge_points.unit_id,
                       knowledge_points.position,
                       knowledge_points.slug,
                       knowledge_points.title,
                       knowledge_points.summary,
                       CASE WHEN frozen.lesson_revision_id IS NULL
                            THEN FALSE ELSE TRUE END AS has_lesson
                FROM education_structure_knowledge_points AS knowledge_points
                JOIN education_structure_units AS units
                  ON units.unit_id = knowledge_points.unit_id
                LEFT JOIN education_publication_kp_lessons AS frozen
                  ON frozen.publication_id = %s
                 AND frozen.knowledge_point_id =
                     knowledge_points.knowledge_point_id
                WHERE units.structure_id = %s
                ORDER BY units.position, knowledge_points.position
                """,
                (result["publication_id"], result["structure_id"]),
            )
            knowledge_points = [dict(row) for row in await cur.fetchall()]
            by_unit: dict[str, list[dict[str, Any]]] = {}
            for knowledge_point in knowledge_points:
                by_unit.setdefault(str(knowledge_point["unit_id"]), []).append(
                    knowledge_point
                )
            for unit in units:
                unit["knowledge_points"] = by_unit.get(str(unit["unit_id"]), [])
            result["units"] = units
    return result


async def get_student_published_kp_lesson(
    *, student_user_id: str, assignment_id: str, knowledge_point_id: str
) -> dict[str, Any] | None:
    """Return one lesson revision frozen by the student's assignment."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT assignments.assignment_id,
                       knowledge_points.knowledge_point_id,
                       knowledge_points.title AS knowledge_point_title,
                       units.unit_id,
                       units.title AS unit_title,
                       revisions.revision_id,
                       revisions.revision,
                       revisions.format,
                       revisions.content_key,
                       revisions.content_sha256,
                       revisions.size_bytes
                FROM education_textbook_assignments AS assignments
                JOIN education_textbook_publications AS publications
                  ON publications.publication_id = assignments.publication_id
                JOIN education_publication_kp_lessons AS frozen
                  ON frozen.publication_id = publications.publication_id
                 AND frozen.knowledge_point_id = %s
                JOIN education_kp_lesson_revisions AS revisions
                  ON revisions.revision_id = frozen.lesson_revision_id
                JOIN education_structure_knowledge_points AS knowledge_points
                  ON knowledge_points.knowledge_point_id =
                     frozen.knowledge_point_id
                JOIN education_structure_units AS units
                  ON units.unit_id = knowledge_points.unit_id
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = publications.version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.user_id = assignments.student_user_id
                 AND memberships.household_id = textbooks.household_id
                WHERE assignments.assignment_id = %s
                  AND assignments.student_user_id = %s
                  AND memberships.role = 'student'
                """,
                (knowledge_point_id, assignment_id, student_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def upsert_kp_progress(
    *,
    student_user_id: str,
    assignment_id: str,
    knowledge_point_id: str,
    status: str,
) -> dict[str, Any] | None:
    """Upsert progress only when the knowledge point is in the assignment snapshot."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO education_learning_kp_progress (
                    assignment_id, knowledge_point_id, status, started_at,
                    completed_at, updated_at
                )
                SELECT assignments.assignment_id, frozen.knowledge_point_id,
                       %s,
                       CASE WHEN %s = 'learning' THEN NOW() ELSE NULL END,
                       CASE WHEN %s IN ('read', 'review_recommended')
                            THEN NOW() ELSE NULL END,
                       NOW()
                FROM education_textbook_assignments AS assignments
                JOIN education_textbook_publications AS publications
                  ON publications.publication_id = assignments.publication_id
                JOIN education_publication_kp_lessons AS frozen
                  ON frozen.publication_id = publications.publication_id
                 AND frozen.knowledge_point_id = %s
                WHERE assignments.assignment_id = %s
                  AND assignments.student_user_id = %s
                ON CONFLICT (assignment_id, knowledge_point_id) DO UPDATE
                SET status = EXCLUDED.status,
                    started_at = COALESCE(
                        education_learning_kp_progress.started_at,
                        EXCLUDED.started_at
                    ),
                    completed_at = COALESCE(
                        EXCLUDED.completed_at,
                        education_learning_kp_progress.completed_at
                    ),
                    updated_at = NOW()
                RETURNING assignment_id, knowledge_point_id, status,
                          started_at, completed_at, updated_at
                """,
                (
                    status,
                    status,
                    status,
                    knowledge_point_id,
                    assignment_id,
                    student_user_id,
                ),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def list_learning_items(
    *,
    student_user_id: str,
    assignment_id: str,
    unit_id: str | None = None,
    knowledge_point_id: str | None = None,
) -> list[dict[str, Any]]:
    """List student-owned learning items within one assignment."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT items.item_id, items.assignment_id, items.unit_id,
                       items.knowledge_point_id, items.kind, items.content,
                       items.source_anchor, items.created_at, items.updated_at
                FROM education_learning_items AS items
                JOIN education_textbook_assignments AS assignments
                  ON assignments.assignment_id = items.assignment_id
                WHERE items.assignment_id = %s
                  AND assignments.student_user_id = %s
                  AND (%s IS NULL OR items.unit_id = %s)
                  AND (
                      %s IS NULL
                      OR items.knowledge_point_id = %s
                  )
                ORDER BY items.created_at DESC, items.item_id
                """,
                (
                    assignment_id,
                    student_user_id,
                    unit_id,
                    unit_id,
                    knowledge_point_id,
                    knowledge_point_id,
                ),
            )
            return [dict(row) for row in await cur.fetchall()]


async def create_learning_item(
    *,
    student_user_id: str,
    assignment_id: str,
    unit_id: str | None,
    knowledge_point_id: str | None,
    kind: str,
    content: str,
    source_anchor: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Create one item only when its target belongs to the published assignment."""
    item_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO education_learning_items (
                    item_id, assignment_id, unit_id, knowledge_point_id,
                    kind, content, source_anchor
                )
                SELECT %s, assignments.assignment_id, %s, %s, %s, %s, %s
                FROM education_textbook_assignments AS assignments
                JOIN education_textbook_publications AS publications
                  ON publications.publication_id = assignments.publication_id
                JOIN education_textbook_structures AS structures
                  ON structures.structure_id = publications.structure_id
                WHERE assignments.assignment_id = %s
                  AND assignments.student_user_id = %s
                  AND (
                      %s IS NULL
                      OR EXISTS (
                          SELECT 1
                          FROM education_structure_units AS units
                          WHERE units.unit_id = %s
                            AND units.structure_id = structures.structure_id
                      )
                  )
                  AND (
                      %s IS NULL
                      OR EXISTS (
                          SELECT 1
                          FROM education_structure_knowledge_points AS knowledge_points
                          JOIN education_structure_units AS units
                            ON units.unit_id = knowledge_points.unit_id
                          WHERE knowledge_points.knowledge_point_id = %s
                            AND units.structure_id = structures.structure_id
                      )
                  )
                RETURNING item_id, assignment_id, unit_id, knowledge_point_id,
                          kind, content, source_anchor, created_at, updated_at
                """,
                (
                    item_id,
                    unit_id,
                    knowledge_point_id,
                    kind,
                    content,
                    Json(source_anchor) if source_anchor is not None else None,
                    assignment_id,
                    student_user_id,
                    unit_id,
                    unit_id,
                    knowledge_point_id,
                    knowledge_point_id,
                ),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def update_learning_item(
    *,
    student_user_id: str,
    item_id: str,
    content: str,
    source_anchor: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Update item content without allowing assignment ownership changes."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE education_learning_items AS items
                SET content = %s, source_anchor = %s, updated_at = NOW()
                FROM education_textbook_assignments AS assignments
                WHERE items.item_id = %s
                  AND assignments.assignment_id = items.assignment_id
                  AND assignments.student_user_id = %s
                RETURNING items.item_id, items.assignment_id, items.unit_id,
                          items.knowledge_point_id, items.kind, items.content,
                          items.source_anchor, items.created_at, items.updated_at
                """,
                (
                    content,
                    Json(source_anchor) if source_anchor is not None else None,
                    item_id,
                    student_user_id,
                ),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def delete_learning_item(
    *, student_user_id: str, item_id: str
) -> dict[str, Any] | None:
    """Delete one student-owned item."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                DELETE FROM education_learning_items AS items
                USING education_textbook_assignments AS assignments
                WHERE items.item_id = %s
                  AND assignments.assignment_id = items.assignment_id
                  AND assignments.student_user_id = %s
                RETURNING items.item_id
                """,
                (item_id, student_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None
