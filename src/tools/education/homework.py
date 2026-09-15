"""Native host tool for creating text-only household homework."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID
from zoneinfo import ZoneInfo

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.server.database.education_members import (
    get_membership_for_user,
    list_student_membership_context,
)
from src.server.app.education.models import EducationTaskResponse
from src.server.services.education_tasks import EducationTaskError, create_task
from src.tools.education.schemas import EducationHomeworkArtifact


def _configurable(config: RunnableConfig | dict[str, Any] | None) -> dict[str, Any]:
    """Read the stable caller context attached by the agent runner."""
    if not config:
        return {}
    value = config.get("configurable", {})
    return value if isinstance(value, dict) else {}


def _caller_user_id(config: RunnableConfig | dict[str, Any] | None) -> str:
    user_id = _configurable(config).get("user_id")
    if not user_id:
        raise ValueError("Unable to create homework: authenticated user_id is missing")
    return str(user_id)


def _request_identity(config: RunnableConfig | dict[str, Any] | None) -> str:
    """Use the request/run identity so transport retries share one key."""
    configurable = _configurable(config)
    for key in ("request_id", "run_id", "thread_id"):
        value = configurable.get(key)
        if value:
            return str(value)
    if config:
        for key in ("request_id", "run_id", "thread_id"):
            value = config.get(key)
            if value:
                return str(value)
    # A deterministic fallback still protects a retry when the caller does
    # not provide an execution identifier. Household/parent scoping in the
    # persistence layer prevents this key crossing an authorization boundary.
    return "unidentified-request"


def _normalized_name(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def _resolve_student(
    students: list[dict[str, Any]], requested_name: str
) -> dict[str, Any]:
    normalized = _normalized_name(requested_name)
    if not normalized:
        raise ValueError("A student name is required")
    matches = [
        student
        for student in students
        if _normalized_name(str(student.get("display_name") or "")) == normalized
    ]
    if len(matches) == 1:
        return matches[0]
    available = [
        str(student["display_name"])
        for student in students
        if student.get("display_name")
    ]
    if len(matches) > 1:
        suffix = f" Available students: {', '.join(available)}." if available else ""
        raise ValueError(f"student name is ambiguous; please choose one.{suffix}")
    suffix = f" Available students: {', '.join(available)}." if available else ""
    raise ValueError(f"student '{requested_name.strip()}' was not found in your household.{suffix}")


def _parse_due_at(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip())
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError("due_at must be a valid ISO 8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("due_at must include a timezone offset")
    return parsed


def _idempotency_key(
    *,
    config: RunnableConfig | dict[str, Any] | None,
    student_id: str,
    title: str,
    description: str,
    due_at: datetime,
    subject_code: str,
    type_code: str,
    practice_source_code: str | None,
    frequency: str,
    weekdays: list[int] | None,
) -> str:
    payload = {
        "request": _request_identity(config),
        "student_id": student_id,
        "title": title,
        "description": description,
        "due_at": due_at.isoformat(),
        "subject_code": subject_code,
        "type_code": type_code,
        "practice_source_code": practice_source_code,
        "frequency": frequency,
        "weekdays": sorted(weekdays) if weekdays else None,
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    # ``education_task_rules.idempotency_key`` is a UUID column. UUID5-style
    # bytes retain deterministic retry semantics while fitting that schema.
    digest = hashlib.sha256(encoded.encode()).digest()[:16]
    return str(UUID(bytes=digest, version=5))


def _json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if hasattr(value, "hex"):
        return str(value)
    return value


async def _create_homework_impl(
    config: RunnableConfig,
    student_name: Annotated[str, "Display name of the student in the parent's household."],
    title: Annotated[str, "Short homework title."],
    description: Annotated[str, "Text instructions for the student."],
    due_at: Annotated[str, "ISO 8601 due timestamp with an explicit timezone offset."],
    subject_code: Annotated[str, "Stable education subject dictionary code."],
    type_code: Annotated[str, "Stable homework type dictionary code."],
    frequency: Annotated[str, "once, daily, weekdays, or weekly."] = "once",
    weekdays: Annotated[list[int] | None, "ISO weekdays 1-7, required only for weekly tasks."] = None,
    practice_source_code: Annotated[
        str | None, "Practice source code (schoolwork or homework) for practice tasks."
    ] = None,
) -> tuple[str, dict[str, Any]]:
    """Create one text homework task for a child in the caller's household.

    The caller must be a household parent. Attachments are intentionally not
    accepted in this first version; use the education page for asset workflows.
    """
    caller_id = _caller_user_id(config)
    membership = await get_membership_for_user(caller_id)
    if not membership or membership.get("role") != "parent":
        raise ValueError("Only a household parent can create homework")

    students = await list_student_membership_context(str(membership["household_id"]))
    student = _resolve_student(students, student_name)
    normalized_title = title.strip()
    if not normalized_title:
        raise ValueError("title is required")
    normalized_description = description.strip()
    parsed_due_at = _parse_due_at(due_at)
    normalized_subject = subject_code.strip()
    normalized_type = type_code.strip()
    normalized_source = practice_source_code.strip() if practice_source_code else None
    if not normalized_subject:
        raise ValueError("subject_code is required")
    if not normalized_type:
        raise ValueError("type_code is required")

    key = _idempotency_key(
        config=config,
        student_id=str(student["user_id"]),
        title=normalized_title,
        description=normalized_description,
        due_at=parsed_due_at,
        subject_code=normalized_subject,
        type_code=normalized_type,
        practice_source_code=normalized_source,
        frequency=frequency,
        weekdays=weekdays,
    )
    try:
        task = await create_task(
            parent_user_id=caller_id,
            assigned_student_id=str(student["user_id"]),
            title=normalized_title,
            description=normalized_description,
            due_at=parsed_due_at,
            subject_code=normalized_subject,
            type_code=normalized_type,
            practice_source_code=normalized_source,
            frequency=frequency,
            weekdays=weekdays,
            material_asset_ids=[],
            idempotency_key=key,
        )
    except EducationTaskError as exc:
        raise ValueError(f"Unable to create homework: {exc}") from exc

    raw_result = dict(task)
    result = _json_safe(raw_result)
    task_id = str(result.get("task_id", ""))
    due_value = raw_result.get("due_at")
    if isinstance(due_value, datetime):
        timezone_name = str(membership.get("timezone") or "UTC")
        local_due = due_value.astimezone(ZoneInfo(timezone_name)).isoformat()
    else:
        local_due = parsed_due_at.astimezone(
            ZoneInfo(str(membership.get("timezone") or "UTC"))
        ).isoformat()
    response = {
        "success": True,
        "task_id": task_id,
        "student_name": str(student.get("display_name") or student_name.strip()),
        "due_at": local_due,
        "destination": "/education",
        "attachments_supported": False,
    }
    artifact = EducationHomeworkArtifact(
        **response,
        task=EducationTaskResponse.model_validate(result),
    ).model_dump(mode="json")
    content = json.dumps(response, ensure_ascii=False)
    return content, artifact


@tool(response_format="content_and_artifact")
async def education_create_homework(
    config: RunnableConfig,
    student_name: Annotated[str, "Display name of the student in the parent's household."],
    title: Annotated[str, "Short homework title."],
    description: Annotated[str, "Text instructions for the student."],
    due_at: Annotated[str, "ISO 8601 due timestamp with an explicit timezone offset."],
    subject_code: Annotated[str, "Stable education subject dictionary code."],
    type_code: Annotated[str, "Stable homework type dictionary code."],
    frequency: Annotated[str, "once, daily, weekdays, or weekly."] = "once",
    weekdays: Annotated[list[int] | None, "ISO weekdays 1-7, required only for weekly tasks."] = None,
    practice_source_code: Annotated[
        str | None, "Practice source code (schoolwork or homework) for practice tasks."
    ] = None,
) -> tuple[str, dict[str, Any]]:
    """Create a text homework task for a child in the caller's household."""
    try:
        return await _create_homework_impl(
            config=config,
            student_name=student_name,
            title=title,
            description=description,
            due_at=due_at,
            subject_code=subject_code,
            type_code=type_code,
            frequency=frequency,
            weekdays=weekdays,
            practice_source_code=practice_source_code,
        )
    except (EducationTaskError, ValueError) as exc:
        message = str(exc)
        return json.dumps({"success": False, "error": message}, ensure_ascii=False), {}
