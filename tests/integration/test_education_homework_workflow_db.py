"""Executable database contracts for the temporary homework compatibility bridge."""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import psycopg.errors
from psycopg.types.json import Jsonb
import pytest


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_homework_compatibility_bridge_accepts_legacy_service_writes(db_conn):
    parent_id = f"parent-{uuid4()}"
    student_id = f"student-{uuid4()}"
    household_id = uuid4()
    rule_id = uuid4()
    task_id = uuid4()
    submission_id = uuid4()
    review_id = uuid4()
    recurrence = {
        "frequency": "weekly",
        "start_date": date.today().isoformat(),
        "due_time": "18:00",
        "weekdays": ["1", "5"],
    }

    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.execute("SELECT version_num FROM alembic_version")
            assert (await cur.fetchone())["version_num"] == "036"

            await cur.executemany(
                "INSERT INTO users (user_id, name) VALUES (%s, %s)",
                [(parent_id, "Parent"), (student_id, "Student")],
            )
            await cur.execute(
                """
                INSERT INTO education_households
                    (household_id, name, model_owner_user_id)
                VALUES (%s, 'Homework compatibility', %s)
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
                    (household_id, parent_id, "parent", "Parent"),
                    (household_id, student_id, "student", "Student"),
                ],
            )

            await cur.execute("SAVEPOINT invalid_weekdays")
            with pytest.raises(psycopg.errors.CheckViolation):
                await cur.execute(
                    """
                    INSERT INTO education_task_rules (
                        task_rule_id, household_id, created_by_user_id,
                        assigned_student_id, title, recurrence, timezone
                    ) VALUES (%s, %s, %s, %s, 'Invalid weekdays', %s::jsonb, 'Asia/Tokyo')
                    """,
                    (
                        uuid4(),
                        household_id,
                        parent_id,
                        student_id,
                        Jsonb({**recurrence, "weekdays": None}),
                    ),
                )
            await cur.execute("ROLLBACK TO SAVEPOINT invalid_weekdays")

            await cur.execute(
                """
                INSERT INTO education_task_rules (
                    task_rule_id, household_id, created_by_user_id,
                    assigned_student_id, title, recurrence, timezone
                ) VALUES (%s, %s, %s, %s, 'Compatibility task', %s::jsonb, 'Asia/Tokyo')
                """,
                (rule_id, household_id, parent_id, student_id, Jsonb(recurrence)),
            )
            await cur.execute(
                """
                INSERT INTO education_tasks (
                    task_id, task_rule_id, household_id, assigned_student_id,
                    occurrence_date, due_at, title
                ) VALUES (%s, %s, %s, %s, CURRENT_DATE, NOW(), 'Compatibility task')
                """,
                (task_id, rule_id, household_id, student_id),
            )
            await cur.execute(
                """
                INSERT INTO education_task_submissions (
                    submission_id, task_id, submitted_by_user_id, sequence, submission_text
                ) VALUES (%s, %s, %s, 1, '')
                RETURNING submission_kind
                """,
                (submission_id, task_id, student_id),
            )
            assert (await cur.fetchone())["submission_kind"] == "check_in"
            await cur.execute("SELECT completed_at FROM education_tasks WHERE task_id = %s", (task_id,))
            assert (await cur.fetchone())["completed_at"] is not None
            await cur.execute("UPDATE education_tasks SET status = 'submitted' WHERE task_id = %s", (task_id,))
            await cur.execute(
                """
                INSERT INTO education_task_reviews (
                    review_id, submission_id, reviewed_by_user_id, decision, feedback_text
                ) VALUES (%s, %s, %s, 'completed', 'Legacy review')
                """,
                (review_id, submission_id, parent_id),
            )
