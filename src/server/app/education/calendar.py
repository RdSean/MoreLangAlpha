"""Household calendar endpoints: parents manage, all household members read."""

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from src.server.services.education_calendar import (
    CalendarAccessError,
    CalendarNotFoundError,
    CalendarSourceConflictError,
    CalendarValidationError,
    delete_source,
    get_events,
    import_calendar,
    list_sources,
)
from src.server.services.education_calendar_parser import MAX_BYTES
from src.server.utils.api import CurrentUserId

router = APIRouter(prefix="/api/v1/education/calendar", tags=["Education calendar"])


class CalendarSourceResponse(BaseModel):
    source_id: UUID
    household_id: UUID
    name: str
    filename: str
    event_count: int
    updated_at: datetime


class CalendarEventResponse(BaseModel):
    event_id: str
    uid: str
    source_id: UUID
    source_name: str
    title: str
    description: str
    location: str
    all_day: bool
    start_at: str
    end_at: str
    dates: list[date]


class CalendarEventsResponse(BaseModel):
    household_id: UUID
    timezone: str
    start_date: date
    end_date: date
    events: list[CalendarEventResponse]


def _http_error(exc: Exception) -> HTTPException:
    status = (
        403
        if isinstance(exc, CalendarAccessError)
        else 404
        if isinstance(exc, CalendarNotFoundError)
        else 409
        if isinstance(exc, CalendarSourceConflictError)
        else 400
    )
    return HTTPException(status_code=status, detail=str(exc))


@router.get("/sources", response_model=list[CalendarSourceResponse])
async def read_sources(user_id: CurrentUserId):
    try:
        return await list_sources(user_id=user_id)
    except CalendarAccessError as exc:
        raise _http_error(exc) from exc


@router.post("/sources", response_model=CalendarSourceResponse)
async def upload_calendar(
    user_id: CurrentUserId,
    file: UploadFile = File(...),
    source_id: UUID | None = Form(None),
):
    try:
        return await import_calendar(
            user_id=user_id,
            filename=file.filename,
            content=await file.read(MAX_BYTES + 1),
            source_id=str(source_id) if source_id else None,
        )
    except (
        CalendarAccessError,
        CalendarNotFoundError,
        CalendarValidationError,
        CalendarSourceConflictError,
    ) as exc:
        raise _http_error(exc) from exc
    finally:
        await file.close()


@router.delete("/sources/{source_id}", status_code=204)
async def remove_calendar(source_id: UUID, user_id: CurrentUserId):
    try:
        await delete_source(user_id=user_id, source_id=str(source_id))
    except (CalendarAccessError, CalendarNotFoundError) as exc:
        raise _http_error(exc) from exc


@router.get("/events", response_model=CalendarEventsResponse)
async def read_events(start_date: date, end_date: date, user_id: CurrentUserId):
    try:
        return await get_events(
            user_id=user_id, start_date=start_date, end_date=end_date
        )
    except (CalendarAccessError, CalendarValidationError) as exc:
        raise _http_error(exc) from exc
