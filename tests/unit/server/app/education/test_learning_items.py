"""HTTP contracts for student learning assets."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.server.app.education.textbooks import router
from src.server.utils.api import get_current_user_id


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as session:
        yield session


@pytest.mark.asyncio
async def test_student_creates_learning_item_and_generates_summary(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"
    assignment_id = uuid4()
    skill_node_id = "unit-1"
    knowledge_point_id = uuid4()
    item = {
        "item_id": uuid4(),
        "assignment_id": assignment_id,
        "skill_node_id": skill_node_id,
        "knowledge_point_id": knowledge_point_id,
        "kind": "note",
        "content": "重点",
        "source_anchor": {"start": 1, "end": 3},
        "created_at": None,
        "updated_at": None,
    }
    summary = {
        **item,
        "item_id": uuid4(),
        "kind": "summary",
        "knowledge_point_id": None,
    }
    with (
        patch(
            "src.server.app.education.textbooks.add_learning_item",
            new=AsyncMock(return_value=item),
        ) as add,
        patch(
            "src.server.app.education.textbooks.generate_node_summary",
            new=AsyncMock(return_value=summary),
        ) as generate,
    ):
        created = await client.post(
            f"/api/v1/education/learning/{assignment_id}/knowledge-points/{knowledge_point_id}/items",
            json={
                "skill_node_id": skill_node_id,
                "kind": "note",
                "content": "重点",
                "source_anchor": {"start": 1, "end": 3},
            },
        )
        summarized = await client.post(
            f"/api/v1/education/learning/{assignment_id}/nodes/{skill_node_id}/summaries"
        )

    assert created.status_code == 201
    assert summarized.status_code == 201
    assert add.await_args.kwargs["knowledge_point_id"] == str(knowledge_point_id)
    assert add.await_args.kwargs["skill_node_id"] == skill_node_id
    assert generate.await_args.kwargs["skill_node_id"] == skill_node_id


@pytest.mark.asyncio
async def test_student_item_mutations_remain_bound_to_assignment_url(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"
    assignment_id = uuid4()
    item_id = uuid4()
    item = {
        "item_id": item_id,
        "assignment_id": assignment_id,
        "skill_node_id": "unit-1",
        "knowledge_point_id": uuid4(),
        "kind": "note",
        "content": "更新后的重点",
        "source_anchor": None,
        "created_at": None,
        "updated_at": None,
    }
    with (
        patch(
            "src.server.app.education.textbooks.edit_learning_item",
            new=AsyncMock(return_value=item),
        ) as edit,
        patch(
            "src.server.app.education.textbooks.remove_learning_item",
            new=AsyncMock(return_value=None),
        ) as remove,
    ):
        updated = await client.patch(
            f"/api/v1/education/learning/{assignment_id}/items/{item_id}",
            json={"content": "更新后的重点"},
        )
        deleted = await client.delete(
            f"/api/v1/education/learning/{assignment_id}/items/{item_id}"
        )

    assert updated.status_code == 200
    assert deleted.status_code == 200
    assert edit.await_args.kwargs["assignment_id"] == str(assignment_id)
    assert remove.await_args.kwargs["assignment_id"] == str(assignment_id)
