"""Contracts for the text-only household homework tool."""

from contextlib import asynccontextmanager
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _fake_db(*, rows=()):
    cursor = AsyncMock()
    cursor.fetchall = AsyncMock(return_value=list(rows))
    connection = MagicMock()

    @asynccontextmanager
    async def cursor_context(**kwargs):
        yield cursor

    connection.cursor = cursor_context

    @asynccontextmanager
    async def db_context():
        yield connection

    return cursor, db_context


@pytest.mark.asyncio
async def test_list_student_membership_context_returns_students_with_optional_grade():
    rows = [
        {"user_id": "student-1", "display_name": "Henry", "grade_code": "g6"},
        {"user_id": "student-2", "display_name": "Mia", "grade_code": None},
    ]
    cursor, fake_db = _fake_db(rows=rows)

    with patch("src.server.database.education_members.get_db_connection", fake_db):
        from src.server.database.education_members import list_student_membership_context

        result = await list_student_membership_context("household-1")

    assert result == rows
    query, params = cursor.execute.await_args.args
    assert "education_student_profiles" in query
    assert "memberships.role = 'student'" in query
    assert "ORDER BY memberships.created_at ASC" in query
    assert params == ("household-1",)
    cursor.fetchall.assert_awaited_once()


def _homework_tool():
    """Load the Task 2 tool while allowing this boundary commit to land first."""
    try:
        from src.tools.education.homework import education_create_homework
    except ModuleNotFoundError as exc:  # pragma: no cover - removed by Task 2
        pytest.xfail(f"native homework tool is implemented in Task 2: {exc}")
    return education_create_homework


_ARGS = {
    "student_name": "Henry",
    "title": "Read",
    "description": "Read the assigned chapter",
    "due_at": "2026-08-28T20:00:00+08:00",
    "subject_code": "chinese",
    "type_code": "read",
}


def _parent_membership():
    return {
        "household_id": "household-1",
        "user_id": "parent-1",
        "role": "parent",
        "timezone": "Asia/Shanghai",
    }


@pytest.mark.asyncio
async def test_homework_tool_requires_configurable_user_id():
    tool = _homework_tool()
    result = await tool.ainvoke(_ARGS, config={"configurable": {}})
    assert "user_id" in json.loads(result)["error"]


@pytest.mark.asyncio
async def test_homework_tool_rejects_non_parent():
    tool = _homework_tool()
    with patch(
        "src.tools.education.homework.get_membership_for_user",
        AsyncMock(return_value={"user_id": "student-1", "role": "student"}),
    ):
        result = await tool.ainvoke(_ARGS, config={"configurable": {"user_id": "student-1"}})
    assert "parent" in json.loads(result)["error"]


@pytest.mark.asyncio
async def test_homework_tool_resolves_unique_student_name(monkeypatch):
    tool = _homework_tool()
    monkeypatch.setattr(
        "src.tools.education.homework.create_task",
        AsyncMock(return_value={"task_id": "task-1"}),
    )
    monkeypatch.setattr(
        "src.tools.education.homework.get_membership_for_user",
        AsyncMock(return_value=_parent_membership()),
    )
    monkeypatch.setattr(
        "src.tools.education.homework.list_student_membership_context",
        AsyncMock(return_value=[{"user_id": "student-1", "display_name": "Henry", "grade_code": "g6"}]),
    )
    result = await tool.ainvoke(
        _ARGS,
        config={"configurable": {"user_id": "parent-1", "run_id": "run-1"}},
    )
    assert json.loads(result)["task_id"] == "task-1"


@pytest.mark.asyncio
async def test_homework_tool_passes_text_only_task_and_stable_idempotency_key(monkeypatch):
    tool = _homework_tool()
    create = AsyncMock(return_value={"task_id": "task-1", "due_at": "2026-08-28T12:00:00+00:00"})
    monkeypatch.setattr("src.tools.education.homework.create_task", create)
    monkeypatch.setattr(
        "src.tools.education.homework.get_membership_for_user",
        AsyncMock(return_value=_parent_membership()),
    )
    monkeypatch.setattr(
        "src.tools.education.homework.list_student_membership_context",
        AsyncMock(return_value=[{"user_id": "student-1", "display_name": "Henry", "grade_code": "g6"}]),
    )
    config = {"configurable": {"user_id": "parent-1", "request_id": "request-1"}}
    await tool.ainvoke(_ARGS, config=config)
    await tool.ainvoke(_ARGS, config=config)
    first = create.await_args_list[0].kwargs
    second = create.await_args_list[1].kwargs
    assert first["assigned_student_id"] == "student-1"
    assert first["material_asset_ids"] == []
    assert first["idempotency_key"] == second["idempotency_key"]
    assert len(first["idempotency_key"]) == 36
    await tool.ainvoke({**_ARGS, "title": "Different"}, config=config)
    assert create.await_args_list[2].kwargs["idempotency_key"] != first["idempotency_key"]


@pytest.mark.asyncio
@pytest.mark.parametrize("student_name", ["Unknown", "Alex"])
async def test_homework_tool_rejects_unknown_or_ambiguous_student(student_name):
    tool = _homework_tool()
    with patch(
        "src.tools.education.homework.get_membership_for_user",
        AsyncMock(return_value=_parent_membership()),
    ), patch(
        "src.tools.education.homework.list_student_membership_context",
        AsyncMock(return_value=[
            {"user_id": "student-1", "display_name": "Alex", "grade_code": "g6"},
            {"user_id": "student-2", "display_name": "Alex", "grade_code": "g6"},
        ]),
    ):
        result = await tool.ainvoke(
            {**_ARGS, "student_name": student_name},
            config={"configurable": {"user_id": "parent-1"}},
        )
    assert "student" in json.loads(result)["error"]


@pytest.mark.asyncio
async def test_homework_tool_rejects_student_outside_parent_household():
    tool = _homework_tool()
    with patch(
        "src.tools.education.homework.get_membership_for_user",
        AsyncMock(return_value=_parent_membership()),
    ), patch(
        "src.tools.education.homework.list_student_membership_context",
        AsyncMock(return_value=[]),
    ):
        result = await tool.ainvoke(
            {**_ARGS, "student_name": "Other Student"},
            config={"configurable": {"user_id": "parent-1"}},
        )
    assert "household" in json.loads(result)["error"]
