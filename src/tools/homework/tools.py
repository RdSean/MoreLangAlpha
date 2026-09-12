"""The agent-facing homework schedule tool.

Read-only: it resolves a period, asks the education service for the household's
tasks in that period, and returns a compact digest for the model plus a
self-contained artifact for the chat card.

It deliberately contains no query of its own — ``get_task_calendar`` already
resolves the caller's household and narrows a student to their own tasks, and a
second implementation of that scoping is exactly how two surfaces start
disagreeing.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from src.server.database.education_members import (
    get_household_membership_context,
    list_household_membership_context,
)
from src.server.services.education_tasks import get_task_calendar
from src.tools.homework.schemas import HomeworkScheduleArgs, HomeworkScheduleArtifact

MAX_CONTENT_TASKS = 40
"""How many tasks the prose digest may list.

The artifact carries everything — the card renders it. The content is what
lands in the model's context, and a month's schedule can run to dozens of rows,
so it is capped with an explicit remainder rather than silently truncated.
"""

_WINDOW_DAYS_AHEAD = {"2w": 13, "1m": 30}


def _get_user_id(config: RunnableConfig) -> str:
    user_id = (config.get("configurable") or {}).get("user_id")
    if not user_id:
        raise ValueError("user_id not found in config.")
    return str(user_id)


def _resolve_range(args: HomeworkScheduleArgs, *, today: date) -> tuple[date, date]:
    """Turn a named period (or an explicit pair) into inclusive dates.

    Week values use ISO weekdays so "this week" means the same Monday-to-Sunday
    window the calendar API's own week statistics use. Without that, the tool
    and the dashboard could report different "this week" counts for the same
    day and both be right about different questions.
    """
    if args.start_date is not None and args.end_date is not None:
        return args.start_date, args.end_date

    window = args.window
    if window == "today":
        return today, today
    if window == "tomorrow":
        tomorrow = today + timedelta(days=1)
        return tomorrow, tomorrow

    monday = today - timedelta(days=today.isoweekday() - 1)
    sunday = monday + timedelta(days=6)
    if window == "this_week":
        return monday, sunday
    if window == "next_week":
        return monday + timedelta(days=7), sunday + timedelta(days=7)
    if window == "last_week":
        return monday - timedelta(days=7), sunday - timedelta(days=7)

    return today, today + timedelta(days=_WINDOW_DAYS_AHEAD[window])


def _due_clock(value: Any) -> str:
    if not isinstance(value, datetime):
        return ""
    return value.strftime("%H:%M")


def _summarize(
    *,
    days: list[dict[str, Any]],
    stats: dict[str, Any],
    start: date,
    end: date,
    timezone_name: str,
    names: dict[str, str],
) -> str:
    """A compact markdown digest for the model, capped at MAX_CONTENT_TASKS."""
    header = (
        f"Homework schedule: {start.isoformat()} to {end.isoformat()} ({timezone_name})"
    )
    counts = (
        f"today {stats.get('today_count', 0)} · this week "
        f"{stats.get('week_count', 0)} · overdue {stats.get('overdue_count', 0)} · "
        f"done {stats.get('completed_count', 0)}"
    )

    lines: list[str] = [header, counts, ""]
    listed = 0
    remaining = 0

    for day in days:
        tasks = day.get("tasks") or []
        if not tasks:
            continue
        rendered: list[str] = []
        for task in tasks:
            if listed >= MAX_CONTENT_TASKS:
                remaining += 1
                continue
            listed += 1
            parts = [str(task.get("title", "")).strip()]
            name = names.get(str(task.get("assigned_student_id", "")))
            if name:
                parts.append(name)
            clock = _due_clock(task.get("due_at"))
            if clock:
                parts.append(clock)
            if task.get("is_overdue"):
                parts.append("overdue")
            elif task.get("is_completed"):
                parts.append("done")
            rendered.append("- " + " · ".join(part for part in parts if part))
        if rendered:
            lines.append(f"### {day['date'].isoformat()}")
            lines.extend(rendered)
            lines.append("")

    if remaining:
        lines.append(f"({remaining} more not listed; see the schedule card)")
    if listed == 0:
        lines.append("No homework is due in this period.")

    return "\n".join(lines).strip()


async def _build_schedule(
    *, user_id: str, args: HomeworkScheduleArgs, now: datetime | None = None
) -> tuple[str, dict[str, Any]]:
    """Resolve, fetch, and shape one schedule. Returns ``(content, artifact)``."""
    if not user_id:
        raise ValueError("user_id not found in config.")

    membership = await get_household_membership_context(user_id)
    if not membership:
        raise ValueError(
            "This account is not part of a household, so it has no homework schedule."
        )
    timezone_name = membership.get("timezone") or "UTC"
    household_id = str(membership["household_id"])

    local_now = (
        now.astimezone(ZoneInfo(timezone_name))
        if now
        else datetime.now(ZoneInfo(timezone_name))
    )
    start, end = _resolve_range(args, today=local_now.date())

    calendar = await get_task_calendar(user_id=user_id, start_date=start, end_date=end)

    # Names travel with the payload: the card cannot make a second request the
    # way the dashboard widget does.
    members = await list_household_membership_context(household_id)
    names = {
        str(member["user_id"]): str(member.get("display_name") or "")
        for member in members
        if member.get("role") == "student"
    }

    artifact = HomeworkScheduleArtifact(
        window=None if args.start_date else args.window,
        start_date=calendar["start_date"],
        end_date=calendar["end_date"],
        timezone=timezone_name,
        stats=calendar["stats"],
        days=calendar["days"],
        student_names=names,
    )
    artifact_payload = artifact.model_dump(mode="json")

    content = _summarize(
        days=calendar["days"],
        stats=calendar["stats"],
        start=calendar["start_date"],
        end=calendar["end_date"],
        timezone_name=timezone_name,
        names=names,
    )
    return content, artifact_payload


@tool(
    "get_homework_schedule",
    args_schema=HomeworkScheduleArgs,
    response_format="content_and_artifact",
)
async def get_homework_schedule(
    window: str = "2w",
    start_date: date | None = None,
    end_date: date | None = None,
    config: RunnableConfig = None,  # type: ignore[assignment]
) -> tuple[str, dict[str, Any]]:
    """Look up this household's homework for a period.

    Use this whenever the user asks what homework is due — today, this week,
    next week, last week, or an explicit date range. Returns a schedule card
    the user can read, and a short digest for you to summarise or reason over.

    Args:
        window: Which period to look at. One of today, tomorrow, this_week,
            next_week, last_week, 2w (default), 1m.
        start_date: First day of an explicit range; supply with end_date.
        end_date: Last day of an explicit range; supply with start_date.
    """
    args = HomeworkScheduleArgs(
        window=window,
        start_date=start_date,
        end_date=end_date,  # type: ignore[arg-type]
    )
    return await _build_schedule(user_id=_get_user_id(config or {}), args=args)
