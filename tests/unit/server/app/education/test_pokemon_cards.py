from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.server.app.education.pokemon_cards import router
from src.server.app.education.pokemon_cards import card_image
from starlette.requests import ClientDisconnect
from src.server.services.education_pokemon_catalog import (
    CardImage,
    PokemonCatalogAccessError,
    PokemonCatalogNotFoundError,
    PokemonCatalogStorageError,
)
from src.server.utils.api import get_current_user_id

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as session:
        yield session


async def test_list_only_returns_client_safe_metadata(client):
    card = dict(
        card_id=str(uuid4()),
        source_card_id="test-1",
        set_code="test",
        series_name="Test",
        name="Pikachu",
        category="Pokemon",
        element="Electric",
        hp=60,
        stage="Basic",
        card_number="001",
        rarity="Rare",
        illustrator="Artist",
        notes="",
        image_width=64,
        image_height=88,
        image_bucket="private",
        image_key="secret",
        image_sha256="a" * 64,
    )
    with patch(
        "src.server.app.education.pokemon_cards.get_catalog",
        AsyncMock(
            return_value={
                "items": [card],
                "total": 1,
                "page": 1,
                "page_size": 20,
                "series": [],
            }
        ),
    ) as listing:
        response = await client.get("/api/v1/education/pokemon-cards?set_code=test")
    assert response.status_code == 200
    assert not {"image_key", "image_bucket", "image_sha256"}.intersection(
        response.json()["items"][0]
    )
    listing.assert_awaited_once_with(
        user_id="parent-1", page=1, page_size=20, set_code="test"
    )


@pytest.mark.parametrize(
    "query", ["page=0", "page=10001", "page_size=0", "page_size=41", "set_code="]
)
async def test_invalid_pagination_is_rejected(client, query):
    assert (
        await client.get(f"/api/v1/education/pokemon-cards?{query}")
    ).status_code == 422


@pytest.mark.parametrize(
    "error,code",
    [
        (PokemonCatalogAccessError("denied"), 403),
        (PokemonCatalogNotFoundError("missing"), 404),
        (PokemonCatalogStorageError("unavailable"), 503),
    ],
)
async def test_image_errors_return_explicit_status(client, error, code):
    with patch(
        "src.server.app.education.pokemon_cards.get_card_image",
        AsyncMock(side_effect=error),
    ):
        response = await client.get(f"/api/v1/education/pokemon-cards/{uuid4()}/image")
    assert response.status_code == code


async def test_images_stream_with_private_cache_and_revalidate(client):
    async def chunks():
        yield b"png"

    with patch(
        "src.server.app.education.pokemon_cards.get_card_image",
        AsyncMock(return_value=CardImage(chunks(), '"digest"', 3)),
    ) as image:
        response = await client.get(f"/api/v1/education/pokemon-cards/{uuid4()}/image")
        assert response.content == b"png"
        assert response.headers["content-type"] == "image/png"
        assert (
            response.headers["cache-control"] == "private, max-age=0, must-revalidate"
        )
        assert response.headers["etag"] == '"digest"'
        image.return_value = CardImage(None, '"digest"', 3)
        response = await client.get(
            f"/api/v1/education/pokemon-cards/{uuid4()}/image",
            headers={"If-None-Match": '"digest"'},
        )
        assert response.status_code == 304
        assert response.content == b""
        assert image.await_args.kwargs["if_none_match"] == '"digest"'


async def test_list_access_denied(client):
    with patch(
        "src.server.app.education.pokemon_cards.get_catalog",
        AsyncMock(side_effect=PokemonCatalogAccessError("denied")),
    ):
        assert (await client.get("/api/v1/education/pokemon-cards")).status_code == 403


async def test_disconnect_before_image_body_starts_still_closes_storage():
    async def chunks():
        yield b"png"

    close = Mock()
    with patch(
        "src.server.app.education.pokemon_cards.get_card_image",
        AsyncMock(return_value=CardImage(chunks(), '"digest"', 3, close)),
    ):
        response = await card_image(uuid4(), "parent", None)
    send = AsyncMock(side_effect=OSError("connection closed"))
    with pytest.raises(ClientDisconnect):
        await response(
            {"type": "http", "asgi": {"spec_version": "2.4"}}, AsyncMock(), send
        )
    close.assert_called_once()
