"""Calendar aggregation and household authorization contracts for homework."""

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.server.services import education_tasks
from src.server.services.education_tasks import (
    EducationTaskError,
    EducationTaskNotFoundError,
    EducationTaskPermissionError,
)


_PARENT_CONTEXT = {
    "household_id": "household-1",
    "role": "parent",
    "timezone": "America/Los_Angeles",
}
_STUDENT_CONTEXT = {**_PARENT_CONTEXT, "role": "student"}
_TASK = {
    "task_id": "bc5734a8-8a30-459f-a1f3-8551feb4c169",
    "task_rule_id": "6eebf7fb-9579-4c5d-825a-2e595b7f1b18",
    "household_id": "household-1",
    "assigned_student_id": "student-1",
    "occurrence_date": date(2026, 8, 1),
    "due_at": datetime(2026, 8, 1, 9, tzinfo=timezone.utc),
    "title": "Read chapter one",
    "description": "",
    "subject_code": "chinese",
    "subject_color": "#D95D39",
    "type_code": "read",
    "practice_source_code": None,
    "grade_code": "g5",
    "status": "open",
    "completed_at": None,
    "created_at": datetime(2026, 7, 30, tzinfo=timezone.utc),
}


@pytest.mark.asyncio
async def test_parent_calendar_can_select_a_same_household_student(monkeypatch):
    monkeypatch.setattr(
        education_tasks, "get_calendar_context_for_user", AsyncMock(return_value=_PARENT_CONTEXT)
    )
    in_household = AsyncMock(return_value=True)
    records = AsyncMock(return_value=[_TASK])
    progress = AsyncMock(
        return_value={"today_count": 1, "week_count": 2, "overdue_count": 3, "completed_count": 4}
    )
    monkeypatch.setattr(education_tasks, "is_student_in_household", in_household)
    monkeypatch.setattr(education_tasks, "list_active_rule_timezones_for_user", AsyncMock(return_value=[]))
    monkeypatch.setattr(education_tasks, "list_calendar_task_records", records)
    monkeypatch.setattr(education_tasks, "get_calendar_progress_counts", progress)

    calendar = await education_tasks.get_task_calendar(
        user_id="parent-1",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 3),
        student_id="student-1",
        now=datetime(2026, 8, 2, 0, 30, tzinfo=timezone.utc),
    )

    assert calendar["student_id"] == "student-1"
    assert [day["date"] for day in calendar["days"]] == [
        date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3),
    ]
    assert calendar["days"][0]["tasks"][0]["subject_color"] == "#D95D39"
    assert calendar["days"][0]["overdue_count"] == 1
    assert calendar["stats"]["today_count"] == 1
    in_household.assert_awaited_once_with(household_id="household-1", user_id="student-1")
    assert records.await_args.kwargs["assigned_student_id"] == "student-1"


@pytest.mark.asyncio
async def test_parent_calendar_hides_a_student_outside_the_household(monkeypatch):
    monkeypatch.setattr(
        education_tasks, "get_calendar_context_for_user", AsyncMock(return_value=_PARENT_CONTEXT)
    )
    monkeypatch.setattr(education_tasks, "is_student_in_household", AsyncMock(return_value=False))

    with pytest.raises(EducationTaskNotFoundError, match="Student account not found"):
        await education_tasks.get_task_calendar(
            user_id="parent-1",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 3),
            student_id="other-student",
        )


@pytest.mark.asyncio
async def test_student_calendar_can_only_query_its_own_tasks(monkeypatch):
    monkeypatch.setattr(
        education_tasks, "get_calendar_context_for_user", AsyncMock(return_value=_STUDENT_CONTEXT)
    )

    with pytest.raises(EducationTaskPermissionError, match="only view their own"):
        await education_tasks.get_task_calendar(
            user_id="student-1",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 3),
            student_id="student-2",
        )


@pytest.mark.asyncio
async def test_calendar_rejects_reversed_or_oversized_ranges():
    with pytest.raises(EducationTaskError, match="end_date"):
        await education_tasks.get_task_calendar(
            user_id="student-1",
            start_date=date(2026, 8, 3),
            end_date=date(2026, 8, 1),
        )

    with pytest.raises(EducationTaskError, match="62 days"):
        await education_tasks.get_task_calendar(
            user_id="student-1",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 10, 2),
        )


@pytest.mark.asyncio
async def test_calendar_rejects_far_future_before_materializing_rules(monkeypatch):
    monkeypatch.setattr(
        education_tasks, "get_calendar_context_for_user", AsyncMock(return_value=_STUDENT_CONTEXT)
    )
    rules = AsyncMock(return_value=[])
    monkeypatch.setattr(education_tasks, "list_active_rule_timezones_for_user", rules)

    with pytest.raises(EducationTaskError, match="12 months"):
        await education_tasks.get_task_calendar(
            user_id="student-1",
            start_date=date(3000, 1, 1),
            end_date=date(3000, 1, 2),
            now=datetime(2026, 8, 2, 0, 30, tzinfo=timezone.utc),
        )

    rules.assert_not_awaited()


@pytest.mark.asyncio
async def test_historical_calendar_materializes_through_current_local_week(monkeypatch):
    monkeypatch.setattr(
        education_tasks, "get_calendar_context_for_user", AsyncMock(return_value=_STUDENT_CONTEXT)
    )
    monkeypatch.setattr(
        education_tasks,
        "list_active_rule_timezones_for_user",
        AsyncMock(
            return_value=[
                {
                    "task_rule_id": "rule-1",
                    "assigned_student_id": "student-1",
                    "timezone": "America/Los_Angeles",
                }
            ]
        ),
    )
    materialize = AsyncMock(return_value=0)
    monkeypatch.setattr(education_tasks, "materialize_task_rule_through", materialize)
    monkeypatch.setattr(education_tasks, "list_calendar_task_records", AsyncMock(return_value=[]))
    monkeypatch.setattr(
        education_tasks,
        "get_calendar_progress_counts",
        AsyncMock(
            return_value={"today_count": 0, "week_count": 0, "overdue_count": 0, "completed_count": 0}
        ),
    )

    await education_tasks.get_task_calendar(
        user_id="student-1",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 2),
        now=datetime(2026, 8, 20, 1, tzinfo=timezone.utc),
    )

    assert materialize.await_args.kwargs["through_date"] == date(2026, 8, 23)


@pytest.mark.asyncio
async def test_calendar_uses_household_timezone_for_today_and_week_boundaries(monkeypatch):
    monkeypatch.setattr(
        education_tasks, "get_calendar_context_for_user", AsyncMock(return_value=_STUDENT_CONTEXT)
    )
    monkeypatch.setattr(education_tasks, "list_active_rule_timezones_for_user", AsyncMock(return_value=[]))
    monkeypatch.setattr(education_tasks, "list_calendar_task_records", AsyncMock(return_value=[]))
    progress = AsyncMock(
        return_value={"today_count": 0, "week_count": 0, "overdue_count": 0, "completed_count": 0}
    )
    monkeypatch.setattr(education_tasks, "get_calendar_progress_counts", progress)

    await education_tasks.get_task_calendar(
        user_id="student-1",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 3),
        now=datetime(2026, 8, 2, 0, 30, tzinfo=timezone.utc),
    )

    assert progress.await_args.kwargs["today"] == date(2026, 8, 1)
    assert progress.await_args.kwargs["week_start"] == date(2026, 7, 27)
    assert progress.await_args.kwargs["week_end"] == date(2026, 8, 2)
