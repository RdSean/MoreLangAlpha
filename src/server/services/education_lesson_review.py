"""Parent lesson generation, review, editing, approval, and publication."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.server.database.education_textbooks import (
    approve_kp_lesson_revision,
    create_kp_lesson_revision,
    get_active_lesson_generation_for_parent,
    get_generation_job_for_parent,
    get_kp_lesson_by_knowledge_point_for_parent,
    get_kp_lesson_for_parent,
    publish_textbook_structure,
)
from src.server.services.education_lesson_jobs import (
    _processing_profile_sha256,
    launch_kp_lesson_generation,
    queue_kp_lesson_generation_for_parent,
)
from src.server.services.education_lesson_validation import (
    KnowledgePointLessonValidationError,
    validate_kp_lesson_outputs,
)
from src.server.services.education_teaching_storage import (
    read_kp_lesson_revision,
    write_kp_lesson_revision,
)
from src.server.services.education_textbooks import (
    TextbookError,
    TextbookNotFoundError,
    TextbookPermissionError,
    TextbookTransitionError,
    get_household_context_for_parent,
)


async def queue_lesson_for_parent(
    *,
    parent_user_id: str,
    knowledge_point_id: str,
    auto_grading: bool = False,
) -> dict[str, Any]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can generate lessons")
    try:
        queued = await queue_kp_lesson_generation_for_parent(
            parent_user_id=parent_user_id,
            knowledge_point_id=knowledge_point_id,
            auto_grading=auto_grading,
        )
    except LookupError as exc:
        raise TextbookNotFoundError("Accepted knowledge point not found") from exc
    try:
        await launch_kp_lesson_generation(
            parent_user_id=parent_user_id,
            generation_job_id=str(queued["generation_job_id"]),
        )
    except Exception as exc:
        projection = await get_generation_job_for_parent(
            parent_user_id=parent_user_id,
            generation_job_id=str(queued["generation_job_id"]),
        )
        if projection and projection.get("status") in {"failed", "cancelled"}:
            return projection
        raise TextbookError("单知识点课程生成无法启动，请稍后重试。") from exc
    return await get_generation_job_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=str(queued["generation_job_id"]),
    ) or queued


async def get_lesson_for_parent(
    *, parent_user_id: str, lesson_id: str
) -> dict[str, Any]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can review lessons")
    lesson = await get_kp_lesson_for_parent(
        parent_user_id=parent_user_id,
        lesson_id=lesson_id,
    )
    if not lesson:
        raise TextbookNotFoundError("Knowledge-point lesson not found")
    revisions = lesson.get("revisions") or []
    latest_revision_id = lesson.get("latest_revision_id")
    latest_revision = next(
        (
            revision
            for revision in revisions
            if str(revision.get("revision_id")) == str(latest_revision_id)
        ),
        None,
    )
    if latest_revision is None:
        raise TextbookNotFoundError("Knowledge-point lesson revision not found")
    content = await read_kp_lesson_revision(str(latest_revision["content_key"]))
    return {
        **lesson,
        "content_markdown": content.decode("utf-8"),
    }


async def get_lesson_for_knowledge_point(
    *, parent_user_id: str, knowledge_point_id: str
) -> dict[str, Any] | None:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can review lessons")
    lesson = await get_kp_lesson_by_knowledge_point_for_parent(
        parent_user_id=parent_user_id,
        knowledge_point_id=knowledge_point_id,
    )
    if not lesson:
        return None
    return await get_lesson_for_parent(
        parent_user_id=parent_user_id,
        lesson_id=str(lesson["lesson_id"]),
    )


async def approve_lesson_for_parent(
    *,
    parent_user_id: str,
    lesson_id: str,
    revision_id: str,
) -> dict[str, Any]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can approve lessons")
    lesson = await get_kp_lesson_for_parent(
        parent_user_id=parent_user_id,
        lesson_id=lesson_id,
    )
    if not lesson:
        raise TextbookNotFoundError("Knowledge-point lesson not found")
    revision_ids = {
        str(revision["revision_id"])
        for revision in lesson.get("revisions", [])
        if isinstance(revision, Mapping)
    }
    if revision_id not in revision_ids:
        raise TextbookNotFoundError("Knowledge-point lesson revision not found")
    approved = await approve_kp_lesson_revision(
        parent_user_id=parent_user_id,
        lesson_id=lesson_id,
        revision_id=revision_id,
    )
    if not approved:
        raise TextbookTransitionError("Knowledge-point lesson cannot be approved")
    return approved


async def create_manual_lesson_revision(
    *,
    parent_user_id: str,
    lesson_id: str,
    content_markdown: str,
) -> dict[str, Any]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can edit lessons")
    lesson = await get_kp_lesson_for_parent(
        parent_user_id=parent_user_id,
        lesson_id=lesson_id,
    )
    if not lesson:
        raise TextbookNotFoundError("Knowledge-point lesson not found")
    revisions = lesson.get("revisions") or []
    next_revision = max(
        (int(revision["revision"]) for revision in revisions),
        default=0,
    ) + 1
    markdown = content_markdown.encode("utf-8")
    try:
        validate_kp_lesson_outputs(
            markdown=markdown,
            practice=None,
            auto_grading=False,
        )
    except KnowledgePointLessonValidationError as exc:
        raise TextbookTransitionError(str(exc)) from exc
    storage_job = {
        **lesson,
        "lesson_revision": next_revision,
    }
    stored = await write_kp_lesson_revision(storage_job, markdown)
    revision = await create_kp_lesson_revision(
        knowledge_point_id=str(lesson["knowledge_point_id"]),
        content_key=stored["content_key"],
        content_sha256=stored["content_sha256"],
        size_bytes=stored["size_bytes"],
        processing_profile_sha256=_processing_profile_sha256(
            auto_grading=False
        ),
        generation_job_id=None,
    )
    if revision is None:
        raise TextbookTransitionError("Knowledge-point lesson revision was not created")
    return revision


async def publish_structure_for_parent(
    *,
    parent_user_id: str,
    version_id: str,
    structure_id: str,
) -> dict[str, Any]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can publish textbook structures")
    publication = await publish_textbook_structure(
        parent_user_id=parent_user_id,
        version_id=version_id,
        structure_id=structure_id,
    )
    if not publication:
        raise TextbookTransitionError(
            "Textbook structure requires approved lessons for every knowledge point"
        )
    return publication


async def get_lesson_generation_status_for_parent(
    *, parent_user_id: str, knowledge_point_id: str
) -> dict[str, Any]:
    """Return the active lesson run for one knowledge point, if any."""
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can read lesson progress")
    job = await get_active_lesson_generation_for_parent(
        parent_user_id=parent_user_id,
        knowledge_point_id=knowledge_point_id,
    )
    return {
        "knowledge_point_id": knowledge_point_id,
        "generating": bool(job),
        "generation_job_id": str(job["generation_job_id"]) if job else None,
        "status": str(job["status"]) if job else None,
        "attempt_count": int(job["attempt_count"] or 0) if job else 0,
        "auto_grading": bool(job["auto_grading"]) if job else False,
        "error_code": job.get("error_code") if job else None,
        "error_message": job.get("error_message") if job else None,
        "started_at": job.get("started_at") if job else None,
        "heartbeat_at": job.get("heartbeat_at") if job else None,
        "root_run_id": str(job["root_run_id"]) if job and job.get("root_run_id") else None,
    }
