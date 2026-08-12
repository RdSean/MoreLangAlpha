"""HTTP boundary tests for private education asset routes."""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.server.app.education.assets import router
from src.server.services.education_assets import EducationAssetNotFoundError
from src.server.utils.api import get_current_user_id


ASSET = {
    "asset_id": "bc5734a8-8a30-459f-a1f3-8551feb4c169",
    "household_id": "6eebf7fb-9579-4c5d-825a-2e595b7f1b18",
    "created_by_user_id": "student-1",
    "original_filename": "worksheet.pdf",
    "content_type": "application/pdf",
    "size_bytes": 12,
    "storage_key": "education/6eebf7fb-9579-4c5d-825a-2e595b7f1b18/bc5734a8-8a30-459f-a1f3-8551feb4c169.pdf",
}


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as session:
        yield session


@pytest.mark.asyncio
async def test_upload_returns_private_metadata_without_storage_key_or_signed_url(client):
    with patch(
        "src.server.app.education.assets.create_education_asset",
        new=AsyncMock(return_value=ASSET),
    ) as create:
        response = await client.post(
            "/api/v1/education/assets",
            files={"file": ("worksheet.pdf", b"%PDF-1.7...", "application/pdf")},
        )

    assert response.status_code == 201
    assert response.json() == {
        "asset_id": ASSET["asset_id"],
        "household_id": ASSET["household_id"],
        "created_by_user_id": ASSET["created_by_user_id"],
        "original_filename": ASSET["original_filename"],
        "content_type": ASSET["content_type"],
        "size_bytes": ASSET["size_bytes"],
    }
    assert "storage_key" not in response.json()
    assert "download_url" not in response.json()
    assert create.await_args.kwargs["user_id"] == "student-1"


@pytest.mark.asyncio
async def test_cross_household_download_is_not_found(client):
    with patch(
        "src.server.app.education.assets.get_education_asset_download_url",
        new=AsyncMock(side_effect=EducationAssetNotFoundError("not found")),
    ):
        response = await client.get(f"/api/v1/education/assets/{ASSET['asset_id']}/download")

    assert response.status_code == 404
