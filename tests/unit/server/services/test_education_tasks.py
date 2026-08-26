"""State-machine contracts for persisted family homework tasks."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.server.services import education_tasks
from src.server.services.education_tasks import (
    EducationTaskError,
    EducationTaskPermissionError,
)


_PARENT_CONTEXT = {"household_id": "h-1", "timezone": "Asia/Tokyo"}
_VALID_CREATION_CONTEXT = {
    "student_exists": True,
    "grade_code": "g5",
    "subject_type_is_valid": True,
    "practice_source_is_valid": True,
}


def _stub_create_context(monkeypatch, context=_VALID_CREATION_CONTEXT):
    monkeypatch.setattr(
        education_tasks,
        "get_household_context_for_parent",
        AsyncMock(return_value=_PARENT_CONTEXT),
    )
    monkeypatch.setattr(
        education_tasks,
        "get_task_creation_context",
        AsyncMock(return_value=context),
    )


@pytest.mark.asyncio
async def test_only_a_parent_can_create_a_task(monkeypatch):
    monkeypatch.setattr(education_tasks, "get_household_context_for_parent", AsyncMock(return_value=None))

    with pytest.raises(EducationTaskPermissionError):
        await education_tasks.create_task(
            parent_user_id="student-1",
            assigned_student_id="student-2",
            title="Read",
            description="",
            due_at=datetime.now(timezone.utc),
            subject_code="chinese",
            type_code="read",
            practice_source_code=None,
            frequency="once",
            weekdays=None,
            material_asset_ids=[],
        )


@pytest.mark.asyncio
async def test_task_creation_requires_assigned_student_current_grade(monkeypatch):
    _stub_create_context(monkeypatch, {**_VALID_CREATION_CONTEXT, "grade_code": None})

    with pytest.raises(EducationTaskError, match="current grade"):
        await education_tasks.create_task(
            parent_user_id="parent-1",
            assigned_student_id="student-1",
            title="Read",
            description="",
            due_at=datetime.now(timezone.utc),
            subject_code="chinese",
            type_code="read",
            practice_source_code=None,
            frequency="once",
            weekdays=None,
            material_asset_ids=[],
        )


@pytest.mark.asyncio
async def test_task_creation_requires_a_valid_subject_type_pair(monkeypatch):
    _stub_create_context(monkeypatch, {**_VALID_CREATION_CONTEXT, "subject_type_is_valid": False})

    with pytest.raises(EducationTaskError, match="subject and homework type"):
        await education_tasks.create_task(
            parent_user_id="parent-1",
            assigned_student_id="student-1",
            title="Read",
            description="",
            due_at=datetime.now(timezone.utc),
            subject_code="math",
            type_code="listen",
            practice_source_code=None,
            frequency="once",
            weekdays=None,
            material_asset_ids=[],
        )


@pytest.mark.asyncio
async def test_task_creation_requires_practice_source_only_for_practice(monkeypatch):
    _stub_create_context(monkeypatch)

    with pytest.raises(EducationTaskError, match="only valid for practice"):
        await education_tasks.create_task(
            parent_user_id="parent-1",
            assigned_student_id="student-1",
            title="Read",
            description="",
            due_at=datetime.now(timezone.utc),
            subject_code="chinese",
            type_code="read",
            practice_source_code="schoolwork",
            frequency="once",
            weekdays=None,
            material_asset_ids=[],
        )

    with pytest.raises(EducationTaskError, match="requires a practice source"):
        await education_tasks.create_task(
            parent_user_id="parent-1",
            assigned_student_id="student-1",
            title="Practice",
            description="",
            due_at=datetime.now(timezone.utc),
            subject_code="math",
            type_code="practice",
            practice_source_code=None,
            frequency="once",
            weekdays=None,
            material_asset_ids=[],
        )


@pytest.mark.asyncio
async def test_task_creation_requires_a_valid_practice_source(monkeypatch):
    _stub_create_context(
        monkeypatch,
        {**_VALID_CREATION_CONTEXT, "practice_source_is_valid": False},
    )
    monkeypatch.setattr(
        education_tasks,
        "create_task_rule_and_instance",
        AsyncMock(return_value={"task_id": "task-1"}),
    )

    with pytest.raises(EducationTaskError, match="practice source is invalid"):
        await education_tasks.create_task(
            parent_user_id="parent-1",
            assigned_student_id="student-1",
            title="Practice",
            description="",
            due_at=datetime.now(timezone.utc),
            subject_code="math",
            type_code="practice",
            practice_source_code="unknown",
            frequency="once",
            weekdays=None,
            material_asset_ids=[],
        )


@pytest.mark.asyncio
async def test_task_creation_persists_student_grade_and_weekly_recurrence(monkeypatch):
    _stub_create_context(monkeypatch)
    write = AsyncMock(return_value={"task_id": "task-1"})
    monkeypatch.setattr(education_tasks, "create_task_rule_and_instance", write)

    await education_tasks.create_task(
        parent_user_id="parent-1",
        assigned_student_id="student-1",
        title="Practice",
        description="",
        due_at=datetime(2026, 8, 31, 9, tzinfo=timezone.utc),
        subject_code="math",
        type_code="practice",
        practice_source_code="schoolwork",
        frequency="weekly",
        weekdays=[1, 3, 5],
        material_asset_ids=[],
    )

    assert write.await_args.kwargs["grade_code"] == "g5"
    assert write.await_args.kwargs["subject_code"] == "math"
    assert write.await_args.kwargs["type_code"] == "practice"
    assert write.await_args.kwargs["recurrence"]["weekdays"] == ["1", "3", "5"]


@pytest.mark.parametrize("weekdays", [None, [], [0], [8], [1, 1], [True]])
@pytest.mark.asyncio
async def test_weekly_task_requires_a_nonempty_unique_iso_weekday_list(monkeypatch, weekdays):
    _stub_create_context(monkeypatch)

    with pytest.raises(EducationTaskError, match="weekly"):
        await education_tasks.create_task(
            parent_user_id="parent-1",
            assigned_student_id="student-1",
            title="Practice",
            description="",
            due_at=datetime.now(timezone.utc),
            subject_code="math",
            type_code="practice",
            practice_source_code="schoolwork",
            frequency="weekly",
            weekdays=weekdays,
            material_asset_ids=[],
        )


@pytest.mark.asyncio
async def test_check_in_allows_an_empty_initial_submission_and_forwards_idempotency_key(monkeypatch):
    monkeypatch.setattr(
        education_tasks,
        "get_membership_for_user",
        AsyncMock(return_value={"role": "student", "household_id": "h-1"}),
    )
    persisted = {"submission_id": "submission-1", "task_id": "task-1", "sequence": 1, "submission_text": ""}
    write = AsyncMock(return_value=persisted)
    monkeypatch.setattr(education_tasks, "check_in_task_record", write)

    result = await education_tasks.check_in_task(
        student_user_id="student-1",
        task_id="task-1",
        submission_text="",
        idempotency_key="idempotency-1",
        asset_ids=[],
    )

    assert result == persisted
    assert write.await_args.kwargs["idempotency_key"] == "idempotency-1"
    assert write.await_args.kwargs["submission_text"] == ""


@pytest.mark.asyncio
async def test_completed_task_accepts_append_only_revision_without_changing_completion(monkeypatch):
    monkeypatch.setattr(
        education_tasks,
        "get_membership_for_user",
        AsyncMock(return_value={"role": "student", "household_id": "h-1"}),
    )
    persisted = {"submission_id": "submission-2", "task_id": "task-1", "sequence": 2, "submission_kind": "revision"}
    append = AsyncMock(return_value=persisted)
    monkeypatch.setattr(education_tasks, "append_revision_submission_record", append)

    result = await education_tasks.append_revision_submission(
        student_user_id="student-1",
        task_id="task-1",
        submission_text="Updated work",
        idempotency_key="idempotency-2",
        asset_ids=[],
    )

    assert result == persisted
    assert append.await_args.kwargs["submission_text"] == "Updated work"


@pytest.mark.asyncio
async def test_only_a_parent_can_review_or_cancel(monkeypatch):
    monkeypatch.setattr(education_tasks, "get_household_context_for_parent", AsyncMock(return_value=None))

    with pytest.raises(EducationTaskPermissionError):
        await education_tasks.review_task(
            parent_user_id="student-1",
            task_id="task-1",
            feedback_text="Please revise.",
            decision="revision_requested",
        )
    with pytest.raises(EducationTaskPermissionError):
        await education_tasks.cancel_task(parent_user_id="student-1", task_id="task-1")


@pytest.mark.asyncio
async def test_parent_feedback_does_not_change_completion_state(monkeypatch):
    monkeypatch.setattr(education_tasks, "get_household_context_for_parent", AsyncMock(return_value=_PARENT_CONTEXT))
    review = AsyncMock(return_value={"review_id": "review-1", "decision": "feedback"})
    monkeypatch.setattr(education_tasks, "review_task_record", review)

    await education_tasks.review_task(
        parent_user_id="parent-1",
        task_id="task-1",
        feedback_text="Nice work",
        decision="feedback",
    )

    assert review.await_args.kwargs["decision"] == "feedback"


@pytest.mark.asyncio
async def test_completed_task_cannot_be_cancelled(monkeypatch):
    monkeypatch.setattr(education_tasks, "get_household_context_for_parent", AsyncMock(return_value=_PARENT_CONTEXT))
    monkeypatch.setattr(education_tasks, "cancel_task_record", AsyncMock(return_value=None))

    with pytest.raises(education_tasks.EducationTaskNotFoundError, match="cannot be cancelled"):
        await education_tasks.cancel_task(parent_user_id="parent-1", task_id="task-1")
