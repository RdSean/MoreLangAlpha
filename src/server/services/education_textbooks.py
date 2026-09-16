"""Versioning, explicit local processing, and authorization for family textbooks."""

import asyncio
import hashlib
import json
import logging
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path, PurePosixPath
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
    get_teaching_asset_review_for_parent,
    get_teaching_input_for_parent,
    get_teaching_job_projection_for_parent,
    get_owned_parse_job,
    get_textbook_for_parent,
    get_student_chapter_context_record,
    get_student_learning as get_student_learning_record,
    list_completed_parse_jobs_for_parent,
    list_student_assignments,
    list_student_learning_records,
    list_textbooks_for_parent,
    publish_textbook_version,
    queue_teaching_package,
    queue_textbook_processing,
    queue_textbook_processing_from_artifacts,
    retry_textbook_processing_job,
    submit_student_answer,
    TextbookQueueValidationError,
    textbook_processing_job_exists,
    update_student_progress,
)
from src.server.database.education_members import get_membership_for_user
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
from src.server.services.education_teaching_assets import (
    TeachingAssetValidationError,
    expected_teaching_asset_paths,
)
from src.server.services.education_teaching_storage import (
    build_staged_teaching_input,
    hydrate_source_asset_manifests,
)
from src.utils.storage import get_bytes


logger = logging.getLogger(__name__)

_STATE_PROBE_ATTEMPTS = 3
_STATE_PROBE_BACKOFF_SECONDS = 0.05
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

    async def reconcile_ambiguous_queue_failure() -> None:
        durable_job_exists = await asyncio.shield(
            _probe_textbook_processing_job_state(
                job_id=job_id,
                version_id=version_id,
            )
        )
        if durable_job_exists is False:
            await cleanup_written_snapshots()

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

    try:
        job = await queue_textbook_processing_from_artifacts(
            parent_user_id=parent_user_id,
            household_id=household_id,
            textbook_id=textbook_id,
            sources=sources,
            extractor_name="managed_ptc",
            extractor_version="1",
            version_id=version_id,
            job_id=job_id,
        )
    except TextbookQueueValidationError as exc:
        await cleanup_written_snapshots()
        raise TextbookError(str(exc)) from exc
    except asyncio.CancelledError:
        await reconcile_ambiguous_queue_failure()
        raise
    except Exception:
        await reconcile_ambiguous_queue_failure()
        raise

    if not job:
        await cleanup_written_snapshots()
        raise TextbookNotFoundError("Textbook not found")
    return job


async def _probe_textbook_processing_job_state(
    *, job_id: str, version_id: str
) -> bool | None:
    """Best-effort exact-state probe; unknown never authorizes cleanup."""
    for attempt in range(1, _STATE_PROBE_ATTEMPTS + 1):
        try:
            durable_state = await textbook_processing_job_exists(
                job_id=job_id,
                version_id=version_id,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            durable_state = None
        if durable_state is not None:
            return bool(durable_state)
        if attempt < _STATE_PROBE_ATTEMPTS:
            await asyncio.sleep(_STATE_PROBE_BACKOFF_SECONDS * attempt)

    logger.warning(
        "textbook_source_snapshot_state_indeterminate",
        extra={"version_id": version_id, "job_id": job_id},
    )
    return None


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


def _managed_skill_hash(skill_name: str) -> str:
    # The managed teaching skills ship in a bundle, so the source is found
    # through the same chain the agent's skill delivery uses rather than a
    # repo-relative path.
    source = _managed_skill_source_root(skill_name) / "SKILL.md"
    try:
        return hashlib.sha256(source.read_bytes()).hexdigest()
    except OSError as exc:
        raise TextbookError("教材教学加工能力当前不可用") from exc


def _managed_skill_source_root(skill_name: str) -> Path:
    """Host directory holding one managed skill, wherever the bundle puts it."""
    from ptc_agent.config.agent import host_skill_dirs

    for root in host_skill_dirs():
        candidate = root / skill_name
        if (candidate / "SKILL.md").is_file():
            return candidate
    raise TextbookError("教材教学加工能力当前不可用")


def _teaching_actions(*, status: str) -> list[str]:
    if status in {"queued", "preparing", "running", "validating"}:
        return ["cancel"]
    if status in {"failed", "cancelled"}:
        return ["resume"]
    return []


def _safe_teaching_projection(job: dict[str, Any]) -> dict[str, Any]:
    """Keep the API shape intentionally independent from PTC runtime records."""
    status = str(job["status"])
    events = [
        {
            "sequence": event["sequence"],
            "phase": event["phase"],
            "summary": event["summary"],
            "chapter_id": event.get("chapter_id"),
            "asset_kind": event.get("asset_kind"),
            "created_at": event.get("created_at"),
        }
        for event in job.get("events", [])
    ]
    phase = job["phase"] if status == "completed" or not events else events[-1]["phase"]
    return {
        "job_id": job["job_id"],
        "teaching_package_id": job["teaching_package_id"],
        "content_version_id": job["content_version_id"],
        "status": status,
        "phase": phase,
        "attempt_count": int(job["attempt_count"]),
        "completed_chapter_count": int(job["completed_chapter_count"]),
        "total_chapter_count": int(job["total_chapter_count"]),
        "last_heartbeat_at": job.get("last_heartbeat_at"),
        "error_message": job.get("error_message") or job.get("package_error_message"),
        "created_at": job.get("created_at"),
        "completed_at": job.get("completed_at"),
        "actions": _teaching_actions(status=status),
        "events": events,
        "attempts": [
            {
                "attempt_id": attempt["attempt_id"],
                "root_run_id": attempt.get("root_run_id"),
                "previous_attempt_id": attempt.get("previous_attempt_id"),
                "status": attempt["status"],
                "started_at": attempt.get("started_at"),
                "heartbeat_at": attempt.get("heartbeat_at"),
                "completed_at": attempt.get("completed_at"),
            }
            for attempt in job.get("attempts", [])
        ],
    }


_REVIEWABLE_TEACHING_ASSET_KINDS = frozenset({"knowledge", "toolkit", "practice"})


def _validated_teaching_asset_review(
    review: Mapping[str, Any],
) -> tuple[Mapping[str, Any], dict[str, Mapping[str, Any]], Any]:
    """Rebuild fixed archive paths only from the service-authored manifest."""
    manifest = review.get("asset_manifest")
    chapters = review.get("chapters")
    if (
        not isinstance(manifest, Mapping)
        or manifest.get("format") != "langalpha-family-teaching-assets/v2"
        or not isinstance(chapters, list)
        or not isinstance(manifest.get("chapters"), list)
    ):
        raise TextbookNotFoundError("Teaching assets are not available")
    manifest_chapters: dict[str, Mapping[str, Any]] = {}
    for entry in manifest["chapters"]:
        if not isinstance(entry, Mapping):
            raise TextbookNotFoundError("Teaching assets are not available")
        chapter_id = str(entry.get("content_chapter_id", ""))
        if not chapter_id or chapter_id in manifest_chapters:
            raise TextbookNotFoundError("Teaching assets are not available")
        manifest_chapters[chapter_id] = entry
    chapter_records: dict[str, Mapping[str, Any]] = {}
    frozen_chapters: list[dict[str, Any]] = []
    for chapter in chapters:
        if not isinstance(chapter, Mapping):
            raise TextbookNotFoundError("Teaching assets are not available")
        chapter_id = str(chapter.get("content_chapter_id", ""))
        manifest_chapter = manifest_chapters.get(chapter_id)
        if not manifest_chapter or chapter_id in chapter_records:
            raise TextbookNotFoundError("Teaching assets are not available")
        chapter_records[chapter_id] = chapter
        frozen_chapters.append(
            {
                "content_chapter_id": chapter_id,
                "content_sha256": manifest_chapter.get("content_sha256"),
                "position": chapter.get("position"),
                "slug": chapter.get("slug"),
            }
        )
    if set(chapter_records) != set(manifest_chapters):
        raise TextbookNotFoundError("Teaching assets are not available")
    try:
        paths = expected_teaching_asset_paths({"chapters": frozen_chapters})
    except TeachingAssetValidationError as exc:
        raise TextbookNotFoundError("Teaching assets are not available") from exc
    return manifest, chapter_records, paths


def _safe_review_asset_metadata(asset: object) -> dict[str, Any]:
    if not isinstance(asset, Mapping):
        raise TextbookNotFoundError("Teaching assets are not available")
    kind = asset.get("kind")
    size_bytes = asset.get("size_bytes")
    sha256 = asset.get("sha256")
    if (
        kind not in _REVIEWABLE_TEACHING_ASSET_KINDS
        or not isinstance(size_bytes, int)
        or isinstance(size_bytes, bool)
        or size_bytes < 0
        or not isinstance(sha256, str)
        or len(sha256) != 64
    ):
        raise TextbookNotFoundError("Teaching assets are not available")
    return {"kind": kind, "size_bytes": size_bytes, "sha256": sha256}


def _private_teaching_asset_key(bundle_prefix: object, relative_path: str) -> str:
    if not isinstance(bundle_prefix, str) or not bundle_prefix.startswith("education/"):
        raise TextbookNotFoundError("Teaching assets are not available")
    prefix_parts = bundle_prefix.split("/")
    if any(part in {"", ".", ".."} for part in prefix_parts):
        raise TextbookNotFoundError("Teaching assets are not available")
    return f"{bundle_prefix}/{relative_path}"


async def get_teaching_asset_summary(
    *, parent_user_id: str, teaching_package_id: str
) -> dict[str, Any]:
    review = await get_teaching_asset_review_for_parent(
        parent_user_id=parent_user_id, teaching_package_id=teaching_package_id
    )
    if not review:
        raise TextbookNotFoundError("Teaching package not found")
    manifest, chapter_records, _paths = _validated_teaching_asset_review(review)
    concept_index = manifest.get("concept_index")
    coverage_audit = manifest.get("coverage_audit")
    if (
        not isinstance(concept_index, Mapping)
        or not isinstance(coverage_audit, Mapping)
        or not isinstance(concept_index.get("size_bytes"), int)
        or not isinstance(concept_index.get("concept_count"), int)
        or not isinstance(coverage_audit.get("size_bytes"), int)
        or coverage_audit.get("status") != "complete"
    ):
        raise TextbookNotFoundError("Teaching assets are not available")
    manifest_chapters = {
        str(chapter["content_chapter_id"]): chapter for chapter in manifest["chapters"]
    }
    chapters = []
    for chapter_id, chapter in sorted(
        chapter_records.items(), key=lambda item: int(item[1]["position"])
    ):
        entry = manifest_chapters[chapter_id]
        assets = entry.get("assets")
        if (
            entry.get("coverage_status") != "complete"
            or not isinstance(entry.get("concept_count"), int)
            or not isinstance(assets, list)
        ):
            raise TextbookNotFoundError("Teaching assets are not available")
        safe_assets = [_safe_review_asset_metadata(asset) for asset in assets]
        if {asset["kind"] for asset in safe_assets} != _REVIEWABLE_TEACHING_ASSET_KINDS:
            raise TextbookNotFoundError("Teaching assets are not available")
        chapters.append(
            {
                "chapter_id": chapter_id,
                "position": chapter["position"],
                "title": chapter["title"],
                "coverage_status": entry["coverage_status"],
                "concept_count": entry["concept_count"],
                "assets": safe_assets,
            }
        )
    return {
        "teaching_package_id": review["teaching_package_id"],
        "format": manifest["format"],
        "concept_index": {
            "size_bytes": concept_index["size_bytes"],
            "concept_count": concept_index["concept_count"],
        },
        "coverage_audit": {
            "size_bytes": coverage_audit["size_bytes"],
            "status": coverage_audit["status"],
        },
        "chapters": chapters,
    }


async def get_teaching_chapter_asset(
    *,
    parent_user_id: str,
    teaching_package_id: str,
    chapter_id: str,
    kind: str,
) -> dict[str, Any]:
    if kind not in _REVIEWABLE_TEACHING_ASSET_KINDS:
        raise TextbookNotFoundError("Teaching asset not found")
    review = await get_teaching_asset_review_for_parent(
        parent_user_id=parent_user_id, teaching_package_id=teaching_package_id
    )
    if not review:
        raise TextbookNotFoundError("Teaching package not found")
    manifest, _chapter_records, paths = _validated_teaching_asset_review(review)
    manifest_chapter = next(
        (
            entry
            for entry in manifest["chapters"]
            if str(entry.get("content_chapter_id")) == chapter_id
        ),
        None,
    )
    if not isinstance(manifest_chapter, Mapping):
        raise TextbookNotFoundError("Teaching asset not found")
    metadata = next(
        (
            _safe_review_asset_metadata(asset)
            for asset in manifest_chapter.get("assets", [])
            if isinstance(asset, Mapping) and asset.get("kind") == kind
        ),
        None,
    )
    if not metadata:
        raise TextbookNotFoundError("Teaching asset not found")
    chapter_paths = paths.for_chapter(chapter_id)
    relative_path = getattr(chapter_paths, kind)
    key = _private_teaching_asset_key(
        review.get("bundle_prefix"), relative_path.removeprefix("outputs/")
    )
    content = await asyncio.to_thread(get_bytes, key)
    if (
        content is None
        or len(content) != metadata["size_bytes"]
        or hashlib.sha256(content).hexdigest() != metadata["sha256"]
    ):
        raise TextbookNotFoundError("Teaching asset not found")
    try:
        decoded: str | dict[str, Any]
        if kind == "toolkit":
            decoded = content.decode("utf-8").strip()
            if not decoded:
                raise ValueError
        else:
            decoded = json.loads(content.decode("utf-8"))
            if not isinstance(decoded, dict):
                raise ValueError
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as exc:
        raise TextbookNotFoundError("Teaching asset not found") from exc
    return {
        "teaching_package_id": review["teaching_package_id"],
        "chapter_id": chapter_id,
        "kind": kind,
        "content": decoded,
    }


async def get_teaching_job_projection(
    *, parent_user_id: str, job_id: str
) -> dict[str, Any]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can manage teaching jobs")
    job = await get_teaching_job_projection_for_parent(
        parent_user_id=parent_user_id, job_id=job_id
    )
    if not job:
        raise TextbookNotFoundError("Teaching job not found")
    return _safe_teaching_projection(job)


async def queue_teaching_package_for_parent(
    *, parent_user_id: str, content_version_id: str
) -> dict[str, Any]:
    """Freeze a reviewed content version and immediately register its root PTC run."""
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can create teaching packages")
    frozen_input = await get_teaching_input_for_parent(
        parent_user_id=parent_user_id, content_version_id=content_version_id
    )
    if not frozen_input:
        raise TextbookNotFoundError("Reviewable textbook content version not found")

    frozen_input = await hydrate_source_asset_manifests(frozen_input)
    job_id = str(uuid4())
    frozen_input["job_id"] = job_id
    staged = build_staged_teaching_input(frozen_input)
    from src.server.database.education_textbooks import TeachingInputHashes
    from src.server.services.education_teaching_jobs import managed_teaching_prompt

    hashes = TeachingInputHashes(
        input_manifest_sha256=staged["manifest_sha256"],
        book_to_skill_sha256=_managed_skill_hash("book-to-skill"),
        knowledge_guy_sha256=_managed_skill_hash("the-knowledge-guy"),
        adapter_prompt_sha256=hashlib.sha256(
            managed_teaching_prompt(job_id).encode("utf-8")
        ).hexdigest(),
    )
    package = await queue_teaching_package(
        parent_user_id=parent_user_id,
        content_version_id=content_version_id,
        hashes=hashes,
        job_id=job_id,
    )
    if not package:
        raise TextbookNotFoundError("Reviewable textbook content version not found")

    from src.server.services.education_managed_ptc import launch_teaching_attempt

    try:
        await launch_teaching_attempt(parent_user_id=parent_user_id, job_id=job_id)
    except Exception:
        projection = await get_teaching_job_projection_for_parent(
            parent_user_id=parent_user_id, job_id=job_id
        )
        if projection and projection["status"] in {"failed", "cancelled"}:
            return _safe_teaching_projection(projection)
        raise TextbookError("教材教学加工无法启动，请稍后重试。")
    return await get_teaching_job_projection(
        parent_user_id=parent_user_id, job_id=job_id
    )


async def cancel_teaching_job_for_parent(
    *, parent_user_id: str, job_id: str
) -> dict[str, Any]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can manage teaching jobs")
    from src.server.services.education_teaching_jobs import cancel_teaching_job

    try:
        await cancel_teaching_job(parent_user_id=parent_user_id, job_id=job_id)
    except LookupError as exc:
        raise TextbookNotFoundError("Teaching job not found") from exc
    return await get_teaching_job_projection(parent_user_id=parent_user_id, job_id=job_id)


async def resume_teaching_job_for_parent(
    *, parent_user_id: str, job_id: str
) -> dict[str, Any]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can manage teaching jobs")
    from src.server.services.education_managed_ptc import resume_teaching_job

    try:
        await resume_teaching_job(parent_user_id=parent_user_id, job_id=job_id)
    except LookupError as exc:
        raise TextbookTransitionError("Teaching job cannot be resumed") from exc
    except Exception as exc:
        projection = await get_teaching_job_projection_for_parent(
            parent_user_id=parent_user_id, job_id=job_id
        )
        if projection and projection["status"] in {"failed", "cancelled"}:
            return _safe_teaching_projection(projection)
        raise TextbookError("教材教学加工无法启动，请稍后重试。") from exc
    return await get_teaching_job_projection(parent_user_id=parent_user_id, job_id=job_id)


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


async def publish_version(
    *,
    parent_user_id: str,
    textbook_id: str,
    version_id: str,
    teaching_package_id: str,
) -> dict[str, Any]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can publish textbook versions")
    try:
        publication = await publish_textbook_version(
            parent_user_id=parent_user_id,
            textbook_id=textbook_id,
            version_id=version_id,
            teaching_package_id=teaching_package_id,
        )
    except ValueError as exc:
        raise TextbookTransitionError(str(exc)) from exc
    if not publication:
        raise TextbookNotFoundError("Textbook version not found")
    return publication


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


async def get_student_learning(
    *, student_user_id: str, assignment_id: str
) -> dict[str, Any]:
    membership = await get_membership_for_user(student_user_id)
    if not membership or membership["role"] != "student":
        raise TextbookPermissionError("Only a student can access learning assignments")
    learning = await get_student_learning_record(
        student_user_id=student_user_id, assignment_id=assignment_id
    )
    if not learning:
        raise TextbookNotFoundError("Learning assignment not found")
    return learning


async def get_student_chapter_context(
    *, student_user_id: str, assignment_id: str, chapter_id: str
) -> dict[str, Any]:
    membership = await get_membership_for_user(student_user_id)
    if not membership or membership["role"] != "student":
        raise TextbookPermissionError(
            "Only a student can access learning chapter context"
        )
    chapter = await get_student_chapter_context_record(
        student_user_id=student_user_id,
        assignment_id=assignment_id,
        chapter_id=chapter_id,
    )
    if not chapter:
        raise TextbookNotFoundError("Learning chapter not found")
    content = "\n\n".join(
        [
            f"# {chapter['textbook_title']} - {chapter['chapter_title']}",
            "以下是学生已分配且已发布的章节材料。只根据这些材料解释、提问和引导学习；"
            "不声称能访问未发布版本、其他学生记录或家长管理资料。",
            chapter["markdown"],
            chapter["teaching_material"],
        ]
    )
    return {
        "assignment_id": str(chapter["assignment_id"]),
        "chapter_id": str(chapter["chapter_id"]),
        "content": content,
    }


async def record_learning_progress(
    *, student_user_id: str, assignment_id: str, chapter_id: str, status: str
) -> dict[str, Any]:
    if status not in {"learning", "read", "check_completed", "review_recommended"}:
        raise TextbookError("Learning progress status is invalid")
    membership = await get_membership_for_user(student_user_id)
    if not membership or membership["role"] != "student":
        raise TextbookPermissionError("Only a student can record learning progress")
    progress = await update_student_progress(
        student_user_id=student_user_id,
        assignment_id=assignment_id,
        chapter_id=chapter_id,
        status=status,
    )
    if not progress:
        raise TextbookNotFoundError("Learning chapter not found")
    return progress


async def answer_learning_question(
    *, student_user_id: str, assignment_id: str, question_id: str, selected_option: str
) -> dict[str, Any]:
    option = selected_option.strip().upper()
    if not option or len(option) > 32:
        raise TextbookError("A valid answer option is required")
    membership = await get_membership_for_user(student_user_id)
    if not membership or membership["role"] != "student":
        raise TextbookPermissionError("Only a student can answer learning questions")
    answer = await submit_student_answer(
        student_user_id=student_user_id,
        assignment_id=assignment_id,
        question_id=question_id,
        selected_option=option,
    )
    if not answer:
        raise TextbookNotFoundError("Learning question not found")
    return answer


async def get_parent_learning_records(
    *, parent_user_id: str, assignment_id: str
) -> dict[str, Any]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can read learning records")
    records = await list_student_learning_records(
        parent_user_id=parent_user_id, assignment_id=assignment_id
    )
    if not records:
        raise TextbookNotFoundError("Learning assignment not found")
    return records
