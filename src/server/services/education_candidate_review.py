"""Parent-reviewed transitions for generated knowledge-point candidates."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.server.database.education_textbooks import (
    KnowledgePointCandidateNotFoundError,
    KnowledgePointCandidateTransitionError,
    TextbookQueueValidationError,
    accept_knowledge_point_candidates_for_parent as db_accept_candidates,
    list_knowledge_point_candidates_for_parent as db_list_candidates,
    merge_knowledge_point_candidates_for_parent as db_merge_candidates,
    reject_knowledge_point_candidates_for_parent as db_reject_candidates,
    split_knowledge_point_candidate_for_parent as db_split_candidate,
    update_knowledge_point_candidate_for_parent as db_update_candidate,
)
from src.server.services.education_textbooks import (
    TextbookNotFoundError,
    TextbookPermissionError,
    TextbookTransitionError,
    get_household_context_for_parent,
)


async def _require_parent(parent_user_id: str, message: str) -> None:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError(message)


async def list_knowledge_point_candidates_for_parent(
    *,
    parent_user_id: str,
    structure_id: str,
) -> dict[str, Any]:
    await _require_parent(
        parent_user_id, "Only a parent can review knowledge-point candidates"
    )
    result = await db_list_candidates(
        parent_user_id=parent_user_id,
        structure_id=structure_id,
    )
    if result is None:
        raise TextbookNotFoundError("Textbook structure not found")
    return result


async def update_knowledge_point_candidate_for_parent(
    *,
    parent_user_id: str,
    candidate_id: str,
    title: str | None,
    summary: str | None,
    point_type: str | None,
) -> dict[str, Any]:
    await _require_parent(
        parent_user_id, "Only a parent can edit knowledge-point candidates"
    )
    try:
        result = await db_update_candidate(
            parent_user_id=parent_user_id,
            candidate_id=candidate_id,
            title=title,
            summary=summary,
            point_type=point_type,
        )
    except TextbookQueueValidationError as exc:
        raise TextbookTransitionError(str(exc)) from exc
    if result is None:
        raise TextbookNotFoundError("Generated knowledge-point candidate not found")
    return result


async def _transition_candidates(
    *,
    parent_user_id: str,
    candidate_ids: list[str],
    transition: Any,
    permission_message: str,
) -> list[dict[str, Any]]:
    await _require_parent(parent_user_id, permission_message)
    try:
        return await transition(
            parent_user_id=parent_user_id,
            candidate_ids=candidate_ids,
        )
    except KnowledgePointCandidateNotFoundError as exc:
        raise TextbookNotFoundError(str(exc)) from exc
    except KnowledgePointCandidateTransitionError as exc:
        raise TextbookTransitionError(str(exc)) from exc


async def accept_knowledge_point_candidates_for_parent(
    *,
    parent_user_id: str,
    candidate_ids: list[str],
) -> list[dict[str, Any]]:
    return await _transition_candidates(
        parent_user_id=parent_user_id,
        candidate_ids=candidate_ids,
        transition=db_accept_candidates,
        permission_message="Only a parent can accept knowledge-point candidates",
    )


async def reject_knowledge_point_candidates_for_parent(
    *,
    parent_user_id: str,
    candidate_ids: list[str],
) -> list[dict[str, Any]]:
    return await _transition_candidates(
        parent_user_id=parent_user_id,
        candidate_ids=candidate_ids,
        transition=db_reject_candidates,
        permission_message="Only a parent can reject knowledge-point candidates",
    )


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
    await _require_parent(
        parent_user_id, "Only a parent can merge knowledge-point candidates"
    )
    if target_id is None and (title is None or point_type is None):
        raise TextbookTransitionError(
            "A new merged candidate requires a title and point type"
        )
    if target_id is None and accept:
        raise TextbookTransitionError("A new merged candidate must remain pending")
    try:
        return await db_merge_candidates(
            parent_user_id=parent_user_id,
            source_ids=source_ids,
            target_id=target_id,
            title=title,
            summary=summary,
            point_type=point_type,
            accept=accept,
        )
    except KnowledgePointCandidateNotFoundError as exc:
        raise TextbookNotFoundError(str(exc)) from exc
    except KnowledgePointCandidateTransitionError as exc:
        raise TextbookTransitionError(str(exc)) from exc


async def split_knowledge_point_candidate_for_parent(
    *,
    parent_user_id: str,
    candidate_id: str,
    items: list[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    await _require_parent(
        parent_user_id, "Only a parent can split knowledge-point candidates"
    )
    try:
        return await db_split_candidate(
            parent_user_id=parent_user_id,
            candidate_id=candidate_id,
            items=[dict(item) for item in items],
        )
    except KnowledgePointCandidateNotFoundError as exc:
        raise TextbookNotFoundError(str(exc)) from exc
    except KnowledgePointCandidateTransitionError as exc:
        raise TextbookTransitionError(str(exc)) from exc
