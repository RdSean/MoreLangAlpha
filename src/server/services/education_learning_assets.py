"""Student-owned progress, notebook items, and deterministic unit summaries."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from src.server.database.education_textbooks import (
    create_learning_item,
    delete_learning_item,
    list_learning_items,
    update_learning_item,
    upsert_kp_progress,
)
from src.server.services.education_textbooks import (
    TextbookNotFoundError,
    TextbookTransitionError,
    get_student_structure,
)


_ITEM_KINDS = frozenset({"question", "highlight", "note", "summary"})
_PROGRESS_STATUSES = frozenset(
    {"not_started", "learning", "read", "review_recommended"}
)


async def _published_structure(
    *, student_user_id: str, assignment_id: str
) -> dict[str, Any]:
    return await get_student_structure(
        student_user_id=student_user_id,
        assignment_id=assignment_id,
    )


def _find_unit(structure: Mapping[str, Any], unit_id: str) -> Mapping[str, Any]:
    for unit in structure.get("units", []):
        if isinstance(unit, Mapping) and str(unit.get("unit_id")) == unit_id:
            return unit
    raise TextbookNotFoundError("Published Unit not found")


def _find_knowledge_point(
    structure: Mapping[str, Any], knowledge_point_id: str
) -> Mapping[str, Any]:
    for unit in structure.get("units", []):
        if not isinstance(unit, Mapping):
            continue
        for point in unit.get("knowledge_points", []):
            if (
                isinstance(point, Mapping)
                and str(point.get("knowledge_point_id"))
                == knowledge_point_id
            ):
                return point
    raise TextbookNotFoundError("Published knowledge point not found")


async def update_learning_progress(
    *,
    student_user_id: str,
    assignment_id: str,
    knowledge_point_id: str,
    status: str,
) -> dict[str, Any]:
    if status not in _PROGRESS_STATUSES:
        raise TextbookTransitionError("Learning progress status is invalid")
    structure = await _published_structure(
        student_user_id=student_user_id,
        assignment_id=assignment_id,
    )
    _find_knowledge_point(structure, knowledge_point_id)
    progress = await upsert_kp_progress(
        student_user_id=student_user_id,
        assignment_id=assignment_id,
        knowledge_point_id=knowledge_point_id,
        status=status,
    )
    if not progress:
        raise TextbookNotFoundError("Learning progress target not found")
    return progress


async def get_learning_items(
    *,
    student_user_id: str,
    assignment_id: str,
    unit_id: str | None = None,
    knowledge_point_id: str | None = None,
) -> list[dict[str, Any]]:
    await _published_structure(
        student_user_id=student_user_id,
        assignment_id=assignment_id,
    )
    return await list_learning_items(
        student_user_id=student_user_id,
        assignment_id=assignment_id,
        unit_id=unit_id,
        knowledge_point_id=knowledge_point_id,
    )


async def add_learning_item(
    *,
    student_user_id: str,
    assignment_id: str,
    unit_id: str | None,
    knowledge_point_id: str | None,
    kind: str,
    content: str,
    source_anchor: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if kind not in _ITEM_KINDS:
        raise TextbookTransitionError("Learning item kind is invalid")
    normalized = content.strip()
    if not normalized:
        raise TextbookTransitionError("Learning item content is required")
    structure = await _published_structure(
        student_user_id=student_user_id,
        assignment_id=assignment_id,
    )
    if unit_id is not None:
        _find_unit(structure, unit_id)
    if knowledge_point_id is not None:
        _find_knowledge_point(structure, knowledge_point_id)
    item = await create_learning_item(
        student_user_id=student_user_id,
        assignment_id=assignment_id,
        unit_id=unit_id,
        knowledge_point_id=knowledge_point_id,
        kind=kind,
        content=normalized,
        source_anchor=source_anchor,
    )
    if not item:
        raise TextbookNotFoundError("Learning item target not found")
    return item


async def edit_learning_item(
    *,
    student_user_id: str,
    item_id: str,
    content: str,
    source_anchor: Mapping[str, Any] | None,
) -> dict[str, Any]:
    normalized = content.strip()
    if not normalized:
        raise TextbookTransitionError("Learning item content is required")
    item = await update_learning_item(
        student_user_id=student_user_id,
        item_id=item_id,
        content=normalized,
        source_anchor=source_anchor,
    )
    if not item:
        raise TextbookNotFoundError("Learning item not found")
    return item


async def remove_learning_item(
    *, student_user_id: str, item_id: str
) -> None:
    if not await delete_learning_item(
        student_user_id=student_user_id,
        item_id=item_id,
    ):
        raise TextbookNotFoundError("Learning item not found")


async def generate_unit_summary(
    *,
    student_user_id: str,
    assignment_id: str,
    unit_id: str,
) -> dict[str, Any]:
    structure = await _published_structure(
        student_user_id=student_user_id,
        assignment_id=assignment_id,
    )
    unit = _find_unit(structure, unit_id)
    items = await list_learning_items(
        student_user_id=student_user_id,
        assignment_id=assignment_id,
        unit_id=unit_id,
    )
    point_titles = {
        str(point["knowledge_point_id"]): str(point["title"])
        for point in unit.get("knowledge_points", [])
    }
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for item in items:
        if item["kind"] == "summary":
            continue
        grouped[str(item.get("knowledge_point_id") or "")].append(item)

    lines = [f"# {unit['title']} · 个性化总结", ""]
    if not items:
        lines.extend(["这个 Unit 还没有追问、划重点或批注。", ""])
    for knowledge_point_id, entries in grouped.items():
        title = point_titles.get(knowledge_point_id, "单元补充")
        lines.extend([f"## {title}", ""])
        for kind, label in (
            ("question", "追问"),
            ("highlight", "划重点"),
            ("note", "批注"),
        ):
            values = [
                str(item["content"]).strip()
                for item in entries
                if item["kind"] == kind and str(item["content"]).strip()
            ]
            if not values:
                continue
            lines.extend([f"### {label}", ""])
            lines.extend(f"- {value}" for value in values)
            lines.append("")
    content = "\n".join(lines).strip()
    summary = await create_learning_item(
        student_user_id=student_user_id,
        assignment_id=assignment_id,
        unit_id=unit_id,
        knowledge_point_id=None,
        kind="summary",
        content=content,
        source_anchor=None,
    )
    if not summary:
        raise TextbookNotFoundError("Unit summary target not found")
    return summary
