"""Authenticated read-only Pokemon catalog routes."""

from uuid import UUID

import anyio
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from starlette.types import Receive, Scope, Send

from src.server.services.education_pokemon_catalog import (
    CardImage,
    PokemonCatalogAccessError,
    PokemonCatalogNotFoundError,
    PokemonCatalogStorageError,
    get_card_image,
    get_catalog,
)
from src.server.utils.api import CurrentUserId

router = APIRouter(prefix="/api/v1/education/pokemon-cards", tags=["Pokemon cards"])


class _CardImageResponse(StreamingResponse):
    def __init__(self, image: CardImage, headers: dict[str, str]):
        super().__init__(image.chunks, media_type="image/png", headers=headers)
        self.close_image = image.close

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Header-send failures happen before the body iterator can run its cleanup.
        try:
            await super().__call__(scope, receive, send)
        finally:
            if self.close_image:
                with anyio.CancelScope(shield=True):
                    await anyio.to_thread.run_sync(self.close_image)


class PokemonCardResponse(BaseModel):
    card_id: UUID
    source_card_id: str
    set_code: str
    series_name: str
    name: str
    category: str
    element: str
    hp: int | None
    stage: str
    card_number: str
    rarity: str
    illustrator: str
    notes: str
    image_width: int
    image_height: int


class PokemonSeriesResponse(BaseModel):
    set_code: str
    series_name: str
    total: int


class PokemonCatalogResponse(BaseModel):
    items: list[PokemonCardResponse]
    total: int
    page: int
    page_size: int
    series: list[PokemonSeriesResponse]


@router.get("", response_model=PokemonCatalogResponse)
async def list_cards(
    user_id: CurrentUserId,
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=40),
    set_code: str | None = Query(None, min_length=1, max_length=128),
):
    try:
        return await get_catalog(
            user_id=user_id, page=page, page_size=page_size, set_code=set_code
        )
    except PokemonCatalogAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/{card_id}/image")
async def card_image(
    card_id: UUID,
    user_id: CurrentUserId,
    if_none_match: str | None = Header(None),
):
    try:
        image = await get_card_image(
            user_id=user_id, card_id=str(card_id), if_none_match=if_none_match
        )
    except PokemonCatalogAccessError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PokemonCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PokemonCatalogStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    headers = {
        "Cache-Control": "private, max-age=0, must-revalidate",
        "ETag": image.etag,
        "X-Content-Type-Options": "nosniff",
    }
    if image.chunks is None:
        return Response(status_code=304, headers=headers)
    headers["Content-Length"] = str(image.content_length)
    return _CardImageResponse(image, headers)
