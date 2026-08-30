"""WeChat iLink channel adapter built on the public wechatbot SDK API."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import aiohttp
from PIL import Image
from io import BytesIO

from wechatbot.crypto import decode_aes_key, decrypt_aes_ecb
from wechatbot.errors import ApiError
from wechatbot.protocol import CDN_BASE_URL, DEFAULT_BASE_URL, ILinkApi
from wechatbot.types import MessageItemType, MessageType

from src.server.channels.adapters.base import ChannelAdapter
from src.server.channels.contracts import (
    BindingCredentials,
    ChannelBindingExpiredError,
    BindingRoute,
    BindingView,
    DeliveryReceipt,
    InboundKind,
    InboundMedia,
    InboundMessage,
    LinkChallenge,
    LinkPollResult,
    LinkPollState,
    LinkStatus,
    OutboundMessage,
    ReplyContext,
    ResolvedImage,
    UpdateBatch,
    TextPart,
)

# Kept for adapter consumers that imported the former concrete error.
BindingExpiredError = ChannelBindingExpiredError


class WeChatILinkAdapter(ChannelAdapter):
    channel_type = "wechat"

    def __init__(
        self,
        *,
        api: ILinkApi | None = None,
        base_url: str = DEFAULT_BASE_URL,
        max_text_length: int = 2000,
    ) -> None:
        self.api = api or ILinkApi()
        self.base_url = base_url.rstrip("/")
        self.max_text_length = max_text_length
        self.max_outbound_text_length = max_text_length

    async def begin_link(
        self, previous_credentials: BindingCredentials | None = None
    ) -> LinkChallenge:
        response = await self.api.get_qr_code(self.base_url, [])
        qrcode = response.get("qrcode")
        image = response.get("qrcode_img_content")
        if not isinstance(qrcode, str) or not qrcode:
            raise RuntimeError("iLink QR response missing qrcode")
        if not isinstance(image, str) or not image:
            raise RuntimeError("iLink QR response missing image")
        expires_at = datetime.now(UTC) + timedelta(
            seconds=float(response.get("expires_in") or 300)
        )
        return LinkChallenge(
            channel_type=self.channel_type,
            challenge_ref=qrcode,
            qr_code_url=image,
            expires_at=expires_at,
            provider_poll_state=LinkPollState(
                values=(("qrcode", qrcode), ("poll_base_url", self.base_url))
            ),
        )

    async def poll_link(
        self, challenge: LinkChallenge, verification_code: str | None = None
    ) -> LinkPollResult:
        state = dict(challenge.provider_poll_state.values)
        qrcode = state.get("qrcode")
        poll_base_url = state.get("poll_base_url", self.base_url)
        if not qrcode:
            raise RuntimeError("iLink QR poll state is missing qrcode")
        try:
            response = await self.api.poll_qr_status(
                poll_base_url, qrcode, verification_code
            )
        except ApiError:
            raise
        status = str(response.get("status") or "").lower()
        next_state = None
        redirect_host = response.get("redirect_host")
        if status == "scaned_but_redirect" and redirect_host:
            next_state = LinkPollState(
                values=(
                    ("qrcode", qrcode),
                    ("poll_base_url", f"https://{redirect_host}"),
                )
            )
        mapped = {
            "wait": LinkStatus.WAITING,
            "waiting": LinkStatus.WAITING,
            "scaned": LinkStatus.SCANNED,
            "scaned_but_redirect": LinkStatus.SCANNED,
            "need_verifycode": LinkStatus.VERIFICATION_REQUIRED,
            "confirmed": LinkStatus.LINKED,
            "expired": LinkStatus.EXPIRED,
            "verify_code_blocked": LinkStatus.FAILED,
            "binded_redirect": LinkStatus.FAILED,
        }.get(status, LinkStatus.WAITING)
        if mapped is not LinkStatus.LINKED:
            return LinkPollResult(status=mapped, next_poll_state=next_state)
        token = response.get("bot_token")
        bot_id = response.get("ilink_bot_id")
        user_id = response.get("ilink_user_id")
        if not all(isinstance(item, str) and item for item in (token, bot_id, user_id)):
            return LinkPollResult(status=LinkStatus.FAILED)
        linked_base_url = str(response.get("baseurl") or poll_base_url).rstrip("/")
        return LinkPollResult(
            status=LinkStatus.LINKED,
            binding=BindingView(
                binding_ref=str(bot_id),
                channel_type=self.channel_type,
                display_name=None,
            ),
            routing=BindingRoute(binding_ref=str(bot_id), peer_ref=str(user_id)),
            credentials=BindingCredentials(
                binding_ref=str(bot_id),
                channel_type=self.channel_type,
                values=(
                    ("token", str(token)),
                    ("base_url", linked_base_url),
                    ("bot_id", str(bot_id)),
                    ("user_id", str(user_id)),
                ),
            ),
        )

    async def fetch_updates(
        self, credentials: BindingCredentials, cursor: str | None
    ) -> UpdateBatch:
        values = dict(credentials.values)
        try:
            response = await self.api.get_updates(
                values["base_url"], values["token"], cursor or ""
            )
        except ApiError as exc:
            if exc.is_session_expired:
                raise ChannelBindingExpiredError from exc
            raise
        return UpdateBatch(
            updates=tuple(response.get("msgs") or ()),
            next_cursor=response.get("get_updates_buf") or cursor,
        )

    def normalize(self, raw_update: object, binding: BindingRoute) -> InboundMessage:
        if not isinstance(raw_update, dict):
            return InboundMessage(
                provider_message_id="invalid",
                peer_ref=None,
                received_at=datetime.now(UTC),
                kind=InboundKind.REJECTED,
                reason="malformed_update",
            )
        raw = raw_update
        provider_id = str(raw.get("msg_id") or raw.get("message_id") or "")
        peer = raw.get("from_user_id")
        received_at = (
            datetime.fromtimestamp(float(raw.get("create_time_ms") or 0) / 1000, tz=UTC)
            if raw.get("create_time_ms")
            else datetime.now(UTC)
        )
        if raw.get("message_type") != MessageType.USER or peer != binding.peer_ref:
            return InboundMessage(
                provider_message_id=provider_id or "invalid",
                peer_ref=str(peer) if peer else None,
                received_at=received_at,
                kind=InboundKind.REJECTED,
                reason="sender_not_bound",
            )
        items = raw.get("item_list")
        if not isinstance(items, list):
            items = []
        texts: list[str] = []
        media: list[InboundMedia] = []
        unsupported = False
        for item in items:
            if not isinstance(item, dict):
                continue
            item_type = item.get("type")
            if item_type == MessageItemType.TEXT:
                text = (item.get("text_item") or {}).get("text")
                if text:
                    texts.append(str(text))
            elif item_type == MessageItemType.IMAGE:
                image = item.get("image_item") or {}
                cdn = image.get("media") or {}
                ref = cdn.get("encrypt_query_param")
                if ref:
                    media.append(
                        InboundMedia(
                            ref=str(ref),
                            mime_type="image/*",
                            aes_key=str(image.get("aeskey") or cdn.get("aes_key") or "")
                            or None,
                            encrypt_type=_int_or_none(cdn.get("encrypt_type")),
                            width=_int_or_none(image.get("thumb_width")),
                            height=_int_or_none(image.get("thumb_height")),
                        )
                    )
            elif item_type in (
                MessageItemType.VOICE,
                MessageItemType.FILE,
                MessageItemType.VIDEO,
            ):
                unsupported = True
        if unsupported and not texts and not media:
            return InboundMessage(
                provider_message_id=provider_id or "invalid",
                peer_ref=str(peer),
                received_at=received_at,
                kind=InboundKind.IGNORED,
                reason="unsupported_media",
            )
        context_token = raw.get("context_token")
        if not isinstance(context_token, str) or not context_token:
            return InboundMessage(
                provider_message_id=provider_id or "invalid",
                peer_ref=str(peer),
                received_at=received_at,
                kind=InboundKind.REJECTED,
                reason="missing_reply_context",
            )
        text = "\n".join(texts) or None
        if text and len(text) > self.max_text_length:
            text = text[: self.max_text_length]
        return InboundMessage(
            provider_message_id=provider_id or "invalid",
            peer_ref=str(peer),
            received_at=received_at,
            kind=InboundKind.MESSAGE,
            text=text,
            media=tuple(media),
            reply_context=ReplyContext(
                route_ref=str(peer),
                values=(("context_token", context_token),),
            ),
        )

    async def deliver(
        self,
        credentials: BindingCredentials,
        reply_context: ReplyContext,
        message: OutboundMessage,
    ) -> DeliveryReceipt:
        values = dict(credentials.values)
        context = dict(reply_context.values)
        context_token = context.get("context_token")
        if not isinstance(context_token, str) or not context_token:
            return DeliveryReceipt(
                accepted=False,
                provider_message_id=None,
                delivered_at=datetime.now(UTC),
                detail="missing_context_token",
            )
        text = "\n".join(
            part.text for part in message.parts if isinstance(part, TextPart)
        )
        if not text:
            return DeliveryReceipt(
                accepted=False,
                provider_message_id=None,
                delivered_at=datetime.now(UTC),
                detail="empty_text",
            )
        payload = ILinkApi.build_text_message(values["user_id"], context_token, text)
        payload["client_id"] = message.client_id
        try:
            await self.api.send_message(values["base_url"], values["token"], payload)
        except ApiError as exc:
            if exc.is_session_expired:
                raise ChannelBindingExpiredError from exc
            raise
        return DeliveryReceipt(
            accepted=True,
            provider_message_id=str(payload["client_id"]),
            delivered_at=datetime.now(UTC),
        )

    async def download_image(
        self,
        media: InboundMedia,
        *,
        max_bytes: int,
        aes_key: str | None = None,
    ) -> bytes:
        url = (
            f"{CDN_BASE_URL}/download?encrypted_query_param={quote(media.ref, safe='')}"
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                response.raise_for_status()
                # AES-ECB adds at most one 16-byte block of PKCS#7 padding.
                max_ciphertext_bytes = max_bytes + 16
                if (
                    response.content_length
                    and response.content_length > max_ciphertext_bytes
                ):
                    raise ValueError("image ciphertext exceeds byte limit")
                ciphertext = bytearray()
                async for chunk in response.content.iter_chunked(64 * 1024):
                    ciphertext.extend(chunk)
                    if len(ciphertext) > max_ciphertext_bytes:
                        raise ValueError("image ciphertext exceeds byte limit")
        key = aes_key or media.aes_key
        if not key:
            raise ValueError("image media is missing aes key")
        return decrypt_aes_ecb(bytes(ciphertext), decode_aes_key(key))

    async def resolve_images(
        self,
        media: tuple[InboundMedia, ...],
        *,
        max_bytes: int,
        max_pixels: int,
    ) -> tuple[ResolvedImage, ...]:
        resolved: list[ResolvedImage] = []
        for item in media:
            data = await self.download_image(item, max_bytes=max_bytes)
            mime, width, height = self.validate_image(
                data, max_bytes=max_bytes, max_pixels=max_pixels
            )
            resolved.append(
                ResolvedImage(
                    content_ref=f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}",
                    mime_type=mime,
                    byte_size=len(data),
                    width=width,
                    height=height,
                )
            )
        return tuple(resolved)

    @staticmethod
    def validate_image(
        data: bytes, *, max_bytes: int, max_pixels: int
    ) -> tuple[str, int, int]:
        if len(data) > max_bytes:
            raise ValueError("image exceeds byte limit")
        with Image.open(BytesIO(data)) as image:
            image.verify()
        with Image.open(BytesIO(data)) as image:
            width, height = image.size
            mime = Image.MIME.get(image.format)
        if not mime or not mime.startswith("image/") or width * height > max_pixels:
            raise ValueError("image failed validation")
        return mime, width, height


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
