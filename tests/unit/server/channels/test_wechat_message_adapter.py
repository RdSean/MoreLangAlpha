"""WeChat iLink message normalization and delivery tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from src.server.channels.adapters.wechat_ilink import (
    BindingExpiredError,
    WeChatILinkAdapter,
)
from src.server.channels.contracts import (
    BindingCredentials,
    BindingRoute,
    InboundKind,
    OutboundMessage,
    ReplyContext,
    TextPart,
)


def _binding() -> BindingRoute:
    return BindingRoute(binding_ref="b1", peer_ref="peer-1")


def _credentials() -> BindingCredentials:
    return BindingCredentials(
        binding_ref="b1",
        channel_type="wechat",
        values=(
            ("token", "secret"),
            ("base_url", "https://base.invalid"),
            ("user_id", "peer-1"),
        ),
    )


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


@pytest.mark.asyncio
async def test_typing_uses_cached_ticket_and_stops_with_status_two() -> None:
    api = AsyncMock()
    api.get_config.return_value = {"typing_ticket": "ticket-1"}
    adapter = WeChatILinkAdapter(api=api)
    context = ReplyContext("peer-1", (("context_token", "ctx"),))

    await adapter.send_typing(_credentials(), context)
    await adapter.send_typing(_credentials(), context)
    await adapter.stop_typing(_credentials(), context)

    api.get_config.assert_awaited_once_with(
        "https://base.invalid", "secret", "peer-1", "ctx"
    )
    assert api.send_typing.await_count == 3
    assert api.send_typing.await_args_list[0].args == (
        "https://base.invalid",
        "secret",
        "peer-1",
        "ticket-1",
        1,
    )
    assert api.send_typing.await_args_list[-1].args[-1] == 2


@pytest.mark.asyncio
async def test_binding_lifecycle_notifies_ilink_without_propagating_errors() -> None:
    api = AsyncMock()
    api.notify_start.side_effect = RuntimeError("offline")
    api.notify_stop.side_effect = RuntimeError("offline")
    adapter = WeChatILinkAdapter(api=api)

    await adapter.on_binding_start(_credentials())
    await adapter.on_binding_stop(_credentials())

    api.notify_start.assert_awaited_once_with("https://base.invalid", "secret")
    api.notify_stop.assert_awaited_once_with("https://base.invalid", "secret")


def test_wechat_final_parts_normalize_markdown_and_preserve_code_blocks() -> None:
    adapter = WeChatILinkAdapter(max_text_length=2000)
    parts = adapter.prepare_outbound_parts(
        (
            TextPart(
                "# Title\n\n| Name | Value |\n| --- | --- |\n| mode | fast |\n\n```python\nprint('ok')\n```"
            ),
        )
    )

    assert parts == (
        TextPart("【Title】\n\n- Name: mode\n  Value: fast\n\n```python\nprint('ok')\n```"),
    )


def test_wechat_final_parts_globally_pack_short_units() -> None:
    adapter = WeChatILinkAdapter(max_text_length=10)

    parts = adapter.prepare_outbound_parts(
        (TextPart("第一段"), TextPart("第二段"), TextPart("第三段"))
    )

    assert parts == (TextPart("第一段\n\n第二段"), TextPart("第三段"))


def test_wechat_final_parts_split_oversized_units_naturally() -> None:
    adapter = WeChatILinkAdapter(max_text_length=8)

    parts = adapter.prepare_outbound_parts((TextPart("aaaaa\nbbbbb"),))

    assert parts == (TextPart("aaaaa"), TextPart("bbbbb"))


def test_wechat_oversized_code_block_keeps_fences_in_each_part() -> None:
    adapter = WeChatILinkAdapter(max_text_length=18)

    parts = adapter.prepare_outbound_parts(
        (TextPart("```python\n" + "abcdefghij " * 5 + "\n```"),)
    )

    assert len(parts) > 1
    assert all(part.text.startswith("```python\n") for part in parts)
    assert all(part.text.endswith("\n```") for part in parts)


def test_image_item_aeskey_takes_precedence_over_cdn_aes_key() -> None:
    adapter = WeChatILinkAdapter(api=AsyncMock())

    inbound = adapter.normalize(
        {
            "message_id": "m-image-key",
            "message_type": 1,
            "from_user_id": "peer-1",
            "context_token": "ctx",
            "item_list": [
                {
                    "type": 2,
                    "image_item": {
                        "aeskey": "image-item-key",
                        "media": {
                            "encrypt_query_param": "q",
                            "aes_key": "cdn-key",
                        },
                    },
                },
            ],
        },
        _binding(),
    )

    assert inbound.media[0].aes_key == "image-item-key"


@pytest.mark.asyncio
async def test_fetch_updates_translates_expired_ilink_session() -> None:
    api = AsyncMock()
    api.get_updates.side_effect = __import__(
        "wechatbot.errors", fromlist=["ApiError"]
    ).ApiError("session expired", errcode=-14)
    adapter = WeChatILinkAdapter(api=api)

    with pytest.raises(BindingExpiredError):
        await adapter.fetch_updates(_credentials(), cursor=None)


def test_message_without_per_message_context_token_is_rejected() -> None:
    adapter = WeChatILinkAdapter(api=AsyncMock())

    inbound = adapter.normalize(
        {
            "message_id": "m-no-context",
            "message_type": 1,
            "from_user_id": "peer-1",
            "item_list": [{"type": 1, "text_item": {"text": "hello"}}],
        },
        _binding(),
    )

    assert inbound.kind is InboundKind.REJECTED
    assert inbound.reason == "missing_reply_context"


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


@pytest.mark.asyncio
async def test_delivery_rejects_missing_context_token_without_sending() -> None:
    api = AsyncMock()
    adapter = WeChatILinkAdapter(api=api)

    receipt = await adapter.deliver(
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
        reply_context=ReplyContext(route_ref="peer-1"),
        message=OutboundMessage(client_id="client-1", parts=(TextPart(text="答复"),)),
    )

    assert not receipt.accepted
    assert receipt.detail == "missing_context_token"
    api.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_delivery_classifies_ilink_context_budget_error() -> None:
    from src.server.channels.contracts import ChannelMessageBudgetError

    api = AsyncMock()
    api.send_message.side_effect = __import__(
        "wechatbot.errors", fromlist=["ApiError"]
    ).ApiError("rate limited", errcode=-2, payload={"ret": -2})
    adapter = WeChatILinkAdapter(api=api)

    with pytest.raises(ChannelMessageBudgetError) as exc_info:
        await adapter.deliver(
            _credentials(),
            ReplyContext("peer-1", (("context_token", "ctx"),)),
            OutboundMessage("client-1", (TextPart("答复"),)),
        )

    assert exc_info.value.provider_code == -2


@pytest.mark.asyncio
async def test_delivery_checks_business_ret_when_sdk_returns_payload() -> None:
    from src.server.channels.contracts import ChannelMessageBudgetError

    api = AsyncMock()
    api.send_message.return_value = {"ret": -2, "errmsg": "rate limited"}
    adapter = WeChatILinkAdapter(api=api)

    with pytest.raises(ChannelMessageBudgetError):
        await adapter.deliver(
            _credentials(),
            ReplyContext("peer-1", (("context_token", "ctx"),)),
            OutboundMessage("client-1", (TextPart("答复"),)),
        )


@pytest.mark.asyncio
async def test_download_image_stops_streaming_when_ciphertext_exceeds_limit(
    monkeypatch,
) -> None:
    class Response:
        content_length = None

        class Content:
            async def iter_chunked(self, size):
                yield b"x" * 21

        content = Content()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def raise_for_status(self):
            return None

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        def get(self, *args, **kwargs):
            return Response()

    monkeypatch.setattr(
        "src.server.channels.adapters.wechat_ilink.aiohttp.ClientSession", Session
    )
    adapter = WeChatILinkAdapter(api=AsyncMock())

    with pytest.raises(ValueError, match="ciphertext exceeds byte limit"):
        await adapter.download_image(
            __import__(
                "src.server.channels.contracts", fromlist=["InboundMedia"]
            ).InboundMedia(ref="ref", mime_type="image/*", aes_key="not-used"),
            max_bytes=4,
        )
