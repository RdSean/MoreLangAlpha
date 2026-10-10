"""State-machine contracts for persisted family homework tasks."""

from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from src.server.services import education_tasks
from src.server.services.education_tasks import (
    EducationTaskAssetError,
    EducationTaskError,
    EducationTaskPermissionError,
    EducationTaskTransitionError,
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
        due_at=datetime.now(timezone.utc) + timedelta(days=10),
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


@pytest.mark.asyncio
async def test_task_creation_reuses_the_original_task_for_a_retried_request_key(monkeypatch):
    _stub_create_context(monkeypatch)
    existing = {"task_id": "task-1", "title": "Already created"}
    find_existing = AsyncMock(return_value=existing)
    write = AsyncMock()
    monkeypatch.setattr(education_tasks, "get_task_by_creation_idempotency", find_existing)
    monkeypatch.setattr(education_tasks, "create_task_rule_and_instance", write)

    result = await education_tasks.create_task(
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
        idempotency_key="ec4075f0-6e7a-4f3d-bf56-c04121bbb395",
    )

    assert result == existing
    find_existing.assert_awaited_once_with(
        household_id="h-1",
        parent_user_id="parent-1",
        idempotency_key="ec4075f0-6e7a-4f3d-bf56-c04121bbb395",
    )
    write.assert_not_awaited()


@pytest.mark.asyncio
async def test_task_creation_persists_its_request_key(monkeypatch):
    _stub_create_context(monkeypatch)
    monkeypatch.setattr(education_tasks, "get_task_by_creation_idempotency", AsyncMock(return_value=None))
    write = AsyncMock(return_value={"task_id": "task-1"})
    monkeypatch.setattr(education_tasks, "create_task_rule_and_instance", write)

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
        idempotency_key="ec4075f0-6e7a-4f3d-bf56-c04121bbb395",
    )

    assert write.await_args.kwargs["idempotency_key"] == "ec4075f0-6e7a-4f3d-bf56-c04121bbb395"


@pytest.mark.asyncio
async def test_task_creation_reports_material_assets_outside_the_household(monkeypatch):
    _stub_create_context(monkeypatch)
    monkeypatch.setattr(
        education_tasks,
        "create_task_rule_and_instance",
        AsyncMock(side_effect=ValueError("One or more material assets are outside the household")),
    )

    with pytest.raises(EducationTaskAssetError, match="material assets"):
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
            material_asset_ids=["asset-1"],
        )


@pytest.mark.asyncio
async def test_task_creation_only_converts_known_asset_ownership_errors(monkeypatch):
    _stub_create_context(monkeypatch)
    monkeypatch.setattr(
        education_tasks,
        "create_task_rule_and_instance",
        AsyncMock(side_effect=ValueError("Unexpected persistence error")),
    )

    with pytest.raises(ValueError) as exc_info:
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

    assert type(exc_info.value) is ValueError


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
async def test_weekly_task_rejects_a_range_without_a_selected_weekday(monkeypatch):
    _stub_create_context(monkeypatch)

    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 8, 30, 8, tzinfo=tz)
    monkeypatch.setattr(education_tasks, "datetime", FrozenDateTime)
    with pytest.raises(EducationTaskError, match="No scheduled homework dates"):
        await education_tasks.create_task(
            parent_user_id="parent-1",
            assigned_student_id="student-1",
            title="Practice",
            description="",
            due_at=datetime(2026, 8, 30, 9, tzinfo=timezone.utc),  # Sunday in Asia/Tokyo
            subject_code="math",
            type_code="practice",
            practice_source_code="schoolwork",
            frequency="weekly",
            weekdays=[1, 3, 5],
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
async def test_check_in_reports_submission_assets_outside_the_household(monkeypatch):
    monkeypatch.setattr(
        education_tasks,
        "get_membership_for_user",
        AsyncMock(return_value={"role": "student", "household_id": "h-1"}),
    )
    monkeypatch.setattr(
        education_tasks,
        "check_in_task_record",
        AsyncMock(side_effect=ValueError("One or more submission assets are outside the household")),
    )

    with pytest.raises(EducationTaskAssetError, match="submission assets"):
        await education_tasks.check_in_task(
            student_user_id="student-1",
            task_id="task-1",
            submission_text="",
            idempotency_key=None,
            asset_ids=["asset-1"],
        )


@pytest.mark.asyncio
async def test_check_in_keeps_task_state_errors_as_conflicts(monkeypatch):
    monkeypatch.setattr(
        education_tasks,
        "get_membership_for_user",
        AsyncMock(return_value={"role": "student", "household_id": "h-1"}),
    )
    monkeypatch.setattr(
        education_tasks,
        "check_in_task_record",
        AsyncMock(side_effect=ValueError("Task cannot be checked in from completed")),
    )

    with pytest.raises(EducationTaskTransitionError, match="cannot be checked in"):
        await education_tasks.check_in_task(
            student_user_id="student-1",
            task_id="task-1",
            submission_text="",
            idempotency_key=None,
            asset_ids=[],
        )


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
async def test_revision_reports_submission_assets_outside_the_household(monkeypatch):
    monkeypatch.setattr(
        education_tasks,
        "get_membership_for_user",
        AsyncMock(return_value={"role": "student", "household_id": "h-1"}),
    )
    monkeypatch.setattr(
        education_tasks,
        "append_revision_submission_record",
        AsyncMock(side_effect=ValueError("One or more submission assets are outside the household")),
    )

    with pytest.raises(EducationTaskAssetError, match="submission assets"):
        await education_tasks.append_revision_submission(
            student_user_id="student-1",
            task_id="task-1",
            submission_text="Updated work",
            idempotency_key=None,
            asset_ids=["asset-1"],
        )


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


@pytest.mark.asyncio
async def test_parent_check_in_preserves_actual_actor(monkeypatch):
    monkeypatch.setattr(education_tasks, "get_membership_for_user", AsyncMock(return_value={"role": "parent", "household_id": "h-1"}))
    write = AsyncMock(return_value={"submitted_by_user_id": "parent-1"})
    monkeypatch.setattr(education_tasks, "check_in_task_record", write)
    result = await education_tasks.check_in_task(student_user_id="parent-1", task_id="task-1", submission_text="完成", idempotency_key="key", asset_ids=[])
    assert result["submitted_by_user_id"] == "parent-1"
    assert write.await_args.kwargs["student_user_id"] == "parent-1"


@pytest.mark.asyncio
async def test_check_in_outside_actor_scope_is_not_found(monkeypatch):
    monkeypatch.setattr(education_tasks, "get_membership_for_user", AsyncMock(return_value={"role": "parent", "household_id": "other"}))
    monkeypatch.setattr(education_tasks, "check_in_task_record", AsyncMock(return_value=None))
    with pytest.raises(education_tasks.EducationTaskNotFoundError):
        await education_tasks.check_in_task(student_user_id="parent-2", task_id="task-1", submission_text="", idempotency_key=None, asset_ids=[])


@pytest.mark.asyncio
@pytest.mark.parametrize("frequency,weekdays,first_day", [
    ("daily", None, "2026-10-10"),
    ("weekdays", None, "2026-10-12"),
    ("weekly", [7], "2026-10-11"),
])
async def test_recurring_task_starts_today_and_ends_on_due_date(monkeypatch, frequency, weekdays, first_day):
    _stub_create_context(monkeypatch)
    write = AsyncMock(return_value={"task_id": "task-1"})
    monkeypatch.setattr(education_tasks, "create_task_rule_and_instance", write)
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 10, 9, tzinfo=tz)
    monkeypatch.setattr(education_tasks, "datetime", FrozenDateTime)

    await education_tasks.create_task(
        parent_user_id="parent-1", assigned_student_id="student-1", title="Daily",
        description="", due_at=datetime(2027, 1, 1, 9, tzinfo=timezone.utc),
        subject_code="math", type_code="practice", practice_source_code="schoolwork",
        frequency=frequency, weekdays=weekdays, material_asset_ids=[],
    )

    recurrence = write.await_args.kwargs["recurrence"]
    assert recurrence["start_date"] == "2026-10-10"
    assert recurrence["end_date"] == "2027-01-01"
    assert write.await_args.kwargs["occurrence_date"].isoformat() == first_day
    assert write.await_args.kwargs["due_at"].date().isoformat() == first_day


@pytest.mark.parametrize("frequency,weekdays,expected", [
    ("daily", None, [date(2026, 12, 30), date(2026, 12, 31), date(2027, 1, 1)]),
    ("weekdays", None, [date(2026, 12, 30), date(2026, 12, 31), date(2027, 1, 1)]),
    ("weekly", ["3"], [date(2026, 12, 30)]),
])
def test_recurrence_stops_at_inclusive_cross_year_deadline(frequency, weekdays, expected):
    from src.server.database.education_tasks import _task_occurrence_dates
    recurrence = {"frequency": frequency, "start_date": "2026-12-30", "end_date": "2027-01-01", "weekdays": weekdays}
    assert _task_occurrence_dates(recurrence=recurrence, from_date=None, through_date=date(2027, 1, 8)) == expected
    assert _task_occurrence_dates(recurrence=recurrence, from_date=date(2027, 1, 2), through_date=date(2027, 1, 8)) == []
