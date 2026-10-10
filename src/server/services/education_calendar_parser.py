"""Bounded, offline ICS parsing for household calendars."""

from datetime import date, datetime, time, timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo

from icalendar import Calendar
import recurring_ical_events

MAX_BYTES = 1024 * 1024
MAX_COMPONENTS = 500
MAX_OCCURRENCES = 2000


class CalendarValidationError(ValueError):
    pass


def _read(content: bytes, timezone: str) -> Calendar:
    if not content or len(content) > MAX_BYTES:
        raise CalendarValidationError("日历文件不能为空，且不能超过 1 MB。")
    try:
        zone = ZoneInfo(timezone)
        cal = Calendar.from_ical(content.decode("utf-8-sig"))
        if cal.name != "VCALENDAR" or cal.errors:
            raise ValueError("Invalid calendar")
        events = cal.walk("VEVENT")
        if not events or len(events) > MAX_COMPONENTS:
            raise CalendarValidationError("日历须包含 1 至 500 条事件或重复事件定义。")
        identities = set()
        for event in events:
            if (
                not event.get("DTSTART")
                and event.get("RECURRENCE-ID")
                and str(event.get("STATUS", "")).upper() == "CANCELLED"
            ):
                event.add("DTSTART", event.decoded("RECURRENCE-ID"))
            if event.errors or not event.get("UID") or not event.get("DTSTART"):
                raise CalendarValidationError("每条日程须包含有效的 UID 和开始时间。")
            for field in ("DTSTART", "DTEND", "RECURRENCE-ID"):
                prop = event.get(field)
                if prop is None:
                    continue
                value = prop.dt
                if not isinstance(value, date) or not 1970 <= value.year <= 2200:
                    raise CalendarValidationError("日程日期须在 1970 至 2200 年之间。")
                if isinstance(value, datetime) and value.tzinfo is None:
                    if prop.params.get("TZID"):
                        raise CalendarValidationError("日程包含无法识别的时区。")
                    event[field] = type(prop)(value.replace(tzinfo=zone))
            for field in ("EXDATE", "RDATE"):
                properties = event.get(field, [])
                if not isinstance(properties, list):
                    properties = [properties]
                for prop in properties:
                    if len(prop.dts) > MAX_OCCURRENCES:
                        raise CalendarValidationError("日程包含过多例外日期。")
                    for item in prop.dts:
                        if isinstance(item.dt, datetime) and item.dt.tzinfo is None:
                            if prop.params.get("TZID"):
                                raise CalendarValidationError(
                                    "日程包含无法识别的时区。"
                                )
                            item.dt = item.dt.replace(tzinfo=zone)
            start = event.decoded("DTSTART")
            end = event.decoded("DTEND", start)
            if isinstance(start, datetime) != isinstance(end, datetime):
                raise CalendarValidationError("日程开始和结束时间的类型须一致。")
            duration = event.decoded("DURATION", end - start)
            if event.get("DTEND") and event.get("DURATION"):
                raise CalendarValidationError("日程不能同时指定结束时间和持续时长。")
            if duration < timedelta(0) or duration > timedelta(days=366):
                raise CalendarValidationError("日程时长须在 0 至 366 天之间。")
            rules = event.get("RRULE", [])
            if not isinstance(rules, list):
                rules = [rules]
            for rule in rules:
                if (
                    int(rule.get("INTERVAL", [1])[0]) <= 0
                    or int(rule.get("COUNT", [1])[0]) <= 0
                ):
                    raise CalendarValidationError("重复间隔和次数须为正整数。")
                if (
                    rule.get("FREQ", [""])[0]
                    not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY")
                    or rule.get("BYSECOND")
                    or rule.get("BYMINUTE")
                ):
                    raise CalendarValidationError("仅支持按天、周、月或年重复的日程。")
            recurrence = event.decoded("RECURRENCE-ID", None)
            identity = (str(event["UID"]), recurrence.isoformat() if recurrence else "")
            if identity in identities:
                raise CalendarValidationError("日历包含重复的 UID 或同一次日程定义。")
            identities.add(identity)
        cal["X-WR-TIMEZONE"] = timezone
        recurring_ical_events.of(cal)
        return cal
    except CalendarValidationError:
        raise
    except Exception as exc:
        raise CalendarValidationError(
            "无法解析 ICS 文件，请检查日期、时区和重复规则。"
        ) from exc


def validate_calendar(content: bytes, timezone: str) -> dict:
    cal = _read(content, timezone)
    return {
        "event_count": len({str(event["UID"]) for event in cal.walk("VEVENT")}),
        "name": str(cal.get("X-WR-CALNAME", cal.get("NAME", ""))).strip()[:255],
    }


def expand_calendar(
    content: bytes, timezone: str, start_date: date, end_date: date
) -> list[dict]:
    cal = _read(content, timezone)
    zone = ZoneInfo(timezone)
    lower = datetime.combine(start_date, time.min, zone)
    upper = datetime.combine(end_date + timedelta(days=1), time.min, zone)
    try:
        events = recurring_ical_events.of(cal).between(lower, upper)
        if len(events) > MAX_OCCURRENCES:
            raise CalendarValidationError("该日期范围包含过多日程，请缩小查询范围。")
        result = []
        for event in events:
            if str(event.get("STATUS", "")).upper() == "CANCELLED":
                continue
            start = event.decoded("DTSTART")
            all_day = not isinstance(start, datetime)
            end = event.decoded(
                "DTEND", start + (timedelta(days=1) if all_day else timedelta(0))
            )
            if not all_day:
                start = start.astimezone(zone)
                end = end.astimezone(zone)
            first = start if all_day else start.date()
            last = (
                end - timedelta(days=1)
                if all_day
                else (end - timedelta(microseconds=1)).date()
                if end > start
                else first
            )
            first, last = max(first, start_date), min(last, end_date)
            if first > last:
                continue
            uid = str(event["UID"])
            recurrence = event.decoded("RECURRENCE-ID", start).isoformat()
            result.append(
                {
                    "event_id": sha256((uid + "\0" + recurrence).encode()).hexdigest(),
                    "uid": uid,
                    "title": str(event.get("SUMMARY", "")).strip()[:1000]
                    or "未命名日程",
                    "description": str(event.get("DESCRIPTION", ""))[:20000],
                    "location": str(event.get("LOCATION", ""))[:2000],
                    "all_day": all_day,
                    "start_at": start.isoformat(),
                    "end_at": end.isoformat(),
                    "dates": [
                        (first + timedelta(days=offset)).isoformat()
                        for offset in range((last - first).days + 1)
                    ],
                }
            )
        return sorted(result, key=lambda item: (item["start_at"], item["event_id"]))
    except CalendarValidationError:
        raise
    except Exception as exc:
        raise CalendarValidationError("无法展开日程的重复规则。") from exc
