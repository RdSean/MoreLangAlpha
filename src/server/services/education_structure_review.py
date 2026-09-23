"""Parent-only creation, editing, and acceptance of textbook structures."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.server.database.education_textbooks import (
    accept_textbook_structure,
    get_generation_job_for_parent,
    get_knowledge_point_source_preview_for_parent,
    get_latest_textbook_structure_for_parent,
    get_teaching_input_for_parent,
    get_textbook_scopes_for_unit,
    get_textbook_structure_for_parent,
    replace_structure_contents,
    requeue_structure_generation,
)
from src.server.services.education_structure_jobs import (
    get_structure_generation_job_for_parent,
    launch_structure_generation,
    queue_structure_generation_for_parent,
)
from src.server.services.education_structure_validation import (
    TextbookStructureValidationError,
    validate_textbook_structure,
)
from src.server.services.education_textbooks import (
    TextbookError,
    TextbookNotFoundError,
    TextbookPermissionError,
    TextbookTransitionError,
    get_household_context_for_parent,
)


async def queue_structure_for_parent(
    *,
    parent_user_id: str,
    content_version_id: str,
    profile_input: Mapping[str, Any] | None = None,
    profile_id: str | None = None,
) -> dict[str, Any]:
    """Queue and immediately launch one structure generation job."""
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can create textbook structures")
    queued: dict[str, Any] | None = None
    try:
        queued = await queue_structure_generation_for_parent(
            parent_user_id=parent_user_id,
            content_version_id=content_version_id,
            profile_input=profile_input,
            profile_id=profile_id,
        )
        if queued.get("status") == "queued":
            await launch_structure_generation(
                parent_user_id=parent_user_id,
                generation_job_id=str(queued["generation_job_id"]),
            )
    except LookupError as exc:
        raise TextbookNotFoundError(
            "Reviewable textbook content version not found"
        ) from exc
    except Exception as exc:
        projection = await get_structure_generation_job_for_parent(
            parent_user_id=parent_user_id,
            generation_job_id=(
                str(queued["generation_job_id"]) if queued else ""
            ),
        )
        if projection and projection.get("status") in {"failed", "cancelled"}:
            return projection
        raise TextbookError("教材结构分析无法启动，请稍后重试。") from exc
    if queued is None:
        raise TextbookError("教材结构分析无法启动，请稍后重试。")
    return await get_structure_generation_job_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=str(queued["generation_job_id"]),
    ) or queued


async def get_structure_for_parent(
    *, parent_user_id: str, structure_id: str
) -> dict[str, Any]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can review textbook structures")
    structure = await get_textbook_structure_for_parent(
        parent_user_id=parent_user_id,
        structure_id=structure_id,
    )
    if not structure:
        raise TextbookNotFoundError("Textbook structure not found")
    return structure


async def get_latest_structure_for_parent(
    *, parent_user_id: str, content_version_id: str
) -> dict[str, Any] | None:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can review textbook structures")
    return await get_latest_textbook_structure_for_parent(
        parent_user_id=parent_user_id,
        content_version_id=content_version_id,
    )


async def get_knowledge_point_source_preview(
    *, parent_user_id: str, knowledge_point_id: str
) -> dict[str, Any]:
    """Return the authoritative reading slice for one knowledge point.

    The slice comes from the canonical book-to-skill line ranges persisted in
    ``education_textbook_scopes``. There is deliberately no fallback: a
    knowledge point whose unit has no verified scope reports an empty preview
    rather than a guessed range.
    """
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can review textbook sources")
    point = await get_knowledge_point_source_preview_for_parent(
        parent_user_id=parent_user_id,
        knowledge_point_id=knowledge_point_id,
    )
    if not point:
        raise TextbookNotFoundError("Knowledge point not found")
    scopes = await get_textbook_scopes_for_unit(
        parent_user_id=parent_user_id,
        unit_id=str(point["unit_id"]),
    )
    if not scopes:
        return {
            "knowledge_point_id": point["knowledge_point_id"],
            "knowledge_point_title": point["knowledge_point_title"],
            "unit_id": point["unit_id"],
            "unit_title": point["unit_title"],
            "snippets": [],
        }
    frozen_input = await get_teaching_input_for_parent(
        parent_user_id=parent_user_id,
        content_version_id=str(point["version_id"]),
    )
    if not frozen_input:
        raise TextbookNotFoundError("Textbook source input not found")
    sources = {
        str(source.get("source_id") or source.get("content_chapter_id") or ""): source
        for source in frozen_input.get("sources", [])
        if isinstance(source, Mapping)
    }
    snippets: list[dict[str, Any]] = []
    for scope in scopes:
        source_id = str(scope.get("source_id") or "")
        source = sources.get(source_id)
        markdown = str(source.get("markdown") or "") if source else ""
        char_start = int(scope["char_start"])
        char_end = int(scope["char_end"])
        if markdown:
            char_start = max(0, min(char_start, len(markdown)))
            char_end = max(char_start, min(char_end, len(markdown)))
        snippets.append(
            {
                "source_id": source_id or "unknown",
                "source_title": (
                    str(source.get("title") or source.get("filename") or "")
                    if source
                    else None
                )
                or None,
                "start": char_start,
                "end": char_end,
                "quote": None,
                "scope_slot": scope.get("slot"),
                "scope_title": scope.get("title"),
                "line_start": scope.get("line_start"),
                "line_end": scope.get("line_end"),
                "markdown": markdown[char_start:char_end],
                "truncated_before": False,
                "truncated_after": False,
            }
        )
    return {
        "knowledge_point_id": point["knowledge_point_id"],
        "knowledge_point_title": point["knowledge_point_title"],
        "unit_id": point["unit_id"],
        "unit_title": point["unit_title"],
        "snippets": snippets,
    }


async def resume_structure_generation_for_parent(
    *,
    parent_user_id: str,
    generation_job_id: str,
) -> dict[str, Any]:
    """Requeue and relaunch one failed structure job in place."""
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can resume textbook structures")
    job = await get_generation_job_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    if not job:
        raise TextbookNotFoundError("Textbook structure generation job not found")
    if job.get("scope") != "structure" or job.get("status") != "failed":
        raise TextbookTransitionError("Only a failed structure job can be resumed")
    if not await requeue_structure_generation(
        generation_job_id=generation_job_id
    ):
        raise TextbookTransitionError("Textbook structure job cannot be resumed")
    try:
        await launch_structure_generation(
            parent_user_id=parent_user_id,
            generation_job_id=generation_job_id,
        )
    except Exception as exc:
        projection = await get_structure_generation_job_for_parent(
            parent_user_id=parent_user_id,
            generation_job_id=generation_job_id,
        )
        if projection and projection.get("status") in {"failed", "cancelled"}:
            return projection
        raise TextbookError("教材结构分析无法继续，请稍后重试。") from exc
    return await get_structure_generation_job_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    ) or job


async def replace_structure_for_parent(
    *,
    parent_user_id: str,
    structure_id: str,
    units: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Replace a reviewable structure projection after full validation."""
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can edit textbook structures")
    structure = await get_textbook_structure_for_parent(
        parent_user_id=parent_user_id,
        structure_id=structure_id,
    )
    if not structure:
        raise TextbookNotFoundError("Textbook structure not found")
    if structure["status"] != "review":
        raise TextbookTransitionError(
            "Only a reviewable textbook structure can be edited"
        )
    frozen_input = await get_teaching_input_for_parent(
        parent_user_id=parent_user_id,
        content_version_id=str(structure["version_id"]),
    )
    if not frozen_input:
        raise TextbookNotFoundError("Textbook structure input not found")
    try:
        validated = validate_textbook_structure(
            {
                "format": "langalpha-managed-textbook-structure/v1",
                "units": list(units),
            },
            frozen_input,
        )
    except TextbookStructureValidationError as exc:
        raise TextbookTransitionError(str(exc)) from exc
    return await replace_structure_contents(
        structure_id=structure_id,
        units=validated["units"],
        warnings=list(validated.get("warnings", [])),
    )


async def accept_structure_for_parent(
    *, parent_user_id: str, structure_id: str
) -> dict[str, Any]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can accept textbook structures")
    structure = await get_textbook_structure_for_parent(
        parent_user_id=parent_user_id,
        structure_id=structure_id,
    )
    if not structure:
        raise TextbookNotFoundError("Textbook structure not found")
    if structure["status"] != "review":
        raise TextbookTransitionError(
            "Only a reviewable textbook structure can be accepted"
        )
    knowledge_point_count = sum(
        len(unit.get("knowledge_points", []))
        for unit in structure.get("units", [])
        if isinstance(unit, Mapping)
    )
    if knowledge_point_count == 0:
        raise TextbookTransitionError(
            "Textbook structure requires at least one knowledge point"
        )
    accepted = await accept_textbook_structure(
        parent_user_id=parent_user_id,
        structure_id=structure_id,
    )
    if not accepted:
        raise TextbookTransitionError("Textbook structure cannot be accepted")
    return accepted


async def get_structure_generation_job(
    *, parent_user_id: str, generation_job_id: str
) -> dict[str, Any]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can read structure jobs")
    job = await get_generation_job_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    if not job:
        raise TextbookNotFoundError("Textbook structure generation job not found")
    return {
        **job,
        "prompt": str(job.get("processing_brief") or ""),
    }
