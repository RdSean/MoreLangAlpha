"""Raw PostgreSQL persistence for versioned family textbook learning."""

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Json

from src.server.database.pool import get_db_connection


@dataclass(frozen=True)
class TeachingInputHashes:
    """Immutable provenance recorded before a managed teaching attempt starts."""

    input_manifest_sha256: str
    book_to_skill_sha256: str
    knowledge_guy_sha256: str
    adapter_prompt_sha256: str


_TEACHING_PROGRESS_PHASES = frozenset(
    {
        "building_skill",
        "generating_teaching",
        "planning",
        "chapter_mapping",
        "concept_linking",
        "coverage_audit",
        "practice_build",
        "teaching_build",
        "bundle_assembling",
        "validating_bundle",
    }
)
_TEACHING_PROGRESS_ASSET_KINDS = frozenset(
    {"knowledge", "toolkit", "practice", "teaching"}
)
_TEACHING_PACKAGE_STATUS_BY_PROGRESS = {
    "building_skill": "building_skill",
    "generating_teaching": "generating_teaching",
    "planning": "preparing",
    "chapter_mapping": "building_skill",
    "concept_linking": "building_skill",
    "coverage_audit": "building_skill",
    "practice_build": "generating_teaching",
    "teaching_build": "generating_teaching",
    "bundle_assembling": "validating",
    "validating_bundle": "validating",
}
_TEACHING_PACKAGE_STATUS_RANK = {
    "preparing": 0,
    "building_skill": 1,
    "generating_teaching": 2,
    "validating": 3,
}
_TEACHING_PROGRESS_LABELS = {
    "planning": "正在规划知识资产加工",
    "chapter_mapping": "已完成章节映射",
    "concept_linking": "已完成概念关联",
    "coverage_audit": "已完成覆盖审计",
    "practice_build": "已完成练习构建",
    "teaching_build": "已完成教学材料生成",
    "bundle_assembling": "正在汇总教材资产",
    "validating_bundle": "正在校验教材资产",
    "building_skill": "已完成知识整理",
    "generating_teaching": "已完成教学材料生成",
}
_TEACHING_ARCHIVE_CALLBACK_LEASE_SECONDS = 360
_SAFE_PATH_COMPONENT = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,254}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class TextbookQueueValidationError(ValueError):
    """A textbook queue request failed before any database write."""


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
            raise TextbookQueueValidationError(
                "asset_manifest paths must be unique"
            )
        if not _SHA256.fullmatch(fields["sha256"]):
            raise TextbookQueueValidationError("asset_manifest sha256 is invalid")
        relative_paths.add(relative_path)
        normalized.append(fields)
    return normalized


def advance_teaching_package_status(*, current: str, target: str) -> str:
    """Keep autonomous progress events from moving the package phase backward."""
    current_rank = _TEACHING_PACKAGE_STATUS_RANK.get(current)
    target_rank = _TEACHING_PACKAGE_STATUS_RANK.get(target)
    if current_rank is None or target_rank is None or target_rank <= current_rank:
        return current
    return target


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
                       packages.teaching_package_id,
                       packages.sequence AS teaching_package_sequence,
                       packages.status,
                       publications.publication_id,
                       publications.publication_id IS NOT NULL AS is_published,
                       COALESCE(
                           packages.asset_manifest <> '{}'::jsonb,
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
                LEFT JOIN education_teaching_packages AS packages
                  ON packages.content_version_id = versions.version_id
                LEFT JOIN education_teaching_jobs AS jobs
                  ON jobs.teaching_package_id = packages.teaching_package_id
                LEFT JOIN education_textbook_publications AS publications
                  ON publications.version_id = versions.version_id
                 AND publications.teaching_package_id =
                     packages.teaching_package_id
                WHERE documents.document_id = %s
                  AND documents.owner_user_id = %s
                ORDER BY sources.created_at,
                         textbooks.created_at,
                         versions.sequence,
                         sources.position,
                         packages.sequence NULLS LAST,
                         packages.teaching_package_id NULLS LAST
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


async def queue_teaching_package(
    *,
    parent_user_id: str,
    content_version_id: str,
    hashes: TeachingInputHashes,
    job_id: str | None = None,
) -> dict[str, Any] | None:
    """Freeze one parent-owned reviewable content version into a queued package."""
    package_id = str(uuid4())
    generated_job_id = str(UUID(job_id)) if job_id else str(uuid4())
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
                      AND versions.status = 'review'
                      AND memberships.user_id = %s
                      AND memberships.role = 'parent'
                    FOR UPDATE OF versions
                    """,
                    (content_version_id, parent_user_id),
                )
                version = await cur.fetchone()
                if not version:
                    return None
                await cur.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence
                    FROM education_teaching_packages
                    WHERE content_version_id = %s
                    """,
                    (content_version_id,),
                )
                sequence = (await cur.fetchone())["sequence"]
                await cur.execute(
                    """
                    INSERT INTO education_teaching_packages (
                        teaching_package_id, content_version_id, sequence, status,
                        input_manifest_sha256, book_to_skill_sha256,
                        knowledge_guy_sha256, adapter_prompt_sha256,
                        created_by_user_id
                    ) VALUES (%s, %s, %s, 'queued', %s, %s, %s, %s, %s)
                    RETURNING teaching_package_id, content_version_id, status, sequence
                    """,
                    (
                        package_id,
                        content_version_id,
                        sequence,
                        hashes.input_manifest_sha256,
                        hashes.book_to_skill_sha256,
                        hashes.knowledge_guy_sha256,
                        hashes.adapter_prompt_sha256,
                        parent_user_id,
                    ),
                )
                package = dict(await cur.fetchone())
                await cur.execute(
                    """
                    INSERT INTO education_teaching_jobs (job_id, teaching_package_id, status)
                    VALUES (%s, %s, 'queued')
                    RETURNING job_id, teaching_package_id, status
                    """,
                    (generated_job_id, package_id),
                )
                job = dict(await cur.fetchone())
    package["job_id"] = job["job_id"]
    return package


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
                            row.get("producer_job_id")
                            or row["content_chapter_id"]
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


async def get_teaching_asset_review_for_parent(
    *, parent_user_id: str, teaching_package_id: str
) -> dict[str, Any] | None:
    """Authorize a parent before returning the private v2 bundle locator."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT packages.teaching_package_id, packages.content_version_id,
                       packages.bundle_prefix, packages.asset_manifest
                FROM education_teaching_packages AS packages
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = packages.content_version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                WHERE packages.teaching_package_id = %s
                  AND packages.status = 'review'
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                """,
                (teaching_package_id, parent_user_id),
            )
            package = await cur.fetchone()
            if not package:
                return None
            result = dict(package)
            await cur.execute(
                """
                SELECT chapter_id AS content_chapter_id, position, slug, title
                FROM education_textbook_chapters
                WHERE version_id = %s
                ORDER BY position
                """,
                (result["content_version_id"],),
            )
            result["chapters"] = [dict(row) for row in await cur.fetchall()]
    return result


async def get_teaching_job_projection_for_parent(
    *, parent_user_id: str, job_id: str
) -> dict[str, Any] | None:
    """Read the whitelisted product projection for one household parent only."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.job_id, jobs.teaching_package_id, packages.content_version_id,
                       jobs.status, packages.status AS phase, jobs.attempt_count,
                       jobs.latest_attempt_id,
                       jobs.error_message, packages.error_message AS package_error_message,
                       jobs.created_at, jobs.completed_at,
                       attempts.heartbeat_at AS last_heartbeat_at,
                       COALESCE((
                           SELECT COUNT(*)
                           FROM education_textbook_chapters AS chapters
                           WHERE chapters.version_id = packages.content_version_id
                       ), 0) AS total_chapter_count,
                       CASE
                           WHEN packages.status IN ('validating', 'review') THEN COALESCE((
                               SELECT COUNT(*)
                               FROM education_textbook_chapters AS chapters
                               WHERE chapters.version_id = packages.content_version_id
                           ), 0)
                           WHEN packages.status = 'building_skill' THEN COALESCE((
                               SELECT COUNT(DISTINCT events.chapter_id)
                               FROM education_teaching_events AS events
                               WHERE events.attempt_id = jobs.latest_attempt_id
                                 AND events.phase IN (
                                     'building_skill', 'chapter_mapping',
                                     'concept_linking', 'coverage_audit'
                                 )
                           ), 0)
                           WHEN packages.status = 'generating_teaching' THEN COALESCE((
                               SELECT COUNT(DISTINCT events.chapter_id)
                               FROM education_teaching_events AS events
                               WHERE events.attempt_id = jobs.latest_attempt_id
                                 AND events.phase IN (
                                     'generating_teaching', 'practice_build', 'teaching_build'
                                 )
                           ), 0)
                           ELSE 0
                       END AS completed_chapter_count
                FROM education_teaching_jobs AS jobs
                JOIN education_teaching_packages AS packages
                  ON packages.teaching_package_id = jobs.teaching_package_id
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = packages.content_version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                LEFT JOIN education_teaching_attempts AS attempts
                  ON attempts.attempt_id = jobs.latest_attempt_id
                WHERE jobs.job_id = %s
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                """,
                (job_id, parent_user_id),
            )
            job = await cur.fetchone()
            if not job:
                return None
            result = dict(job)
            latest_attempt_id = result.get("latest_attempt_id")
            if latest_attempt_id:
                await cur.execute(
                    """
                    SELECT sequence, phase, summary, chapter_id, asset_kind, created_at
                    FROM education_teaching_events
                    WHERE attempt_id = %s
                    ORDER BY sequence
                    """,
                    (latest_attempt_id,),
                )
                result["events"] = [dict(row) for row in await cur.fetchall()]
            else:
                result["events"] = []
            await cur.execute(
                """
                SELECT attempt_id, root_run_id, previous_attempt_id, status,
                       started_at, heartbeat_at, completed_at
                FROM education_teaching_attempts
                WHERE job_id = %s
                ORDER BY started_at DESC
                """,
                (job_id,),
            )
            result["attempts"] = [dict(row) for row in await cur.fetchall()]
    return result


async def create_teaching_attempt(
    *, job_id: str, managed_workspace_id: str, managed_thread_id: str
) -> dict[str, Any] | None:
    """Reserve an attempt before the managed PTC root run is dispatched."""
    attempt_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT jobs.job_id, jobs.teaching_package_id, jobs.attempt_count,
                           jobs.latest_attempt_id AS previous_attempt_id
                    FROM education_teaching_jobs AS jobs
                    JOIN education_teaching_packages AS packages
                      ON packages.teaching_package_id = jobs.teaching_package_id
                    WHERE jobs.job_id = %s
                      AND jobs.status = 'queued'
                      AND packages.status = 'queued'
                    FOR UPDATE OF jobs, packages
                    """,
                    (job_id,),
                )
                job = await cur.fetchone()
                if not job:
                    return None
                await cur.execute(
                    """
                    UPDATE education_teaching_packages
                    SET status = 'preparing', error_code = NULL, error_message = NULL
                    WHERE teaching_package_id = %s AND status = 'queued'
                    """,
                    (job["teaching_package_id"],),
                )
                await cur.execute(
                    """
                    INSERT INTO education_teaching_attempts (
                        attempt_id, job_id, previous_attempt_id, managed_workspace_id,
                        managed_thread_id, status
                    ) VALUES (%s, %s, %s, %s, %s, 'preparing')
                    RETURNING attempt_id, job_id, managed_workspace_id, managed_thread_id,
                              previous_attempt_id, root_run_id
                    """,
                    (
                        attempt_id,
                        job_id,
                        job["previous_attempt_id"],
                        managed_workspace_id,
                        managed_thread_id,
                    ),
                )
                attempt = dict(await cur.fetchone())
                await cur.execute(
                    """
                    UPDATE education_teaching_jobs
                    SET status = 'preparing', attempt_count = attempt_count + 1,
                        latest_attempt_id = %s, claimed_at = NOW(), updated_at = NOW()
                    WHERE job_id = %s AND status = 'queued'
                    """,
                    (attempt_id, job_id),
                )
    return attempt


async def record_teaching_event(
    *,
    attempt_id: str,
    phase: str,
    summary: str,
    chapter_id: str | None = None,
    asset_kind: str | None = None,
) -> None:
    """Append one whitelisted progress event for the active frozen attempt only."""
    if phase not in _TEACHING_PROGRESS_PHASES:
        raise ValueError("Invalid teaching progress phase")
    if asset_kind is not None and asset_kind not in _TEACHING_PROGRESS_ASSET_KINDS:
        raise ValueError("Teaching progress asset kind is invalid")
    if chapter_id is not None:
        try:
            UUID(str(chapter_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("Teaching progress chapter is invalid") from exc

    event_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                allowed_package_statuses = [
                    "preparing",
                    "building_skill",
                    "generating_teaching",
                    "validating",
                ]
                if chapter_id is None:
                    await cur.execute(
                        """
                        SELECT attempts.job_id, packages.status AS package_status
                        FROM education_teaching_attempts AS attempts
                        JOIN education_teaching_jobs AS jobs ON jobs.job_id = attempts.job_id
                        JOIN education_teaching_packages AS packages
                          ON packages.teaching_package_id = jobs.teaching_package_id
                        WHERE attempts.attempt_id = %s
                          AND attempts.status = 'running'
                          AND jobs.latest_attempt_id = attempts.attempt_id
                          AND jobs.status = 'running'
                          AND packages.status = ANY(%s::varchar[])
                        FOR UPDATE OF attempts, jobs, packages
                        """,
                        (attempt_id, allowed_package_statuses),
                    )
                else:
                    await cur.execute(
                        """
                        SELECT attempts.job_id, chapters.position, packages.status AS package_status
                        FROM education_teaching_attempts AS attempts
                        JOIN education_teaching_jobs AS jobs ON jobs.job_id = attempts.job_id
                        JOIN education_teaching_packages AS packages
                          ON packages.teaching_package_id = jobs.teaching_package_id
                        JOIN education_textbook_chapters AS chapters
                          ON chapters.version_id = packages.content_version_id
                         AND chapters.chapter_id = %s
                        WHERE attempts.attempt_id = %s
                          AND attempts.status = 'running'
                          AND jobs.latest_attempt_id = attempts.attempt_id
                          AND jobs.status = 'running'
                          AND packages.status = ANY(%s::varchar[])
                        FOR UPDATE OF attempts, jobs, packages
                        """,
                        (chapter_id, attempt_id, allowed_package_statuses),
                    )
                active = await cur.fetchone()
                if not active:
                    return
                await cur.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence
                    FROM education_teaching_events
                    WHERE attempt_id = %s
                    """,
                    (attempt_id,),
                )
                sequence = (await cur.fetchone())["sequence"]
                # The caller passes untrusted model text. Only a local status
                # template reaches the database or parent-facing projection.
                del summary
                label = _TEACHING_PROGRESS_LABELS[phase]
                safe_summary = (
                    f"Agent 已报告：第 {active['position']} 章{label}"
                    if chapter_id is not None
                    else f"Agent 已报告：{label}"
                )
                await cur.execute(
                    """
                    INSERT INTO education_teaching_events (
                        event_id, attempt_id, sequence, phase, chapter_id, asset_kind, summary
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        event_id,
                        attempt_id,
                        sequence,
                        phase,
                        chapter_id,
                        asset_kind,
                        safe_summary,
                    ),
                )
                next_status = advance_teaching_package_status(
                    current=str(active["package_status"]),
                    target=_TEACHING_PACKAGE_STATUS_BY_PROGRESS[phase],
                )
                if next_status != active["package_status"]:
                    await cur.execute(
                        """
                        UPDATE education_teaching_packages AS packages
                        SET status = %s, error_code = NULL, error_message = NULL
                        FROM education_teaching_jobs AS jobs
                        WHERE jobs.job_id = %s
                          AND jobs.latest_attempt_id = %s
                          AND jobs.teaching_package_id = packages.teaching_package_id
                          AND packages.status = %s
                        """,
                        (
                            next_status,
                            active["job_id"],
                            attempt_id,
                            active["package_status"],
                        ),
                    )


async def settle_teaching_attempt(
    *,
    attempt_id: str,
    root_run_id: str,
    status: str,
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any] | None:
    """Settle a root-run attempt exactly once and project its safe status to the job."""
    if status not in {"running", "completed", "failed", "cancelled", "worker_lost"}:
        raise ValueError("Invalid teaching attempt status")
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE education_teaching_attempts
                    SET root_run_id = %s, status = %s, heartbeat_at = NOW(),
                        completed_at = CASE WHEN %s IN ('completed', 'failed', 'cancelled', 'worker_lost')
                                            THEN NOW() ELSE completed_at END,
                        error_code = %s, error_message = %s
                    WHERE attempt_id = %s AND status IN ('preparing', 'running')
                    RETURNING attempt_id, job_id, root_run_id, status
                    """,
                    (
                        root_run_id,
                        status,
                        status,
                        error_code,
                        error_message[:10_000] if error_message else None,
                        attempt_id,
                    ),
                )
                attempt = await cur.fetchone()
                if not attempt:
                    return None
                job_status = {
                    "running": "running",
                    "completed": "completed",
                    "failed": "failed",
                    "cancelled": "cancelled",
                    "worker_lost": "failed",
                }[status]
                await cur.execute(
                    """
                    UPDATE education_teaching_jobs
                    SET status = %s, completed_at = CASE WHEN %s IN ('completed', 'failed', 'cancelled')
                                                         THEN NOW() ELSE completed_at END,
                        error_code = %s, error_message = %s, updated_at = NOW()
                    WHERE job_id = %s AND latest_attempt_id = %s
                    """,
                    (
                        job_status,
                        job_status,
                        error_code,
                        error_message[:10_000] if error_message else None,
                        attempt["job_id"],
                        attempt_id,
                    ),
                )
                if status in {"failed", "cancelled", "worker_lost"}:
                    package_status = "cancelled" if status == "cancelled" else "failed"
                    await cur.execute(
                        """
                        UPDATE education_teaching_packages AS packages
                        SET status = %s, error_code = %s, error_message = %s
                        FROM education_teaching_jobs AS jobs
                        WHERE jobs.job_id = %s
                          AND jobs.latest_attempt_id = %s
                          AND jobs.teaching_package_id = packages.teaching_package_id
                          AND packages.status IN ('preparing', 'building_skill',
                                                  'generating_teaching', 'validating')
                        """,
                        (
                            package_status,
                            error_code,
                            error_message[:10_000] if error_message else None,
                            attempt["job_id"],
                            attempt_id,
                        ),
                    )
    return dict(attempt)


async def touch_teaching_attempt(*, attempt_id: str, root_run_id: str) -> bool:
    """Refresh a live managed attempt only while it remains the current root run."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE education_teaching_attempts AS attempts
                    SET heartbeat_at = NOW()
                    FROM education_teaching_jobs AS jobs
                    WHERE attempts.attempt_id = %s
                      AND attempts.root_run_id = %s
                      AND attempts.status = 'running'
                      AND jobs.job_id = attempts.job_id
                      AND jobs.latest_attempt_id = attempts.attempt_id
                      AND jobs.status = 'running'
                    RETURNING attempts.attempt_id
                    """,
                    (attempt_id, root_run_id),
                )
                return await cur.fetchone() is not None


async def begin_teaching_validation(
    *, attempt_id: str, root_run_id: str
) -> dict[str, Any] | None:
    """Claim the short candidate-validation phase before reading sandbox output.

    This is the cancellation race boundary: a parent cancellation that wins
    before this transition prevents any candidate download, archive or review
    projection by the terminal callback.
    """
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE education_teaching_attempts AS attempts
                    SET heartbeat_at = NOW()
                    FROM education_teaching_jobs AS jobs
                    JOIN education_teaching_packages AS packages
                      ON packages.teaching_package_id = jobs.teaching_package_id
                    WHERE attempts.attempt_id = %s
                      AND attempts.root_run_id = %s
                      AND attempts.status = 'running'
                      AND jobs.job_id = attempts.job_id
                      AND jobs.latest_attempt_id = attempts.attempt_id
                      AND jobs.status = 'running'
                      AND packages.status IN ('preparing', 'building_skill',
                                              'generating_teaching', 'validating')
                    RETURNING attempts.attempt_id, attempts.job_id
                    """,
                    (attempt_id, root_run_id),
                )
                attempt = await cur.fetchone()
                if not attempt:
                    return None
                await cur.execute(
                    """
                    UPDATE education_teaching_jobs
                    SET status = 'validating', updated_at = NOW()
                    WHERE job_id = %s AND latest_attempt_id = %s AND status = 'running'
                    """,
                    (attempt["job_id"], attempt_id),
                )
                await cur.execute(
                    """
                    UPDATE education_teaching_packages AS packages
                    SET status = 'validating'
                    FROM education_teaching_jobs AS jobs
                    WHERE jobs.job_id = %s
                      AND jobs.latest_attempt_id = %s
                      AND jobs.teaching_package_id = packages.teaching_package_id
                      AND packages.status IN ('preparing', 'building_skill',
                                              'generating_teaching', 'validating')
                    """,
                    (attempt["job_id"], attempt_id),
                )
    return dict(attempt)


async def store_teaching_archive_stage(
    *,
    attempt_id: str,
    job_id: str,
    root_run_id: str,
    validated_assets: dict[str, Any],
    output_bundle: bytes,
    output_bundle_sha256: str,
) -> bool:
    """Persist one service-validated candidate before private object writes."""
    if len(output_bundle_sha256) != 64:
        raise ValueError("Teaching archive stage digest is invalid")
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT attempts.attempt_id
                    FROM education_teaching_attempts AS attempts
                    JOIN education_teaching_jobs AS jobs ON jobs.job_id = attempts.job_id
                    JOIN education_teaching_packages AS packages
                      ON packages.teaching_package_id = jobs.teaching_package_id
                    WHERE attempts.attempt_id = %s
                      AND attempts.job_id = %s
                      AND attempts.root_run_id = %s
                      AND attempts.status = 'running'
                      AND jobs.latest_attempt_id = attempts.attempt_id
                      AND jobs.status = 'validating'
                      AND packages.status = 'validating'
                    FOR UPDATE OF attempts, jobs, packages
                    """,
                    (attempt_id, job_id, root_run_id),
                )
                if await cur.fetchone() is None:
                    return False
                await cur.execute(
                    """
                    INSERT INTO education_teaching_archive_staging (
                        attempt_id, job_id, root_run_id, validated_assets,
                        output_bundle, output_bundle_sha256
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (attempt_id) DO NOTHING
                    RETURNING attempt_id
                    """,
                    (
                        attempt_id,
                        job_id,
                        root_run_id,
                        Json(validated_assets),
                        output_bundle,
                        output_bundle_sha256,
                    ),
                )
                return await cur.fetchone() is not None


async def claim_teaching_archive_stage_for_parent(
    *, parent_user_id: str, job_id: str
) -> dict[str, Any] | None:
    """Claim a failed archive retry without minting a second PTC root run."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT stages.attempt_id, stages.job_id, stages.root_run_id,
                           stages.validated_assets, stages.output_bundle,
                           stages.output_bundle_sha256
                    FROM education_teaching_archive_staging AS stages
                    JOIN education_teaching_attempts AS attempts
                      ON attempts.attempt_id = stages.attempt_id
                    JOIN education_teaching_jobs AS jobs ON jobs.job_id = stages.job_id
                    JOIN education_teaching_packages AS packages
                      ON packages.teaching_package_id = jobs.teaching_package_id
                    JOIN education_textbook_versions AS versions
                      ON versions.version_id = packages.content_version_id
                    JOIN education_textbooks AS textbooks
                      ON textbooks.textbook_id = versions.textbook_id
                    JOIN education_memberships AS memberships
                      ON memberships.household_id = textbooks.household_id
                    WHERE stages.job_id = %s
                      AND memberships.user_id = %s
                      AND memberships.role = 'parent'
                      AND attempts.job_id = jobs.job_id
                      AND attempts.root_run_id = stages.root_run_id
                      AND attempts.status = 'failed'
                      AND jobs.latest_attempt_id = attempts.attempt_id
                      AND jobs.status = 'failed'
                      AND packages.status = 'failed'
                      AND (
                          (
                              attempts.error_code = 'managed_archive_pending'
                              AND jobs.error_code = 'managed_archive_pending'
                              AND packages.error_code = 'managed_archive_pending'
                          )
                          OR (
                              attempts.error_code = 'managed_terminal_unprojected'
                              AND jobs.error_code = 'managed_terminal_unprojected'
                              AND packages.error_code = 'managed_terminal_unprojected'
                          )
                      )
                    FOR UPDATE OF stages, attempts, jobs, packages
                    """,
                    (job_id, parent_user_id),
                )
                stage = await cur.fetchone()
                if not stage:
                    return None
                await cur.execute(
                    """
                    UPDATE education_teaching_archive_staging
                    SET created_at = NOW()
                    WHERE attempt_id = %s AND job_id = %s AND root_run_id = %s
                    """,
                    (stage["attempt_id"], stage["job_id"], stage["root_run_id"]),
                )
                await cur.execute(
                    """
                    UPDATE education_teaching_attempts
                    SET status = 'running', completed_at = NULL, heartbeat_at = NOW(),
                        error_code = NULL, error_message = NULL
                    WHERE attempt_id = %s AND status = 'failed'
                    """,
                    (stage["attempt_id"],),
                )
                await cur.execute(
                    """
                    UPDATE education_teaching_jobs
                    SET status = 'validating', completed_at = NULL,
                        error_code = NULL, error_message = NULL, updated_at = NOW()
                    WHERE job_id = %s AND latest_attempt_id = %s AND status = 'failed'
                    """,
                    (stage["job_id"], stage["attempt_id"]),
                )
                await cur.execute(
                    """
                    UPDATE education_teaching_packages AS packages
                    SET status = 'validating', error_code = NULL, error_message = NULL
                    FROM education_teaching_jobs AS jobs
                    WHERE jobs.job_id = %s
                      AND jobs.latest_attempt_id = %s
                      AND jobs.teaching_package_id = packages.teaching_package_id
                      AND packages.status = 'failed'
                    """,
                    (stage["job_id"], stage["attempt_id"]),
                )
    return dict(stage)


async def delete_teaching_archive_stage(
    *, attempt_id: str, job_id: str, root_run_id: str
) -> None:
    """Drop internal recovery bytes after their package is safely reviewable."""
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                DELETE FROM education_teaching_archive_staging
                WHERE attempt_id = %s AND job_id = %s AND root_run_id = %s
                """,
                (attempt_id, job_id, root_run_id),
            )


async def complete_teaching_attempt(
    *,
    job_id: str,
    attempt_id: str,
    root_run_id: str,
    bundle_prefix: str,
    asset_manifest: dict[str, Any] | None = None,
    package: dict[str, Any],
) -> dict[str, Any] | None:
    """Atomically persist a validated candidate and make its package reviewable.

    ``package`` is already normalized by the service validator. The database
    still pins it to the active attempt and its package, so a late completion
    cannot overwrite a cancelled/retried job or create a review projection for
    a different root run.
    """
    chapters = package.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise ValueError("Validated teaching package must contain chapters")
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT attempts.attempt_id, attempts.job_id,
                           attempts.root_run_id, jobs.teaching_package_id
                    FROM education_teaching_attempts AS attempts
                    JOIN education_teaching_jobs AS jobs ON jobs.job_id = attempts.job_id
                    JOIN education_teaching_packages AS packages
                      ON packages.teaching_package_id = jobs.teaching_package_id
                    WHERE attempts.attempt_id = %s
                      AND attempts.job_id = %s
                      AND attempts.root_run_id = %s
                      AND attempts.status = 'running'
                      AND jobs.status IN ('running', 'validating')
                      AND packages.status IN ('preparing', 'building_skill',
                                              'generating_teaching', 'validating')
                    FOR UPDATE OF attempts, jobs, packages
                    """,
                    (attempt_id, job_id, root_run_id),
                )
                attempt = await cur.fetchone()
                if not attempt:
                    return None
                teaching_package_id = str(attempt["teaching_package_id"])
                for chapter in chapters:
                    if not isinstance(chapter, dict):
                        raise ValueError("Validated teaching chapter is invalid")
                    await cur.execute(
                        """
                        INSERT INTO education_teaching_package_chapters (
                            package_chapter_id, teaching_package_id,
                            content_chapter_id, position, learning_objectives,
                            knowledge_points, key_difficulties, prerequisites,
                            teaching_material
                        ) VALUES (
                            %s, %s, %s,
                            (SELECT position FROM education_textbook_chapters
                             WHERE chapter_id = %s),
                            %s, %s, %s, %s, %s
                        )
                        RETURNING package_chapter_id
                        """,
                        (
                            str(uuid4()),
                            teaching_package_id,
                            chapter["content_chapter_id"],
                            chapter["content_chapter_id"],
                            Json(chapter["learning_objectives"]),
                            Json(chapter["knowledge_points"]),
                            Json(chapter["key_difficulties"]),
                            Json(chapter["prerequisites"]),
                            chapter["teaching_material"],
                        ),
                    )
                    package_chapter = await cur.fetchone()
                    if not package_chapter:
                        raise ValueError("Validated content chapter is unavailable")
                    package_chapter_id = str(package_chapter["package_chapter_id"])
                    for question in chapter.get("questions", []):
                        await cur.execute(
                            """
                            INSERT INTO education_teaching_package_questions (
                                question_id, package_chapter_id, position, prompt,
                                options, correct_option, explanation, knowledge_point
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                str(uuid4()),
                                package_chapter_id,
                                question["position"],
                                question["prompt"],
                                Json(question["options"]),
                                question["correct_option"],
                                question["explanation"],
                                question["knowledge_point"],
                            ),
                        )
                await cur.execute(
                    """
                    UPDATE education_teaching_packages
                    SET status = 'review', bundle_prefix = %s, reviewed_at = NOW(),
                        asset_manifest = COALESCE(%s::jsonb, asset_manifest),
                        error_code = NULL, error_message = NULL
                    WHERE teaching_package_id = %s
                    """,
                    (
                        bundle_prefix,
                        Json(asset_manifest) if asset_manifest is not None else None,
                        teaching_package_id,
                    ),
                )
                await cur.execute(
                    """
                    UPDATE education_teaching_attempts
                    SET status = 'completed', heartbeat_at = NOW(), completed_at = NOW(),
                        error_code = NULL, error_message = NULL
                    WHERE attempt_id = %s AND status = 'running'
                    RETURNING attempt_id, status
                    """,
                    (attempt_id,),
                )
                completed = await cur.fetchone()
                if not completed:
                    raise ValueError("Teaching attempt completion was lost")
                await cur.execute(
                    """
                    UPDATE education_teaching_jobs
                    SET status = 'completed', completed_at = NOW(), updated_at = NOW(),
                        error_code = NULL, error_message = NULL
                    WHERE job_id = %s AND latest_attempt_id = %s
                    """,
                    (job_id, attempt_id),
                )
    return dict(completed)


async def get_teaching_job_for_parent(
    *, parent_user_id: str, job_id: str
) -> dict[str, Any] | None:
    """Return one parent-owned job and its frozen, database-authorized chapters.

    This internal read model intentionally returns Markdown only to the teaching
    service. It never projects object-store keys to an API response.
    """
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.job_id, jobs.status AS job_status, jobs.attempt_count,
                       packages.teaching_package_id, packages.sequence AS teaching_package_sequence,
                       packages.content_version_id, packages.created_by_user_id,
                       versions.sequence AS content_version_sequence,
                       textbooks.household_id, textbooks.slug, textbooks.title,
                       EXISTS (
                           SELECT 1
                           FROM education_textbook_artifact_sources AS artifact_sources
                           WHERE artifact_sources.version_id = versions.version_id
                       ) AS artifact_backed
                FROM education_teaching_jobs AS jobs
                JOIN education_teaching_packages AS packages
                  ON packages.teaching_package_id = jobs.teaching_package_id
                JOIN education_textbook_versions AS versions
                  ON versions.version_id = packages.content_version_id
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                WHERE jobs.job_id = %s
                  AND memberships.user_id = %s
                  AND memberships.role = 'parent'
                """,
                (job_id, parent_user_id),
            )
            job = await cur.fetchone()
            if not job:
                return None
            result = dict(job)
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
                (result["content_version_id"],),
            )
            rows = [dict(row) for row in await cur.fetchall()]
            if artifact_backed:
                result["sources"] = [
                    {
                        "source_id": str(
                            row.get("producer_job_id")
                            or row["content_chapter_id"]
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


async def mark_teaching_job_cancel_requested(
    *, parent_user_id: str, job_id: str
) -> dict[str, Any] | None:
    """Durably record cancellation before signalling the PTC root execution."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE education_teaching_jobs AS jobs
                    SET status = 'cancelled', cancel_requested_at = COALESCE(cancel_requested_at, NOW()),
                        completed_at = NOW(), error_code = NULL, error_message = NULL,
                        updated_at = NOW()
                    FROM education_teaching_packages AS packages
                    JOIN education_textbook_versions AS versions
                      ON versions.version_id = packages.content_version_id
                    JOIN education_textbooks AS textbooks
                      ON textbooks.textbook_id = versions.textbook_id
                    JOIN education_memberships AS memberships
                      ON memberships.household_id = textbooks.household_id
                    WHERE jobs.job_id = %s
                      AND jobs.teaching_package_id = packages.teaching_package_id
                      AND memberships.user_id = %s
                      AND memberships.role = 'parent'
                      AND jobs.status IN ('queued', 'preparing', 'running', 'validating')
                    RETURNING jobs.job_id, jobs.status, jobs.latest_attempt_id,
                              jobs.teaching_package_id
                    """,
                    (job_id, parent_user_id),
                )
                job = await cur.fetchone()
                if not job:
                    return None
                await cur.execute(
                    """
                    UPDATE education_teaching_packages
                    SET status = 'cancelled', error_code = NULL, error_message = NULL
                    WHERE teaching_package_id = %s
                      AND status IN ('queued', 'preparing', 'building_skill',
                                     'generating_teaching', 'validating')
                    """,
                    (job["teaching_package_id"],),
                )
                if job["latest_attempt_id"] is None:
                    return dict(job)
                await cur.execute(
                    """
                    UPDATE education_teaching_attempts
                    SET status = 'cancelled', heartbeat_at = NOW(), completed_at = NOW(),
                        error_code = NULL, error_message = NULL
                    WHERE attempt_id = %s AND status IN ('preparing', 'running')
                    RETURNING managed_thread_id, root_run_id
                    """,
                    (job["latest_attempt_id"],),
                )
                attempt = await cur.fetchone()
    result = dict(job)
    if attempt:
        result.update(dict(attempt))
    return result


async def requeue_teaching_job(
    *, parent_user_id: str, job_id: str
) -> dict[str, Any] | None:
    """Make a failed/cancelled frozen job eligible for exactly one new attempt."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE education_teaching_jobs AS jobs
                    SET status = 'queued', cancel_requested_at = NULL,
                        error_code = NULL, error_message = NULL, completed_at = NULL,
                        claimed_at = NULL, updated_at = NOW()
                    FROM education_teaching_packages AS packages
                    JOIN education_textbook_versions AS versions
                      ON versions.version_id = packages.content_version_id
                    JOIN education_textbooks AS textbooks
                      ON textbooks.textbook_id = versions.textbook_id
                    JOIN education_memberships AS memberships
                      ON memberships.household_id = textbooks.household_id
                    WHERE jobs.job_id = %s
                      AND jobs.teaching_package_id = packages.teaching_package_id
                      AND memberships.user_id = %s
                      AND memberships.role = 'parent'
                      AND jobs.status IN ('failed', 'cancelled')
                      AND packages.status IN ('failed', 'cancelled')
                    RETURNING jobs.job_id, jobs.status, jobs.latest_attempt_id,
                              jobs.teaching_package_id
                    """,
                    (job_id, parent_user_id),
                )
                job = await cur.fetchone()
                if not job:
                    return None
                await cur.execute(
                    """
                    UPDATE education_teaching_packages
                    SET status = 'queued', error_code = NULL, error_message = NULL
                    WHERE teaching_package_id = %s
                      AND status IN ('failed', 'cancelled')
                    """,
                    (job["teaching_package_id"],),
                )
    result = dict(job)
    result.pop("teaching_package_id", None)
    return result


async def fail_preparing_teaching_attempt(
    *, attempt_id: str, error_code: str, error_message: str
) -> dict[str, Any] | None:
    """Terminally settle a pre-root provisioning failure without minting a run id."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE education_teaching_attempts
                    SET status = 'failed', heartbeat_at = NOW(), completed_at = NOW(),
                        error_code = %s, error_message = %s
                    WHERE attempt_id = %s AND status = 'preparing'
                    RETURNING attempt_id, job_id, status
                    """,
                    (error_code, error_message[:10_000], attempt_id),
                )
                attempt = await cur.fetchone()
                if not attempt:
                    return None
                await cur.execute(
                    """
                    UPDATE education_teaching_jobs
                    SET status = 'failed', completed_at = NOW(), error_code = %s,
                        error_message = %s, updated_at = NOW()
                    WHERE job_id = %s AND latest_attempt_id = %s
                    """,
                    (error_code, error_message[:10_000], attempt["job_id"], attempt_id),
                )
                await cur.execute(
                    """
                    UPDATE education_teaching_packages AS packages
                    SET status = 'failed', error_code = %s, error_message = %s
                    FROM education_teaching_jobs AS jobs
                    WHERE jobs.job_id = %s
                      AND jobs.latest_attempt_id = %s
                      AND jobs.teaching_package_id = packages.teaching_package_id
                      AND packages.status = 'preparing'
                    """,
                    (error_code, error_message[:10_000], attempt["job_id"], attempt_id),
                )
    return {"attempt_id": str(attempt["attempt_id"]), "status": str(attempt["status"])}


async def settle_recovered_teaching_root_run(
    *, root_run_id: str, status: str, error_code: str, error_message: str
) -> dict[str, Any] | None:
    """Project a scanner-finalized managed root to a retriable product failure.

    The recovery scanner owns the root-run CAS but cannot invoke the dead
    executor's callback. This operation is deliberately keyed solely by the
    already durable root id, so it cannot discover or access a sandbox, and it
    loses cleanly to a parent cancellation or a newer retry attempt.
    """
    if status not in {"failed", "cancelled"}:
        raise ValueError("Invalid recovered teaching status")
    package_status = "cancelled" if status == "cancelled" else "failed"
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE education_teaching_attempts AS attempts
                    SET status = %s, heartbeat_at = NOW(), completed_at = NOW(),
                        error_code = %s, error_message = %s
                    FROM education_teaching_jobs AS jobs
                    JOIN education_teaching_packages AS packages
                      ON packages.teaching_package_id = jobs.teaching_package_id
                    WHERE attempts.root_run_id = %s
                      AND attempts.status = 'running'
                      AND jobs.job_id = attempts.job_id
                      AND jobs.latest_attempt_id = attempts.attempt_id
                      AND jobs.status IN ('running', 'validating')
                      AND packages.status IN ('preparing', 'building_skill',
                                              'generating_teaching', 'validating')
                      AND NOT EXISTS (
                          SELECT 1
                          FROM education_teaching_archive_staging AS stages
                          WHERE stages.attempt_id = attempts.attempt_id
                            AND stages.job_id = attempts.job_id
                            AND stages.root_run_id = attempts.root_run_id
                            AND stages.created_at > NOW() - (%s * INTERVAL '1 second')
                      )
                    RETURNING attempts.attempt_id, attempts.job_id, attempts.status
                    """,
                    (
                        status,
                        error_code,
                        error_message[:10_000],
                        root_run_id,
                        _TEACHING_ARCHIVE_CALLBACK_LEASE_SECONDS,
                    ),
                )
                attempt = await cur.fetchone()
                if not attempt:
                    return None
                await cur.execute(
                    """
                    UPDATE education_teaching_jobs
                    SET status = %s, completed_at = NOW(), error_code = %s,
                        error_message = %s, updated_at = NOW()
                    WHERE job_id = %s AND latest_attempt_id = %s
                    """,
                    (
                        status,
                        error_code,
                        error_message[:10_000],
                        attempt["job_id"],
                        attempt["attempt_id"],
                    ),
                )
                await cur.execute(
                    """
                    UPDATE education_teaching_packages AS packages
                    SET status = %s, error_code = %s, error_message = %s
                    FROM education_teaching_jobs AS jobs
                    WHERE jobs.job_id = %s
                      AND jobs.latest_attempt_id = %s
                      AND jobs.teaching_package_id = packages.teaching_package_id
                      AND packages.status IN ('preparing', 'building_skill',
                                              'generating_teaching', 'validating')
                    """,
                    (
                        package_status,
                        error_code,
                        error_message[:10_000],
                        attempt["job_id"],
                        attempt["attempt_id"],
                    ),
                )
    return {"attempt_id": str(attempt["attempt_id"]), "status": str(attempt["status"])}


async def reconcile_terminal_teaching_root_runs(*, limit: int = 100) -> int:
    """Repair product attempts whose already-terminal root missed its callback.

    The query is deliberately bounded and reads no sandbox or object-store
    state. Each row then goes through the same root-id keyed conditional
    settlement used by recovery, so a concurrent cancellation or retry simply
    wins and this reconciliation becomes a no-op.
    """
    if limit <= 0 or limit > 1_000:
        raise ValueError("Teaching root reconciliation limit is invalid")
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT attempts.root_run_id, roots.status AS root_status,
                       stages.attempt_id IS NOT NULL AS has_archive_stage
                FROM education_teaching_attempts AS attempts
                JOIN education_teaching_jobs AS jobs ON jobs.job_id = attempts.job_id
                JOIN education_teaching_packages AS packages
                  ON packages.teaching_package_id = jobs.teaching_package_id
                JOIN conversation_responses AS roots
                  ON roots.conversation_response_id = attempts.root_run_id
                LEFT JOIN education_teaching_archive_staging AS stages
                  ON stages.attempt_id = attempts.attempt_id
                 AND stages.job_id = attempts.job_id
                 AND stages.root_run_id = attempts.root_run_id
                WHERE attempts.status = 'running'
                  AND jobs.latest_attempt_id = attempts.attempt_id
                  AND jobs.status IN ('running', 'validating')
                  AND packages.status IN ('preparing', 'building_skill',
                                          'generating_teaching', 'validating')
                  AND roots.status != 'in_progress'
                  AND (
                      stages.attempt_id IS NULL
                      OR stages.created_at <= NOW() - (%s * INTERVAL '1 second')
                  )
                ORDER BY roots.created_at
                LIMIT %s
                """,
                (_TEACHING_ARCHIVE_CALLBACK_LEASE_SECONDS, limit),
            )
            roots = [dict(row) for row in await cur.fetchall()]

    repaired = 0
    for root in roots:
        terminal_status = str(root.get("root_status") or "")
        status = "cancelled" if terminal_status == "cancelled" else "failed"
        has_archive_stage = bool(root.get("has_archive_stage"))
        error_code = (
            "managed_cancelled"
            if status == "cancelled"
            else (
                "managed_archive_pending"
                if has_archive_stage
                else "managed_terminal_unprojected"
            )
        )
        error_message = (
            "教材教学加工已取消。"
            if status == "cancelled"
            else (
                "教材教学资产已校验，正在等待私有存储连接，请继续运行。"
                if has_archive_stage
                else "教材教学加工进程中断，请重新运行。"
            )
        )
        result = await settle_recovered_teaching_root_run(
            root_run_id=str(root["root_run_id"]),
            status=status,
            error_code=error_code,
            error_message=error_message,
        )
        if result is not None:
            repaired += 1
    return repaired


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
        raise TextbookQueueValidationError(
            "At least one parse job source is required"
        )

    try:
        household_component = _validated_path_component(
            str(household_id), "household_id"
        )
    except ValueError as exc:
        raise TextbookQueueValidationError(str(exc)) from exc
    producer_job_ids = [
        str(source.get("producer_job_id") or "") for source in sources
    ]
    if any(not job_id for job_id in producer_job_ids):
        raise TextbookQueueValidationError(
            "Every source requires a producer_job_id"
        )
    if len(set(producer_job_ids)) != len(producer_job_ids):
        raise TextbookQueueValidationError(
            "Duplicate producer_job_id sources are not allowed"
        )
    for source in sources:
        if not str(source.get("document_id") or ""):
            raise TextbookQueueValidationError(
                "Every source requires a document_id"
            )
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


async def textbook_processing_job_exists(
    *, job_id: str, version_id: str
) -> bool:
    """Return whether the exact processing row is durably visible."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM education_processing_jobs
                    WHERE job_id = %s AND version_id = %s
                ) AS exists
                """,
                (job_id, version_id),
            )
            row = await cur.fetchone()
    return bool(row and row["exists"])


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
                            chapter_id, version_id, position, slug, title, page_start, page_end, markdown,
                            teaching_material, markdown_key, teaching_material_key
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                            chapter.get("teaching_material"),
                            chapter["markdown_key"],
                            chapter.get("teaching_material_key"),
                        ),
                    )
                    for question in chapter.get("questions", []):
                        await cur.execute(
                            """
                            INSERT INTO education_chapter_questions (
                                question_id, chapter_id, position, prompt, options, correct_option, explanation, knowledge_point
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                str(uuid4()),
                                chapter_id,
                                question["position"],
                                question["prompt"],
                                Json(question["options"]),
                                question["correct_option"],
                                question["explanation"],
                                question["knowledge_point"],
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
                    SELECT assets.asset_id, assets.original_filename,
                           assets.content_type, assets.size_bytes
                    FROM education_textbook_sources AS sources
                    JOIN education_assets AS assets ON assets.asset_id = sources.asset_id
                    WHERE sources.version_id = %s
                    ORDER BY sources.position
                    """,
                    (version["version_id"],),
                )
                version["sources"] = [dict(row) for row in await cur.fetchall()]
                await cur.execute(
                    """
                    SELECT chapters.chapter_id, chapters.position, chapters.slug, chapters.title,
                           chapters.page_start, chapters.page_end, chapters.markdown, chapters.teaching_material
                    FROM education_textbook_chapters AS chapters
                    WHERE chapters.version_id = %s ORDER BY chapters.position
                    """,
                    (version["version_id"],),
                )
                chapters = [dict(row) for row in await cur.fetchall()]
                for chapter in chapters:
                    await cur.execute(
                        """
                        SELECT question_id, position, prompt, options, correct_option, explanation, knowledge_point
                        FROM education_chapter_questions WHERE chapter_id = %s ORDER BY position
                        """,
                        (chapter["chapter_id"],),
                    )
                    chapter["questions"] = [dict(row) for row in await cur.fetchall()]
                version["chapters"] = chapters
                await cur.execute(
                    """
                    SELECT packages.teaching_package_id, jobs.job_id, packages.sequence,
                           packages.status, jobs.status AS job_status,
                           COALESCE((
                               SELECT COUNT(*)
                               FROM education_teaching_package_chapters AS package_chapters
                               WHERE package_chapters.teaching_package_id = packages.teaching_package_id
                           ), 0) AS chapter_count,
                           COALESCE((
                               SELECT COUNT(*)
                               FROM education_teaching_package_questions AS package_questions
                               JOIN education_teaching_package_chapters AS package_chapters
                                 ON package_chapters.package_chapter_id = package_questions.package_chapter_id
                               WHERE package_chapters.teaching_package_id = packages.teaching_package_id
                           ), 0) AS question_count
                    FROM education_teaching_packages AS packages
                    JOIN education_teaching_jobs AS jobs
                      ON jobs.teaching_package_id = packages.teaching_package_id
                    WHERE packages.content_version_id = %s
                    ORDER BY packages.sequence DESC
                    """,
                    (version["version_id"],),
                )
                version["teaching_packages"] = [
                    dict(row) for row in await cur.fetchall()
                ]
                reviewable_package = next(
                    (
                        package
                        for package in version["teaching_packages"]
                        if package["status"] == "review"
                    ),
                    None,
                )
                if reviewable_package:
                    await cur.execute(
                        """
                        SELECT package_chapters.content_chapter_id,
                               package_chapters.teaching_material,
                               package_questions.question_id, package_questions.position,
                               package_questions.prompt, package_questions.options,
                               package_questions.correct_option,
                               package_questions.explanation,
                               package_questions.knowledge_point
                        FROM education_teaching_package_chapters AS package_chapters
                        LEFT JOIN education_teaching_package_questions AS package_questions
                          ON package_questions.package_chapter_id = package_chapters.package_chapter_id
                        WHERE package_chapters.teaching_package_id = %s
                        ORDER BY package_chapters.position, package_questions.position
                        """,
                        (reviewable_package["teaching_package_id"],),
                    )
                    package_rows = [dict(row) for row in await cur.fetchall()]
                    teaching_by_chapter: dict[Any, dict[str, Any]] = {}
                    for row in package_rows:
                        teaching = teaching_by_chapter.setdefault(
                            row["content_chapter_id"],
                            {
                                "teaching_material": row["teaching_material"],
                                "questions": [],
                            },
                        )
                        if row["question_id"] is not None:
                            teaching["questions"].append(
                                {
                                    key: row[key]
                                    for key in (
                                        "question_id",
                                        "position",
                                        "prompt",
                                        "options",
                                        "correct_option",
                                        "explanation",
                                        "knowledge_point",
                                    )
                                }
                            )
                    for chapter in chapters:
                        teaching = teaching_by_chapter.get(chapter["chapter_id"])
                        if teaching:
                            chapter.update(teaching)
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


async def publish_textbook_version(
    *,
    parent_user_id: str,
    textbook_id: str,
    version_id: str,
    teaching_package_id: str,
) -> dict[str, Any] | None:
    publication_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT versions.version_id
                    FROM education_textbook_versions AS versions
                    JOIN education_textbooks AS textbooks ON textbooks.textbook_id = versions.textbook_id
                    JOIN education_memberships AS memberships ON memberships.household_id = textbooks.household_id
                    WHERE versions.version_id = %s AND textbooks.textbook_id = %s
                      AND memberships.user_id = %s AND memberships.role = 'parent'
                    FOR UPDATE
                    """,
                    (version_id, textbook_id, parent_user_id),
                )
                if not await cur.fetchone():
                    return None
                await cur.execute(
                    "SELECT status FROM education_textbook_versions WHERE version_id = %s",
                    (version_id,),
                )
                version = await cur.fetchone()
                if version["status"] != "review":
                    raise ValueError(
                        f"Textbook version cannot be published from {version['status']}"
                    )
                await cur.execute(
                    "SELECT COUNT(*) AS count FROM education_textbook_chapters WHERE version_id = %s",
                    (version_id,),
                )
                if (await cur.fetchone())["count"] == 0:
                    raise ValueError("Textbook version has no reviewable chapters")
                await cur.execute(
                    """
                    SELECT packages.teaching_package_id
                    FROM education_teaching_packages AS packages
                    WHERE packages.teaching_package_id = %s
                      AND packages.content_version_id = %s
                      AND packages.status = 'review'
                      AND NOT EXISTS (
                          SELECT 1
                          FROM education_textbook_chapters AS content_chapters
                          WHERE content_chapters.version_id = %s
                            AND NOT EXISTS (
                                SELECT 1
                                FROM education_teaching_package_chapters AS package_chapters
                                JOIN education_teaching_package_questions AS package_questions
                                  ON package_questions.package_chapter_id = package_chapters.package_chapter_id
                                WHERE package_chapters.teaching_package_id = packages.teaching_package_id
                                  AND package_chapters.content_chapter_id = content_chapters.chapter_id
                            )
                      )
                    FOR UPDATE
                    """,
                    (teaching_package_id, version_id, version_id),
                )
                if not await cur.fetchone():
                    raise ValueError(
                        "Textbook version requires a reviewed teaching package with every chapter and question set"
                    )
                await cur.execute(
                    """
                    INSERT INTO education_textbook_publications (
                        publication_id, version_id, teaching_package_id, published_by_user_id
                    ) VALUES (%s, %s, %s, %s)
                    RETURNING publication_id, version_id, teaching_package_id, published_by_user_id, created_at
                    """,
                    (publication_id, version_id, teaching_package_id, parent_user_id),
                )
                publication = dict(await cur.fetchone())
                await cur.execute(
                    "UPDATE education_textbook_versions SET status = 'published', published_at = NOW() WHERE version_id = %s",
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
                       COALESCE((SELECT COUNT(*) FROM education_teaching_package_chapters
                                 WHERE teaching_package_id = publications.teaching_package_id), 0) AS chapter_count,
                       COALESCE((SELECT COUNT(*) FROM education_learning_progress AS progress
                                 WHERE progress.assignment_id = assignments.assignment_id
                                   AND progress.status IN ('read', 'check_completed')), 0) AS completed_chapter_count
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


async def get_student_learning(
    *, student_user_id: str, assignment_id: str
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT assignments.assignment_id, assignments.publication_id, textbooks.title AS textbook_title,
                       textbooks.slug AS textbook_slug, versions.sequence AS version_sequence
                FROM education_textbook_assignments AS assignments
                JOIN education_textbook_publications AS publications ON publications.publication_id = assignments.publication_id
                JOIN education_textbook_versions AS versions ON versions.version_id = publications.version_id
                JOIN education_textbooks AS textbooks ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.user_id = assignments.student_user_id
                 AND memberships.household_id = textbooks.household_id
                WHERE assignments.assignment_id = %s AND assignments.student_user_id = %s AND memberships.role = 'student'
                """,
                (assignment_id, student_user_id),
            )
            assignment = await cur.fetchone()
            if not assignment:
                return None
            await cur.execute(
                """
                SELECT content_chapters.chapter_id, content_chapters.position, content_chapters.slug,
                       content_chapters.title, content_chapters.markdown,
                       package_chapters.teaching_material,
                       COALESCE(progress.status, 'not_started') AS progress_status,
                       progress.last_read_at, progress.completed_at
                FROM education_textbook_publications AS publications
                JOIN education_teaching_package_chapters AS package_chapters
                  ON package_chapters.teaching_package_id = publications.teaching_package_id
                JOIN education_textbook_chapters AS content_chapters
                  ON content_chapters.chapter_id = package_chapters.content_chapter_id
                LEFT JOIN education_learning_progress AS progress
                  ON progress.chapter_id = content_chapters.chapter_id AND progress.assignment_id = %s
                WHERE publications.publication_id = %s
                ORDER BY package_chapters.position
                """,
                (assignment_id, assignment["publication_id"]),
            )
            chapters = [dict(row) for row in await cur.fetchall()]
            for chapter in chapters:
                await cur.execute(
                    """
                    SELECT questions.question_id, questions.position, questions.prompt, questions.options,
                           questions.explanation, questions.knowledge_point, answers.selected_option,
                           answers.is_correct, answers.answered_at
                    FROM education_teaching_package_questions AS questions
                    LEFT JOIN education_learning_answers AS answers
                      ON answers.question_id = questions.question_id AND answers.assignment_id = %s
                    JOIN education_teaching_package_chapters AS package_chapters
                      ON package_chapters.package_chapter_id = questions.package_chapter_id
                    WHERE package_chapters.content_chapter_id = %s
                      AND package_chapters.teaching_package_id = (
                          SELECT teaching_package_id
                          FROM education_textbook_publications
                          WHERE publication_id = %s
                      )
                    ORDER BY questions.position
                    """,
                    (
                        assignment_id,
                        chapter["chapter_id"],
                        assignment["publication_id"],
                    ),
                )
                chapter["questions"] = [dict(row) for row in await cur.fetchall()]
    result = dict(assignment)
    result["chapters"] = chapters
    return result


async def get_student_chapter_context_record(
    *, student_user_id: str, assignment_id: str, chapter_id: str
) -> dict[str, Any] | None:
    """Return published chapter material only through the student's assigned snapshot."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT assignments.assignment_id, content_chapters.chapter_id,
                       textbooks.title AS textbook_title, content_chapters.title AS chapter_title,
                       content_chapters.markdown, package_chapters.teaching_material
                FROM education_textbook_assignments AS assignments
                JOIN education_textbook_publications AS publications ON publications.publication_id = assignments.publication_id
                JOIN education_textbook_versions AS versions ON versions.version_id = publications.version_id
                JOIN education_textbooks AS textbooks ON textbooks.textbook_id = versions.textbook_id
                JOIN education_teaching_package_chapters AS package_chapters
                  ON package_chapters.teaching_package_id = publications.teaching_package_id
                JOIN education_textbook_chapters AS content_chapters
                  ON content_chapters.chapter_id = package_chapters.content_chapter_id
                JOIN education_memberships AS memberships
                  ON memberships.user_id = assignments.student_user_id
                 AND memberships.household_id = textbooks.household_id
                WHERE assignments.assignment_id = %s AND assignments.student_user_id = %s
                  AND content_chapters.chapter_id = %s AND memberships.role = 'student'
                """,
                (assignment_id, student_user_id, chapter_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def update_student_progress(
    *, student_user_id: str, assignment_id: str, chapter_id: str, status: str
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO education_learning_progress (assignment_id, chapter_id, status, last_read_at, completed_at, updated_at)
                SELECT assignments.assignment_id, chapters.chapter_id, %s, NOW(),
                       CASE WHEN %s IN ('read', 'check_completed') THEN NOW() ELSE NULL END, NOW()
                FROM education_textbook_assignments AS assignments
                JOIN education_textbook_publications AS publications ON publications.publication_id = assignments.publication_id
                JOIN education_textbook_versions AS versions ON versions.version_id = publications.version_id
                JOIN education_textbooks AS textbooks ON textbooks.textbook_id = versions.textbook_id
                JOIN education_teaching_package_chapters AS package_chapters
                  ON package_chapters.teaching_package_id = publications.teaching_package_id
                JOIN education_textbook_chapters AS chapters
                  ON chapters.chapter_id = package_chapters.content_chapter_id
                JOIN education_memberships AS memberships
                  ON memberships.user_id = assignments.student_user_id
                 AND memberships.household_id = textbooks.household_id
                WHERE assignments.assignment_id = %s AND assignments.student_user_id = %s
                  AND chapters.chapter_id = %s AND memberships.role = 'student'
                ON CONFLICT (assignment_id, chapter_id) DO UPDATE
                SET status = EXCLUDED.status, last_read_at = NOW(),
                    completed_at = CASE WHEN EXCLUDED.status IN ('read', 'check_completed') THEN NOW() ELSE education_learning_progress.completed_at END,
                    updated_at = NOW()
                RETURNING assignment_id, chapter_id, status, last_read_at, completed_at, updated_at
                """,
                (status, status, assignment_id, student_user_id, chapter_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def submit_student_answer(
    *, student_user_id: str, assignment_id: str, question_id: str, selected_option: str
) -> dict[str, Any] | None:
    answer_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                SELECT questions.question_id, package_chapters.content_chapter_id AS chapter_id,
                       questions.correct_option
                FROM education_textbook_assignments AS assignments
                JOIN education_textbook_publications AS publications ON publications.publication_id = assignments.publication_id
                JOIN education_textbook_versions AS versions ON versions.version_id = publications.version_id
                JOIN education_textbooks AS textbooks ON textbooks.textbook_id = versions.textbook_id
                JOIN education_teaching_package_chapters AS package_chapters
                  ON package_chapters.teaching_package_id = publications.teaching_package_id
                JOIN education_teaching_package_questions AS questions
                  ON questions.package_chapter_id = package_chapters.package_chapter_id
                JOIN education_memberships AS memberships
                  ON memberships.user_id = assignments.student_user_id
                 AND memberships.household_id = textbooks.household_id
                    WHERE assignments.assignment_id = %s AND assignments.student_user_id = %s
                      AND questions.question_id = %s AND memberships.role = 'student'
                    FOR UPDATE
                    """,
                    (assignment_id, student_user_id, question_id),
                )
                question = await cur.fetchone()
                if not question:
                    return None
                await cur.execute(
                    """
                    INSERT INTO education_learning_answers (answer_id, assignment_id, question_id, selected_option, is_correct)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (assignment_id, question_id) DO NOTHING
                    RETURNING answer_id, assignment_id, question_id, selected_option, is_correct, answered_at
                    """,
                    (
                        answer_id,
                        assignment_id,
                        question_id,
                        selected_option,
                        selected_option == question["correct_option"],
                    ),
                )
                answer = await cur.fetchone()
                if not answer:
                    await cur.execute(
                        """
                        SELECT answer_id, assignment_id, question_id, selected_option, is_correct, answered_at
                        FROM education_learning_answers WHERE assignment_id = %s AND question_id = %s
                        """,
                        (assignment_id, question_id),
                    )
                    answer = await cur.fetchone()
                await cur.execute(
                    """
                    INSERT INTO education_learning_progress (assignment_id, chapter_id, status, completed_at, updated_at)
                    VALUES (%s, %s, 'check_completed', NOW(), NOW())
                    ON CONFLICT (assignment_id, chapter_id) DO UPDATE
                    SET status = 'check_completed', completed_at = NOW(), updated_at = NOW()
                    """,
                    (assignment_id, question["chapter_id"]),
                )
    return dict(answer) if answer else None


async def list_student_learning_records(
    *, parent_user_id: str, assignment_id: str
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT assignments.assignment_id, assignments.student_user_id, textbooks.title AS textbook_title
                FROM education_textbook_assignments AS assignments
                JOIN education_textbook_publications AS publications ON publications.publication_id = assignments.publication_id
                JOIN education_textbook_versions AS versions ON versions.version_id = publications.version_id
                JOIN education_textbooks AS textbooks ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships ON memberships.household_id = textbooks.household_id
                WHERE assignments.assignment_id = %s AND memberships.user_id = %s AND memberships.role = 'parent'
                """,
                (assignment_id, parent_user_id),
            )
            assignment = await cur.fetchone()
            if not assignment:
                return None
            await cur.execute(
                """
                    SELECT progress.chapter_id, content_chapters.title AS chapter_title, progress.status, progress.last_read_at,
                       progress.completed_at, COALESCE(answer_counts.correct_count, 0) AS correct_count,
                       COALESCE(answer_counts.answer_count, 0) AS answer_count
                FROM education_learning_progress AS progress
                JOIN education_textbook_assignments AS assignments
                  ON assignments.assignment_id = progress.assignment_id
                JOIN education_textbook_publications AS publications
                  ON publications.publication_id = assignments.publication_id
                JOIN education_teaching_package_chapters AS package_chapters
                  ON package_chapters.teaching_package_id = publications.teaching_package_id
                 AND package_chapters.content_chapter_id = progress.chapter_id
                JOIN education_textbook_chapters AS content_chapters
                  ON content_chapters.chapter_id = progress.chapter_id
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) FILTER (WHERE is_correct) AS correct_count, COUNT(*) AS answer_count
                    FROM education_learning_answers WHERE assignment_id = progress.assignment_id
                      AND question_id IN (
                          SELECT questions.question_id
                          FROM education_teaching_package_questions AS questions
                          WHERE questions.package_chapter_id = package_chapters.package_chapter_id
                      )
                ) AS answer_counts ON TRUE
                WHERE progress.assignment_id = %s ORDER BY package_chapters.position
                """,
                (assignment_id,),
            )
            records = [dict(row) for row in await cur.fetchall()]
    result = dict(assignment)
    result["records"] = records
    return result
