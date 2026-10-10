"""Read-only parent catalog and private card-image delivery."""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import anyio
from starlette.concurrency import iterate_in_threadpool

from src.server.database.education_members import get_membership_for_user
from src.server.database.education_pokemon_cards import (
    get_pokemon_card,
    list_pokemon_cards,
)
from src.utils.storage.s3_compatible import StorageConfig, open_download_stream


class PokemonCatalogAccessError(PermissionError):
    pass


class PokemonCatalogNotFoundError(LookupError):
    pass


class PokemonCatalogStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class CardImage:
    chunks: AsyncIterator[bytes] | None
    etag: str
    content_length: int
    close: Callable[[], None] | None = None


async def _require_parent(user_id: str) -> None:
    member = await get_membership_for_user(user_id)
    if not member or member["role"] != "parent":
        raise PokemonCatalogAccessError("只有家长可以查看卡牌目录。")


async def get_catalog(
    *, user_id: str, page: int, page_size: int, set_code: str | None
) -> dict:
    await _require_parent(user_id)
    return await list_pokemon_cards(page=page, page_size=page_size, set_code=set_code)


async def get_card_image(
    *, user_id: str, card_id: str, if_none_match: str | None
) -> CardImage:
    await _require_parent(user_id)
    card = await get_pokemon_card(card_id)
    if not card:
        raise PokemonCatalogNotFoundError("卡牌不存在。")
    expected_key = (
        f"education/pokemon/cards/{card['source_card_id']}/{card['image_sha256']}.png"
    )
    if (
        card["image_bucket"] != StorageConfig.BUCKET_NAME
        or card["image_key"] != expected_key
    ):
        raise PokemonCatalogStorageError("卡图暂时无法读取。")
    etag = f'"{card["image_sha256"]}"'
    if if_none_match and any(
        value.strip().removeprefix("W/") in {etag, "*"}
        for value in if_none_match.split(",")
    ):
        return CardImage(None, etag, card["image_byte_size"])
    try:
        stream = await anyio.to_thread.run_sync(open_download_stream, expected_key)
    except Exception as exc:
        raise PokemonCatalogStorageError("卡图暂时无法读取。") from exc
    if stream.content_length != card["image_byte_size"]:
        await anyio.to_thread.run_sync(stream.close)
        raise PokemonCatalogStorageError("卡图暂时无法读取。")

    async def chunks():
        try:
            async for chunk in iterate_in_threadpool(stream.chunks):
                yield chunk
        finally:
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(stream.close)

    return CardImage(chunks(), etag, card["image_byte_size"], stream.close)
