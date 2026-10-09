from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
import pytest_asyncio

from src.server.app.education.textbooks import router
from src.server.utils.api import get_current_user_id

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from src.server.app.education.textbooks import router


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as session:
        yield session


BOOK_ID = "bc5734a8-8a30-459f-a1f3-8551feb4c169"


@pytest.mark.asyncio
async def test_cover_upload_route_is_parent_only(client, monkeypatch):
    from src.server.services import education_textbook_cover

    client._transport.app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    cover = AsyncMock(return_value={"cover_available": True, "cover_updated_at": "now"})
    monkeypatch.setattr(education_textbook_cover, "replace_textbook_cover", cover)
    response = await client.post(
        f"/api/v1/education/textbooks/{BOOK_ID}/cover",
        files={"file": ("cover.png", b"\x89PNG\r\n\x1a\ncover", "image/png")},
    )
    assert response.status_code == 200
    assert response.json()["cover_available"] is True
    assert cover.call_args.kwargs["parent_user_id"] == "parent-1"


@pytest.mark.asyncio
async def test_cover_delete_route_maps_parent_permission(client, monkeypatch):
    from src.server.services import education_textbook_cover
    from src.server.services.education_textbooks import TextbookPermissionError

    client._transport.app.dependency_overrides[get_current_user_id] = lambda: "student-1"
    monkeypatch.setattr(
        education_textbook_cover,
        "remove_textbook_cover",
        AsyncMock(side_effect=TextbookPermissionError("parent only")),
    )
    response = await client.delete(f"/api/v1/education/textbooks/{BOOK_ID}/cover")
    assert response.status_code == 403
