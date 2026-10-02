"""Server-owned semantic stages for managed textbook work."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any


_STAGE_MESSAGES_BY_ITEM_KIND: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {
        "structure": MappingProxyType(
            {
                "structure_reading": "正在阅读教材结构线索",
                "structure_organizing": "正在整理章节层级",
                "structure_splitting": "正在切分知识点",
                "structure_validating": "正在校验教材结构",
            }
        ),
        "material": MappingProxyType(
            {
                "material_reading": "正在阅读知识点原文",
                "material_organizing": "正在组织讲义内容",
                "material_writing": "正在撰写讲义",
                "material_validating": "正在校验讲义产物",
            }
        ),
        "supplementary": MappingProxyType(
            {
                "supplementary_reading": "正在汇总全书讲义",
                "supplementary_organizing": "正在整理全书附加材料",
                "supplementary_validating": "正在校验附加材料",
            }
        ),
    }
)


def progress_contract(item: Mapping[str, Any]) -> dict[str, Any]:
    """Return a fresh model-facing contract for one managed item."""
    item_kind = str(item.get("kind") or "")
    stages = _STAGE_MESSAGES_BY_ITEM_KIND.get(item_kind)
    if stages is None:
        raise ValueError("Unsupported textbook item kind for progress")
    return {
        "tool": "report_progress",
        "allowed_stages": list(stages),
    }


def progress_message(stage: str, *, item_kind: str) -> str | None:
    """Map an allowed item-scoped stage to its server-owned public message."""
    messages = _STAGE_MESSAGES_BY_ITEM_KIND.get(item_kind)
    if messages is None:
        return None
    return messages.get(stage)
