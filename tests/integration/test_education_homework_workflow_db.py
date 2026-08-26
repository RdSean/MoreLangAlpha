"""Executable database contracts for the temporary homework compatibility bridge."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import psycopg.errors
from psycopg.types.json import Jsonb
import pytest
from sqlalchemy.exc import DBAPIError


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _run_alembic(test_db_uri: str, revision: str, *, downgrade: bool) -> None:
    project_root = Path(__file__).parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option(
        "sqlalchemy.url",
        test_db_uri.replace("postgresql://", "postgresql+psycopg://", 1),
    )
    await asyncio.to_thread(
        command.downgrade if downgrade else command.upgrade,
        config,
        revision,
    )


async def test_homework_final_workflow_rejects_legacy_writes(db_conn):
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
            assert (await cur.fetchone())["version_num"] == "039"

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
            await cur.execute(
                """
                INSERT INTO education_student_profiles (household_id, user_id, grade_code)
                VALUES (%s, %s, 'g5')
                """,
                (household_id, student_id),
            )

            await cur.execute("SAVEPOINT invalid_weekdays")
            with pytest.raises(psycopg.errors.CheckViolation):
                await cur.execute(
                    """
                    INSERT INTO education_task_rules (
                        task_rule_id, household_id, created_by_user_id,
                        assigned_student_id, title, recurrence, timezone,
                        subject_code, type_code, practice_source_code, grade_code
                    ) VALUES (%s, %s, %s, %s, 'Invalid weekdays', %s::jsonb, 'Asia/Tokyo', 'math', 'practice', 'schoolwork', 'g5')
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

            for invalid_weekdays in ([None], ["1", None]):
                await cur.execute("SAVEPOINT invalid_weekday_element")
                with pytest.raises(psycopg.errors.CheckViolation):
                    await cur.execute(
                        """
                        INSERT INTO education_task_rules (
                            task_rule_id, household_id, created_by_user_id,
                            assigned_student_id, title, recurrence, timezone,
                            subject_code, type_code, practice_source_code, grade_code
                        ) VALUES (%s, %s, %s, %s, 'Invalid weekday element', %s::jsonb, 'Asia/Tokyo', 'math', 'practice', 'schoolwork', 'g5')
                        """,
                        (
                            uuid4(),
                            household_id,
                            parent_id,
                            student_id,
                            Jsonb({**recurrence, "weekdays": invalid_weekdays}),
                        ),
                    )
                await cur.execute("ROLLBACK TO SAVEPOINT invalid_weekday_element")

            await cur.execute(
                """
                INSERT INTO education_task_rules (
                    task_rule_id, household_id, created_by_user_id,
                    assigned_student_id, title, recurrence, timezone,
                    subject_code, type_code, practice_source_code, grade_code
                ) VALUES (%s, %s, %s, %s, 'Finalized task', %s::jsonb, 'Asia/Tokyo', 'math', 'practice', 'schoolwork', 'g5')
                """,
                (rule_id, household_id, parent_id, student_id, Jsonb(recurrence)),
            )
            await cur.execute(
                """
                INSERT INTO education_tasks (
                    task_id, task_rule_id, household_id, assigned_student_id,
                    occurrence_date, due_at, title, subject_code, type_code,
                    practice_source_code, grade_code
                ) VALUES (%s, %s, %s, %s, CURRENT_DATE, NOW(), 'Finalized task', 'math', 'practice', 'schoolwork', 'g5')
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
            assert (await cur.fetchone())["completed_at"] is None
            await cur.execute("SAVEPOINT legacy_task_status")
            with pytest.raises(psycopg.errors.CheckViolation):
                await cur.execute("UPDATE education_tasks SET status = 'submitted' WHERE task_id = %s", (task_id,))
            await cur.execute("ROLLBACK TO SAVEPOINT legacy_task_status")
            await cur.execute("SAVEPOINT legacy_review_decision")
            with pytest.raises(psycopg.errors.CheckViolation):
                await cur.execute(
                    """
                    INSERT INTO education_task_reviews (
                        review_id, submission_id, reviewed_by_user_id, decision, feedback_text
                    ) VALUES (%s, %s, %s, 'completed', 'Legacy review')
                    """,
                    (review_id, submission_id, parent_id),
                )
            await cur.execute("ROLLBACK TO SAVEPOINT legacy_review_decision")


async def test_036_downgrade_converts_legacy_task_states(db_conn, test_db_uri):
    parent_id = f"downgrade-parent-{uuid4()}"
    student_id = f"downgrade-student-{uuid4()}"
    household_id = uuid4()
    submitted_rule_id = uuid4()
    revision_rule_id = uuid4()
    submitted_task_id = uuid4()
    revision_task_id = uuid4()
    submission_id = uuid4()
    recurrence = {
        "frequency": "once",
        "start_date": date.today().isoformat(),
        "due_time": "18:00",
    }

    await _run_alembic(test_db_uri, "036", downgrade=True)
    await db_conn.execute("BEGIN")
    async with db_conn.cursor() as cur:
        await cur.execute("SELECT version_num FROM alembic_version")
        assert (await cur.fetchone())["version_num"] == "036"
        await cur.executemany(
            "INSERT INTO users (user_id, name) VALUES (%s, %s)",
            [(parent_id, "Downgrade Parent"), (student_id, "Downgrade Student")],
        )
        await cur.execute(
            """
            INSERT INTO education_households (household_id, name, model_owner_user_id)
            VALUES (%s, 'Downgrade compatibility', %s)
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
                (household_id, parent_id, "parent", "Downgrade Parent"),
                (household_id, student_id, "student", "Downgrade Student"),
            ],
        )
        await cur.executemany(
            """
            INSERT INTO education_task_rules (
                task_rule_id, household_id, created_by_user_id,
                assigned_student_id, title, recurrence, timezone
            ) VALUES (%s, %s, %s, %s, %s, %s::jsonb, 'Asia/Tokyo')
            """,
            [
                (
                    submitted_rule_id,
                    household_id,
                    parent_id,
                    student_id,
                    "Submitted legacy task",
                    Jsonb(recurrence),
                ),
                (
                    revision_rule_id,
                    household_id,
                    parent_id,
                    student_id,
                    "Revision legacy task",
                    Jsonb(recurrence),
                ),
            ],
        )
        await cur.executemany(
            """
            INSERT INTO education_tasks (
                task_id, task_rule_id, household_id, assigned_student_id,
                occurrence_date, due_at, title, status
            ) VALUES (%s, %s, %s, %s, CURRENT_DATE, NOW(), %s, %s)
            """,
            [
                (
                    submitted_task_id,
                    submitted_rule_id,
                    household_id,
                    student_id,
                    "Submitted legacy task",
                    "open",
                ),
                (
                    revision_task_id,
                    revision_rule_id,
                    household_id,
                    student_id,
                    "Revision legacy task",
                    "revision_requested",
                ),
            ],
        )
        await cur.execute(
            """
            INSERT INTO education_task_submissions (
                submission_id, task_id, submitted_by_user_id, sequence, submission_text
            ) VALUES (%s, %s, %s, 1, '')
            """,
            (submission_id, submitted_task_id, student_id),
        )
        await cur.execute(
            """
            UPDATE education_tasks
            SET status = 'submitted', completed_at = NULL
            WHERE task_id = %s
            """,
            (submitted_task_id,),
        )
    await db_conn.execute("COMMIT")

    try:
        await _run_alembic(test_db_uri, "035", downgrade=True)

        async with db_conn.cursor() as cur:
            await cur.execute("SELECT version_num FROM alembic_version")
            assert (await cur.fetchone())["version_num"] == "035"
            await cur.execute(
                """
                SELECT task_id, status, completed_at
                FROM education_tasks
                WHERE task_id = ANY(%s::uuid[])
                ORDER BY task_id
                """,
                ([submitted_task_id, revision_task_id],),
            )
            tasks = {row["task_id"]: row for row in await cur.fetchall()}
            assert tasks[submitted_task_id]["status"] == "completed"
            assert tasks[submitted_task_id]["completed_at"] is not None
            assert tasks[revision_task_id]["status"] == "open"
    finally:
        await _run_alembic(test_db_uri, "head", downgrade=False)


async def test_038_upgrade_rejects_dirty_weekly_recurrence_from_036(db_conn, test_db_uri):
    parent_id = f"dirty-parent-{uuid4()}"
    student_id = f"dirty-student-{uuid4()}"
    household_id = uuid4()
    rule_id = uuid4()
    dirty_recurrence = {
        "frequency": "weekly",
        "start_date": date.today().isoformat(),
        "due_time": "18:00",
        "weekdays": ["1", None],
    }

    await _run_alembic(test_db_uri, "036", downgrade=True)
    try:
        async with db_conn.transaction():
            async with db_conn.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO users (user_id, name) VALUES (%s, %s)",
                    [(parent_id, "Dirty Parent"), (student_id, "Dirty Student")],
                )
                await cur.execute(
                    """
                    INSERT INTO education_households (household_id, name, model_owner_user_id)
                    VALUES (%s, 'Dirty recurrence', %s)
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
                        (household_id, parent_id, "parent", "Dirty Parent"),
                        (household_id, student_id, "student", "Dirty Student"),
                    ],
                )
                await cur.execute(
                    """
                    INSERT INTO education_task_rules (
                        task_rule_id, household_id, created_by_user_id,
                        assigned_student_id, title, recurrence, timezone
                    ) VALUES (%s, %s, %s, %s, 'Dirty recurrence', %s::jsonb, 'Asia/Tokyo')
                    """,
                    (rule_id, household_id, parent_id, student_id, Jsonb(dirty_recurrence)),
                )

        with pytest.raises(DBAPIError, match="invalid weekly recurrence metadata"):
            await _run_alembic(test_db_uri, "038", downgrade=False)
    finally:
        async with db_conn.cursor() as cur:
            await cur.execute("DELETE FROM education_task_rules WHERE task_rule_id = %s", (rule_id,))
        await _run_alembic(test_db_uri, "head", downgrade=False)


async def test_legacy_completed_review_upgrades_and_serializes_in_task_list(db_conn, test_db_uri):
    from src.server.app.education.models import EducationTaskResponse

    parent_id = f"legacy-parent-{uuid4()}"
    student_id = f"legacy-student-{uuid4()}"
    household_id = uuid4()
    rule_id = uuid4()
    task_id = uuid4()
    submission_id = uuid4()
    review_id = uuid4()
    recurrence = {
        "frequency": "once",
        "start_date": date.today().isoformat(),
        "due_time": "18:00",
    }

    await _run_alembic(test_db_uri, "034", downgrade=True)
    try:
        async with db_conn.transaction():
            async with db_conn.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO users (user_id, name) VALUES (%s, %s)",
                    [(parent_id, "Legacy Parent"), (student_id, "Legacy Student")],
                )
                await cur.execute(
                    """
                    INSERT INTO education_households (household_id, name, model_owner_user_id)
                    VALUES (%s, 'Legacy review', %s)
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
                        (household_id, parent_id, "parent", "Legacy Parent"),
                        (household_id, student_id, "student", "Legacy Student"),
                    ],
                )
                await cur.execute(
                    """
                    INSERT INTO education_task_rules (
                        task_rule_id, household_id, created_by_user_id,
                        assigned_student_id, title, recurrence, timezone
                    ) VALUES (%s, %s, %s, %s, 'Legacy task', %s::jsonb, 'Asia/Tokyo')
                    """,
                    (rule_id, household_id, parent_id, student_id, Jsonb(recurrence)),
                )
                await cur.execute(
                    """
                    INSERT INTO education_tasks (
                        task_id, task_rule_id, household_id, assigned_student_id,
                        occurrence_date, due_at, title, status
                    ) VALUES (%s, %s, %s, %s, CURRENT_DATE, NOW(), 'Legacy task', 'submitted')
                    """,
                    (task_id, rule_id, household_id, student_id),
                )
                await cur.execute(
                    """
                    INSERT INTO education_task_submissions (
                        submission_id, task_id, submitted_by_user_id, sequence, submission_text
                    ) VALUES (%s, %s, %s, 1, '')
                    """,
                    (submission_id, task_id, student_id),
                )
                await cur.execute(
                    """
                    INSERT INTO education_task_reviews (
                        review_id, submission_id, reviewed_by_user_id, decision, feedback_text
                    ) VALUES (%s, %s, %s, 'completed', 'Legacy completed review')
                    """,
                    (review_id, submission_id, parent_id),
                )

        await _run_alembic(test_db_uri, "head", downgrade=False)
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                SELECT tasks.task_id, tasks.task_rule_id, tasks.household_id,
                       tasks.assigned_student_id, tasks.occurrence_date, tasks.due_at,
                       tasks.title, tasks.description, tasks.status, tasks.created_at,
                       reviews.decision AS latest_review_decision,
                       reviews.feedback_text AS latest_feedback_text
                FROM education_tasks AS tasks
                JOIN education_task_submissions AS submissions ON submissions.task_id = tasks.task_id
                JOIN education_task_reviews AS reviews ON reviews.submission_id = submissions.submission_id
                WHERE tasks.task_id = %s
                """,
                (task_id,),
            )
            task = dict(await cur.fetchone())

        response = EducationTaskResponse.model_validate(task)
        assert response.latest_review_decision == "feedback"
        assert response.model_dump(mode="json")["latest_review_decision"] == "feedback"
    finally:
        await _run_alembic(test_db_uri, "head", downgrade=False)
