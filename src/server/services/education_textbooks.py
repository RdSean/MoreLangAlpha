"""Current textbook workbench, jobs, and student authorization facade."""

import hashlib
import logging
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote
from uuid import UUID

from src.config.settings import get_document_parsing_config
from src.server.database.education_tasks import get_household_context_for_parent
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
from src.server.services.education_textbook_source_snapshots import (
    TextbookSourceSnapshotError,
    create_textbook_from_library_source,
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

if TYPE_CHECKING:
    from src.server.app.education.book_models import BookJobCreateRequest


logger = logging.getLogger(__name__)

_MARKDOWN_IMAGE_RE = re.compile(
    r"""!\[[^\]]*\]\(\s*(?P<target><[^>\n]+>|[^\s)]+)"""
    r"""(?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?\s*\)""",
    re.DOTALL,
)


class TextbookError(RuntimeError):
    """Base exception for family textbook operations."""


class TextbookTransitionError(TextbookError, ValueError):
    """A textbook operation violates its current processing contract."""


class TextbookPermissionError(TextbookError, PermissionError):
    """The caller does not own the required household teaching capability."""


class TextbookNotFoundError(TextbookError, LookupError):
    """The requested textbook record is absent or outside its visible scope."""


class TextbookProcessingError(TextbookError):
    """A current textbook artifact or job could not be safely read."""


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


async def delete_managed_textbook(*, parent_user_id: str, textbook_id: UUID) -> None:
    from psycopg.errors import DeadlockDetected, LockNotAvailable
    from src.server.database.education_book_deletion import delete_textbook_for_parent
    from src.server.database.conversation import thread_exists_key
    from src.server.services.thread_lifecycle_feed import publish_thread_deleted
    from src.utils.cache.redis_cache import get_cache_client

    if await get_household_context_for_parent(parent_user_id) is None:
        raise TextbookPermissionError("只有家长可以删除教材")
    try:
        threads = await delete_textbook_for_parent(
            parent_user_id=parent_user_id, textbook_id=textbook_id
        )
    except LookupError as exc:
        raise TextbookNotFoundError(str(exc)) from exc
    except ValueError as exc:
        raise TextbookTransitionError(str(exc)) from exc
    except (DeadlockDetected, LockNotAvailable) as exc:
        raise TextbookTransitionError("教材正在被修改，请稍后重试") from exc
    for thread in threads:
        try:
            cache = get_cache_client()
            if cache.enabled and cache.client:
                await cache.client.delete(
                    thread_exists_key(str(thread["conversation_thread_id"]))
                )
            await publish_thread_deleted(
                user_id=thread["user_id"],
                thread_id=str(thread["conversation_thread_id"]),
                workspace_id=str(thread["workspace_id"]),
            )
        except Exception:
            logger.exception("Could not publish deleted learning thread hint")


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


async def list_learning_assignments(*, student_user_id: str) -> list[dict[str, Any]]:
    membership = await get_membership_for_user(student_user_id)
    if not membership or membership["role"] != "student":
        raise TextbookPermissionError("Only a student can access learning assignments")
    assignments = await list_student_textbook_assignments(
        student_user_id=student_user_id
    )
    return [{**row, "textbook_id": str(row["textbook_id"])} for row in assignments]


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
