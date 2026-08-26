"""Real PostgreSQL contracts for role-scoped homework task timelines."""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from src.server.database import education_tasks
from src.server.services import education_tasks as education_task_service


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_task_detail_scopes_timeline_and_preserves_asset_review_order(db_conn, monkeypatch):
    household_id = uuid4()
    other_household_id = uuid4()
    parent_id = f"detail-parent-{uuid4()}"
    student_id = f"detail-student-{uuid4()}"
    other_student_id = f"detail-other-student-{uuid4()}"
    other_parent_id = f"detail-other-parent-{uuid4()}"
    rule_id = uuid4()
    task_id = uuid4()
    check_in_id = uuid4()
    revision_id = uuid4()
    review_one_id = uuid4()
    review_two_id = uuid4()
    material_later_id = uuid4()
    material_earlier_id = uuid4()
    answer_later_id = uuid4()
    answer_earlier_id = uuid4()
    created_at = datetime(2026, 8, 9, 8, tzinfo=timezone.utc)

    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.executemany(
                "INSERT INTO users (user_id, name) VALUES (%s, %s)",
                [
                    (parent_id, "Detail parent"),
                    (student_id, "Assigned student"),
                    (other_student_id, "Other student"),
                    (other_parent_id, "Other parent"),
                ],
            )
            await cur.executemany(
                """
                INSERT INTO education_households (household_id, name, model_owner_user_id)
                VALUES (%s, %s, %s)
                """,
                [
                    (household_id, "Detail household", parent_id),
                    (other_household_id, "Other household", other_parent_id),
                ],
            )
            await cur.executemany(
                """
                INSERT INTO education_memberships
                    (household_id, user_id, role, display_name)
                VALUES (%s, %s, %s, %s)
                """,
                [
                    (household_id, parent_id, "parent", "Detail parent"),
                    (household_id, student_id, "student", "Assigned student"),
                    (household_id, other_student_id, "student", "Other student"),
                    (other_household_id, other_parent_id, "parent", "Other parent"),
                ],
            )
            await cur.execute(
                """
                INSERT INTO education_task_rules (
                    task_rule_id, household_id, created_by_user_id, assigned_student_id,
                    title, recurrence, timezone
                ) VALUES (
                    %s, %s, %s, %s, 'Read chapter one',
                    '{"frequency":"once","start_date":"2026-08-09","due_time":"09:00"}'::jsonb,
                    'UTC'
                )
                """,
                (rule_id, household_id, parent_id, student_id),
            )
            await cur.execute(
                """
                INSERT INTO education_tasks (
                    task_id, task_rule_id, household_id, assigned_student_id,
                    occurrence_date, due_at, title, status, completed_at, created_at
                ) VALUES (%s, %s, %s, %s, '2026-08-09', %s, 'Read chapter one', 'completed', %s, %s)
                """,
                (task_id, rule_id, household_id, student_id, created_at, created_at, created_at),
            )
            await cur.executemany(
                """
                INSERT INTO education_assets (
                    asset_id, household_id, created_by_user_id, storage_key,
                    original_filename, content_type, size_bytes, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, 1, %s)
                """,
                [
                    (material_later_id, household_id, parent_id, f"education/{household_id}/{material_later_id}.pdf", "later-material.pdf", "application/pdf", datetime(2026, 8, 8, 2, tzinfo=timezone.utc)),
                    (material_earlier_id, household_id, parent_id, f"education/{household_id}/{material_earlier_id}.png", "earlier-material.png", "image/png", datetime(2026, 8, 8, 1, tzinfo=timezone.utc)),
                    (answer_later_id, household_id, student_id, f"education/{household_id}/{answer_later_id}.pdf", "later-answer.pdf", "application/pdf", datetime(2026, 8, 9, 2, tzinfo=timezone.utc)),
                    (answer_earlier_id, household_id, student_id, f"education/{household_id}/{answer_earlier_id}.jpg", "earlier-answer.jpg", "image/jpeg", datetime(2026, 8, 9, 1, tzinfo=timezone.utc)),
                ],
            )
            await cur.executemany(
                "INSERT INTO education_task_material_assets (task_id, asset_id) VALUES (%s, %s)",
                [(task_id, material_later_id), (task_id, material_earlier_id)],
            )
            await cur.executemany(
                """
                INSERT INTO education_task_submissions (
                    submission_id, task_id, submitted_by_user_id, sequence,
                    submission_text, submission_kind, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                [
                    (check_in_id, task_id, student_id, 1, "Done", "check_in", created_at),
                    (revision_id, task_id, student_id, 2, "Updated", "revision", datetime(2026, 8, 9, 3, tzinfo=timezone.utc)),
                ],
            )
            await cur.executemany(
                "INSERT INTO education_task_submission_assets (submission_id, asset_id) VALUES (%s, %s)",
                [(check_in_id, answer_later_id), (check_in_id, answer_earlier_id)],
            )
            await cur.executemany(
                """
                INSERT INTO education_task_reviews (
                    review_id, submission_id, reviewed_by_user_id,
                    decision, feedback_text, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                """,
                [
                    (review_two_id, check_in_id, parent_id, "feedback", "Second feedback", datetime(2026, 8, 9, 5, tzinfo=timezone.utc)),
                    (review_one_id, check_in_id, parent_id, "revision_requested", "First feedback", datetime(2026, 8, 9, 4, tzinfo=timezone.utc)),
                ],
            )

    @asynccontextmanager
    async def use_test_connection():
        yield db_conn

    monkeypatch.setattr(education_tasks, "get_db_connection", use_test_connection)

    parent_detail = await education_tasks.get_task_detail_for_user(
        task_id=str(task_id), user_id=parent_id
    )
    student_detail = await education_tasks.get_task_detail_for_user(
        task_id=str(task_id), user_id=student_id
    )
    assert parent_detail is not None
    assert student_detail is not None
    assert [asset["original_filename"] for asset in parent_detail["parent_materials"]] == [
        "earlier-material.png", "later-material.pdf"
    ]
    assert [submission["sequence"] for submission in parent_detail["submissions"]] == [1, 2]
    assert [asset["original_filename"] for asset in parent_detail["submissions"][0]["assets"]] == [
        "earlier-answer.jpg", "later-answer.pdf"
    ]
    assert [review["feedback_text"] for review in parent_detail["submissions"][0]["reviews"]] == [
        "First feedback", "Second feedback"
    ]
    assert await education_tasks.get_task_detail_for_user(
        task_id=str(task_id), user_id=other_student_id
    ) is None
    assert await education_tasks.get_task_detail_for_user(
        task_id=str(task_id), user_id=other_parent_id
    ) is None

    monkeypatch.setattr(
        education_task_service,
        "get_task_detail_for_user",
        education_tasks.get_task_detail_for_user,
    )
    detail = await education_task_service.get_task_detail(user_id=student_id, task_id=str(task_id))
    assert detail["parent_materials"][0]["download_endpoint"] == (
        f"/api/v1/education/assets/{material_earlier_id}/download"
    )
    assert "storage_key" not in detail["parent_materials"][0]
