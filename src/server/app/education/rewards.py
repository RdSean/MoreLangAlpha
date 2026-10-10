"""Authenticated household rewards API."""

from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import Response

from src.server.app.education.pokemon_cards import _CardImageResponse
from src.server.app.education.reward_models import (
    OpenedRewardPack,
    PurchaseRequest,
    RewardCollectionPage,
    RewardLevel,
    RewardPack,
    RewardPage,
    RewardPrices,
    RewardSettings,
    RewardSummary,
    RewardTransaction,
)
from src.server.services import education_rewards as service
from src.server.services.education_pokemon_catalog import PokemonCatalogStorageError
from src.server.utils.api import CurrentUserId

router = APIRouter(prefix="/api/v1/education/rewards", tags=["Education rewards"])


async def call(operation, **kwargs):
    try:
        return await operation(**kwargs)
    except service.RewardAccessError as exc:
        raise HTTPException(403, detail=str(exc)) from exc
    except service.RewardNotFound as exc:
        raise HTTPException(404, detail=str(exc)) from exc
    except service.RewardConflict as exc:
        raise HTTPException(409, detail=str(exc)) from exc
    except PokemonCatalogStorageError as exc:
        raise HTTPException(503, detail=str(exc)) from exc


@router.get("/summary", response_model=RewardSummary)
async def summary(
    user_id: CurrentUserId, student_id: str | None = Query(None, max_length=255)
):
    return await call(service.summary, user_id=user_id, student_id=student_id)


@router.post("/sync", response_model=RewardSummary)
async def sync(
    user_id: CurrentUserId, student_id: str | None = Query(None, max_length=255)
):
    return await call(service.sync, user_id=user_id, student_id=student_id)


@router.get("/settings", response_model=RewardSettings)
async def settings(user_id: CurrentUserId):
    return await call(service.get_settings, user_id=user_id)


@router.put("/settings", response_model=RewardSettings)
async def update_settings(body: RewardPrices, user_id: CurrentUserId):
    return await call(
        service.update_settings, user_id=user_id, prices=body.model_dump()
    )


@router.post("/purchases", response_model=RewardPack)
async def purchase(body: PurchaseRequest, user_id: CurrentUserId):
    return await call(
        service.purchase,
        user_id=user_id,
        pack_type=body.pack_type,
        expected_price=body.expected_price,
        idempotency_key=str(body.idempotency_key),
    )


@router.post("/packs/{pack_id}/open", response_model=OpenedRewardPack)
async def open_pack(pack_id: UUID, user_id: CurrentUserId):
    return await call(service.open_pack, user_id=user_id, pack_id=str(pack_id))


@router.get("/packs", response_model=RewardPage[RewardPack])
async def packs(
    user_id: CurrentUserId,
    student_id: str | None = Query(None, max_length=255),
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=40),
    unopened: bool = False,
):
    return await call(
        service.list_records,
        user_id=user_id,
        student_id=student_id,
        kind="packs",
        page=page,
        page_size=page_size,
        unopened=unopened,
    )


@router.get("/collection", response_model=RewardCollectionPage)
async def collection(
    user_id: CurrentUserId,
    student_id: str | None = Query(None, max_length=255),
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=40),
    level: RewardLevel | None = None,
    set_code: str | None = Query(None, max_length=128),
):
    return await call(
        service.list_records,
        user_id=user_id,
        student_id=student_id,
        kind="collection",
        page=page,
        page_size=page_size,
        level=level,
        set_code=set_code,
    )


@router.get("/transactions", response_model=RewardPage[RewardTransaction])
async def transactions(
    user_id: CurrentUserId,
    student_id: str | None = Query(None, max_length=255),
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(20, ge=1, le=40),
):
    return await call(
        service.list_records,
        user_id=user_id,
        student_id=student_id,
        kind="transactions",
        page=page,
        page_size=page_size,
    )


@router.get("/cards/{card_id}/image")
async def card_image(
    card_id: UUID,
    user_id: CurrentUserId,
    student_id: str | None = Query(None, max_length=255),
    if_none_match: str | None = Header(None),
):
    image = await call(
        service.get_card_image,
        user_id=user_id,
        student_id=student_id,
        card_id=str(card_id),
        if_none_match=if_none_match,
    )
    headers = {
        "Cache-Control": "private, max-age=0, must-revalidate",
        "ETag": image.etag,
        "X-Content-Type-Options": "nosniff",
    }
    if image.chunks is None:
        return Response(status_code=304, headers=headers)
    headers["Content-Length"] = str(image.content_length)
    return _CardImageResponse(image, headers)
