"""Versioning, explicit local processing, and authorization for family textbooks."""

import asyncio
import json
import logging
from collections.abc import Mapping
from io import BytesIO
from pathlib import PurePosixPath
from typing import Any
from uuid import uuid4

from src.config.settings import get_document_parsing_config
from src.server.database.education_tasks import get_household_context_for_parent
from src.server.database.education_textbooks import (
    assign_textbook_publication,
    claim_textbook_processing_job,
    complete_textbook_processing_job,
    create_textbook_record,
    fail_textbook_processing_job,
    get_processing_job_for_parent,
    get_owned_parse_job,
    get_textbook_for_parent,
    get_student_published_kp_lesson,
    get_student_published_structure,
    list_completed_parse_jobs_for_parent,
    list_student_assignments,
    list_textbooks_for_parent,
    queue_textbook_processing,
    queue_textbook_processing_from_artifacts,
    retry_textbook_processing_job,
    TextbookQueueValidationError,
)
from src.server.database.education_members import get_membership_for_user
from src.server.database.session_lock import await_settled
from src.server.services.education_textbook_source_snapshots import (
    TextbookSourceSnapshotError,
    cleanup_snapshot_objects,
    freeze_parse_job_source,
)
from src.server.services.education_textbook_snapshot_reads import (
    TextbookSnapshotReadError,
    read_snapshot_artifact_bytes,
)
from src.server.services.education_textbook_storage import write_textbook_content_bundle
from src.server.services.education_teaching_storage import (
    read_kp_lesson_revision,
)
from src.utils.storage import get_bytes


logger = logging.getLogger(__name__)

_SOURCE_SNAPSHOT_FORMAT = "langalpha-textbook-source-snapshot/v1"
_MARKDOWN_MEDIA_TYPE = "text/markdown"
_MARKDOWN_FORMATS = frozenset({"gfm", "markdown"})

_VALID_VERSION_TRANSITIONS = {
    ("draft", "processing"),
    ("processing", "review"),
    ("processing", "failed"),
    ("failed", "processing"),
    ("review", "published"),
}


class TextbookError(RuntimeError):
    """Base exception for family textbook operations."""


class TextbookTransitionError(TextbookError, ValueError):
    """A textbook version state change violates publication immutability."""


class TextbookPermissionError(TextbookError, PermissionError):
    """The caller does not own the required household teaching capability."""


class TextbookNotFoundError(TextbookError, LookupError):
    """The requested textbook record is absent or outside its visible scope."""


class TextbookProcessingError(TextbookError):
    """The durable local processing job failed after it was claimed."""


def assert_version_transition(*, current: str, target: str) -> None:
    if (current, target) not in _VALID_VERSION_TRANSITIONS:
        raise TextbookTransitionError(
            f"Cannot transition textbook version from {current} to {target}"
        )


def _required_title(value: str) -> str:
    title = value.strip()
    if not title:
        raise TextbookError("textbook title is required")
    return title


def _slug(value: str, *, unique_suffix: str | None = None) -> str:
    import re

    base = re.sub(r"[^0-9A-Za-z._-]+", "-", value.strip()).strip(".-").lower()
    if not base:
        base = "textbook"
    if unique_suffix:
        return f"{base[: max(1, 80 - len(unique_suffix) - 1)]}-{unique_suffix}"
    return base[:80]


def _uses_artifact_sources(job: Mapping[str, Any]) -> bool:
    sources = job.get("sources")
    return (
        isinstance(sources, list)
        and bool(sources)
        and any(
            isinstance(source, Mapping) and source.get("snapshot_prefix")
            for source in sources
        )
    )


def _snapshot_prefix(value: object) -> str:
    if not isinstance(value, str) or not value.startswith("education/") or not value.endswith("/"):
        raise TextbookProcessingError("A frozen textbook snapshot prefix is invalid")
    path = PurePosixPath(value.rstrip("/"))
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise TextbookProcessingError("A frozen textbook snapshot prefix is invalid")
    if "\\" in value or "\x00" in value:
        raise TextbookProcessingError("A frozen textbook snapshot prefix is invalid")
    return value


def _snapshot_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise TextbookProcessingError("A frozen textbook artifact path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise TextbookProcessingError("A frozen textbook artifact path is invalid")
    normalized = path.as_posix()
    return normalized if normalized.startswith("artifacts/") else f"artifacts/{normalized}"


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _source_position(source: Mapping[str, Any]) -> int:
    position = source.get("position")
    if not isinstance(position, int) or isinstance(position, bool) or position <= 0:
        raise TextbookProcessingError("A frozen textbook source position is invalid")
    return position


def _artifact_bundle_prefix(sources: list[Mapping[str, Any]]) -> str:
    namespaces = {
        "/".join(_snapshot_prefix(source.get("snapshot_prefix")).rstrip("/").split("/")[:-1])
        for source in sources
    }
    if len(namespaces) != 1:
        raise TextbookProcessingError("Frozen textbook sources do not share one bundle")
    return namespaces.pop()


async def build_frozen_artifact_package(job: dict[str, Any]) -> dict[str, Any]:
    """Load each immutable source snapshot once into a complete Markdown source row."""
    sources = job.get("sources")
    if not isinstance(sources, list) or not sources:
        raise TextbookProcessingError("Textbook processing has no frozen sources")
    try:
        ordered_sources = sorted(sources, key=_source_position)
    except TypeError as exc:
        raise TextbookProcessingError("A frozen textbook source is invalid") from exc
    if len({_source_position(source) for source in ordered_sources}) != len(ordered_sources):
        raise TextbookProcessingError("Frozen textbook source positions must be unique")

    max_bytes = int(get_document_parsing_config().max_upload_bytes)
    if max_bytes <= 0:
        raise TextbookProcessingError("Textbook source size limit is invalid")

    chapters: list[dict[str, Any]] = []
    used_slugs: set[str] = set()
    for source in ordered_sources:
        if not isinstance(source, Mapping):
            raise TextbookProcessingError("A frozen textbook source is invalid")
        prefix = _snapshot_prefix(source.get("snapshot_prefix"))
        primary_artifact_id = source.get("primary_artifact_id")
        primary_sha256 = source.get("primary_sha256")
        document_id = source.get("document_id")
        producer_job_id = source.get("producer_job_id")
        if not isinstance(primary_artifact_id, str) or not primary_artifact_id:
            raise TextbookProcessingError("A frozen textbook primary artifact is invalid")
        if not _is_sha256(primary_sha256):
            raise TextbookProcessingError("A frozen textbook source digest is invalid")

        manifest_bytes = await asyncio.to_thread(
            get_bytes, f"{prefix}manifest.json"
        )
        if (
            not isinstance(manifest_bytes, bytes)
            or not manifest_bytes
            or len(manifest_bytes) > max_bytes
        ):
            raise TextbookProcessingError("A frozen textbook snapshot manifest is invalid")
        try:
            manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TextbookProcessingError(
                "A frozen textbook snapshot manifest is invalid"
            ) from exc
        if not isinstance(manifest, Mapping) or manifest.get("format") != _SOURCE_SNAPSHOT_FORMAT:
            raise TextbookProcessingError("A frozen textbook snapshot manifest is invalid")
        if (
            str(manifest.get("document_id") or "") != str(document_id or "")
            or str(manifest.get("producer_job_id") or "") != str(producer_job_id or "")
            or str(manifest.get("primary_artifact_id") or "") != primary_artifact_id
        ):
            raise TextbookProcessingError(
                "A frozen textbook snapshot manifest does not match its source"
            )

        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, list) or not artifacts:
            raise TextbookProcessingError("A frozen textbook snapshot has no artifacts")
        if any(not isinstance(artifact, Mapping) for artifact in artifacts):
            raise TextbookProcessingError("A frozen textbook snapshot artifact is invalid")
        primary_matches = [
            artifact
            for artifact in artifacts
            if str(artifact.get("artifact_id") or "") == primary_artifact_id
        ]
        if len(primary_matches) != 1:
            raise TextbookProcessingError(
                "A frozen textbook snapshot primary artifact is missing"
            )
        primary = primary_matches[0]
        if str(primary.get("artifact_kind") or "") != "primary_document":
            raise TextbookProcessingError(
                "A frozen textbook snapshot primary artifact is invalid"
            )
        if str(primary.get("format") or "").strip().lower() not in _MARKDOWN_FORMATS:
            raise TextbookProcessingError(
                "A frozen textbook snapshot Markdown format is invalid"
            )
        media_type = str(primary.get("media_type") or "").split(";", 1)[0].strip().lower()
        if media_type != _MARKDOWN_MEDIA_TYPE:
            raise TextbookProcessingError(
                "A frozen textbook snapshot Markdown media type is invalid"
            )
        manifest_sha256 = primary.get("sha256")
        if not _is_sha256(manifest_sha256) or manifest_sha256 != primary_sha256:
            raise TextbookProcessingError(
                "A frozen textbook snapshot primary digest is invalid"
            )
        relative_path = _snapshot_relative_path(primary.get("relative_path"))
        try:
            content, artifact_key = await read_snapshot_artifact_bytes(
                snapshot_prefix=prefix,
                relative_path=relative_path,
                expected_sha256=primary_sha256,
                max_bytes=max_bytes,
                read_bytes=get_bytes,
            )
        except TextbookSnapshotReadError as exc:
            raise TextbookProcessingError(
                "A frozen textbook snapshot primary artifact is invalid"
            ) from exc
        declared_size = primary.get("size_bytes")
        if declared_size is not None and (
            not isinstance(declared_size, int)
            or isinstance(declared_size, bool)
            or declared_size != len(content)
        ):
            raise TextbookProcessingError(
                "A frozen textbook snapshot primary size is invalid"
            )
        try:
            markdown = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TextbookProcessingError(
                "A frozen textbook snapshot Markdown is not UTF-8"
            ) from exc
        if not markdown.strip():
            raise TextbookProcessingError(
                "A frozen textbook snapshot Markdown is empty"
            )

        title = source.get("source_filename")
        if not isinstance(title, str) or not title.strip():
            raise TextbookProcessingError("A frozen textbook source filename is invalid")
        title = title.strip()
        slug = _slug(title)
        if slug in used_slugs:
            slug = _slug(f"{_source_position(source):02d}-{title}")
        used_slugs.add(slug)
        chapters.append(
            {
                "position": _source_position(source),
                "slug": slug,
                "title": title,
                "page_start": None,
                "page_end": None,
                "markdown_key": artifact_key,
                "markdown": markdown,
            }
        )
    return {
        "extractor": {"name": "managed_ptc", "version": "1"},
        "chapters": chapters,
    }


async def create_textbook(*, parent_user_id: str, title: str) -> dict[str, Any]:
    context = await get_household_context_for_parent(parent_user_id)
    if not context:
        raise TextbookPermissionError("Only a parent can create family textbooks")
    textbook = await create_textbook_record(
        household_id=str(context["household_id"]),
        parent_user_id=parent_user_id,
        title=_required_title(title),
        slug=_slug(title, unique_suffix=uuid4().hex[:12]),
    )
    if not textbook:
        raise TextbookPermissionError(
            "Only a household parent can create family textbooks"
        )
    return textbook


async def start_processing(
    *,
    parent_user_id: str,
    textbook_id: str,
    source_asset_ids: list[str],
    extractor_name: str = "local_fixture",
    extractor_version: str = "1",
) -> dict[str, Any]:
    """Explicitly freeze sources into a queued local processing job; no upload is implicitly included."""
    context = await get_household_context_for_parent(parent_user_id)
    if not context:
        raise TextbookPermissionError("Only a parent can start textbook processing")
    if not source_asset_ids:
        raise TextbookError("At least one textbook source is required")
    job = await queue_textbook_processing(
        parent_user_id=parent_user_id,
        household_id=str(context["household_id"]),
        textbook_id=textbook_id,
        source_asset_ids=list(dict.fromkeys(source_asset_ids)),
        extractor_name=extractor_name,
        extractor_version=extractor_version,
    )
    if not job:
        raise TextbookNotFoundError("Textbook not found")
    return job


async def start_processing_from_parse_jobs(
    *,
    parent_user_id: str,
    textbook_id: str,
    source_parse_job_ids: list[str],
) -> dict[str, Any]:
    """Freeze every completed library bundle before creating any processing job."""
    context = await get_household_context_for_parent(parent_user_id)
    if not context:
        raise TextbookPermissionError(
            "Only a parent can start textbook processing"
        )
    if not source_parse_job_ids:
        raise TextbookError("At least one textbook source is required")
    if len(set(source_parse_job_ids)) != len(source_parse_job_ids):
        raise TextbookError("Duplicate parse job sources are not allowed")

    textbook = await get_textbook_for_parent(
        parent_user_id=parent_user_id,
        textbook_id=textbook_id,
    )
    household_id = str(context["household_id"])
    if not textbook or str(textbook["household_id"]) != household_id:
        raise TextbookNotFoundError("Textbook not found")

    version_id = str(uuid4())
    job_id = str(uuid4())
    sources: list[dict[str, Any]] = []
    written_keys: list[str] = []

    async def cleanup_written_snapshots() -> None:
        if written_keys:
            await asyncio.shield(cleanup_snapshot_objects(written_keys))

    try:
        for position, producer_job_id in enumerate(source_parse_job_ids, start=1):
            owned_job = await get_owned_parse_job(
                owner_user_id=parent_user_id,
                producer_job_id=producer_job_id,
            )
            if (
                not owned_job
                or str(owned_job.get("status") or "") != "completed"
            ):
                raise TextbookNotFoundError(
                    "One or more parse job sources are unavailable or incomplete"
                )
            try:
                frozen = await freeze_parse_job_source(
                    owner_user_id=parent_user_id,
                    document_id=str(owned_job["document_id"]),
                    producer_job_id=producer_job_id,
                    household_id=household_id,
                    textbook_slug=str(textbook["slug"]),
                    version_id=version_id,
                    position=position,
                )
            except TextbookSourceSnapshotError as exc:
                raise TextbookError(str(exc)) from exc
            sources.append(frozen.source)
            written_keys.extend(frozen.written_keys)
    except BaseException:
        await cleanup_written_snapshots()
        raise

    queue_task = asyncio.create_task(
        queue_textbook_processing_from_artifacts(
            parent_user_id=parent_user_id,
            household_id=household_id,
            textbook_id=textbook_id,
            sources=sources,
            extractor_name="managed_ptc",
            extractor_version="1",
            version_id=version_id,
            job_id=job_id,
        )
    )
    try:
        job = await await_settled(queue_task)
    except TextbookQueueValidationError as exc:
        await cleanup_written_snapshots()
        raise TextbookError(str(exc)) from exc
    except asyncio.CancelledError:
        logger.warning(
            "textbook_source_snapshot_queue_outcome_ambiguous",
            extra={"version_id": version_id, "job_id": job_id},
        )
        raise
    except Exception:
        logger.warning(
            "textbook_source_snapshot_queue_outcome_ambiguous",
            extra={"version_id": version_id, "job_id": job_id},
        )
        raise

    if not job:
        await cleanup_written_snapshots()
        raise TextbookNotFoundError("Textbook not found")
    return job


def build_local_fixture_package(job: dict[str, Any]) -> dict[str, Any]:
    """Generate deterministic review material; a PTC/Datalab extractor can replace this adapter later."""
    chapter_slug = "01-overview"
    source_names = "、".join(source["original_filename"] for source in job["sources"])
    markdown_key = f"education/{job['household_id']}/{_slug(job['slug'])}/v{job['version_sequence']}/chapters/{chapter_slug}.md"
    title = f"{job['title']}：导读"
    return {
        "extractor": {"name": "local_fixture", "version": "1"},
        "chapters": [
            {
                "position": 1,
                "slug": chapter_slug,
                "title": title,
                "page_start": None,
                "page_end": None,
                "markdown_key": markdown_key,
                "markdown": f"# {title}\n\n本章基于已冻结资料：{source_names}。\n\n请先阅读资料，再用自己的话说明本章的学习目标。\n",
            }
        ],
    }


async def build_local_pdf_package(job: dict[str, Any]) -> dict[str, Any]:
    """Extract frozen PDF text into stable review chapters without using RAG."""
    extracted_sources: list[tuple[str, list[str]]] = []
    for source in job["sources"]:
        if source.get("content_type") != "application/pdf":
            continue
        content = await asyncio.to_thread(get_bytes, source["storage_key"])
        if content is None:
            raise TextbookProcessingError(
                "A frozen textbook source is no longer available"
            )
        try:
            import pypdf

            reader = await asyncio.to_thread(pypdf.PdfReader, BytesIO(content))
            pages = [
                (await asyncio.to_thread(page.extract_text) or "").strip()
                for page in reader.pages
            ]
        except Exception as exc:
            raise TextbookProcessingError(
                "The local PDF extractor could not read a source"
            ) from exc
        if any(pages):
            extracted_sources.append(
                (source["original_filename"], [page for page in pages if page])
            )
    if not extracted_sources:
        return build_local_fixture_package(job)

    prefix = f"education/{job['household_id']}/{_slug(job['slug'])}/v{job['version_sequence']}"
    chapters: list[dict[str, Any]] = []
    position = 1
    for filename, pages in extracted_sources:
        for offset in range(0, len(pages), 10):
            selected_pages = pages[offset : offset + 10]
            page_start = offset + 1
            page_end = offset + len(selected_pages)
            slug = f"{position:02d}-pages-{page_start}-{page_end}"
            title = f"{job['title']}：{filename} 第 {page_start}-{page_end} 页"
            chapters.append(
                {
                    "position": position,
                    "slug": slug,
                    "title": title,
                    "page_start": page_start,
                    "page_end": page_end,
                    "markdown_key": f"{prefix}/chapters/{slug}.md",
                    "markdown": f"# {title}\n\n" + "\n\n".join(selected_pages),
                }
            )
            position += 1
    return {
        "extractor": {"name": "local_pypdf", "version": "1"},
        "knowledge_foundations": ["book-to-skill", "the-knowledge-guy"],
        "chapters": chapters,
    }


async def process_textbook_job(*, job_id: str) -> dict[str, Any]:
    """Claim a persisted job and persist reviewable frozen Markdown content."""
    job = await claim_textbook_processing_job(job_id=job_id)
    if not job:
        raise TextbookNotFoundError("Textbook processing job is not queued")
    try:
        if _uses_artifact_sources(job):
            package = await build_frozen_artifact_package(job)
            prefix = _artifact_bundle_prefix(job["sources"])
        else:
            package = await build_local_pdf_package(job)
            prefix = await write_textbook_content_bundle(job, package)
        completed = await complete_textbook_processing_job(
            job_id=str(job["job_id"]),
            version_id=str(job["version_id"]),
            attempt_count=int(job["attempt_count"]),
            bundle_prefix=prefix,
            extractor=package["extractor"],
            chapters=package["chapters"],
        )
        if not completed:
            raise TextbookProcessingError("Textbook processing claim was lost")
        return completed
    except Exception as exc:
        await fail_textbook_processing_job(
            job_id=str(job["job_id"]),
            version_id=str(job["version_id"]),
            attempt_count=int(job["attempt_count"]),
            error_message=str(exc),
        )
        if isinstance(exc, TextbookError):
            raise
        raise TextbookProcessingError("Local textbook processing failed") from exc


async def list_parent_textbooks(*, parent_user_id: str) -> list[dict[str, Any]]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can manage family textbooks")
    return await list_textbooks_for_parent(parent_user_id)


async def list_completed_textbook_parse_jobs(
    *, parent_user_id: str
) -> list[dict[str, Any]]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError(
            "Only a parent can select textbook sources"
        )
    return await list_completed_parse_jobs_for_parent(
        parent_user_id=parent_user_id
    )


async def get_parent_textbook(
    *, parent_user_id: str, textbook_id: str
) -> dict[str, Any]:
    textbook = await get_textbook_for_parent(
        parent_user_id=parent_user_id, textbook_id=textbook_id
    )
    if not textbook:
        raise TextbookNotFoundError("Textbook not found")
    return textbook


async def run_processing_for_parent(
    *, parent_user_id: str, job_id: str
) -> dict[str, Any]:
    job = await get_processing_job_for_parent(
        parent_user_id=parent_user_id, job_id=job_id
    )
    if not job:
        raise TextbookNotFoundError("Textbook processing job not found")
    if job["status"] != "queued":
        raise TextbookTransitionError(
            f"Textbook processing job cannot run from {job['status']}"
        )
    return await process_textbook_job(job_id=job_id)


async def retry_processing_for_parent(
    *, parent_user_id: str, job_id: str
) -> dict[str, Any]:
    job = await retry_textbook_processing_job(
        parent_user_id=parent_user_id, job_id=job_id
    )
    if not job:
        raise TextbookTransitionError(
            "Only a failed or expired textbook processing job can be retried"
        )
    return job


async def assign_publication(
    *, parent_user_id: str, publication_id: str, student_user_id: str
) -> dict[str, Any]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can assign textbook publications")
    assignment = await assign_textbook_publication(
        parent_user_id=parent_user_id,
        publication_id=publication_id,
        student_user_id=student_user_id,
    )
    if not assignment:
        raise TextbookNotFoundError("Publication or household student not found")
    return assignment


async def list_learning_assignments(*, student_user_id: str) -> list[dict[str, Any]]:
    membership = await get_membership_for_user(student_user_id)
    if not membership or membership["role"] != "student":
        raise TextbookPermissionError("Only a student can access learning assignments")
    return await list_student_assignments(student_user_id)


async def get_student_structure(
    *, student_user_id: str, assignment_id: str
) -> dict[str, Any]:
    membership = await get_membership_for_user(student_user_id)
    if not membership or membership["role"] != "student":
        raise TextbookPermissionError("Only a student can access learning assignments")
    structure = await get_student_published_structure(
        student_user_id=student_user_id,
        assignment_id=assignment_id,
    )
    if not structure:
        raise TextbookNotFoundError("Published textbook structure not found")
    return structure


async def get_student_kp_lesson(
    *, student_user_id: str, assignment_id: str, knowledge_point_id: str
) -> dict[str, Any]:
    membership = await get_membership_for_user(student_user_id)
    if not membership or membership["role"] != "student":
        raise TextbookPermissionError("Only a student can access learning lessons")
    lesson = await get_student_published_kp_lesson(
        student_user_id=student_user_id,
        assignment_id=assignment_id,
        knowledge_point_id=knowledge_point_id,
    )
    if not lesson:
        raise TextbookNotFoundError("Published knowledge-point lesson not found")
    content = await read_kp_lesson_revision(str(lesson["content_key"]))
    return {
        **lesson,
        "content_markdown": content.decode("utf-8"),
    }
