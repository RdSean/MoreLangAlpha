"""Homework task state-machine rules and education-domain orchestration."""

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.server.database.education_members import get_membership_for_user
from src.server.database.education_tasks import (
    cancel_task as cancel_task_record,
    create_task_rule_and_instance,
    get_household_context_for_parent,
    is_student_in_household,
    list_active_rule_timezones_for_user,
    list_tasks_for_user as list_task_records,
    materialize_task_rule_through,
    review_task as review_task_record,
    stop_task_rule as stop_task_rule_record,
    submit_task as submit_task_record,
)

_VALID_TRANSITIONS = {
    ("open", "submitted"),
    ("submitted", "revision_requested"),
    ("submitted", "completed"),
    ("revision_requested", "submitted"),
}


class EducationTaskError(RuntimeError):
    """Base exception for education homework operations."""


class EducationTaskTransitionError(EducationTaskError, ValueError):
    """A requested task status change is outside the settled workflow."""


def assert_task_transition(*, current: str, target: str) -> None:
    """Raise unless the homework task follows the allowed review workflow."""
    if (current, target) not in _VALID_TRANSITIONS:
        raise EducationTaskTransitionError(
            f"Cannot transition education task from {current} to {target}"
        )


class EducationTaskPermissionError(EducationTaskError, PermissionError):
    """The caller is not allowed to perform this homework operation."""


class EducationTaskNotFoundError(EducationTaskError, LookupError):
    """The requested task is absent or outside the caller's household scope."""


def _required_text(value: str, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise EducationTaskError(f"{field} is required")
    return normalized


async def create_task(
    *, parent_user_id: str, assigned_student_id: str, title: str,
    description: str, due_at: datetime, frequency: str, material_asset_ids: list[str],
) -> dict[str, Any]:
    """Create a parent-owned rule and materialize its first homework instance."""
    if due_at.tzinfo is None or due_at.utcoffset() is None:
        raise EducationTaskError("due_at must include a timezone")
    context = await get_household_context_for_parent(parent_user_id)
    if not context:
        raise EducationTaskPermissionError("Only a parent can create homework tasks")
    household_id = str(context["household_id"])
    if not await is_student_in_household(household_id=household_id, user_id=assigned_student_id):
        raise EducationTaskPermissionError("The assigned student must belong to the household")
    if frequency not in {"once", "daily"}:
        raise EducationTaskError("Task frequency must be once or daily")
    timezone_name = context["timezone"]
    local_due = due_at.astimezone(ZoneInfo(timezone_name))
    recurrence = {
        "frequency": frequency,
        "start_date": local_due.date().isoformat(),
        "due_time": local_due.timetz().replace(tzinfo=None).isoformat(timespec="minutes"),
    }
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
        material_asset_ids=material_asset_ids,
    )


async def submit_task(
    *, student_user_id: str, task_id: str, submission_text: str,
    idempotency_key: str | None, asset_ids: list[str],
) -> dict[str, Any]:
    """Append an immutable submission from the task's assigned student only."""
    member = await get_membership_for_user(student_user_id)
    if not member or member["role"] != "student":
        raise EducationTaskPermissionError("Only the assigned student can submit homework")
    try:
        submission = await submit_task_record(
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
    """Persist a plain-text parent review for the latest immutable submission."""
    if decision not in {"revision_requested", "completed"}:
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
    """Allow a household parent to cancel an active materialized instance."""
    if not await get_household_context_for_parent(parent_user_id):
        raise EducationTaskPermissionError("Only a parent can cancel homework")
    task = await cancel_task_record(task_id=task_id, parent_user_id=parent_user_id)
    if not task:
        raise EducationTaskNotFoundError("Homework task not found or cannot be cancelled")
    return task


async def stop_task_rule(*, parent_user_id: str, task_rule_id: str) -> None:
    """Stop future recurrence while preserving every existing instance and review."""
    if not await get_household_context_for_parent(parent_user_id):
        raise EducationTaskPermissionError("Only a parent can stop homework rules")
    if not await stop_task_rule_record(task_rule_id=task_rule_id, parent_user_id=parent_user_id):
        raise EducationTaskNotFoundError("Homework rule not found or already stopped")


async def list_tasks(user_id: str) -> list[dict[str, Any]]:
    """Materialize visible daily rules in each household timezone, then list tasks."""
    for rule in await list_active_rule_timezones_for_user(user_id):
        local_today = datetime.now(ZoneInfo(rule["timezone"])).date()
        await materialize_task_rule_through(
            task_rule_id=str(rule["task_rule_id"]), through_date=local_today
        )
    return await list_task_records(user_id)
