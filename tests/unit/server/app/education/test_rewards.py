from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.server.app.education import rewards
from src.server.utils.api import get_current_user_id

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(rewards.router)
    app.dependency_overrides[get_current_user_id] = lambda: "student"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


@pytest.mark.parametrize(
    "error,status",
    [
        (rewards.service.RewardAccessError("denied"), 403),
        (rewards.service.RewardConflict("changed"), 409),
        (rewards.service.RewardNotFound("missing"), 404),
    ],
)
async def test_explicit_reward_errors(client, monkeypatch, error, status):
    monkeypatch.setattr(rewards.service, "open_pack", AsyncMock(side_effect=error))
    assert (
        await client.post(f"/api/v1/education/rewards/packs/{uuid4()}/open")
    ).status_code == status


@pytest.mark.parametrize(
    "body",
    [
        {"pack_type": "rare", "expected_price": 0, "idempotency_key": str(uuid4())},
        {"pack_type": "daily", "expected_price": 1.5, "idempotency_key": str(uuid4())},
        {"pack_type": "daily", "expected_price": 5},
        {"pack_type": "admin", "expected_price": 5, "idempotency_key": str(uuid4())},
    ],
)
async def test_invalid_purchases_never_reach_service(client, monkeypatch, body):
    purchase = AsyncMock()
    monkeypatch.setattr(rewards.service, "purchase", purchase)
    assert (
        await client.post("/api/v1/education/rewards/purchases", json=body)
    ).status_code == 422
    purchase.assert_not_awaited()


async def test_collection_filters_out_storage_fields(client, monkeypatch):
    from datetime import datetime, timezone
    from tests.integration.test_education_pokemon_cards_db import record

    now = datetime.now(timezone.utc)
    card = {
        **record(),
        "card_id": str(uuid4()),
        "reward_level": "basic",
        "quantity": 2,
        "first_obtained_at": now,
        "last_obtained_at": now,
    }
    monkeypatch.setattr(
        rewards.service,
        "list_records",
        AsyncMock(
            return_value={"items": [card], "total": 1, "page": 1, "page_size": 20,"series":[]}
        ),
    )
    response = await client.get("/api/v1/education/rewards/collection")
    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["quantity"] == 2
    assert not {
        "image_key",
        "image_bucket",
        "image_sha256",
        "source_image_path",
    }.intersection(item)
