"""The artifact envelope and tool arguments are the contract's backend half.

The frontend consumes the exported JSON Schema, so anything asserted here about
the shape is what the generated zod will enforce on the other side.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from scripts.contracts.export_schemas import build_schemas
from src.server.app.education.models import EducationCalendarStatsResponse
from src.tools.homework.schemas import (
    MAX_RANGE_DAYS,
    HomeworkScheduleArgs,
    HomeworkScheduleArtifact,
)


def _stats() -> EducationCalendarStatsResponse:
    return EducationCalendarStatsResponse(
        today_count=0, week_count=0, overdue_count=0, completed_count=0
    )


def _artifact(**overrides: object) -> HomeworkScheduleArtifact:
    fields: dict[str, object] = {
        "window": "2w",
        "start_date": date(2026, 9, 12),
        "end_date": date(2026, 9, 25),
        "timezone": "Asia/Tokyo",
        "stats": _stats(),
        "days": [],
        "student_names": {},
    }
    fields.update(overrides)
    return HomeworkScheduleArtifact(**fields)  # type: ignore[arg-type]


class TestArtifactSchema:
    def test_is_published_as_a_contract(self) -> None:
        schema = build_schemas()["web/src/contracts/homework-schedule.schema.json"]
        assert schema["properties"]["type"]["const"] == "homework_schedule"
        assert "student_names" in schema["properties"]
        # The envelope reuses the calendar's own models rather than restating
        # them — that reuse is what makes the chat card and the dashboard widget
        # describe the same payload.
        assert "EducationCalendarDayResponse" in schema.get("$defs", {})

    def test_defaults_its_discriminator(self) -> None:
        assert _artifact().type == "homework_schedule"

    def test_round_trips_through_the_wire_shape(self) -> None:
        artifact = _artifact()
        restored = HomeworkScheduleArtifact.model_validate(
            artifact.model_dump(mode="json")
        )
        assert restored == artifact

    def test_carries_child_names_so_the_client_never_fetches(self) -> None:
        # A chat artifact cannot make a second request; the names it renders
        # have to arrive with it.
        artifact = _artifact(student_names={"student-1": "henry"})
        assert artifact.model_dump(mode="json")["student_names"] == {
            "student-1": "henry"
        }

    def test_requires_the_range_and_the_timezone(self) -> None:
        for missing in ("start_date", "end_date", "timezone", "stats", "days"):
            fields = {
                "window": "2w",
                "start_date": date(2026, 9, 12),
                "end_date": date(2026, 9, 25),
                "timezone": "Asia/Tokyo",
                "stats": _stats(),
                "days": [],
                "student_names": {},
            }
            fields.pop(missing)
            with pytest.raises(ValidationError):
                HomeworkScheduleArtifact(**fields)  # type: ignore[arg-type]


class TestArguments:
    def test_defaults_to_a_two_week_window(self) -> None:
        assert HomeworkScheduleArgs().window == "2w"

    def test_accepts_an_explicit_range(self) -> None:
        args = HomeworkScheduleArgs(
            start_date=date(2026, 9, 7), end_date=date(2026, 9, 13)
        )
        assert (args.start_date, args.end_date) == (date(2026, 9, 7), date(2026, 9, 13))

    def test_accepts_every_documented_window(self) -> None:
        for window in (
            "today",
            "tomorrow",
            "this_week",
            "next_week",
            "last_week",
            "2w",
            "1m",
        ):
            assert HomeworkScheduleArgs(window=window).window == window  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "fields",
        [
            {"start_date": date(2026, 9, 7)},
            {"end_date": date(2026, 9, 13)},
        ],
    )
    def test_requires_the_range_to_be_supplied_together(self, fields: dict) -> None:
        with pytest.raises(ValidationError, match="together"):
            HomeworkScheduleArgs(**fields)

    def test_rejects_an_inverted_range(self) -> None:
        with pytest.raises(ValidationError, match="before"):
            HomeworkScheduleArgs(
                start_date=date(2026, 9, 13), end_date=date(2026, 9, 7)
            )

    def test_rejects_a_range_over_the_calendar_ceiling(self) -> None:
        # Mirrors the calendar API's own limit so the model gets a readable
        # message instead of a downstream 400.
        with pytest.raises(ValidationError, match=str(MAX_RANGE_DAYS)):
            HomeworkScheduleArgs(
                start_date=date(2026, 1, 1),
                end_date=date(2026, 1, 1) + timedelta(days=MAX_RANGE_DAYS),
            )

    def test_accepts_a_range_just_under_the_ceiling(self) -> None:
        args = HomeworkScheduleArgs(
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 1) + timedelta(days=MAX_RANGE_DAYS - 1),
        )
        assert args.end_date == date(2026, 3, 3)
