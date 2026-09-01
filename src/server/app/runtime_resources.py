"""Runtime resource status and bounded recovery endpoints."""

from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ptc_agent.tokenizer_resource import (
    TokenizerResourceStatus,
    get_tokenizer_resource_status,
    prepare_tokenizer_resource,
)
from src.server.utils.api import CurrentUserId

router = APIRouter(prefix="/api/v1/runtime-resources", tags=["Runtime Resources"])


class TokenizerStatusResponse(BaseModel):
    encoding: str
    status: Literal["ready", "approximate"]
    exact: bool
    error_code: str | None = None


def _public_status(status: TokenizerResourceStatus) -> TokenizerStatusResponse:
    return TokenizerStatusResponse(**status.to_public_dict())


@router.get("/tokenizer", response_model=TokenizerStatusResponse)
async def get_tokenizer_status(_user_id: CurrentUserId) -> TokenizerStatusResponse:
    return _public_status(get_tokenizer_resource_status())


@router.post("/tokenizer/download", response_model=TokenizerStatusResponse)
async def download_tokenizer_vocabulary(
    _user_id: CurrentUserId,
) -> TokenizerStatusResponse:
    try:
        status = await asyncio.to_thread(
            prepare_tokenizer_resource,
            allow_download=True,
        )
    except Exception:
        raise HTTPException(
            status_code=503,
            detail={"code": "tokenizer_vocabulary_unavailable"},
        ) from None

    if not status.exact:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "tokenizer_vocabulary_unavailable",
                "resource_status": status.to_public_dict(),
            },
        )
    return _public_status(status)
