"""Contracts for the text-only household homework tool."""

from contextlib import asynccontextmanager
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


@pytest.mark.asyncio
async def test_homework_tool_requires_configurable_user_id():
    tool = _homework_tool()
    with pytest.raises(Exception, match="user_id"):
        await tool.ainvoke(
            {"student_name": "Henry", "title": "Read", "description": "Read"},
            config={"configurable": {}},
        )


@pytest.mark.asyncio
async def test_homework_tool_rejects_non_parent():
    tool = _homework_tool()
    with pytest.raises(Exception, match="parent"):
        await tool.ainvoke(
            {"student_name": "Henry", "title": "Read", "description": "Read"},
            config={"configurable": {"user_id": "student-1"}},
        )


@pytest.mark.asyncio
async def test_homework_tool_resolves_unique_student_name(monkeypatch):
    tool = _homework_tool()
    monkeypatch.setattr(
        "src.tools.education.homework.create_task",
        AsyncMock(return_value={"task_id": "task-1"}),
    )
    result = await tool.ainvoke(
        {"student_name": "Henry", "title": "Read", "description": "Read"},
        config={"configurable": {"user_id": "parent-1"}},
    )
    assert result["task_id"] == "task-1"


@pytest.mark.asyncio
@pytest.mark.parametrize("student_name", ["Unknown", "Alex"])
async def test_homework_tool_rejects_unknown_or_ambiguous_student(student_name):
    tool = _homework_tool()
    with pytest.raises(Exception, match="student"):
        await tool.ainvoke(
            {"student_name": student_name, "title": "Read", "description": "Read"},
            config={"configurable": {"user_id": "parent-1"}},
        )


@pytest.mark.asyncio
async def test_homework_tool_rejects_student_outside_parent_household():
    tool = _homework_tool()
    with pytest.raises(Exception, match="household"):
        await tool.ainvoke(
            {"student_name": "Other Student", "title": "Read", "description": "Read"},
            config={"configurable": {"user_id": "parent-1"}},
        )
