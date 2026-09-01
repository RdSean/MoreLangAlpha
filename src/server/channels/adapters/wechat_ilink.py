"""WeChat iLink channel adapter built on the public wechatbot SDK API."""

from __future__ import annotations

import base64
import re
import time
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
    ChannelMessageBudgetError,
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
from src.server.channels.events import MessageChunk, MessageStop

# Kept for adapter consumers that imported the former concrete error.
BindingExpiredError = ChannelBindingExpiredError

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_TABLE_RULE_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")
_FENCE_RE = re.compile(r"^```([^\n`]*)\s*$")


def _split_table_row(line: str) -> list[str]:
    row = line.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [cell.strip() for cell in row.split("|")]


def _rewrite_header(line: str) -> str:
    match = _HEADER_RE.match(line)
    if not match:
        return line.rstrip()
    title = match.group(2).strip()
    return f"【{title}】" if len(match.group(1)) == 1 else f"**{title}**"


def _rewrite_table(lines: list[str]) -> str:
    if len(lines) < 3:
        return "\n".join(lines)
    headers = _split_table_row(lines[0])
    rows = [_split_table_row(line) for line in lines[2:] if line.strip()]
    if not headers or not rows:
        return "\n".join(lines)
    rendered: list[str] = []
    for row in rows:
        pairs = []
        for index, value in enumerate(row):
            if index >= len(headers):
                break
            value = value.strip()
            if value:
                pairs.append((headers[index] or f"Column {index + 1}", value))
        if not pairs:
            continue
        rendered.append(f"- {pairs[0][0]}: {pairs[0][1]}")
        rendered.extend(f"  {label}: {value}" for label, value in pairs[1:])
    return "\n".join(rendered) if rendered else "\n".join(lines)


def _normalize_markdown(content: str) -> str:
    lines = content.splitlines()
    result: list[str] = []
    in_code = False
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        if _FENCE_RE.match(line.strip()):
            in_code = not in_code
            result.append(line)
            index += 1
            continue
        if in_code:
            result.append(line)
            index += 1
            continue
        if (
            index + 1 < len(lines)
            and "|" in lines[index]
            and _TABLE_RULE_RE.match(lines[index + 1].rstrip())
        ):
            table = [lines[index].rstrip(), lines[index + 1].rstrip()]
            index += 2
            while index < len(lines) and "|" in lines[index]:
                table.append(lines[index].rstrip())
                index += 1
            result.append(_rewrite_table(table))
            continue
        result.append(_rewrite_header(line))
        index += 1
    normalized = "\n".join(item.rstrip() for item in result)
    return re.sub(r"\n{3,}", "\n\n", normalized).strip()


def _split_markdown_blocks(content: str) -> list[str]:
    if not content:
        return []
    blocks: list[str] = []
    current: list[str] = []
    in_code = False
    for raw_line in content.splitlines():
        line = raw_line.rstrip()
        if _FENCE_RE.match(line.strip()):
            if not in_code and current:
                blocks.append("\n".join(current).strip())
                current = []
            current.append(line)
            in_code = not in_code
            if not in_code:
                blocks.append("\n".join(current).strip())
                current = []
            continue
        if in_code:
            current.append(line)
        elif not line.strip():
            if current:
                blocks.append("\n".join(current).strip())
                current = []
        else:
            current.append(line)
    if current:
        blocks.append("\n".join(current).strip())
    return [block for block in blocks if block]


def _split_delivery_units(content: str) -> list[str]:
    units: list[str] = []
    for block in _split_markdown_blocks(content):
        if _FENCE_RE.match(block.splitlines()[0].strip()):
            units.append(block)
            continue
        current: list[str] = []
        for raw_line in block.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                if current:
                    units.append("\n".join(current).strip())
                    current = []
                continue
            if current and raw_line.startswith((" ", "\t")):
                current.append(line)
            else:
                if current:
                    units.append("\n".join(current).strip())
                current = [line]
        if current:
            units.append("\n".join(current).strip())
    return [unit for unit in units if unit]


def _hard_split_plain(text: str, limit: int) -> list[str]:
    limit = max(1, limit)
    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        split_at = max(window.rfind("\n"), window.rfind(" "))
        if split_at < limit * 3 // 10:
            split_at = limit
        chunks.append(remaining[:split_at].rstrip())
        remaining = remaining[split_at:].lstrip()
    if remaining:
        chunks.append(remaining)
    return chunks or [text]


def _hard_split(text: str, limit: int) -> list[str]:
    """Split one oversized unit while keeping fenced code chunks valid."""
    lines = text.splitlines()
    if len(lines) >= 2 and _FENCE_RE.match(lines[0].strip()) and lines[-1].strip() == "```":
        opening = lines[0]
        closing = "```"
        body = "\n".join(lines[1:-1])
        body_limit = max(1, limit - len(opening) - len(closing) - 2)
        return [
            f"{opening}\n{chunk}\n{closing}" for chunk in _hard_split_plain(body, body_limit)
        ]
    return _hard_split_plain(text, limit)


def _pack_units(units: list[str], limit: int) -> list[str]:
    packed: list[str] = []
    current = ""
    for unit in units:
        if len(unit) > limit:
            if current:
                packed.append(current)
                current = ""
            packed.extend(_hard_split(unit, limit))
            continue
        candidate = unit if not current else f"{current}\n\n{unit}"
        if len(candidate) <= limit:
            current = candidate
        else:
            packed.append(current)
            current = unit
    if current:
        packed.append(current)
    return packed


def _split_final_text(content: str, limit: int) -> list[str]:
    units = _split_delivery_units(content)
    return _pack_units(units, limit) or [content]


class WeChatILinkAdapter(ChannelAdapter):
    channel_type = "wechat"
    supports_typing = True
    max_messages_per_context = 10
    continuation_command = "继续"
    continuation_notice = "内容较长，已发送前半部分。回复“继续”获取后续内容。"

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
        self._typing_tickets: dict[tuple[str, str], tuple[str, float]] = {}
        self._started_binding_tokens: set[str] = set()

    @staticmethod
    def _context_token(reply_context: ReplyContext) -> str | None:
        value = dict(reply_context.values).get("context_token")
        return value if isinstance(value, str) and value else None

    def _typing_key(
        self, credentials: BindingCredentials, reply_context: ReplyContext
    ) -> tuple[str, str]:
        return (credentials.binding_ref, reply_context.route_ref)

    def _cached_typing_ticket(
        self, credentials: BindingCredentials, reply_context: ReplyContext
    ) -> str | None:
        key = self._typing_key(credentials, reply_context)
        entry = self._typing_tickets.get(key)
        if not entry:
            return None
        if time.monotonic() - entry[1] >= 600:
            self._typing_tickets.pop(key, None)
            return None
        return entry[0]

    async def _typing_ticket(
        self, credentials: BindingCredentials, reply_context: ReplyContext
    ) -> str | None:
        cached = self._cached_typing_ticket(credentials, reply_context)
        if cached:
            return cached
        context_token = self._context_token(reply_context)
        if not context_token:
            return None
        values = dict(credentials.values)
        try:
            response = await self.api.get_config(
                values["base_url"],
                values["token"],
                reply_context.route_ref,
                context_token,
            )
        except Exception:
            return None
        ticket = response.get("typing_ticket") if isinstance(response, dict) else None
        if not isinstance(ticket, str) or not ticket:
            return None
        self._typing_tickets[self._typing_key(credentials, reply_context)] = (
            ticket,
            time.monotonic(),
        )
        return ticket

    async def on_binding_start(self, credentials: BindingCredentials) -> None:
        values = dict(credentials.values)
        token = values.get("token")
        base_url = values.get("base_url")
        if not token or not base_url or credentials.binding_ref in self._started_binding_tokens:
            return
        try:
            await self.api.notify_start(base_url, token)
        except Exception:
            return
        self._started_binding_tokens.add(credentials.binding_ref)

    async def on_binding_stop(self, credentials: BindingCredentials) -> None:
        values = dict(credentials.values)
        token = values.get("token")
        base_url = values.get("base_url")
        if not token or not base_url:
            return
        try:
            await self.api.notify_stop(base_url, token)
        except Exception:
            pass
        self._started_binding_tokens.discard(credentials.binding_ref)

    async def send_typing(
        self, credentials: BindingCredentials, reply_context: ReplyContext
    ) -> None:
        ticket = await self._typing_ticket(credentials, reply_context)
        if not ticket:
            return
        values = dict(credentials.values)
        try:
            await self.api.send_typing(
                values["base_url"],
                values["token"],
                reply_context.route_ref,
                ticket,
                1,
            )
        except Exception:
            pass

    async def stop_typing(
        self, credentials: BindingCredentials, reply_context: ReplyContext
    ) -> None:
        ticket = self._cached_typing_ticket(credentials, reply_context)
        if not ticket:
            return
        values = dict(credentials.values)
        try:
            await self.api.send_typing(
                values["base_url"],
                values["token"],
                reply_context.route_ref,
                ticket,
                2,
            )
        except Exception:
            pass

    def prepare_outbound_parts(
        self, parts: tuple[Any, ...]
    ) -> tuple[Any, ...]:
        prepared: list[Any] = []
        text_units: list[str] = []

        def flush_text() -> None:
            if not text_units:
                return
            prepared.extend(
                TextPart(chunk)
                for chunk in _pack_units(text_units, self.max_text_length)
                if chunk
            )
            text_units.clear()

        for part in parts:
            if not isinstance(part, TextPart):
                flush_text()
                prepared.append(part)
                continue
            formatted = _normalize_markdown(part.text)
            if not formatted:
                continue
            text_units.extend(_split_delivery_units(formatted))
        flush_text()
        return tuple(prepared)

    def render_message_event(self, event: Any, sink: Any) -> None:
        """Expose only main-agent ordinary text on the user-facing channel."""

        if isinstance(event, MessageChunk):
            if event.content_type not in (None, "text"):
                return
            if event.role and event.role not in {"assistant", "agent", "main"}:
                return
            if event.agent is not None and event.agent != "main":
                return
            if event.text:
                sink.on_delta(event.text)
            return
        if isinstance(event, MessageStop):
            # A final stop closes the durable answer; intermediate boundaries
            # are intentionally invisible on WeChat.
            return

    def format_tool_event(
        self,
        event: Any,
        *,
        mode: str = "all",
        preview_max_len: int = 40,
    ) -> str | None:
        return None

    async def begin_link(
        self, previous_credentials: BindingCredentials | None = None
    ) -> LinkChallenge:
        known_tokens: list[str] = []
        if previous_credentials and previous_credentials.channel_type == self.channel_type:
            token = dict(previous_credentials.values).get("token")
            if isinstance(token, str) and token:
                known_tokens.append(token)
        response = await self.api.get_qr_code(self.base_url, known_tokens)
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
            qr_code_url=_render_qr_image(image),
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
        if status == "binded_redirect":
            return LinkPollResult(
                status=LinkStatus.LINKED,
                reuse_existing_binding=True,
            )
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
            response = await self.api.send_message(
                values["base_url"], values["token"], payload
            )
        except ApiError as exc:
            if exc.is_session_expired:
                raise ChannelBindingExpiredError from exc
            if exc.errcode == -2:
                raise ChannelMessageBudgetError(
                    "iLink context message budget exhausted",
                    provider_code=exc.errcode,
                ) from exc
            raise
        if isinstance(response, dict):
            raw_code = response.get("ret")
            if raw_code in (None, 0):
                raw_code = response.get("errcode", 0)
            try:
                code = int(raw_code)
            except (TypeError, ValueError):
                code = 0
            if code == -2:
                raise ChannelMessageBudgetError(
                    "iLink context message budget exhausted", provider_code=code
                )
            if code == -14:
                raise ChannelBindingExpiredError
            if code != 0:
                raise ApiError(
                    str(response.get("errmsg") or f"send_message failed ({code})"),
                    errcode=code,
                    payload={"ret": code},
                )
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


def _render_qr_image(content: str) -> str:
    """Render iLink's QR payload as a browser-displayable PNG data URL."""
    if content.startswith("data:image/"):
        return content
    try:
        import qrcode
    except ImportError as exc:  # pragma: no cover - dependency is declared directly
        raise RuntimeError("qrcode package is required to render WeChat QR codes") from exc

    qr = qrcode.QRCode(box_size=8, border=2)
    qr.add_data(content)
    qr.make(fit=True)
    output = BytesIO()
    qr.make_image().save(output, format="PNG")
    encoded = base64.b64encode(output.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
