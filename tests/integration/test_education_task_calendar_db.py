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
        "today_count": 1,
        "week_count": 1,
        "overdue_count": 1,
        "completed_count": 1,
        "total_points": 1,
    }

    sibling_id = f"calendar-sibling-{uuid4()}"
    foreign_parent_id = f"calendar-foreign-parent-{uuid4()}"
    foreign_household_id = uuid4()
    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.executemany(
                "INSERT INTO users (user_id, name) VALUES (%s, %s)",
                [(sibling_id, "Sibling"), (foreign_parent_id, "Foreign parent")],
            )
            await cur.execute(
                "INSERT INTO education_households (household_id, name, model_owner_user_id) VALUES (%s, 'Other', %s)",
                (foreign_household_id, foreign_parent_id),
            )
            await cur.executemany(
                "INSERT INTO education_memberships (household_id, user_id, role, display_name) VALUES (%s, %s, %s, %s)",
                [(household_id, sibling_id, "student", "Sibling"), (foreign_household_id, foreign_parent_id, "parent", "Other")],
            )
    for unauthorized_actor in (sibling_id, foreign_parent_id):
        assert await education_tasks.check_in_task(
            task_id=str(later_task_id), student_user_id=unauthorized_actor,
            submission_text="", idempotency_key=None, asset_ids=[],
        ) is None

    # A household parent checks in on behalf of the student, preserving actor.
    submission = await education_tasks.check_in_task(
        task_id=str(later_task_id), student_user_id=parent_id,
        submission_text="Parent checked", idempotency_key=str(later_task_id), asset_ids=[],
    )
    assert submission["submitted_by_user_id"] == parent_id
    again = await education_tasks.check_in_task(
        task_id=str(later_task_id), student_user_id=parent_id,
        submission_text="Retry", idempotency_key=str(later_task_id), asset_ids=[],
    )
    assert again["submission_id"] == submission["submission_id"]
    # Even a completed task outside the selected month contributes exactly once.
    counts = await education_tasks.get_calendar_progress_counts(
        household_id=str(household_id), assigned_student_id=student_id,
        today=date(2026, 9, 1), week_start=date(2026, 8, 31), week_end=date(2026, 9, 6),
        start_date=date(2026, 9, 1), end_date=date(2026, 9, 30),
        now=datetime(2026, 9, 1, tzinfo=timezone.utc),
    )
    assert counts["completed_count"] == 0
    assert counts["total_points"] == 2
    assert await education_tasks.check_in_task(
        task_id=str(later_task_id), student_user_id=foreign_parent_id,
        submission_text="", idempotency_key=None, asset_ids=[],
    ) is None

    # Inclusive rule deadline also bounds real database materialization.
    async with db_conn.cursor() as cur:
        await cur.execute(
            "UPDATE education_task_rules SET recurrence = %s::jsonb WHERE task_rule_id = %s",
            ('{"frequency":"daily","start_date":"2026-08-01","end_date":"2026-08-03","due_time":"09:00"}', later_rule_id),
        )
    assert await education_tasks.materialize_task_rule_through(
        task_rule_id=str(later_rule_id), from_date=date(2026, 8, 1), through_date=date(2026, 8, 10),
    ) == 2
    assert await education_tasks.materialize_task_rule_through(
        task_rule_id=str(later_rule_id), from_date=date(2026, 8, 4), through_date=date(2026, 8, 10),
    ) == 0
