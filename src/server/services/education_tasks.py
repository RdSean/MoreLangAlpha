"""Homework completion, recurrence, and household authorization rules."""

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from src.server.database.education_members import get_membership_for_user
from src.server.database.education_tasks import (
    append_revision_submission as append_revision_submission_record,
    cancel_task as cancel_task_record,
    check_in_task as check_in_task_record,
    create_task_rule_and_instance,
    get_calendar_context_for_user,
    get_calendar_progress_counts,
    get_household_context_for_parent,
    get_task_detail_for_user,
    get_task_creation_context,
    is_student_in_household,
    list_active_rule_timezones_for_user,
    list_calendar_task_records,
    list_tasks_for_user as list_task_records,
    materialize_task_rule_through,
    review_task as review_task_record,
    stop_task_rule as stop_task_rule_record,
)


class EducationTaskError(RuntimeError):
    """Base exception for education homework operations."""


class EducationTaskTransitionError(EducationTaskError, ValueError):
    """A requested homework operation is invalid for the current task state."""


class EducationTaskAssetError(EducationTaskError):
    """Referenced homework attachments are unavailable in the household."""


class EducationTaskPermissionError(EducationTaskError, PermissionError):
    """The caller is not allowed to perform this homework operation."""


class EducationTaskNotFoundError(EducationTaskError, LookupError):
    """The requested task is absent or outside the caller's household scope."""


_ASSET_OWNERSHIP_ERRORS = frozenset({
    "One or more material assets are outside the household",
    "One or more submission assets are outside the household",
})
_MAX_CALENDAR_RANGE_DAYS = 62
# Calendar browsing can materialize recurring instances, so bound its absolute
# horizon as well as each individual request window.
_MAX_CALENDAR_FUTURE_DAYS = 366


def _task_asset_error(exc: ValueError) -> EducationTaskAssetError | None:
    if str(exc) in _ASSET_OWNERSHIP_ERRORS:
        return EducationTaskAssetError(str(exc))
    return None


def _required_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise EducationTaskError(f"{field} is required")
    return normalized


def _normalize_weekdays(*, frequency: str, weekdays: list[int] | None) -> list[str] | None:
    if frequency == "weekly":
        if (
            not weekdays
            or len(set(weekdays)) != len(weekdays)
            or any(type(day) is not int or day not in range(1, 8) for day in weekdays)
        ):
            raise EducationTaskError("weekly tasks require a nonempty unique ISO weekday list")
        return [str(day) for day in sorted(weekdays)]
    if weekdays:
        raise EducationTaskError("weekdays are only valid for weekly tasks")
    return None


def _validate_practice_source(*, type_code: str, practice_source_code: str | None) -> None:
    if type_code == "practice" and not practice_source_code:
        raise EducationTaskError("practice requires a practice source")
    if type_code != "practice" and practice_source_code is not None:
        raise EducationTaskError("practice source is only valid for practice tasks")


async def create_task(
    *, parent_user_id: str, assigned_student_id: str, title: str,
    description: str, due_at: datetime, subject_code: str, type_code: str,
    practice_source_code: str | None, frequency: str, weekdays: list[int] | None,
    material_asset_ids: list[str],
) -> dict[str, Any]:
    """Create a classified parent rule and materialize its first task instance."""
    if due_at.tzinfo is None or due_at.utcoffset() is None:
        raise EducationTaskError("due_at must include a timezone")
    if frequency not in {"once", "daily", "weekdays", "weekly"}:
        raise EducationTaskError("Task frequency is invalid")
    _validate_practice_source(type_code=type_code, practice_source_code=practice_source_code)
    normalized_weekdays = _normalize_weekdays(frequency=frequency, weekdays=weekdays)

    context = await get_household_context_for_parent(parent_user_id)
    if not context:
        raise EducationTaskPermissionError("Only a parent can create homework tasks")
    household_id = str(context["household_id"])
    assignment = await get_task_creation_context(
        household_id=household_id,
        assigned_student_id=assigned_student_id,
        subject_code=subject_code,
        type_code=type_code,
        practice_source_code=practice_source_code,
    )
    if not assignment or not assignment["student_exists"]:
        raise EducationTaskPermissionError("The assigned student must belong to the household")
    if not assignment["grade_code"]:
        raise EducationTaskError("The assigned student must have a current grade")
    if not assignment["subject_type_is_valid"]:
        raise EducationTaskError("The subject and homework type combination is invalid")
    if type_code == "practice" and not assignment["practice_source_is_valid"]:
        raise EducationTaskError("The practice source is invalid")

    timezone_name = context["timezone"]
    local_due = due_at.astimezone(ZoneInfo(timezone_name))
    if (
        frequency == "weekly"
        and normalized_weekdays is not None
        and str(local_due.isoweekday()) not in normalized_weekdays
    ):
        raise EducationTaskError("The initial due date must be one of the selected weekly weekdays")
    recurrence: dict[str, Any] = {
        "frequency": frequency,
        "start_date": local_due.date().isoformat(),
        "due_time": local_due.timetz().replace(tzinfo=None).isoformat(timespec="minutes"),
    }
    if normalized_weekdays is not None:
        recurrence["weekdays"] = normalized_weekdays
    try:
        return await create_task_rule_and_instance(
            parent_user_id=parent_user_id,
            household_id=household_id,
            assigned_student_id=assigned_student_id,
            title=_required_text(title, "title"),
            description=description.strip(),
            recurrence=recurrence,
            timezone_name=timezone_name,
            occurrence_date=local_due.date(),
            due_at=local_due,
            subject_code=subject_code,
            type_code=type_code,
            practice_source_code=practice_source_code,
            grade_code=assignment["grade_code"],
            material_asset_ids=material_asset_ids,
        )
    except ValueError as exc:
        if asset_error := _task_asset_error(exc):
            raise asset_error from exc
        raise


async def _require_student(student_user_id: str) -> None:
    member = await get_membership_for_user(student_user_id)
    if not member or member["role"] != "student":
        raise EducationTaskPermissionError("Only the assigned student can submit homework")


async def check_in_task(
    *, student_user_id: str, task_id: str, submission_text: str,
    idempotency_key: str | None, asset_ids: list[str],
) -> dict[str, Any]:
    """Record an initial optional submission and permanently complete the task."""
    await _require_student(student_user_id)
    try:
        submission = await check_in_task_record(
            task_id=task_id,
            student_user_id=student_user_id,
            submission_text=submission_text.strip(),
            idempotency_key=idempotency_key,
            asset_ids=asset_ids,
        )
    except ValueError as exc:
        if asset_error := _task_asset_error(exc):
            raise asset_error from exc
        raise EducationTaskTransitionError(str(exc)) from exc
    if not submission:
        raise EducationTaskNotFoundError("Homework task not found")
    return submission


async def submit_task(
    *, student_user_id: str, task_id: str, submission_text: str,
    idempotency_key: str | None, asset_ids: list[str],
) -> dict[str, Any]:
    """Compatibility name for the original first-submission endpoint."""
    return await check_in_task(
        student_user_id=student_user_id,
        task_id=task_id,
        submission_text=submission_text,
        idempotency_key=idempotency_key,
        asset_ids=asset_ids,
    )


async def append_revision_submission(
    *, student_user_id: str, task_id: str, submission_text: str,
    idempotency_key: str | None, asset_ids: list[str],
) -> dict[str, Any]:
    """Append a meaningful revision after check-in without altering completion."""
    if not submission_text.strip() and not asset_ids:
        raise EducationTaskError("A revision needs text or at least one attachment")
    await _require_student(student_user_id)
    try:
        submission = await append_revision_submission_record(
            task_id=task_id,
            student_user_id=student_user_id,
            submission_text=submission_text.strip(),
            idempotency_key=idempotency_key,
            asset_ids=asset_ids,
        )
    except ValueError as exc:
        if asset_error := _task_asset_error(exc):
            raise asset_error from exc
        raise EducationTaskTransitionError(str(exc)) from exc
    if not submission:
        raise EducationTaskNotFoundError("Homework task not found")
    return submission


async def review_task(
    *, parent_user_id: str, task_id: str, feedback_text: str, decision: str
) -> dict[str, Any]:
    """Append parent feedback without changing the completed task state."""
    if decision not in {"feedback", "revision_requested"}:
        raise EducationTaskError("Review decision is invalid")
    if not await get_household_context_for_parent(parent_user_id):
        raise EducationTaskPermissionError("Only a parent can review homework")
    try:
        review = await review_task_record(
            task_id=task_id,
            parent_user_id=parent_user_id,
            feedback_text=_required_text(feedback_text, "feedback"),
            decision=decision,
        )
    except ValueError as exc:
        raise EducationTaskTransitionError(str(exc)) from exc
    if not review:
        raise EducationTaskNotFoundError("Homework task not found")
    return review


async def cancel_task(*, parent_user_id: str, task_id: str) -> dict[str, Any]:
    """Allow a household parent to cancel an open materialized instance only."""
    if not await get_household_context_for_parent(parent_user_id):
        raise EducationTaskPermissionError("Only a parent can cancel homework")
    task = await cancel_task_record(task_id=task_id, parent_user_id=parent_user_id)
    if not task:
        raise EducationTaskNotFoundError("Homework task not found or cannot be cancelled")
    return task


async def stop_task_rule(*, parent_user_id: str, task_rule_id: str) -> None:
    """Stop future recurrence while preserving every existing task and review."""
    if not await get_household_context_for_parent(parent_user_id):
        raise EducationTaskPermissionError("Only a parent can stop homework rules")
    if not await stop_task_rule_record(task_rule_id=task_rule_id, parent_user_id=parent_user_id):
        raise EducationTaskNotFoundError("Homework rule not found or already stopped")


def _asset_download_endpoint(asset_id: str) -> str:
    """Reference the existing scoped download route without exposing object storage."""
    return f"/api/v1/education/assets/{asset_id}/download"


def _detail_asset(asset: dict[str, Any]) -> dict[str, Any]:
    return {
        **asset,
        "download_endpoint": _asset_download_endpoint(str(asset["asset_id"])),
    }


async def get_task_detail(*, user_id: str, task_id: str) -> dict[str, Any]:
    """Read a task and append-only submission timeline within its role boundary."""
    detail = await get_task_detail_for_user(task_id=task_id, user_id=user_id)
    if not detail:
        raise EducationTaskNotFoundError("Homework task not found")
    detail["parent_materials"] = [
        _detail_asset(asset) for asset in detail["parent_materials"]
    ]
    for submission in detail["submissions"]:
        submission["assets"] = [
            _detail_asset(asset) for asset in submission["assets"]
        ]
    return detail


async def list_tasks(user_id: str) -> list[dict[str, Any]]:
    """Materialize visible recurring rules in each household timezone, then list tasks."""
    for rule in await list_active_rule_timezones_for_user(user_id):
        local_today = datetime.now(ZoneInfo(rule["timezone"])).date()
        await materialize_task_rule_through(
            task_rule_id=str(rule["task_rule_id"]), through_date=local_today
        )
    return await list_task_records(user_id)


def _validate_calendar_range(*, start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise EducationTaskError("end_date must not be before start_date")
    if (end_date - start_date).days >= _MAX_CALENDAR_RANGE_DAYS:
        raise EducationTaskError("Calendar date range cannot exceed 62 days")


def _validate_calendar_horizon(*, end_date: date, local_today: date) -> None:
    if end_date > local_today + timedelta(days=_MAX_CALENDAR_FUTURE_DAYS):
        raise EducationTaskError("Calendar end_date cannot be more than 12 months ahead")


def _calendar_materialization_windows(
    *, start_date: date, end_date: date, week_start: date, week_end: date,
) -> list[tuple[date, date]]:
    """Merge calendar and current-stat windows without bridging long gaps."""
    windows = sorted(((start_date, end_date), (week_start, week_end)))
    merged: list[tuple[date, date]] = []
    for window_start, window_end in windows:
        if merged and window_start <= merged[-1][1] + timedelta(days=1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], window_end))
        else:
            merged.append((window_start, window_end))
    return merged


async def _resolve_calendar_student_scope(
    *, user_id: str, student_id: str | None,
) -> tuple[dict[str, Any], str | None]:
    context = await get_calendar_context_for_user(user_id)
    if not context:
        raise EducationTaskPermissionError("Only household members can view homework calendars")

    role = context["role"]
    household_id = str(context["household_id"])
    if role == "student":
        if student_id is not None and student_id != user_id:
            raise EducationTaskPermissionError("Students can only view their own homework calendar")
        return context, user_id
    if role != "parent":
        raise EducationTaskPermissionError("Only household members can view homework calendars")
    if student_id is not None and not await is_student_in_household(
        household_id=household_id, user_id=student_id
    ):
        # Do not reveal whether a student exists outside the parent's household.
        raise EducationTaskNotFoundError("Student account not found")
    return context, student_id


async def get_task_calendar(
    *, user_id: str, start_date: date, end_date: date, student_id: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return a bounded, role-scoped calendar and progress summary.

    Parents may narrow to one same-household student, or omit the student for a
    household overview. Students always receive only their own tasks. ``now``
    is injectable to preserve deterministic timezone and overdue tests.
    """
    _validate_calendar_range(start_date=start_date, end_date=end_date)
    context, assigned_student_id = await _resolve_calendar_student_scope(
        user_id=user_id, student_id=student_id
    )
    timezone = ZoneInfo(context["timezone"])
    current_time = now or datetime.now(timezone)
    if current_time.tzinfo is None or current_time.utcoffset() is None:
        raise EducationTaskError("Calendar clock must include a timezone")
    local_today = current_time.astimezone(timezone).date()
    week_start = local_today - timedelta(days=local_today.isoweekday() - 1)
    week_end = week_start + timedelta(days=6)
    _validate_calendar_horizon(end_date=end_date, local_today=local_today)
    materialization_windows = _calendar_materialization_windows(
        start_date=start_date,
        end_date=end_date,
        week_start=week_start,
        week_end=week_end,
    )

    for rule in await list_active_rule_timezones_for_user(user_id):
        if assigned_student_id is None or rule.get("assigned_student_id") == assigned_student_id:
            for materialization_start, materialization_end in materialization_windows:
                await materialize_task_rule_through(
                    task_rule_id=str(rule["task_rule_id"]),
                    from_date=materialization_start,
                    through_date=materialization_end,
                )

    household_id = str(context["household_id"])
    task_records = await list_calendar_task_records(
        household_id=household_id,
        assigned_student_id=assigned_student_id,
        start_date=start_date,
        end_date=end_date,
    )
    progress = await get_calendar_progress_counts(
        household_id=household_id,
        assigned_student_id=assigned_student_id,
        today=local_today,
        week_start=week_start,
        week_end=week_end,
        start_date=start_date,
        end_date=end_date,
        now=current_time,
    )

    tasks_by_date: dict[date, list[dict[str, Any]]] = {}
    for task in task_records:
        is_overdue = task["status"] == "open" and task["due_at"] < current_time
        tasks_by_date.setdefault(task["occurrence_date"], []).append(
            {
                **task,
                "is_completed": task["status"] == "completed",
                "is_overdue": is_overdue,
            }
        )

    days: list[dict[str, Any]] = []
    day = start_date
    while day <= end_date:
        tasks = tasks_by_date.get(day, [])
        days.append(
            {
                "date": day,
                "task_count": len(tasks),
                "completed_count": sum(task["is_completed"] for task in tasks),
                "overdue_count": sum(task["is_overdue"] for task in tasks),
                "tasks": tasks,
            }
        )
        day += timedelta(days=1)
    return {
        "student_id": assigned_student_id,
        "start_date": start_date,
        "end_date": end_date,
        "days": days,
        "stats": progress,
    }
