"""User-scoped channel linking service."""

from __future__ import annotations

from uuid import UUID

from src.server.channels.adapters.wechat_ilink import WeChatILinkAdapter
from src.server.channels.contracts import LinkStatus
from src.server.database import channels as channel_db
from src.server.models.channels import (
    ChannelStatus,
    LinkAttemptResponse,
    UpdateChannelRequest,
)


async def get_status(user_id: str, adapter: WeChatILinkAdapter) -> ChannelStatus:
    row = await channel_db.get_user_binding(user_id, adapter.channel_type)
    if not row:
        return ChannelStatus(channel_type=adapter.channel_type, status="unlinked", idle_timeout_seconds=21600)
    return ChannelStatus(
        channel_type=adapter.channel_type,
        status=row["status"],
        display_name=row.get("display_name"),
        idle_timeout_seconds=int(row.get("idle_timeout_seconds") or 21600),
        last_error_code=row.get("last_error_code"),
    )


async def start_link(user_id: str, adapter: WeChatILinkAdapter) -> LinkAttemptResponse:
    challenge = await adapter.begin_link()
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
    attempt = await channel_db.get_link_attempt_for_user(user_id, attempt_id)
    if not attempt:
        raise LookupError("link attempt not found")
    challenge = channel_db.challenge_from_row(attempt)
    result = await adapter.poll_link(challenge, verification_code)
    if result.next_poll_state:
        await channel_db.update_link_poll_state(attempt_id, result.next_poll_state)
    await channel_db.update_link_attempt_status(attempt_id, result.status.value)
    if result.status is LinkStatus.LINKED:
        if not result.credentials or not result.binding or not result.routing:
            raise RuntimeError("linked response missing credentials")
        await channel_db.activate_binding(
            user_id=user_id,
            channel_type=adapter.channel_type,
            binding=result.binding,
            route=result.routing,
            credentials=result.credentials,
        )
    return LinkAttemptResponse(
        attempt_id=attempt_id,
        channel_type=adapter.channel_type,
        status=result.status.value,
        expires_at=attempt["expires_at"],
        verification_required=result.status is LinkStatus.VERIFICATION_REQUIRED,
    )


async def cancel_link(user_id: str, attempt_id: UUID) -> bool:
    return await channel_db.cancel_link_attempt(user_id, attempt_id)


async def update_status(user_id: str, body: UpdateChannelRequest) -> ChannelStatus:
    row = await channel_db.update_binding_timeout(user_id, "wechat", body.idle_timeout_seconds)
    if not row:
        raise LookupError("wechat binding not found")
    return await get_status(user_id, WeChatILinkAdapter())


async def disconnect(user_id: str) -> bool:
    binding = await channel_db.get_user_binding(user_id, "wechat")
    return bool(binding and await channel_db.disconnect_binding(binding["binding_id"], user_id))
