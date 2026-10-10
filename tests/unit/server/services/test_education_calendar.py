from datetime import date

import pytest

from src.server.services.education_calendar_parser import (
    CalendarValidationError,
    expand_calendar,
    validate_calendar,
)


def calendar(*events):
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Tests//EN\r\n"
        + "\r\n".join(events)
        + "\r\nEND:VCALENDAR\r\n"
    ).encode()


def event(body):
    return "BEGIN:VEVENT\r\n" + body + "\r\nEND:VEVENT"


def test_all_day_end_is_exclusive_and_spans_each_day():
    content = calendar(
        event(
            "UID:holiday\r\nDTSTART;VALUE=DATE:20261010\r\nDTEND;VALUE=DATE:20261012\r\nSUMMARY:Holiday"
        )
    )
    result = expand_calendar(
        content, "Asia/Tokyo", date(2026, 10, 10), date(2026, 10, 12)
    )
    assert result[0]["dates"] == ["2026-10-10", "2026-10-11"]
    assert result[0]["all_day"] is True


def test_recurrence_exclusion_and_moved_override():
    content = calendar(
        event(
            "UID:lesson\r\nDTSTART;TZID=Asia/Tokyo:20261010T090000\r\nDTEND;TZID=Asia/Tokyo:20261010T100000\r\nRRULE:FREQ=DAILY;COUNT=4\r\nEXDATE;TZID=Asia/Tokyo:20261011T090000\r\nSUMMARY:Lesson"
        ),
        event(
            "UID:lesson\r\nRECURRENCE-ID;TZID=Asia/Tokyo:20261012T090000\r\nDTSTART;TZID=Asia/Tokyo:20261012T150000\r\nDTEND;TZID=Asia/Tokyo:20261012T160000\r\nSUMMARY:Moved"
        ),
    )
    result = expand_calendar(
        content, "Asia/Tokyo", date(2026, 10, 10), date(2026, 10, 13)
    )
    assert [entry["dates"] for entry in result] == [
        ["2026-10-10"],
        ["2026-10-12"],
        ["2026-10-13"],
    ]
    assert result[1]["title"] == "Moved"
    assert "15:00:00+09:00" in result[1]["start_at"]


def test_utc_and_floating_times_use_household_timezone():
    content = calendar(
        event(
            "UID:utc\r\nDTSTART:20261009T230000Z\r\nDTEND:20261010T000000Z\r\nSUMMARY:UTC"
        ),
        event("UID:local\r\nDTSTART:20261010T090000\r\nSUMMARY:Local"),
    )
    result = expand_calendar(
        content, "Asia/Tokyo", date(2026, 10, 10), date(2026, 10, 10)
    )
    assert [entry["dates"] for entry in result] == [["2026-10-10"], ["2026-10-10"]]
    assert result[0]["start_at"].endswith("08:00:00+09:00")
    assert result[1]["start_at"].endswith("09:00:00+09:00")


def test_cancelled_override_removes_occurrence():
    content = calendar(
        event("UID:lesson\r\nDTSTART:20261010T090000Z\r\nRRULE:FREQ=DAILY;COUNT=2"),
        event(
            "UID:lesson\r\nRECURRENCE-ID:20261011T090000Z\r\nDTSTART:20261011T090000Z\r\nSTATUS:CANCELLED"
        ),
    )
    assert (
        len(expand_calendar(content, "UTC", date(2026, 10, 10), date(2026, 10, 12)))
        == 1
    )


@pytest.mark.parametrize(
    "content",
    [
        b"bad",
        calendar(event("UID:missing")),
        calendar(event("DTSTART:20261010T090000Z")),
        calendar(event("UID:dense\r\nDTSTART:20261010T090000Z\r\nRRULE:FREQ=SECONDLY")),
    ],
)
def test_invalid_or_excessive_calendar_is_rejected(content):
    with pytest.raises(CalendarValidationError):
        validate_calendar(content, "UTC")


def test_duplicate_uid_occurrence_is_rejected():
    content = calendar(
        event("UID:duplicate\r\nDTSTART:20261010T090000Z"),
        event("UID:duplicate\r\nDTSTART:20261010T100000Z"),
    )
    with pytest.raises(CalendarValidationError):
        validate_calendar(content, "UTC")


def test_zero_interval_is_rejected_at_import():
    content = calendar(
        event("UID:broken\r\nDTSTART:20261010T090000Z\r\nRRULE:FREQ=DAILY;INTERVAL=0")
    )
    with pytest.raises(CalendarValidationError):
        validate_calendar(content, "UTC")


def test_cancelled_override_without_start_is_supported():
    content = calendar(
        event("UID:lesson\r\nDTSTART:20261010T090000Z\r\nRRULE:FREQ=DAILY;COUNT=2"),
        event("UID:lesson\r\nRECURRENCE-ID:20261011T090000Z\r\nSTATUS:CANCELLED"),
    )
    assert (
        len(expand_calendar(content, "UTC", date(2026, 10, 10), date(2026, 10, 12)))
        == 1
    )


def test_daily_recurrence_preserves_local_time_across_dst():
    content = calendar(
        event(
            "UID:dst\r\nDTSTART;TZID=America/New_York:20261031T090000\r\nRRULE:FREQ=DAILY;COUNT=2"
        )
    )
    result = expand_calendar(
        content, "America/New_York", date(2026, 10, 31), date(2026, 11, 1)
    )
    assert result[0]["start_at"].endswith("09:00:00-04:00")
    assert result[1]["start_at"].endswith("09:00:00-05:00")


def test_floating_repeat_and_exclusion_use_household_time():
    content = calendar(
        event(
            "UID:floating\r\nDTSTART:20261010T090000\r\nRRULE:FREQ=DAILY;UNTIL=20261012T090000\r\nEXDATE:20261011T090000"
        )
    )
    result = expand_calendar(
        content, "Asia/Tokyo", date(2026, 10, 10), date(2026, 10, 12)
    )
    assert [entry["dates"] for entry in result] == [["2026-10-10"], ["2026-10-12"]]
