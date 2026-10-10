from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.server.app.education.calendar import router
from src.server.services.education_calendar import (
    CalendarAccessError,
    CalendarNotFoundError,
    CalendarValidationError,
)
from src.server.utils.api import get_current_user_id


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user_id] = lambda: "member-1"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as session:
        yield session


@pytest.mark.asyncio
async def test_upload_passes_bytes_and_explicit_source_identity(client):
    source_id = "64f3e502-187c-47af-bbe2-ad38f914cc1f"
    with patch(
        "src.server.app.education.calendar.import_calendar",
        AsyncMock(
            return_value={
                "source_id": source_id,
                "household_id": "64f3e502-187c-47af-bbe2-ad38f914cc1f",
                "name": "Classes",
                "filename": "classes.ics",
                "event_count": 1,
                "updated_at": "2026-10-10T00:00:00Z",
            }
        ),
    ) as upload:
        response = await client.post(
            "/api/v1/education/calendar/sources",
            files={"file": ("classes.ics", b"ICS", "text/calendar")},
            data={"source_id": source_id},
        )
    assert response.status_code == 200
    assert upload.await_args.kwargs == {
        "user_id": "member-1",
        "filename": "classes.ics",
        "content": b"ICS",
        "source_id": source_id,
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error,status",
    [
        (CalendarAccessError("denied"), 403),
        (CalendarNotFoundError("missing"), 404),
        (CalendarValidationError("invalid"), 400),
    ],
)
async def test_upload_errors_have_explicit_status(client, error, status):
    with patch(
        "src.server.app.education.calendar.import_calendar",
        AsyncMock(side_effect=error),
    ):
        response = await client.post(
            "/api/v1/education/calendar/sources", files={"file": ("test.ics", b"ICS")}
        )
    assert response.status_code == status


@pytest.mark.asyncio
async def test_calendar_requires_date_boundaries(client):
    assert (
        await client.get("/api/v1/education/calendar/events?start_date=2026-10-10")
    ).status_code == 422
