"""Homework completion, recurrence, and household authorization rules."""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.server.database.education_members import get_membership_for_user
from src.server.database.education_tasks import (
    append_revision_submission as append_revision_submission_record,
    cancel_task as cancel_task_record,
    check_in_task as check_in_task_record,
    create_task_rule_and_instance,
    get_household_context_for_parent,
    get_task_creation_context,
    list_active_rule_timezones_for_user,
    list_tasks_for_user as list_task_records,
    materialize_task_rule_through,
    review_task as review_task_record,
    stop_task_rule as stop_task_rule_record,
)


class EducationTaskError(RuntimeError):
    """Base exception for education homework operations."""


class EducationTaskTransitionError(EducationTaskError, ValueError):
    """A requested homework operation is invalid for the current task state."""


class EducationTaskPermissionError(EducationTaskError, PermissionError):
    """The caller is not allowed to perform this homework operation."""


class EducationTaskNotFoundError(EducationTaskError, LookupError):
    """The requested task is absent or outside the caller's household scope."""


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
    recurrence: dict[str, Any] = {
        "frequency": frequency,
        "start_date": local_due.date().isoformat(),
        "due_time": local_due.timetz().replace(tzinfo=None).isoformat(timespec="minutes"),
    }
    if normalized_weekdays is not None:
        recurrence["weekdays"] = normalized_weekdays
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


async def list_tasks(user_id: str) -> list[dict[str, Any]]:
    """Materialize visible recurring rules in each household timezone, then list tasks."""
    for rule in await list_active_rule_timezones_for_user(user_id):
        local_today = datetime.now(ZoneInfo(rule["timezone"])).date()
        await materialize_task_rule_through(
            task_rule_id=str(rule["task_rule_id"]), through_date=local_today
        )
    return await list_task_records(user_id)
