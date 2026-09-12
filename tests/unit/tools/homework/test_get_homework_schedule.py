"""Behaviour of the agent-facing homework schedule tool.

The service layer it delegates to has its own scoping tests; what matters here
is that the tool asks it the right question, presents the answer self-containedly
and keeps the content it hands the model within a readable size.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone as dt_timezone
import uuid
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import pytest

from src.tools.homework import tools as homework_tools
from src.tools.homework.schemas import HomeworkScheduleArgs, HomeworkScheduleArtifact

# Every test in this module drives an async tool.
pytestmark = pytest.mark.asyncio

HOUSEHOLD = "household-1"
STUDENT_ID = "student-1"
PARENT_ID = "parent-1"

# A Wednesday, so every week-boundary assertion has a non-obvious answer.
NOW = datetime(2026, 9, 16, 9, 0, tzinfo=ZoneInfo("Asia/Tokyo"))


def _task(*, day: date, title: str = "语文预习", overdue: bool = False) -> dict:
    return {
        "task_id": str(uuid.uuid4()),
        "task_rule_id": str(uuid.uuid4()),
        "household_id": str(uuid.uuid4()),
        "assigned_student_id": STUDENT_ID,
        "occurrence_date": day,
        "due_at": datetime.combine(
            day, datetime.min.time(), tzinfo=ZoneInfo("Asia/Tokyo")
        )
        + timedelta(hours=19),
        "title": title,
        "description": "",
        "subject_code": "chinese",
        "subject_color": "#D95D39",
        "type_code": "preview",
        "practice_source_code": None,
        "grade_code": "g6",
        "status": "open",
        "completed_at": None,
        "created_at": None,
        "is_completed": False,
        "is_overdue": overdue,
    }


def _calendar(
    start: date, end: date, *, per_day: dict[date, list[dict]] | None = None
) -> dict:
    per_day = per_day or {}
    days = []
    cursor = start
    while cursor <= end:
        tasks = per_day.get(cursor, [])
        days.append(
            {
                "date": cursor,
                "task_count": len(tasks),
                "completed_count": sum(1 for t in tasks if t["is_completed"]),
                "overdue_count": sum(1 for t in tasks if t["is_overdue"]),
                "tasks": tasks,
            }
        )
        cursor += timedelta(days=1)
    return {
        "student_id": None,
        "start_date": start,
        "end_date": end,
        "days": days,
        "stats": {
            "today_count": 0,
            "week_count": 0,
            "overdue_count": 0,
            "completed_count": 0,
        },
    }


@pytest.fixture
def stubbed(monkeypatch):
    """Patch the tool's collaborators and capture the calendar request."""
    captured: dict[str, object] = {"calendar_calls": []}

    monkeypatch.setattr(
        homework_tools,
        "get_household_membership_context",
        AsyncMock(
            return_value={
                "household_id": HOUSEHOLD,
                "user_id": PARENT_ID,
                "role": "parent",
                "display_name": "lee",
                "timezone": "Asia/Tokyo",
            }
        ),
    )
    monkeypatch.setattr(
        homework_tools,
        "list_household_membership_context",
        AsyncMock(
            return_value=[
                {"user_id": PARENT_ID, "role": "parent", "display_name": "lee"},
                {"user_id": STUDENT_ID, "role": "student", "display_name": "henry"},
            ]
        ),
    )

    def fake_calendar(**kwargs):
        captured["calendar_calls"].append(kwargs)
        return _calendar(
            kwargs["start_date"],
            kwargs["end_date"],
            per_day=kwargs.pop("_per_day", None) or captured.get("per_day") or {},
        )

    async def calendar(**kwargs):
        return fake_calendar(**kwargs)

    monkeypatch.setattr(homework_tools, "get_task_calendar", calendar)
    captured["requests"] = lambda: [
        (call["start_date"], call["end_date"]) for call in captured["calendar_calls"]
    ]
    return captured


async def _run(args: HomeworkScheduleArgs, stubbed, *, user_id: str = PARENT_ID):
    return await homework_tools._build_schedule(user_id=user_id, args=args, now=NOW)


class TestRangeResolution:
    @pytest.mark.parametrize(
        ("window", "expected"),
        [
            ("today", (date(2026, 9, 16), date(2026, 9, 16))),
            ("tomorrow", (date(2026, 9, 17), date(2026, 9, 17))),
            # Week boundaries follow the backend's isoweekday convention, so the
            # window starts on Monday — the same week the calendar API's "this
            # week" statistics describe.
            ("this_week", (date(2026, 9, 14), date(2026, 9, 20))),
            ("next_week", (date(2026, 9, 21), date(2026, 9, 27))),
            ("last_week", (date(2026, 9, 7), date(2026, 9, 13))),
            ("2w", (date(2026, 9, 16), date(2026, 9, 29))),
            ("1m", (date(2026, 9, 16), date(2026, 10, 16))),
        ],
    )
    async def test_resolves_each_window_to_exact_dates(
        self, window, expected, stubbed
    ) -> None:
        await _run(HomeworkScheduleArgs(window=window), stubbed)
        assert stubbed["requests"]() == [expected]

    async def test_explicit_range_wins_over_the_window(self, stubbed) -> None:
        await _run(
            HomeworkScheduleArgs(
                window="today",
                start_date=date(2026, 9, 7),
                end_date=date(2026, 9, 13),
            ),
            stubbed,
        )
        assert stubbed["requests"]() == [(date(2026, 9, 7), date(2026, 9, 13))]

    async def test_resolves_in_the_household_timezone(self, stubbed) -> None:
        # 2026-09-16T23:30Z is already the 17th in Tokyo; resolving in UTC would
        # put "today" on the wrong day for half the planet.
        late = datetime(2026, 9, 16, 23, 30, tzinfo=dt_timezone.utc)
        await homework_tools._build_schedule(
            user_id=PARENT_ID, args=HomeworkScheduleArgs(window="today"), now=late
        )
        assert stubbed["requests"]() == [(date(2026, 9, 17), date(2026, 9, 17))]


class TestScoping:
    async def test_asks_the_service_as_the_calling_user(self, stubbed) -> None:
        # The service resolves the household from this id; the tool must not
        # pass anything it worked out itself.
        await _run(
            HomeworkScheduleArgs(window="today"), stubbed, user_id="someone-else"
        )
        assert stubbed["calendar_calls"][0]["user_id"] == "someone-else"

    async def test_requires_a_user_id(self, stubbed) -> None:
        with pytest.raises(ValueError, match="user_id"):
            await homework_tools._build_schedule(
                user_id="", args=HomeworkScheduleArgs(), now=NOW
            )


class TestArtifact:
    async def test_names_every_child_the_payload_mentions(self, stubbed) -> None:
        # The card cannot fetch the member list, so the names have to be here.
        _, artifact = await _run(HomeworkScheduleArgs(window="today"), stubbed)
        assert artifact["student_names"] == {STUDENT_ID: "henry"}

    async def test_carries_the_household_timezone(self, stubbed) -> None:
        _, artifact = await _run(HomeworkScheduleArgs(window="today"), stubbed)
        assert artifact["timezone"] == "Asia/Tokyo"

    async def test_validates_against_the_published_schema(self, stubbed) -> None:
        _, artifact = await _run(HomeworkScheduleArgs(window="2w"), stubbed)
        # Round-trip through the model, the same shape the frontend validates.
        restored = HomeworkScheduleArtifact.model_validate(artifact)
        assert restored.type == "homework_schedule"

    async def test_does_not_carry_a_discriminator_the_client_cannot_switch_on(
        self, stubbed
    ) -> None:
        _, artifact = await _run(HomeworkScheduleArgs(window="today"), stubbed)
        assert artifact["type"] == "homework_schedule"


class TestContent:
    async def test_states_the_range_and_the_counts(self, stubbed) -> None:
        content, _ = await _run(HomeworkScheduleArgs(window="this_week"), stubbed)
        assert "2026-09-14" in content
        assert "2026-09-20" in content
        assert "Asia/Tokyo" in content
        assert "overdue" in content

    async def test_names_the_child_in_a_task_line(self, stubbed) -> None:
        per_day = {date(2026, 9, 16): [_task(day=date(2026, 9, 16))]}
        stubbed["per_day"] = per_day
        content, _ = await _run(HomeworkScheduleArgs(window="today"), stubbed)
        assert "henry" in content
        assert "语文预习" in content

    async def test_caps_what_it_hands_the_model(self, stubbed) -> None:
        day = date(2026, 9, 16)
        stubbed["per_day"] = {
            day: [
                _task(day=day, title=f"作业 {i}")
                for i in range(homework_tools.MAX_CONTENT_TASKS + 5)
            ]
        }
        content, artifact = await _run(HomeworkScheduleArgs(window="today"), stubbed)

        listed = content.count("\n- ")
        assert listed == homework_tools.MAX_CONTENT_TASKS
        assert "5 more" in content
        # The cap is on the prose only: the artifact still carries everything,
        # because that is what the card renders.
        assert artifact["days"][0]["task_count"] == homework_tools.MAX_CONTENT_TASKS + 5

    async def test_says_so_plainly_when_there_is_nothing(self, stubbed) -> None:
        content, _ = await _run(HomeworkScheduleArgs(window="today"), stubbed)
        assert "No homework" in content
