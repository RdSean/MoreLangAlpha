"""Family calendar import and range reads, isolated from agent runtimes."""

from datetime import date
from hashlib import sha256
from pathlib import PurePosixPath

import anyio
from anyio.to_process import run_sync

from src.server.database.education_calendar import (
    CalendarSourceConflictError as CalendarSourceConflictError,
    CalendarSourceLimitError,
    delete_calendar_source,
    list_calendar_sources,
    save_calendar_source,
)
from src.server.database.education_members import get_membership_for_user
from src.server.services.education_calendar_parser import (
    CalendarValidationError,
    MAX_OCCURRENCES,
    expand_calendar,
    validate_calendar,
)


class CalendarAccessError(PermissionError):
    pass


class CalendarNotFoundError(LookupError):
    pass


async def _membership(user_id: str, *, parent: bool = False) -> dict:
    member = await get_membership_for_user(user_id)
    if not member or (parent and member["role"] != "parent"):
        raise CalendarAccessError(
            "需要家庭成员身份。" if not parent else "只有家长可以管理家庭日历。"
        )
    return member


async def list_sources(*, user_id: str) -> list[dict]:
    member = await _membership(user_id)
    return await list_calendar_sources(str(member["household_id"]))


async def import_calendar(
    *, user_id: str, filename: str | None, content: bytes, source_id: str | None = None
) -> dict:
    member = await _membership(user_id, parent=True)
    filename = PurePosixPath((filename or "").replace("\\", "/")).name.strip()
    if not filename.lower().endswith(".ics") or len(filename) > 255:
        raise CalendarValidationError(
            "请选择有效的 .ics 文件，文件名不能超过 255 个字符。"
        )
    try:
        with anyio.fail_after(10):
            metadata = await run_sync(
                validate_calendar, content, member["timezone"], cancellable=True
            )
        text = content.decode("utf-8-sig")
    except TimeoutError as exc:
        raise CalendarValidationError("日历解析耗时过长，请简化日历后重试。") from exc
    except UnicodeDecodeError as exc:
        raise CalendarValidationError("请使用 UTF-8 编码的 ICS 文件。") from exc
    try:
        source = await save_calendar_source(
            household_id=str(member["household_id"]),
            user_id=user_id,
            filename=filename,
            name=metadata["name"] or PurePosixPath(filename).stem,
            content=text,
            digest=sha256(text.encode()).hexdigest(),
            event_count=metadata["event_count"],
            source_id=source_id,
        )
    except CalendarSourceLimitError as exc:
        raise CalendarValidationError(str(exc)) from exc
    if not source:
        raise CalendarNotFoundError("家庭日历不存在。")
    return source


async def delete_source(*, user_id: str, source_id: str) -> None:
    member = await _membership(user_id, parent=True)
    if not await delete_calendar_source(
        household_id=str(member["household_id"]), source_id=source_id
    ):
        raise CalendarNotFoundError("家庭日历不存在。")


async def get_events(*, user_id: str, start_date: date, end_date: date) -> dict:
    member = await _membership(user_id)
    if (
        end_date < start_date
        or (end_date - start_date).days > 61
        or start_date.year < 1970
        or end_date.year > 2200
    ):
        raise CalendarValidationError(
            "日历查询范围须在 1970 至 2200 年内，且不能超过 62 天。"
        )
    sources = await list_calendar_sources(
        str(member["household_id"]), include_content=True
    )
    events = {}
    try:
        with anyio.fail_after(10):
            for source in sources:
                expanded = await run_sync(
                    expand_calendar,
                    source["content"].encode(),
                    member["timezone"],
                    start_date,
                    end_date,
                    cancellable=True,
                )
                for event in expanded:
                    event.update(
                        source_id=str(source["source_id"]), source_name=source["name"]
                    )
                    events.setdefault(event["event_id"], event)
                if len(events) > MAX_OCCURRENCES:
                    raise CalendarValidationError(
                        "该日期范围包含过多日程，请缩小查询范围。"
                    )
    except TimeoutError as exc:
        raise CalendarValidationError(
            "日历展开耗时过长，请缩小日期范围或更新日历。"
        ) from exc
    return {
        "household_id": str(member["household_id"]),
        "timezone": member["timezone"],
        "start_date": start_date,
        "end_date": end_date,
        "events": sorted(
            events.values(), key=lambda event: (event["start_at"], event["event_id"])
        ),
    }
