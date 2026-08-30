"""WeChat iLink linking behavior using the SDK's low-level API."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from src.server.channels.adapters.wechat_ilink import WeChatILinkAdapter
from src.server.channels.contracts import LinkStatus


@pytest.mark.asyncio
async def test_link_status_and_credentials_are_mapped_without_file_storage() -> None:
    api = AsyncMock()
    api.get_qr_code.return_value = {
        "qrcode": "opaque-qrcode",
        "qrcode_img_content": "data:image/png;base64,qr",
        "expires_in": 300,
    }
    adapter = WeChatILinkAdapter(api=api)

    challenge = await adapter.begin_link()
    assert challenge.qr_code_url.startswith("data:image/")
    assert challenge.provider_poll_state.values[0] == ("qrcode", "opaque-qrcode")

    api.poll_qr_status.return_value = {
        "status": "confirmed",
        "bot_token": "secret-token",
        "ilink_bot_id": "bot-1",
        "ilink_user_id": "peer-1",
        "baseurl": "https://redirected.invalid",
    }
    result = await adapter.poll_link(challenge)

    assert result.status is LinkStatus.LINKED
    assert result.credentials is not None
    assert ("token", "secret-token") in result.credentials.values
    assert result.routing is not None
    assert result.routing.peer_ref == "peer-1"


@pytest.mark.asyncio
async def test_verify_code_is_forwarded_once_and_redirect_state_is_returned() -> None:
    api = AsyncMock()
    adapter = WeChatILinkAdapter(api=api)
    from src.server.channels.contracts import LinkChallenge, LinkPollState

    challenge = LinkChallenge(
        channel_type="wechat",
        challenge_ref="attempt-1",
        qr_code_url="data:image/png;base64,qr",
        expires_at=datetime.now(UTC),
        provider_poll_state=LinkPollState(
            values=(("qrcode", "qrcode-1"), ("poll_base_url", "https://base.invalid"))
        ),
    )
    api.poll_qr_status.return_value = {
        "status": "scaned_but_redirect",
        "redirect_host": "new.invalid",
    }

    result = await adapter.poll_link(challenge, verification_code="123456")
    api.poll_qr_status.assert_awaited_once_with(
        "https://base.invalid", "qrcode-1", "123456"
    )
    assert result.status is LinkStatus.SCANNED
    assert result.next_poll_state is not None
    assert result.next_poll_state.values[1] == ("poll_base_url", "https://new.invalid")
    assert "123456" not in repr(adapter)
