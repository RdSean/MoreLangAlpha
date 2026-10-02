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


_MATERIAL_ACTIONS = MappingProxyType(
    {
        "reading_context": (
            ("material_reading",),
            "正在补充前后文背景",
            "当前确需参考相邻原文、目录或已有材料；只报告实际读取的内容。",
        ),
        "examining_visuals": (
            ("material_reading",),
            "正在解读原文图表",
            "原文确有相关图表且当前实际读取和解读；不为上报新增图片。",
        ),
        "clarifying_concepts": (
            ("material_organizing", "material_writing"),
            "正在澄清概念与术语",
            "正在梳理定义、概念关系或术语含义；适用于各学科，不要求新增词表。",
        ),
        "organizing_explanation": (
            ("material_organizing",),
            "正在安排讲解顺序",
            "正在安排本份讲义的讲述次序；不表示学生状态分析或课程规划。",
        ),
        "explaining_source_examples": (
            ("material_writing",),
            "正在整理原文示例",
            "原文确有相关例题、案例、代码或例句，且当前正在讲解它们。",
        ),
        "creating_examples": (
            ("material_writing",),
            "正在编写辅助示例",
            "原有任务或材料深度确需辅助示例且用户未禁止；上报本身不授权新增内容。",
        ),
        "explaining_exercises": (
            ("material_writing",),
            "正在组织练习解析",
            "任务范围内确有练习且当前实际处理；不要求非练习材料新增练习。",
        ),
        "checking_sources": (
            ("material_validating",),
            "正在核对来源与引用",
            "正在实际核对来源、引用和锚点；报告不证明校验已经通过。",
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
        "allowed_actions": {
            action: {"stages": list(stages), "message": message, "when": when}
            for action, (stages, message, when) in _MATERIAL_ACTIONS.items()
        }
        if item_kind == "material"
        else {},
    }


def progress_message(
    stage: str, *, item_kind: str, action: str | None = None
) -> str | None:
    """Map an allowed item-scoped stage to its server-owned public message."""
    messages = _STAGE_MESSAGES_BY_ITEM_KIND.get(item_kind)
    if messages is None or stage not in messages:
        return None
    if action is not None:
        specification = (
            _MATERIAL_ACTIONS.get(action) if item_kind == "material" else None
        )
        if specification is None or stage not in specification[0]:
            return None
        return specification[1]
    return messages.get(stage)
