"""Durable, provider-neutral channel gateway worker orchestration."""

from __future__ import annotations

import base64
import hashlib
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from src.config.settings import get_channel_gateway_config
from src.server.channels.contracts import (
    AgentSession,
    AgentTurn,
    InboundKind,
    MediaPart,
    OpenSessionRequest,
    OutboundMessage,
    ResolvedImage,
    TextPart,
)
from src.server.channels.adapters.wechat_ilink import BindingExpiredError
from src.server.database import channels as channel_db

logger = logging.getLogger(__name__)


def _peer_hash(peer_ref: str) -> str:
    return hashlib.sha256(peer_ref.encode("utf-8")).hexdigest()


def _external_thread_id(
    binding_id: uuid.UUID, peer_hash: str, session_id: uuid.UUID
) -> str:
    raw = f"{binding_id}:{peer_hash}:{session_id}".encode()
    digest = (
        base64.urlsafe_b64encode(hashlib.sha256(raw).digest()[:18]).decode().rstrip("=")
    )
    return f"channel-{digest}"


def split_outbound_parts(
    parts: tuple[TextPart | MediaPart, ...], *, max_text_length: int
) -> tuple[TextPart | MediaPart, ...]:
    """Split provider-limited text without changing delivery order."""
    split: list[TextPart | MediaPart] = []
    for part in parts:
        if not isinstance(part, TextPart):
            split.append(part)
            continue
        split.extend(
            TextPart(part.text[index : index + max_text_length])
            for index in range(0, len(part.text), max_text_length)
        )
    return tuple(split)


class GatewayRunner:
    """Run polling, inbound processing and outbox delivery as independent ticks."""

    def __init__(
        self,
        *,
        channel_adapters: dict[str, Any],
        agent_adapter: Any,
        repository: Any = channel_db,
        worker_id: str | None = None,
    ) -> None:
        self.channel_adapters = channel_adapters
        self.agent_adapter = agent_adapter
        self.repository = repository
        self.worker_id = worker_id or f"gateway-{uuid.uuid4()}"
        self.config = get_channel_gateway_config()
        self._stopped = False

    async def stop(self) -> None:
        self._stopped = True

    async def poll_bindings_once(self) -> int:
        count = 0
        for binding_id in await self.repository.list_active_binding_ids(
            self.config.worker_concurrency * 2
        ):
            lease = await self.repository.claim_binding_lease(
                binding_id, self.worker_id, self.config.binding_lease_seconds
            )
            if lease is None:
                continue
            try:
                await self.ingest_binding(lease)
                count += 1
            except BindingExpiredError:
                await self.repository.mark_binding_reauth(
                    lease.binding_id, "session_expired"
                )
            except Exception:
                logger.warning(
                    "channel poll failed for type=%s", lease.channel_type, exc_info=True
                )
            finally:
                await self.repository.release_binding_lease(
                    lease.binding_id, self.worker_id, lease.generation
                )
        return count

    async def ingest_binding(self, lease: Any) -> int:
        adapter = self.channel_adapters.get(lease.channel_type)
        if adapter is None:
            raise RuntimeError(f"no adapter for channel type {lease.channel_type}")
        batch = await adapter.fetch_updates(lease.credentials, lease.cursor)
        persisted = []
        for raw in batch.updates:
            normalized = adapter.normalize(raw, lease.route)
            if normalized.kind is not InboundKind.MESSAGE:
                persisted.append(
                    channel_db.PersistedInbound(
                        provider_message_id=normalized.provider_message_id,
                        session_id=None,
                        kind=normalized.kind,
                        peer_lookup_hash=None,
                        text=None,
                        received_at=normalized.received_at,
                    )
                )
                continue
            if not normalized.peer_ref:
                continue
            peer_hash = _peer_hash(normalized.peer_ref)
            persisted.append(
                channel_db.PersistedInbound(
                    provider_message_id=normalized.provider_message_id,
                    session_id=None,
                    kind=normalized.kind,
                    peer_lookup_hash=peer_hash,
                    text=normalized.text,
                    peer_ref=normalized.peer_ref,
                    media=normalized.media,
                    reply_context=normalized.reply_context,
                    received_at=normalized.received_at,
                )
            )
        cursor = batch.next_cursor if batch.next_cursor is not None else lease.cursor
        return await self.repository.persist_update_batch(
            lease.binding_id,
            cursor,
            persisted,
            binding_epoch=lease.binding_epoch,
            idle_timeout_seconds=lease.idle_timeout_seconds,
        )

    async def process_inbound_once(self) -> int:
        claims = await self.repository.claim_pending_inbound(
            self.config.worker_concurrency, self.config.inbound_lease_seconds
        )
        processed = 0
        for claim in claims:
            try:
                if claim.kind is not InboundKind.MESSAGE or claim.session_id is None:
                    processed += 1
                    continue
                async with self.repository.hold_active_binding_epoch(
                    claim.binding_id, claim.binding_epoch
                ) as active:
                    if not active:
                        continue
                    session_ref = claim.agent_session_ref
                    peer_ref = claim.peer_ref or ""
                    if not session_ref:
                        external = _external_thread_id(
                            claim.binding_id, claim.peer_lookup_hash, claim.session_id
                        )
                        opened = await self.agent_adapter.open_session(
                            OpenSessionRequest(
                                binding_ref=str(claim.binding_id),
                                actor_ref=claim.user_id,
                                peer_ref=peer_ref,
                                session_key=external,
                            )
                        )
                        session_ref = opened.ref
                    else:
                        opened = AgentSession(
                            ref=session_ref,
                            opened_at=datetime.now(UTC),
                            actor_ref=claim.user_id,
                        )
                    images: list[ResolvedImage] = []
                    adapter = self.channel_adapters.get(claim.channel_type)
                    if adapter and claim.media and hasattr(adapter, "download_image"):
                        for media in claim.media:
                            data = await adapter.download_image(
                                media, max_bytes=self.config.max_image_bytes
                            )
                            mime, width, height = adapter.validate_image(
                                data,
                                max_bytes=self.config.max_image_bytes,
                                max_pixels=self.config.max_image_pixels,
                            )
                            import base64 as _b64

                            encoded = _b64.b64encode(data).decode("ascii")
                            images.append(
                                ResolvedImage(
                                    f"data:{mime};base64,{encoded}",
                                    mime,
                                    len(data),
                                    width,
                                    height,
                                )
                            )
                    result = await self.agent_adapter.run_turn(
                        opened,
                        AgentTurn(
                            request_key=claim.request_key,
                            text=claim.text,
                            received_at=datetime.now(UTC),
                            images=tuple(images),
                        ),
                    )
                if claim.channel_type == "wechat":
                    result = result.__class__(
                        parts=split_outbound_parts(
                            result.parts,
                            max_text_length=self.config.max_ilink_text_length,
                        ),
                        session_ref=result.session_ref,
                    )
                await self.repository.ack_inbound_and_enqueue_deliveries(claim, result)
                processed += 1
            except BindingExpiredError:
                await self.repository.mark_binding_reauth(
                    claim.binding_id, "session_expired"
                )
                await self.repository.nack_inbound(
                    claim.inbound_message_id,
                    claim.lease_generation,
                    "session_expired",
                    0,
                    1,
                )
            except Exception as exc:
                attempts = getattr(claim, "attempts", 1)
                delay = min(300, 2 ** max(0, attempts - 1))
                await self.repository.nack_inbound(
                    claim.inbound_message_id,
                    claim.lease_generation,
                    type(exc).__name__.lower()[:64],
                    delay,
                    self.config.max_delivery_attempts,
                )
        return processed

    async def deliver_once(self) -> int:
        deliveries = await self.repository.claim_due_deliveries(
            self.config.worker_concurrency, self.config.outbox_lease_seconds
        )
        delivered = 0
        for delivery in deliveries:
            adapter = self.channel_adapters.get(delivery.channel_type)
            if adapter is None:
                await self.repository.nack_delivery(
                    delivery.delivery_id,
                    delivery.lease_generation,
                    "adapter_missing",
                    60,
                    self.config.max_delivery_attempts,
                )
                continue
            parts = []
            for payload in [delivery.payload]:
                if isinstance(payload.get("text"), str):
                    parts.append(TextPart(payload["text"]))
                elif payload.get("media_ref"):
                    parts.append(
                        MediaPart(
                            payload["media_ref"],
                            payload.get("mime_type", "application/octet-stream"),
                            payload.get("caption"),
                        )
                    )
            message = OutboundMessage(str(delivery.client_id), tuple(parts))
            try:
                async with self.repository.hold_active_binding_epoch(
                    delivery.binding_id, delivery.binding_epoch
                ) as active:
                    if not active:
                        continue
                    receipt = await adapter.deliver(
                        delivery.credentials, delivery.reply_context, message
                    )
                if not receipt.accepted:
                    raise RuntimeError(receipt.detail or "delivery rejected")
                await self.repository.ack_delivery(
                    delivery.delivery_id, delivery.lease_generation
                )
                delivered += 1
            except BindingExpiredError:
                await self.repository.mark_binding_reauth(
                    delivery.binding_id, "session_expired"
                )
                await self.repository.nack_delivery(
                    delivery.delivery_id,
                    delivery.lease_generation,
                    "session_expired",
                    0,
                    1,
                )
            except Exception as exc:
                delay = min(300, 2 ** max(0, getattr(delivery, "attempts", 1) - 1))
                await self.repository.nack_delivery(
                    delivery.delivery_id,
                    delivery.lease_generation,
                    type(exc).__name__.lower()[:64],
                    delay,
                    self.config.max_delivery_attempts,
                )
        return delivered
