"""User-scoped channel linking service."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from src.config.settings import get_channel_gateway_config
from src.server.channels.adapters.wechat_ilink import WeChatILinkAdapter
from src.server.channels.contracts import LinkPollResult, LinkStatus
from src.server.database import channels as channel_db
from src.server.models.channels import (
    ChannelStatus,
    LinkAttemptResponse,
    UpdateChannelRequest,
)


async def get_status(user_id: str, adapter: WeChatILinkAdapter) -> ChannelStatus:
    row = await channel_db.get_user_binding(user_id, adapter.channel_type)
    if not row:
        return ChannelStatus(
            channel_type=adapter.channel_type,
            status="unlinked",
            idle_timeout_seconds=21600,
        )
    return ChannelStatus(
        channel_type=adapter.channel_type,
        status=row["status"],
        display_name=row.get("display_name"),
        idle_timeout_seconds=int(row.get("idle_timeout_seconds") or 21600),
        last_error_code=row.get("last_error_code"),
    )


async def start_link(user_id: str, adapter: WeChatILinkAdapter) -> LinkAttemptResponse:
    previous_credentials = await channel_db.get_active_binding_credentials(
        user_id, adapter.channel_type
    )
    challenge = await adapter.begin_link(previous_credentials)
    attempt_id = await channel_db.create_link_attempt(
        user_id=user_id,
        channel_type=adapter.channel_type,
        challenge=challenge,
    )
    return LinkAttemptResponse(
        attempt_id=attempt_id,
        channel_type=adapter.channel_type,
        status="waiting",
        qr_code_url=challenge.qr_code_url,
        expires_at=challenge.expires_at,
    )


async def poll_link(
    user_id: str,
    attempt_id: UUID,
    adapter: WeChatILinkAdapter,
    verification_code: str | None = None,
) -> LinkAttemptResponse:
    worker_id = f"channel-link-{uuid4()}"
    config = get_channel_gateway_config()
    attempt = await channel_db.claim_link_attempt(
        user_id,
        attempt_id,
        worker_id,
        lease_seconds=config.link_attempt_lease_seconds,
    )
    if not attempt:
        current = await channel_db.get_link_attempt_for_user(user_id, attempt_id)
        if not current:
            raise LookupError("link attempt not found")
        return _link_attempt_response(current)
    challenge = channel_db.challenge_from_row(attempt)
    try:
        result = await asyncio.wait_for(
            adapter.poll_link(challenge, verification_code),
            timeout=config.link_poll_timeout_seconds,
        )
    except asyncio.TimeoutError:
        result = LinkPollResult(status=LinkStatus.WAITING)
    await channel_db.finalize_link_attempt(
        user_id=user_id,
        attempt_id=attempt_id,
        worker_id=worker_id,
        lease_generation=int(attempt["lease_generation"]),
        result=result,
    )
    current = await channel_db.get_link_attempt_for_user(user_id, attempt_id)
    if not current:
        raise LookupError("link attempt not found")
    return _link_attempt_response(current)


def _link_attempt_response(attempt: dict) -> LinkAttemptResponse:
    return LinkAttemptResponse(
        attempt_id=attempt["attempt_id"],
        channel_type=attempt["channel_type"],
        status=attempt["status"],
        qr_code_url=attempt.get("qr_code_url"),
        expires_at=attempt["expires_at"],
        verification_required=attempt["status"]
        == LinkStatus.VERIFICATION_REQUIRED.value,
    )


async def cancel_link(user_id: str, attempt_id: UUID) -> bool:
    return await channel_db.cancel_link_attempt(user_id, attempt_id)


async def update_status(user_id: str, body: UpdateChannelRequest) -> ChannelStatus:
    row = await channel_db.update_binding_timeout(
        user_id, "wechat", body.idle_timeout_seconds
    )
    if not row:
        raise LookupError("wechat binding not found")
    return await get_status(user_id, WeChatILinkAdapter())


async def disconnect(user_id: str) -> bool:
    binding = await channel_db.get_user_binding(user_id, "wechat")
    return bool(
        binding and await channel_db.disconnect_binding(binding["binding_id"], user_id)
    )
