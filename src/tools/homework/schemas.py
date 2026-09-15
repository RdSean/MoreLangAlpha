"""Contract for the homework tools: the arguments they take, the payload they
return.

This module is the single source of truth for a shape that crosses to the
frontend. ``scripts/contracts/export_schemas.py`` publishes it as JSON Schema,
``web/scripts/generate-contracts.mjs`` turns that into zod, and the chat card
validates the artifact against it before rendering. Change a field here and the
frontend cannot silently disagree — the drift tests fail instead.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from src.server.app.education.models import (
    EducationCalendarDayResponse,
    EducationCalendarStatsResponse,
)

HomeworkScheduleWindow = Literal[
    "today",
    "tomorrow",
    "this_week",
    "next_week",
    "last_week",
    "2w",
    "1m",
]
"""The periods the tool can resolve on its own.

Chosen to cover how the question is actually asked — "今天有什么作业", "上周的"
— rather than exposing a date-picker vocabulary. Week values are resolved in the
household's timezone using the same `isoweekday` convention the calendar API
already uses for its "this week" statistics, so the tool and the dashboard
cannot disagree about where a week starts.
"""

MAX_RANGE_DAYS = 62
"""Mirrors the ceiling the calendar API enforces.

Checked here as well so the model gets a readable validation message instead of
a downstream request failure it cannot interpret.
"""


class HomeworkScheduleArgs(BaseModel):
    """What the model may ask for.

    Either name a period (``window``) or give an explicit range (``start_date``
    plus ``end_date``). An explicit range wins when both are supplied: the model
    that bothered to work out dates meant them.
    """

    window: HomeworkScheduleWindow = Field(
        default="2w",
        description=(
            "Which period to look at. Use 'today' for what is due today, "
            "'last_week' or 'next_week' for those weeks, 'this_week' for the "
            "current week, or '2w'/'1m' for a longer look ahead."
        ),
    )
    start_date: date | None = Field(
        default=None,
        description="First day of an explicit range; supply together with end_date.",
    )
    end_date: date | None = Field(
        default=None,
        description="Last day of an explicit range; supply together with start_date.",
    )

    @model_validator(mode="after")
    def _check_range(self) -> HomeworkScheduleArgs:
        if (self.start_date is None) != (self.end_date is None):
            raise ValueError("start_date and end_date must be supplied together")
        if self.start_date is None or self.end_date is None:
            return self
        if self.end_date < self.start_date:
            raise ValueError("end_date must not be before start_date")
        span = (self.end_date - self.start_date).days
        if span >= MAX_RANGE_DAYS:
            raise ValueError(
                f"range cannot exceed {MAX_RANGE_DAYS} days; ask for a shorter period"
            )
        return self


class HomeworkScheduleArtifact(BaseModel):
    """The payload the chat card renders.

    It reuses the calendar API's own day, task and stats models rather than
    restating them, so the artifact and the dashboard widget describe the same
    payload — one generated contract covers both.

    It is deliberately self-contained: ``student_names`` and ``timezone`` are
    resolved by the tool because a chat artifact cannot make a second request,
    whereas the dashboard widget fetches the member list separately. That
    difference is the reason the two components are copies rather than one
    shared component.
    """

    type: Literal["homework_schedule"] = "homework_schedule"
    """Discriminator the frontend dispatches on. Kept to a literal so the
    generated schema carries a `const`, not a free string."""

    window: str | None = Field(
        default=None,
        description="The named period that produced this range, when one was used.",
    )
    start_date: date
    end_date: date
    timezone: str = Field(description="Household timezone, for rendering times.")
    stats: EducationCalendarStatsResponse
    days: list[EducationCalendarDayResponse]
    student_names: dict[str, str] = Field(
        default_factory=dict,
        description="assigned_student_id to display name, for the ids present in days.",
    )
