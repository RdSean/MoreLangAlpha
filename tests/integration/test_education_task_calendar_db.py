"""Real PostgreSQL contracts for the household homework calendar read model."""

from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.server.database import education_tasks
from src.server.services import education_tasks as education_task_service


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_calendar_uses_subject_colours_and_stable_due_time_order(db_conn, monkeypatch):
    household_id = uuid4()
    parent_id = f"calendar-parent-{uuid4()}"
    student_id = f"calendar-student-{uuid4()}"
    later_rule_id = uuid4()
    earlier_rule_id = uuid4()
    later_task_id = uuid4()
    earlier_task_id = uuid4()
    occurrence = date(2026, 8, 1)

    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.executemany(
                "INSERT INTO users (user_id, name) VALUES (%s, %s)",
                [(parent_id, "Calendar parent"), (student_id, "Calendar student")],
            )
            await cur.execute(
                """
                INSERT INTO education_households (household_id, name, timezone, model_owner_user_id)
                VALUES (%s, 'Calendar household', 'America/Los_Angeles', %s)
                """,
                (household_id, parent_id),
            )
            await cur.executemany(
                """
                INSERT INTO education_memberships
                    (household_id, user_id, role, display_name)
                VALUES (%s, %s, %s, %s)
                """,
                [
                    (household_id, parent_id, "parent", "Calendar parent"),
                    (household_id, student_id, "student", "Calendar student"),
                ],
            )
            await cur.executemany(
                """
                INSERT INTO education_task_rules (
                    task_rule_id, household_id, created_by_user_id, assigned_student_id,
                    title, recurrence, timezone, subject_code, type_code, grade_code
                ) VALUES (
                    %s, %s, %s, %s, 'Read',
                    '{"frequency":"once","start_date":"2026-08-01","due_time":"09:00"}'::jsonb,
                    'America/Los_Angeles', 'chinese', 'read', 'g5'
                )
                """,
                [
                    (later_rule_id, household_id, parent_id, student_id),
                    (earlier_rule_id, household_id, parent_id, student_id),
                ],
            )
            await cur.executemany(
                """
                INSERT INTO education_tasks (
                    task_id, task_rule_id, household_id, assigned_student_id,
                    occurrence_date, due_at, title, subject_code, type_code, grade_code,
                    status, completed_at, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'chinese', 'read', 'g5', %s, %s, %s)
                """,
                [
                    (
                        later_task_id, later_rule_id, household_id, student_id, occurrence,
                        datetime(2026, 8, 1, 17, tzinfo=timezone.utc), "Later", "open", None,
                        datetime(2026, 7, 31, tzinfo=timezone.utc),
                    ),
                    (
                        earlier_task_id, earlier_rule_id, household_id, student_id, occurrence,
                        datetime(2026, 8, 1, 16, tzinfo=timezone.utc), "Earlier", "completed",
                        datetime(2026, 8, 1, 16, 30, tzinfo=timezone.utc),
                        datetime(2026, 7, 30, tzinfo=timezone.utc),
                    ),
                ],
            )

    @asynccontextmanager
    async def use_test_connection():
        yield db_conn

    monkeypatch.setattr(education_tasks, "get_db_connection", use_test_connection)
    monkeypatch.setattr(
        education_task_service,
        "list_active_rule_timezones_for_user",
        AsyncMock(return_value=[]),
    )

    calendar = await education_task_service.get_task_calendar(
        user_id=parent_id,
        student_id=student_id,
        start_date=occurrence,
        end_date=occurrence,
        now=datetime(2026, 8, 2, 1, tzinfo=timezone.utc),
    )

    day = calendar["days"][0]
    assert [task["title"] for task in day["tasks"]] == ["Earlier", "Later"]
    assert [task["subject_color"] for task in day["tasks"]] == ["#D95D39", "#D95D39"]
    assert day["completed_count"] == 1
    assert day["overdue_count"] == 1
    assert calendar["stats"] == {
        "today_count": 2,
        "week_count": 2,
        "overdue_count": 1,
        "completed_count": 1,
    }
