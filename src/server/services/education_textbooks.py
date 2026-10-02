"""Versioning, explicit local processing, and authorization for family textbooks."""

import asyncio
import hashlib
import json
import logging
import re
from collections.abc import Mapping
from io import BytesIO
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote
from uuid import UUID, uuid4

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
    list_completed_parse_jobs_for_parent,
    list_textbooks_for_parent,
    queue_textbook_processing,
    queue_textbook_processing_from_artifacts,
    retry_textbook_processing_job,
    TextbookQueueValidationError,
)
from src.server.database.education_members import get_membership_for_user
from src.server.database.education_books import (
    get_managed_asset_for_user,
    get_managed_material_for_user,
    get_managed_source_for_user,
    get_managed_structure_for_user,
    get_managed_textbook_for_parent,
    list_book_source_candidates_for_parent,
    list_managed_textbooks_for_parent,
)
from src.server.database.education_learning import (
    assign_textbook_students,
    get_student_assignment_by_id,
    list_student_textbook_assignments,
    list_textbook_assignments_for_parent,
    revoke_textbook_students,
)
from src.server.database.education_book_jobs import (
    create_materials_job,
    get_book_job_for_parent,
    retry_book_job,
)
from src.server.database.session_lock import await_settled
from src.server.services.education_textbook_source_snapshots import (
    TextbookSourceSnapshotError,
    cleanup_snapshot_objects,
    create_textbook_from_library_source,
    freeze_parse_job_source,
)
from src.server.services.education_textbook_snapshot_reads import (
    TextbookSnapshotReadError,
    read_snapshot_artifact_bytes,
    safe_asset_manifest_entry,
)
from src.server.services.education_book_storage import read_material_bytes
from src.server.services.education_book_jobs import cancel_book_job
from src.server.services.education_book_structure import (
    get_more_to_skills_identity,
    project_material_content_files,
)
from src.server.services.education_textbook_storage import write_textbook_content_bundle
from src.utils.storage import get_bytes

if TYPE_CHECKING:
    from src.server.app.education.book_models import BookJobCreateRequest


logger = logging.getLogger(__name__)

_SOURCE_SNAPSHOT_FORMAT = "langalpha-textbook-source-snapshot/v1"
_MARKDOWN_MEDIA_TYPE = "text/markdown"
_MARKDOWN_FORMATS = frozenset({"gfm", "markdown"})
_MARKDOWN_IMAGE_RE = re.compile(
    r"""!\[[^\]]*\]\(\s*(?P<target><[^>\n]+>|[^\s)]+)"""
    r"""(?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?\s*\)""",
    re.DOTALL,
)

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


def _managed_source_candidate(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "document_id": str(row["document_id"]),
        "parse_job_id": str(row["parse_job_id"]),
        "primary_artifact_id": str(row["primary_artifact_id"]),
        "filename": str(row["filename"]),
        "media_type": str(row["media_type"]),
        "parser_id": str(row["parser_id"]),
        "parser_name": str(row["parser_name"]),
        "completed_at": row["completed_at"],
        "content_sha256": str(row["content_sha256"]),
        "size_bytes": int(row["size_bytes"]),
        "image_count": int(row["image_count"]),
    }


def _managed_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "textbook_id": str(row["textbook_id"]),
        "title": str(row["title"]),
        "structure_status": str(row["structure_status"]),
        "materials": {
            "total": int(row["material_total"]),
            "ready": int(row["material_ready"]),
        },
        "current_job": row.get("current_job"),
        "updated_at": row["updated_at"],
    }


def _rewrite_managed_asset_urls(
    markdown: str,
    *,
    textbook_id: str | UUID,
    manifest: object,
) -> str:
    if not isinstance(manifest, list):
        return markdown
    assets = [
        safe
        for entry in manifest
        if (safe := safe_asset_manifest_entry(entry)) is not None
        and safe["artifact_kind"] == "embedded_image"
    ]
    by_path = {asset["relative_path"]: asset for asset in assets}
    by_basename: dict[str, list[dict[str, str]]] = {}
    for asset in assets:
        basename = PurePosixPath(asset["relative_path"]).name
        by_basename.setdefault(basename, []).append(asset)

    def replace(match: re.Match[str]) -> str:
        raw_target = match.group("target")
        bracketed = raw_target.startswith("<") and raw_target.endswith(">")
        target = raw_target[1:-1].strip() if bracketed else raw_target.strip()
        target = unquote(target)
        if (
            not target
            or target.startswith(("#", "//", "/"))
            or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target)
        ):
            return match.group(0)
        normalized = target[2:] if target.startswith("./") else target
        if (
            "\\" in normalized
            or "\x00" in normalized
            or any(part in {"", ".", ".."} for part in normalized.split("/"))
        ):
            return match.group(0)
        asset = by_path.get(normalized)
        if asset is None:
            matches = by_basename.get(PurePosixPath(normalized).name, [])
            if len(matches) != 1:
                return match.group(0)
            asset = matches[0]
        endpoint = (
            f"/api/v1/education/textbooks/{textbook_id}/assets/{asset['artifact_id']}"
        )
        replacement = f"<{endpoint}>" if bracketed else endpoint
        return match.group(0).replace(raw_target, replacement, 1)

    return _MARKDOWN_IMAGE_RE.sub(replace, markdown)


async def list_book_source_candidates(*, parent_user_id: str) -> list[dict[str, Any]]:
    rows = await list_book_source_candidates_for_parent(parent_user_id=parent_user_id)
    return [_managed_source_candidate(row) for row in rows]


async def create_managed_textbook(
    *,
    parent_user_id: str,
    parse_job_id: str,
    primary_artifact_id: str,
    title: str,
    idempotency_key: str,
) -> dict[str, str]:
    context = await get_household_context_for_parent(parent_user_id)
    if context is None:
        raise TextbookPermissionError("Only a parent can create family textbooks")
    normalized_title = _required_title(title)
    source_suffix = hashlib.sha256(
        f"{parse_job_id}:{primary_artifact_id}".encode("utf-8")
    ).hexdigest()[:12]
    try:
        created = await create_textbook_from_library_source(
            parent_user_id=parent_user_id,
            household_id=str(context["household_id"]),
            title=normalized_title,
            slug=_slug(normalized_title, unique_suffix=source_suffix),
            parse_job_id=parse_job_id,
            primary_artifact_id=primary_artifact_id,
            idempotency_key=idempotency_key,
            identity=get_more_to_skills_identity(),
        )
    except (TextbookSourceSnapshotError, ValueError) as exc:
        raise TextbookError(str(exc)) from exc
    return {
        "textbook_id": str(created["textbook_id"]),
        "job_id": str(created["job_id"]),
    }


async def list_managed_textbooks(*, parent_user_id: str) -> list[dict[str, Any]]:
    rows = await list_managed_textbooks_for_parent(parent_user_id=parent_user_id)
    return [_managed_summary(row) for row in rows]


async def get_managed_textbook_workbench(
    *, parent_user_id: str, textbook_id: str | UUID
) -> dict[str, Any]:
    row = await get_managed_textbook_for_parent(
        parent_user_id=parent_user_id,
        textbook_id=textbook_id,
    )
    if row is None:
        raise TextbookNotFoundError("Textbook not found")
    summary = _managed_summary(row)
    summary.update(
        {
            "source": {
                **_managed_source_candidate(row),
                "frozen_at": row["frozen_at"],
            },
            "current_structure_id": row["current_structure_id"],
            "recent_job": row.get("recent_job"),
            "assigned_student_count": int(row["assigned_student_count"]),
        }
    )
    return summary


async def get_managed_textbook_structure(
    *, user_id: str, textbook_id: str | UUID
) -> dict[str, Any]:
    row = await get_managed_structure_for_user(
        user_id=user_id,
        textbook_id=textbook_id,
    )
    if row is None:
        raise TextbookNotFoundError("Textbook structure not found")
    points = [dict(point) for point in row["knowledge_points"]]
    content_files = {
        str(point["skill_kp_id"]): f"materials/{point['knowledge_point_id']}.md"
        for point in points
        if point.get("content_key") is not None
    }
    projections = []
    for point in points:
        content_file = content_files.get(str(point["skill_kp_id"]))
        projections.append(
            {
                "knowledge_point_id": point["knowledge_point_id"],
                "skill_kp_id": point["skill_kp_id"],
                "position": point["position"],
                "title": point["title"],
                "unit_skill_node_id": point["unit_skill_node_id"],
                "node_skill_ids": point["node_skill_ids"],
                "start_line": point["start_line"],
                "end_line": point["end_line"],
                "content_file": content_file,
                "material_available": content_file is not None,
            }
        )
    return {
        "textbook_id": str(row["textbook_id"]),
        "structure_id": row["structure_id"],
        "schema_version": row["schema_version"],
        "structure": project_material_content_files(
            row["structure_json"], content_files
        ),
        "knowledge_points": projections,
        "warnings": list(row["validation_warnings"] or []),
    }


async def get_managed_textbook_source(
    *,
    user_id: str,
    textbook_id: str | UUID,
    start_line: int,
    end_line: int,
) -> dict[str, Any]:
    if end_line < start_line:
        raise TextbookError("end_line must be greater than or equal to start_line")
    row = await get_managed_source_for_user(
        user_id=user_id,
        textbook_id=textbook_id,
    )
    if row is None:
        raise TextbookNotFoundError("Textbook source not found")
    prefix = str(row["source_snapshot_prefix"])
    markdown_key = str(row["source_markdown_key"])
    if not markdown_key.startswith(prefix):
        raise TextbookProcessingError("The textbook source pointer is invalid")
    try:
        content, _ = await read_snapshot_artifact_bytes(
            snapshot_prefix=prefix,
            relative_path=markdown_key.removeprefix(prefix),
            expected_sha256=str(row["source_content_sha256"]),
            max_bytes=int(row["source_size_bytes"]),
        )
        markdown = content.decode("utf-8")
    except (TextbookSnapshotReadError, UnicodeDecodeError) as exc:
        raise TextbookProcessingError("The textbook source is unavailable") from exc
    lines = markdown.splitlines()
    total_lines = len(lines)
    if total_lines == 0 or start_line > total_lines:
        raise TextbookError("start_line exceeds the textbook source")
    actual_end = min(end_line, total_lines)
    return {
        "textbook_id": str(row["textbook_id"]),
        "start_line": start_line,
        "end_line": actual_end,
        "total_lines": total_lines,
        "markdown": _rewrite_managed_asset_urls(
            "\n".join(lines[start_line - 1 : actual_end]),
            textbook_id=row["textbook_id"],
            manifest=row["source_asset_manifest"],
        ),
    }


async def get_managed_knowledge_point_material(
    *,
    user_id: str,
    textbook_id: str | UUID,
    knowledge_point_id: str | UUID,
) -> dict[str, Any]:
    row = await get_managed_material_for_user(
        user_id=user_id,
        textbook_id=textbook_id,
        knowledge_point_id=knowledge_point_id,
    )
    if row is None:
        raise TextbookNotFoundError("Knowledge point not found")
    base = {
        "textbook_id": str(row["textbook_id"]),
        "knowledge_point_id": row["knowledge_point_id"],
        "skill_kp_id": str(row["skill_kp_id"]),
    }
    if row.get("content_key") is None:
        return {
            **base,
            "material_available": False,
            "markdown": None,
            "generated_at": None,
            "depth": None,
            "requirements": None,
            "content_sha256": None,
        }
    try:
        content = await read_material_bytes(
            household_id=UUID(str(row["household_id"])),
            textbook_id=UUID(str(row["textbook_id"])),
            knowledge_point_id=UUID(str(row["knowledge_point_id"])),
            content_key=str(row["content_key"]),
            expected_sha256=str(row["content_sha256"]),
            expected_size=int(row["size_bytes"]),
        )
        markdown = content.decode("utf-8")
    except (RuntimeError, UnicodeDecodeError) as exc:
        raise TextbookProcessingError("The textbook material is unavailable") from exc
    return {
        **base,
        "material_available": True,
        "markdown": _rewrite_managed_asset_urls(
            markdown,
            textbook_id=row["textbook_id"],
            manifest=row["source_asset_manifest"],
        ),
        "generated_at": row["updated_at"],
        "depth": row["depth"],
        "requirements": row["requirements"],
        "content_sha256": row["content_sha256"],
    }


async def open_managed_textbook_asset(
    *, user_id: str, textbook_id: str | UUID, asset_id: str
) -> dict[str, Any]:
    row = await get_managed_asset_for_user(
        user_id=user_id,
        textbook_id=textbook_id,
        asset_id=asset_id,
    )
    if row is None:
        raise TextbookNotFoundError("Textbook asset not found")
    manifest = safe_asset_manifest_entry(row.get("manifest_entry"))
    if manifest is None or manifest["artifact_id"] != asset_id:
        raise TextbookProcessingError("The textbook asset manifest is invalid")
    try:
        content, _ = await read_snapshot_artifact_bytes(
            snapshot_prefix=str(row["source_snapshot_prefix"]),
            relative_path=manifest["relative_path"],
            expected_sha256=manifest["sha256"],
            max_bytes=get_document_parsing_config().max_upload_bytes,
        )
    except TextbookSnapshotReadError as exc:
        raise TextbookProcessingError("The textbook asset is unavailable") from exc
    return {
        "content": content,
        "media_type": manifest["media_type"],
        "sha256": manifest["sha256"],
    }


async def create_managed_textbook_job(
    *,
    parent_user_id: str,
    textbook_id: str | UUID,
    request: BookJobCreateRequest,
) -> dict[str, Any]:
    textbook = await get_managed_textbook_for_parent(
        parent_user_id=parent_user_id,
        textbook_id=textbook_id,
    )
    if textbook is None:
        raise TextbookNotFoundError("Textbook not found")
    if textbook.get("current_job") is not None:
        raise TextbookTransitionError("The textbook already has an active job")
    if request.kind != "materials":
        raise TextbookTransitionError(
            "Structure analysis is created when the textbook is added"
        )
    try:
        created = await create_materials_job(
            textbook_id=textbook_id,
            requested_by_user_id=parent_user_id,
            knowledge_point_ids=request.knowledge_point_ids,
            depth=request.depth,
            requirements=request.requirements,
            replace_existing=request.replace_existing,
            include_supplementary=request.include_supplementary,
            idempotency_key=request.idempotency_key,
            identity=get_more_to_skills_identity(),
        )
    except ValueError as exc:
        if "targets must belong" in str(exc):
            raise TextbookNotFoundError(
                "One or more knowledge points were not found"
            ) from exc
        raise TextbookTransitionError(str(exc)) from exc
    result = await get_book_job_for_parent(
        job_id=created["job_id"],
        parent_user_id=parent_user_id,
    )
    if result is None:
        raise TextbookProcessingError("The textbook job could not be read")
    return result


async def cancel_managed_textbook_job(
    *, parent_user_id: str, job_id: str | UUID
) -> dict[str, Any]:
    visible = await get_book_job_for_parent(
        job_id=job_id,
        parent_user_id=parent_user_id,
    )
    if visible is None:
        raise TextbookNotFoundError("Book job not found")
    try:
        await cancel_book_job(job_id=str(job_id))
    except LookupError as exc:
        raise TextbookTransitionError("The textbook job is no longer active") from exc
    result = await get_book_job_for_parent(
        job_id=job_id,
        parent_user_id=parent_user_id,
    )
    if result is None:
        raise TextbookProcessingError("The cancelled textbook job could not be read")
    return result


async def retry_managed_textbook_job(
    *, parent_user_id: str, job_id: str | UUID
) -> dict[str, Any]:
    visible = await get_book_job_for_parent(
        job_id=job_id,
        parent_user_id=parent_user_id,
    )
    if visible is None:
        raise TextbookNotFoundError("Book job not found")
    try:
        created = await retry_book_job(
            source_job_id=job_id,
            requested_by_user_id=parent_user_id,
            idempotency_key=f"retry:{job_id}",
            identity=get_more_to_skills_identity(),
        )
    except (LookupError, ValueError) as exc:
        raise TextbookTransitionError(str(exc)) from exc
    result = await get_book_job_for_parent(
        job_id=created["job_id"],
        parent_user_id=parent_user_id,
    )
    if result is None:
        raise TextbookProcessingError("The retried textbook job could not be read")
    return result


def _public_assignment(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "textbook_id": str(row["textbook_id"]),
        "student_user_id": str(row["student_user_id"]),
        "assigned_at": row["created_at"],
    }


async def list_managed_textbook_assignments(
    *, parent_user_id: str, textbook_id: str | UUID
) -> list[dict[str, Any]]:
    if (
        await get_managed_textbook_for_parent(
            parent_user_id=parent_user_id,
            textbook_id=textbook_id,
        )
        is None
    ):
        raise TextbookNotFoundError("Textbook not found")
    rows = await list_textbook_assignments_for_parent(
        textbook_id=textbook_id,
        parent_user_id=parent_user_id,
    )
    return [_public_assignment(row) for row in rows]


async def assign_managed_textbook(
    *,
    parent_user_id: str,
    textbook_id: str | UUID,
    student_user_ids: list[str],
) -> list[dict[str, Any]]:
    try:
        rows = await assign_textbook_students(
            textbook_id=textbook_id,
            student_user_ids=student_user_ids,
            assigned_by_user_id=parent_user_id,
        )
    except PermissionError as exc:
        raise TextbookNotFoundError("Textbook or student not found") from exc
    if rows is None:
        raise TextbookNotFoundError("Textbook not found")
    return [_public_assignment(row) for row in rows]


async def revoke_managed_textbook(
    *,
    parent_user_id: str,
    textbook_id: str | UUID,
    student_user_ids: list[str],
) -> None:
    revoked = await revoke_textbook_students(
        textbook_id=textbook_id,
        student_user_ids=student_user_ids,
        parent_user_id=parent_user_id,
    )
    if revoked is None:
        raise TextbookNotFoundError("Textbook not found")


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
    if (
        not isinstance(value, str)
        or not value.startswith("education/")
        or not value.endswith("/")
    ):
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
    return (
        normalized if normalized.startswith("artifacts/") else f"artifacts/{normalized}"
    )


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
        "/".join(
            _snapshot_prefix(source.get("snapshot_prefix")).rstrip("/").split("/")[:-1]
        )
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
    if len({_source_position(source) for source in ordered_sources}) != len(
        ordered_sources
    ):
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
            raise TextbookProcessingError(
                "A frozen textbook primary artifact is invalid"
            )
        if not _is_sha256(primary_sha256):
            raise TextbookProcessingError("A frozen textbook source digest is invalid")

        manifest_bytes = await asyncio.to_thread(get_bytes, f"{prefix}manifest.json")
        if (
            not isinstance(manifest_bytes, bytes)
            or not manifest_bytes
            or len(manifest_bytes) > max_bytes
        ):
            raise TextbookProcessingError(
                "A frozen textbook snapshot manifest is invalid"
            )
        try:
            manifest = json.loads(manifest_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TextbookProcessingError(
                "A frozen textbook snapshot manifest is invalid"
            ) from exc
        if (
            not isinstance(manifest, Mapping)
            or manifest.get("format") != _SOURCE_SNAPSHOT_FORMAT
        ):
            raise TextbookProcessingError(
                "A frozen textbook snapshot manifest is invalid"
            )
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
            raise TextbookProcessingError(
                "A frozen textbook snapshot artifact is invalid"
            )
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
        media_type = (
            str(primary.get("media_type") or "").split(";", 1)[0].strip().lower()
        )
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
            raise TextbookProcessingError(
                "A frozen textbook source filename is invalid"
            )
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
        raise TextbookPermissionError("Only a parent can start textbook processing")
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
            if not owned_job or str(owned_job.get("status") or "") != "completed":
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
        "knowledge_foundations": ["book-to-skill"],
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
        raise TextbookPermissionError("Only a parent can select textbook sources")
    return await list_completed_parse_jobs_for_parent(parent_user_id=parent_user_id)


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
    return await list_student_textbook_assignments(student_user_id=student_user_id)


async def get_student_structure(
    *, student_user_id: str, assignment_id: str
) -> dict[str, Any]:
    membership = await get_membership_for_user(student_user_id)
    if not membership or membership["role"] != "student":
        raise TextbookPermissionError("Only a student can access learning assignments")
    assignment = await get_student_assignment_by_id(
        student_user_id=student_user_id,
        assignment_id=assignment_id,
    )
    if not assignment:
        raise TextbookNotFoundError("Textbook assignment not found")
    structure = await get_managed_textbook_structure(
        user_id=student_user_id,
        textbook_id=assignment["textbook_id"],
    )
    return {
        **structure,
        "assignment_id": assignment["assignment_id"],
        "textbook_title": assignment["textbook_title"],
    }


async def get_student_kp_lesson(
    *, student_user_id: str, assignment_id: str, knowledge_point_id: str
) -> dict[str, Any]:
    membership = await get_membership_for_user(student_user_id)
    if not membership or membership["role"] != "student":
        raise TextbookPermissionError("Only a student can access learning lessons")
    assignment = await get_student_assignment_by_id(
        student_user_id=student_user_id,
        assignment_id=assignment_id,
    )
    if not assignment:
        raise TextbookNotFoundError("Textbook assignment not found")
    material = await get_managed_knowledge_point_material(
        user_id=student_user_id,
        textbook_id=assignment["textbook_id"],
        knowledge_point_id=knowledge_point_id,
    )
    return {
        **material,
        "assignment_id": assignment["assignment_id"],
    }
