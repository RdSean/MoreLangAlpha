from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.server.services import education_pokemon_catalog as catalog
from src.utils.storage.s3_compatible import ObjectDownloadStream

pytestmark = pytest.mark.asyncio


@pytest.fixture
def dependencies():
    with (
        patch.object(
            catalog,
            "get_membership_for_user",
            AsyncMock(return_value={"role": "parent"}),
        ) as member,
        patch.object(
            catalog,
            "list_pokemon_cards",
            AsyncMock(
                return_value={
                    "items": [],
                    "total": 0,
                    "page": 1,
                    "page_size": 20,
                    "series": [],
                }
            ),
        ) as listing,
        patch.object(catalog, "get_pokemon_card", AsyncMock()) as card,
        patch.object(catalog, "open_download_stream") as storage,
        patch.object(catalog.StorageConfig, "BUCKET_NAME", "cards"),
    ):
        card.return_value = {
            "card_id": "card-1",
            "source_card_id": "test-1",
            "image_bucket": "cards",
            "image_key": f"education/pokemon/cards/test-1/{'a' * 64}.png",
            "image_sha256": "a" * 64,
            "image_content_type": "image/png",
            "image_byte_size": 3,
        }
        storage.return_value = ObjectDownloadStream(iter([b"png"]), 3, Mock())
        yield member, listing, card, storage


@pytest.mark.parametrize("member", [None, {"role": "student"}])
async def test_catalog_and_images_require_parent_before_database_or_storage(
    dependencies, member
):
    membership, listing, card, storage = dependencies
    membership.return_value = member
    with pytest.raises(catalog.PokemonCatalogAccessError):
        await catalog.get_catalog(
            user_id="student", page=1, page_size=20, set_code=None
        )
    with pytest.raises(catalog.PokemonCatalogAccessError):
        await catalog.get_card_image(
            user_id="student", card_id="card-1", if_none_match=None
        )
    listing.assert_not_awaited()
    card.assert_not_awaited()
    storage.assert_not_called()


async def test_image_stream_closes_and_does_not_expose_storage_address(dependencies):
    _, _, _, storage = dependencies
    response = await catalog.get_card_image(
        user_id="parent", card_id="card-1", if_none_match=None
    )
    assert b"".join([chunk async for chunk in response.chunks]) == b"png"
    storage.return_value.close.assert_called_once()
    assert response.etag == f'"{"a" * 64}"'
    storage.assert_called_once_with(f"education/pokemon/cards/test-1/{'a' * 64}.png")


async def test_matching_etag_checks_access_but_does_not_open_storage(dependencies):
    membership, _, card, storage = dependencies
    response = await catalog.get_card_image(
        user_id="parent", card_id="card-1", if_none_match=f'"{"a" * 64}"'
    )
    assert response.chunks is None
    membership.assert_awaited_once()
    card.assert_awaited_once()
    storage.assert_not_called()


@pytest.mark.parametrize(
    "field,value", [("image_bucket", "unrelated"), ("image_key", "unrelated/image.png")]
)
async def test_catalog_image_cannot_open_unrelated_objects(dependencies, field, value):
    _, _, card, storage = dependencies
    card.return_value[field] = value
    with pytest.raises(catalog.PokemonCatalogStorageError):
        await catalog.get_card_image(
            user_id="parent", card_id="card-1", if_none_match=None
        )
    storage.assert_not_called()


async def test_missing_card_and_unavailable_storage_have_distinct_errors(dependencies):
    _, _, card, storage = dependencies
    storage.side_effect = RuntimeError("private backend details")
    with pytest.raises(catalog.PokemonCatalogStorageError, match="卡图暂时无法读取"):
        await catalog.get_card_image(
            user_id="parent", card_id="card-1", if_none_match=None
        )
    card.return_value = None
    with pytest.raises(catalog.PokemonCatalogNotFoundError):
        await catalog.get_card_image(
            user_id="parent", card_id="missing", if_none_match=None
        )


async def test_mismatched_length_closes_storage_body(dependencies):
    _, _, _, storage = dependencies
    storage.return_value = ObjectDownloadStream(iter([b"bad"]), 999, Mock())
    with pytest.raises(catalog.PokemonCatalogStorageError):
        await catalog.get_card_image(
            user_id="parent", card_id="card-1", if_none_match=None
        )
    storage.return_value.close.assert_called_once()
