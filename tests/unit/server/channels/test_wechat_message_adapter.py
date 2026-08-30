"""WeChat iLink message normalization and delivery tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.server.channels.adapters.wechat_ilink import WeChatILinkAdapter
from src.server.channels.contracts import (
    BindingRoute,
    InboundKind,
    OutboundMessage,
    ReplyContext,
    TextPart,
)


def _binding() -> BindingRoute:
    return BindingRoute(binding_ref="b1", peer_ref="peer-1")


def test_only_bound_sender_text_and_image_become_processable() -> None:
    adapter = WeChatILinkAdapter(api=AsyncMock())
    inbound = adapter.normalize(
        {
            "message_id": "m1",
            "message_type": 1,
            "from_user_id": "peer-1",
            "context_token": "ctx",
            "create_time_ms": 1720000000000,
            "item_list": [
                {"type": 1, "text_item": {"text": "请解释"}},
                {
                    "type": 2,
                    "image_item": {
                        "media": {
                            "encrypt_query_param": "q",
                            "aes_key": "a",
                        },
                        "thumb_width": 20,
                        "thumb_height": 30,
                    },
                },
            ],
        },
        _binding(),
    )
    assert inbound.kind is InboundKind.MESSAGE
    assert inbound.text == "请解释"
    assert len(inbound.media) == 1
    assert inbound.reply_context is not None


@pytest.mark.parametrize("item_type", [3, 4, 5])
def test_voice_file_and_video_are_ignored_without_download(item_type: int) -> None:
    adapter = WeChatILinkAdapter(api=AsyncMock())
    inbound = adapter.normalize(
        {
            "message_id": "m-ignore",
            "message_type": 1,
            "from_user_id": "peer-1",
            "item_list": [{"type": item_type, "file_item": {}}],
        },
        _binding(),
    )
    assert inbound.kind is InboundKind.IGNORED


@pytest.mark.asyncio
async def test_delivery_uses_explicit_inbound_context_and_client_id() -> None:
    api = AsyncMock()
    api.send_message.return_value = {"ret": 0}
    adapter = WeChatILinkAdapter(api=api)
    await adapter.deliver(
        credentials=__import__(
            "src.server.channels.contracts", fromlist=["BindingCredentials"]
        ).BindingCredentials(
            binding_ref="b1",
            channel_type="wechat",
            values=(
                ("token", "secret"),
                ("base_url", "https://base.invalid"),
                ("user_id", "peer-1"),
            ),
        ),
        reply_context=ReplyContext(
            route_ref="peer-1", values=(("context_token", "ctx"),)
        ),
        message=OutboundMessage(client_id="client-1", parts=(TextPart(text="答复"),)),
    )
    sent = api.send_message.await_args.args[2]
    assert sent["client_id"] == "client-1"
    assert sent["context_token"] == "ctx"
