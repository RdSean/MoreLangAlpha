"""State-machine contracts for persisted family homework tasks."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.server.services import education_tasks
from src.server.services.education_tasks import (
    EducationTaskPermissionError,
    EducationTaskTransitionError,
    assert_task_transition,
)


def test_homework_state_machine_allows_submission_revision_resubmission_and_completion():
    status = "open"
    for next_status in ("submitted", "revision_requested", "submitted", "completed"):
        assert_task_transition(current=status, target=next_status)
        status = next_status

    assert status == "completed"


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("open", "completed"),
        ("open", "revision_requested"),
        ("submitted", "open"),
        ("revision_requested", "completed"),
        ("completed", "submitted"),
        ("cancelled", "submitted"),
    ],
)
def test_homework_state_machine_rejects_invalid_transitions(current, target):
    with pytest.raises(EducationTaskTransitionError):
        assert_task_transition(current=current, target=target)


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
            frequency="once",
            material_asset_ids=[],
        )


@pytest.mark.asyncio
async def test_student_submission_passes_the_idempotency_key_to_locked_persistence(monkeypatch):
    monkeypatch.setattr(
        education_tasks,
        "get_membership_for_user",
        AsyncMock(return_value={"role": "student", "household_id": "h-1"}),
    )
    persisted = {"submission_id": "submission-1", "task_id": "task-1", "sequence": 1, "submission_text": "Done"}
    write = AsyncMock(return_value=persisted)
    monkeypatch.setattr(education_tasks, "submit_task_record", write)

    result = await education_tasks.submit_task(
        student_user_id="student-1",
        task_id="task-1",
        submission_text="Done",
        idempotency_key="idempotency-1",
        asset_ids=[],
    )

    assert result == persisted
    assert write.await_args.kwargs["idempotency_key"] == "idempotency-1"


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
