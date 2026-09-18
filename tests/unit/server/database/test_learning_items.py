"""Persistence contracts for student-owned learning assets."""

from contextlib import asynccontextmanager

import pytest

from src.server.database import education_textbooks


@pytest.mark.asyncio
async def test_upsert_kp_progress_is_assignment_scoped(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = {
        "assignment_id": "assignment-1",
        "knowledge_point_id": "kp-1",
        "status": "learning",
    }

    result = await education_textbooks.upsert_kp_progress(
        student_user_id="student-1",
        assignment_id="assignment-1",
        knowledge_point_id="kp-1",
        status="learning",
    )

    assert result["status"] == "learning"
    sql = mock_cursor.execute.call_args.args[0]
    assert "assignments.student_user_id = %s" in sql
    assert "education_publication_kp_lessons" in sql


@pytest.mark.asyncio
async def test_create_learning_item_rejects_foreign_assignment(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = None

    result = await education_textbooks.create_learning_item(
        student_user_id="student-1",
        assignment_id="assignment-1",
        unit_id=None,
        knowledge_point_id="kp-1",
        kind="note",
        content="重点",
        source_anchor=None,
    )

    assert result is None


@pytest.mark.asyncio
async def test_update_and_delete_learning_item_require_student_owner(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"item_id": "item-1", "content": "更新"},
        {"item_id": "item-1"},
    ]

    updated = await education_textbooks.update_learning_item(
        student_user_id="student-1",
        item_id="item-1",
        content="更新",
        source_anchor=None,
    )
    deleted = await education_textbooks.delete_learning_item(
        student_user_id="student-1",
        item_id="item-1",
    )

    assert updated["content"] == "更新"
    assert deleted["item_id"] == "item-1"
