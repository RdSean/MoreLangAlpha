"""Durable, provider-neutral channel gateway worker orchestration."""

from __future__ import annotations

import base64
import asyncio
import hashlib
import inspect
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from src.config.settings import get_channel_gateway_config
from src.server.channels.contracts import (
    AgentSession,
    AgentTurn,
    AgentTurnResult,
    ChannelBindingExpiredError,
    ChannelMessageBudgetError,
    InboundKind,
    MediaPart,
    OpenSessionRequest,
    OutboundMessage,
    TextPart,
)
from src.server.services.channels.event_dispatcher import (
    ChannelEventDispatcher,
    PresentationSink,
)
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
    parts: tuple[TextPart | MediaPart, ...], *, max_text_length: int | None
) -> tuple[TextPart | MediaPart, ...]:
    """Split provider-limited text without changing delivery order."""
    if max_text_length is None:
        return parts
    split: list[TextPart | MediaPart] = []
    for part in parts:
        if not isinstance(part, TextPart):
            split.append(part)
            continue
        split.extend(TextPart(text) for text in _split_text(part.text, max_text_length))
    return tuple(split)


def apply_context_message_budget(
    parts: tuple[TextPart | MediaPart, ...],
    *,
    max_messages: int | None,
    notice: str,
) -> tuple[tuple[TextPart | MediaPart, ...], tuple[TextPart | MediaPart, ...]]:
    """Reserve one provider bubble to explain how the remaining tail is fetched."""
    if max_messages is None or len(parts) <= max_messages:
        return parts, ()
    if max_messages < 2:
        raise ValueError("context message budget must leave room for a notice")
    visible_count = max_messages - 1
    return parts[:visible_count] + (TextPart(notice),), parts[visible_count:]


def _split_text(text: str, limit: int) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        window = remaining[:limit]
        split_at = -1
        for separator in ("\n\n", "\n", " "):
            position = window.rfind(separator)
            if position > limit * 3 // 10:
                split_at = position + len(separator)
                break
        if split_at == -1:
            split_at = limit
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]
    return chunks


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
        self._started_bindings: dict[str, tuple[Any, Any]] = {}

    async def _start_binding(self, binding_id: Any, adapter: Any, credentials: Any) -> None:
        key = str(binding_id)
        if key in self._started_bindings:
            return
        hook = getattr(adapter, "on_binding_start", None)
        if callable(hook):
            try:
                await hook(credentials)
            except Exception:
                logger.debug("channel binding start hook failed", exc_info=True)
        self._started_bindings[key] = (adapter, credentials)

    async def _stop_binding(self, key: str, adapter: Any, credentials: Any) -> None:
        hook = getattr(adapter, "on_binding_stop", None)
        if callable(hook):
            try:
                await hook(credentials)
            except Exception:
                logger.debug("channel binding stop hook failed", exc_info=True)
        self._started_bindings.pop(key, None)

    async def stop(self) -> None:
        self._stopped = True
        started = list(self._started_bindings.items())
        for key, (adapter, credentials) in started:
            await self._stop_binding(key, adapter, credentials)

    async def _run_agent_turn(
        self,
        session: AgentSession,
        turn: AgentTurn,
        on_event: Any,
    ):
        """Call event-aware agents while preserving legacy adapter signatures."""

        run_turn = self.agent_adapter.run_turn
        try:
            parameters = inspect.signature(run_turn).parameters.values()
            accepts_events = any(
                parameter.name == "on_event"
                or parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parameters
            )
        except (TypeError, ValueError):
            accepts_events = True
        if accepts_events:
            return await run_turn(session, turn, on_event=on_event)
        return await run_turn(session, turn)

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
            adapter = self.channel_adapters.get(lease.channel_type)
            try:
                if adapter is None:
                    raise RuntimeError(f"no adapter for channel type {lease.channel_type}")
                await self._start_binding(lease.binding_id, adapter, lease.credentials)
                await self.ingest_binding(lease)
                count += 1
            except ChannelBindingExpiredError:
                await self._stop_binding(
                    str(lease.binding_id), adapter, lease.credentials
                )
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

    def _inbound_lease_seconds(self) -> int:
        """A claim has to outlive the turn it was taken for.

        Inbound claims are not renewed while they run, so the lease taken here
        is the only thing stopping a second worker — or another coroutine in
        this one — from claiming the same message while the first turn is still
        going. With a turn budget longer than the lease the loser's dispatch
        answers 409, and the retry path eventually marks a message dead that the
        first turn answered perfectly well.
        """
        return max(
            self.config.inbound_lease_seconds,
            int(self.config.agent_turn_timeout_seconds) + 30,
        )

    async def process_inbound_once(self) -> int:
        claims = await self.repository.claim_pending_inbound(
            self.config.worker_concurrency, self._inbound_lease_seconds()
        )
        processed = 0
        for claim in claims:
            try:
                if claim.kind is not InboundKind.MESSAGE or claim.session_id is None:
                    processed += 1
                    continue
                adapter = self.channel_adapters.get(claim.channel_type)
                if adapter is None:
                    raise RuntimeError(f"no adapter for channel type {claim.channel_type}")
                continuation = None
                continuation_id = None
                command = getattr(adapter, "continuation_command", None)
                load_continuation = getattr(
                    self.repository, "get_pending_continuation", None
                )
                async with self.repository.hold_active_binding_epoch(
                    claim.binding_id, claim.binding_epoch
                ) as active:
                    if not active:
                        continue
                    if (
                        callable(load_continuation)
                        and command
                        and claim.text
                        and claim.text.strip() == command
                    ):
                        continuation = await load_continuation(
                            claim.binding_id,
                            claim.session_id,
                            claim.binding_epoch,
                        )
                    if continuation is not None:
                        continuation_id = continuation.continuation_id
                        result = AgentTurnResult(parts=continuation.parts)
                    else:
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
                        images = (
                            await adapter.resolve_images(
                                claim.media,
                                max_bytes=self.config.max_image_bytes,
                                max_pixels=self.config.max_image_pixels,
                            )
                            if claim.media
                            else ()
                        )
                        sink = PresentationSink()
                        dispatcher = ChannelEventDispatcher(adapter, sink)
                        typing_task: asyncio.Task[Any] | None = None
                        typing_stop = asyncio.Event()
                        credentials = getattr(claim, "credentials", None)
                        reply_context = getattr(claim, "reply_context", None)
                        if (
                            getattr(adapter, "supports_typing", False)
                            and credentials is not None
                            and reply_context is not None
                            and callable(getattr(adapter, "keep_typing", None))
                        ):
                            typing_task = asyncio.create_task(
                                adapter.keep_typing(
                                    credentials,
                                    reply_context,
                                    stop_event=typing_stop,
                                ),
                                name=f"channel-typing-{claim.inbound_message_id}",
                            )
                        try:
                            result = await self._run_agent_turn(
                                opened,
                                AgentTurn(
                                    request_key=claim.request_key,
                                    text=claim.text,
                                    received_at=datetime.now(UTC),
                                    channel_type=claim.channel_type,
                                    images=images,
                                ),
                                dispatcher.dispatch,
                            )
                        finally:
                            if typing_task is not None:
                                typing_stop.set()
                                try:
                                    await asyncio.wait_for(typing_task, timeout=2.0)
                                except asyncio.TimeoutError:
                                    typing_task.cancel()
                                    await asyncio.gather(
                                        typing_task, return_exceptions=True
                                    )
                                except Exception:
                                    logger.debug(
                                        "channel typing task failed", exc_info=True
                                    )
                        rendered_parts = sink.parts
                        if rendered_parts:
                            media_parts = tuple(
                                part for part in result.parts if isinstance(part, MediaPart)
                            )
                            result = result.__class__(
                                parts=rendered_parts + media_parts,
                                session_ref=result.session_ref,
                            )
                prepared_parts = tuple(result.parts)
                prepare = getattr(adapter, "prepare_outbound_parts", None)
                if callable(prepare):
                    prepared_parts = tuple(prepare(prepared_parts))
                max_messages = getattr(adapter, "max_messages_per_context", None)
                notice = getattr(adapter, "continuation_notice", None)
                remaining_parts: tuple[TextPart | MediaPart, ...] = ()
                if max_messages is not None:
                    if not notice:
                        notice = "内容较长，回复“继续”获取后续内容。"
                    prepared_parts, remaining_parts = apply_context_message_budget(
                        prepared_parts,
                        max_messages=max_messages,
                        notice=notice,
                    )
                result = result.__class__(
                    parts=split_outbound_parts(
                        prepared_parts,
                        max_text_length=adapter.max_outbound_text_length,
                    ),
                    session_ref=result.session_ref,
                )
                ack_kwargs: dict[str, Any] = {}
                if remaining_parts:
                    ack_kwargs["continuation_parts"] = remaining_parts
                    ack_kwargs["continuation_expires_at"] = datetime.now(UTC) + timedelta(
                        seconds=int(getattr(claim, "idle_timeout_seconds", 21_600))
                    )
                if continuation_id is not None:
                    ack_kwargs["continuation_id"] = continuation_id
                await self.repository.ack_inbound_and_enqueue_deliveries(
                    claim, result, **ack_kwargs
                )
                processed += 1
            except ChannelBindingExpiredError:
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
                code = str(
                    getattr(exc, "code", None) or type(exc).__name__.lower()
                )[:64]
                # The class name alone is not a diagnosis: every adapter
                # failure is a FlashAgentError, and "flashagenterror" says
                # nothing about whether it was a timeout, an empty answer, or a
                # rejected request.
                logger.warning(
                    "channel inbound %s failed (%s, attempt %s/%s): %s",
                    claim.inbound_message_id,
                    code,
                    attempts,
                    self.config.max_delivery_attempts,
                    exc,
                )
                await self.repository.nack_inbound(
                    claim.inbound_message_id,
                    claim.lease_generation,
                    code,
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
            except ChannelMessageBudgetError as exc:
                error_code = f"context_budget_{str(exc.provider_code)[:16]}"
                park = getattr(
                    self.repository, "park_delivery_context_budget", None
                )
                if callable(park):
                    parked = await park(
                        delivery.delivery_id,
                        delivery.lease_generation,
                        error_code,
                        expires_at=datetime.now(UTC) + timedelta(hours=6),
                    )
                    if parked:
                        continue
                await self.repository.nack_delivery(
                    delivery.delivery_id,
                    delivery.lease_generation,
                    error_code,
                    0,
                    1,
                )
            except ChannelBindingExpiredError:
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
                code = str(
                    getattr(exc, "code", None) or type(exc).__name__.lower()
                )[:64]
                logger.warning(
                    "channel delivery %s failed (%s): %s",
                    delivery.delivery_id,
                    code,
                    exc,
                )
                await self.repository.nack_delivery(
                    delivery.delivery_id,
                    delivery.lease_generation,
                    code,
                    delay,
                    self.config.max_delivery_attempts,
                )
        return delivered
