from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.server.channels.contracts import LinkChallenge, LinkPollState
from tests.conftest import create_test_app


@pytest_asyncio.fixture
async def client():
    from src.server.app.channels import router

    app = create_test_app(router)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as value:
        yield value


@pytest.mark.asyncio
async def test_create_link_attempt_returns_qr_without_credentials(client):
    challenge = LinkChallenge(
        channel_type="wechat",
        challenge_ref="secret-qr-token",
        qr_code_url="data:image/png;base64,qr",
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        provider_poll_state=LinkPollState((("qrcode", "secret-qr-token"),)),
    )
    with (
        patch("src.server.services.channels.linking.WeChatILinkAdapter.begin_link", new=AsyncMock(return_value=challenge)),
        patch("src.server.services.channels.linking.channel_db.create_link_attempt", new=AsyncMock(return_value=uuid4())),
    ):
        response = await client.post("/api/v1/channels/wechat/link-attempts")
    assert response.status_code == 201
    body = response.json()
    assert body["qr_code_url"] == challenge.qr_code_url
    assert "secret-qr-token" not in str(body)


@pytest.mark.asyncio
async def test_get_wechat_status_is_scoped_to_current_user(client):
    with patch(
        "src.server.services.channels.linking.channel_db.get_user_binding",
        new=AsyncMock(return_value=None),
    ) as get_binding:
        response = await client.get("/api/v1/channels/wechat")
    assert response.status_code == 200
    assert response.json()["status"] == "unlinked"
    get_binding.assert_awaited_once_with("test-user-123", "wechat")
