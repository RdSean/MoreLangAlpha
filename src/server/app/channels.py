"""Authenticated API for user-owned channel bindings."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from src.server.channels.adapters.wechat_ilink import WeChatILinkAdapter
from src.server.models.channels import (
    LinkAttemptResponse,
    LinkPollRequest,
    UpdateChannelRequest,
)
from src.server.services.channels import linking
from src.server.utils.api import CurrentUserId

router = APIRouter(prefix="/api/v1/channels", tags=["Channels"])


def _adapter() -> WeChatILinkAdapter:
    return WeChatILinkAdapter()


@router.get("/wechat")
async def get_wechat_status(user_id: CurrentUserId):
    return await linking.get_status(user_id, _adapter())


@router.post(
    "/wechat/link-attempts",
    response_model=LinkAttemptResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_wechat_link_attempt(user_id: CurrentUserId):
    return await linking.start_link(user_id, _adapter())


@router.post(
    "/wechat/link-attempts/{attempt_id}/poll", response_model=LinkAttemptResponse
)
async def poll_wechat_link_attempt(
    attempt_id: UUID, body: LinkPollRequest, user_id: CurrentUserId
):
    try:
        return await linking.poll_link(
            user_id, attempt_id, _adapter(), body.verification_code
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="link attempt not found") from exc


@router.delete(
    "/wechat/link-attempts/{attempt_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def cancel_wechat_link_attempt(attempt_id: UUID, user_id: CurrentUserId):
    if not await linking.cancel_link(user_id, attempt_id):
        raise HTTPException(status_code=404, detail="link attempt not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch("/wechat")
async def update_wechat_status(body: UpdateChannelRequest, user_id: CurrentUserId):
    try:
        return await linking.update_status(user_id, body)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail="wechat binding not found") from exc


@router.delete("/wechat", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_wechat(user_id: CurrentUserId):
    if not await linking.disconnect(user_id):
        raise HTTPException(status_code=404, detail="wechat binding not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
