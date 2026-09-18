"""Parent-only creation, editing, and acceptance of textbook structures."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.server.database.education_textbooks import (
    accept_textbook_structure,
    get_generation_job_for_parent,
    get_teaching_input_for_parent,
    get_textbook_structure_for_parent,
    replace_structure_contents,
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
    *, parent_user_id: str, content_version_id: str
) -> dict[str, Any]:
    """Queue and immediately launch one structure generation job."""
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can create textbook structures")
    queued: dict[str, Any] | None = None
    try:
        queued = await queue_structure_generation_for_parent(
            parent_user_id=parent_user_id,
            content_version_id=content_version_id,
        )
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
    return job
