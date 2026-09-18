"""Student learning asset service contracts."""

from unittest.mock import AsyncMock

import pytest

from src.server.services import education_learning_assets


STRUCTURE = {
    "units": [
        {
            "unit_id": "unit-1",
            "title": "Unit 1",
            "knowledge_points": [
                {
                    "knowledge_point_id": "kp-1",
                    "title": "世界运动",
                }
            ],
        }
    ]
}


@pytest.mark.asyncio
async def test_add_learning_item_requires_published_target(monkeypatch):
    monkeypatch.setattr(
        education_learning_assets,
        "get_student_structure",
        AsyncMock(return_value=STRUCTURE),
    )
    create = AsyncMock(
        return_value={
            "item_id": "item-1",
            "kind": "highlight",
            "content": "重点",
        }
    )
    monkeypatch.setattr(
        education_learning_assets,
        "create_learning_item",
        create,
    )

    item = await education_learning_assets.add_learning_item(
        student_user_id="student-1",
        assignment_id="assignment-1",
        unit_id="unit-1",
        knowledge_point_id="kp-1",
        kind="highlight",
        content="  重点  ",
        source_anchor={"start": 1, "end": 3},
    )

    assert item["item_id"] == "item-1"
    assert create.await_args.kwargs["content"] == "重点"


@pytest.mark.asyncio
async def test_generate_summary_uses_only_own_items(monkeypatch):
    monkeypatch.setattr(
        education_learning_assets,
        "get_student_structure",
        AsyncMock(return_value=STRUCTURE),
    )
    monkeypatch.setattr(
        education_learning_assets,
        "list_learning_items",
        AsyncMock(
            return_value=[
                {
                    "kind": "note",
                    "knowledge_point_id": "kp-1",
                    "content": "记住 simple 是核心",
                },
                {
                    "kind": "highlight",
                    "knowledge_point_id": "kp-1",
                    "content": "It's a simple game.",
                },
            ]
        ),
    )
    create = AsyncMock(
        return_value={
            "item_id": "summary-1",
            "kind": "summary",
            "content": "# Unit 1",
        }
    )
    monkeypatch.setattr(
        education_learning_assets,
        "create_learning_item",
        create,
    )

    summary = await education_learning_assets.generate_unit_summary(
        student_user_id="student-1",
        assignment_id="assignment-1",
        unit_id="unit-1",
    )

    assert summary["kind"] == "summary"
    content = create.await_args.kwargs["content"]
    assert "## 世界运动" in content
    assert "记住 simple 是核心" in content
    assert "It's a simple game." in content
