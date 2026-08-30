"""Durable persistence for generic channel gateways.

This module is the only SQL boundary for channel state.  Provider adapters and
the gateway runner receive typed values, while credentials, cursors, routes,
media references, and reply contexts remain encrypted in PostgreSQL.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Sequence
from uuid import NAMESPACE_URL, UUID, uuid5

from psycopg.rows import dict_row

from src.server.channels.contracts import (
    AgentTurnResult,
    BindingCredentials,
    BindingRoute,
    InboundKind,
    InboundMedia,
    LinkChallenge,
    LinkPollResult,
    LinkPollState,
    ReplyContext,
)
from src.server.database.encryption import get_encryption_key
from src.server.database.pool import get_db_connection


@dataclass(frozen=True)
class BindingLease:
    binding_id: UUID
    user_id: str
    channel_type: str
    credentials: BindingCredentials
    route: BindingRoute
    cursor: str
    generation: int
    idle_timeout_seconds: int = 21_600
    binding_epoch: int = 1


@dataclass(frozen=True)
class PersistedInbound:
    provider_message_id: str
    session_id: UUID | None
    kind: InboundKind
    peer_lookup_hash: str | None
    text: str | None
    peer_ref: str | None = None
    media: tuple[InboundMedia, ...] = ()
    reply_context: ReplyContext | None = None
    received_at: datetime | None = None


@dataclass(frozen=True)
class ClaimedInbound:
    inbound_message_id: UUID
    binding_id: UUID
    session_id: UUID | None
    provider_message_id: str
    kind: InboundKind
    text: str | None
    media: tuple[InboundMedia, ...]
    reply_context: ReplyContext | None
    request_key: str
    lease_generation: int
    user_id: str
    agent_session_ref: str | None
    peer_lookup_hash: str
    peer_ref: str | None
    attempts: int
    channel_type: str = "wechat"
    binding_epoch: int = 1


@dataclass(frozen=True)
class ClaimedDelivery:
    delivery_id: UUID
    binding_id: UUID
    session_id: UUID
    inbound_message_id: UUID
    sequence_no: int
    client_id: UUID
    payload: dict[str, Any]
    reply_context: ReplyContext
    lease_generation: int
    user_id: str
    credentials: BindingCredentials
    attempts: int
    channel_type: str = "wechat"
    binding_epoch: int = 1


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"))


def _media_json(media: Sequence[InboundMedia]) -> str:
    return _json(
        [
            {
                "ref": item.ref,
                "mime_type": item.mime_type,
                "byte_size": item.byte_size,
                "width": item.width,
                "height": item.height,
                "aes_key": item.aes_key,
                "encrypt_type": item.encrypt_type,
            }
            for item in media
        ]
    )


def _reply_json(reply_context: ReplyContext | None) -> str | None:
    if reply_context is None:
        return None
    return _json(
        {"route_ref": reply_context.route_ref, "values": list(reply_context.values)}
    )


def _credentials_from_row(row: dict[str, Any]) -> BindingCredentials:
    values = row.get("credentials") or {}
    return BindingCredentials(
        binding_ref=str(row["binding_id"]),
        channel_type=row["channel_type"],
        values=tuple((str(key), str(value)) for key, value in values.items()),
    )


async def claim_binding_lease(
    binding_id: UUID | str, worker_id: str, seconds: int
) -> BindingLease | None:
    """Claim one binding using a compare-and-set lease generation."""
    key = get_encryption_key()
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE channel_bindings
                    SET lease_owner = %s,
                        lease_expires_at = clock_timestamp() + make_interval(secs => %s),
                        lease_generation = lease_generation + 1,
                        updated_at = NOW()
                    WHERE binding_id = %s
                      AND status = 'active'
                      AND (lease_expires_at IS NULL OR lease_expires_at <= NOW()
                           OR lease_owner = %s)
                    RETURNING binding_id, user_id, channel_type,
                              pgp_sym_decrypt(credentials_ciphertext, %s) AS credentials,
                              pgp_sym_decrypt(bound_peer_ciphertext, %s) AS bound_peer,
                              COALESCE(pgp_sym_decrypt(cursor_ciphertext, %s), '') AS cursor,
                              lease_generation, idle_timeout_seconds, binding_epoch
                    """,
                    (worker_id, float(seconds), binding_id, worker_id, key, key, key),
                )
                row = await cur.fetchone()
                if not row:
                    return None
                try:
                    credentials = json.loads(row["credentials"] or "{}")
                    bound_peer = str(row["bound_peer"] or "")
                except (TypeError, ValueError) as exc:
                    raise RuntimeError(
                        "channel binding ciphertext is malformed"
                    ) from exc
                return BindingLease(
                    binding_id=row["binding_id"],
                    user_id=row["user_id"],
                    channel_type=row["channel_type"],
                    credentials=BindingCredentials(
                        binding_ref=str(row["binding_id"]),
                        channel_type=row["channel_type"],
                        values=tuple((str(k), str(v)) for k, v in credentials.items()),
                    ),
                    route=BindingRoute(
                        binding_ref=str(row["binding_id"]), peer_ref=bound_peer
                    ),
                    cursor=str(row["cursor"] or ""),
                    generation=int(row["lease_generation"]),
                    idle_timeout_seconds=int(row.get("idle_timeout_seconds") or 21_600),
                    binding_epoch=int(row["binding_epoch"]),
                )


async def release_binding_lease(
    binding_id: UUID | str, worker_id: str, generation: int
) -> bool:
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE channel_bindings
                SET lease_owner = NULL, lease_expires_at = NULL, updated_at = NOW()
                WHERE binding_id = %s AND lease_owner = %s AND lease_generation = %s
                """,
                (binding_id, worker_id, generation),
            )
            return cur.rowcount == 1


async def persist_update_batch(
    binding_id: UUID | str,
    cursor: str,
    messages: Sequence[PersistedInbound],
    *,
    binding_epoch: int = 1,
    idle_timeout_seconds: int = 21_600,
) -> int:
    """Persist a cursor and deduplicated inbound rows atomically.

    The binding row lock fences stale pollers. Session creation happens only
    after proving a provider message is new, so duplicate getupdates batches
    cannot extend an otherwise idle conversation.
    """
    key = get_encryption_key()
    inserted = 0
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT binding_id
                    FROM channel_bindings
                    WHERE binding_id = %s AND status = 'active' AND binding_epoch = %s
                    FOR UPDATE
                    """,
                    (binding_id, binding_epoch),
                )
                if not await cur.fetchone():
                    return 0
                for message in messages:
                    await cur.execute(
                        """
                        SELECT inbound_message_id
                        FROM channel_inbound_messages
                        WHERE binding_id = %s AND provider_message_id = %s
                        """,
                        (binding_id, message.provider_message_id),
                    )
                    if await cur.fetchone():
                        continue
                    session_id = message.session_id
                    if message.kind is InboundKind.IGNORED:
                        status = "ignored"
                    elif message.kind is InboundKind.REJECTED:
                        status = "rejected"
                    else:
                        status = "pending"
                    if message.kind is InboundKind.MESSAGE:
                        if not message.peer_ref or not message.peer_lookup_hash:
                            status = "rejected"
                            session_id = None
                        else:
                            session_id = await _get_or_rotate_session_locked(
                                cur,
                                binding_id=binding_id,
                                binding_epoch=binding_epoch,
                                peer_ref=message.peer_ref,
                                peer_lookup_hash=message.peer_lookup_hash,
                                received_at=message.received_at or datetime.now(UTC),
                                idle_timeout_seconds=idle_timeout_seconds,
                                key=key,
                            )
                    await cur.execute(
                        """
                        INSERT INTO channel_inbound_messages (
                            binding_id, session_id, provider_message_id, kind, status,
                            peer_lookup_hash, text_content, media_ciphertext,
                            reply_context_ciphertext, received_at, binding_epoch
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s,
                            CASE WHEN %s IS NULL THEN NULL
                                 ELSE pgp_sym_encrypt(%s, %s) END,
                            CASE WHEN %s IS NULL THEN NULL
                                 ELSE pgp_sym_encrypt(%s, %s) END,
                            %s, %s
                        )
                        ON CONFLICT (binding_id, provider_message_id) DO NOTHING
                        """,
                        (
                            binding_id,
                            session_id,
                            message.provider_message_id,
                            message.kind.value,
                            status,
                            message.peer_lookup_hash,
                            message.text,
                            _media_json(message.media)
                            if message.media and message.kind is not InboundKind.IGNORED
                            else None,
                            _media_json(message.media)
                            if message.media and message.kind is not InboundKind.IGNORED
                            else None,
                            key,
                            _reply_json(message.reply_context),
                            _reply_json(message.reply_context),
                            key,
                            message.received_at or datetime.now(UTC),
                            binding_epoch,
                        ),
                    )
                    inserted += int(cur.rowcount or 0)
                await cur.execute(
                    """
                    UPDATE channel_bindings
                    SET cursor_ciphertext = pgp_sym_encrypt(%s, %s), updated_at = NOW()
                    WHERE binding_id = %s AND status = 'active' AND binding_epoch = %s
                    """,
                    (cursor, key, binding_id, binding_epoch),
                )
    return inserted


async def _get_or_rotate_session_locked(
    cur: Any,
    *,
    binding_id: UUID | str,
    binding_epoch: int,
    peer_ref: str,
    peer_lookup_hash: str,
    received_at: datetime,
    idle_timeout_seconds: int,
    key: str,
) -> UUID:
    await cur.execute(
        """
        SELECT session_id, last_inbound_at
        FROM channel_sessions
        WHERE binding_id = %s AND binding_epoch = %s AND peer_lookup_hash = %s
          AND status = 'active'
        FOR UPDATE
        """,
        (binding_id, binding_epoch, peer_lookup_hash),
    )
    row = await cur.fetchone()
    if row:
        elapsed = (received_at - row["last_inbound_at"]).total_seconds()
        if elapsed <= idle_timeout_seconds:
            await cur.execute(
                """
                UPDATE channel_sessions
                SET last_inbound_at = GREATEST(last_inbound_at, %s)
                WHERE session_id = %s
                """,
                (received_at, row["session_id"]),
            )
            return row["session_id"]
        await cur.execute(
            """
            UPDATE channel_sessions
            SET status = 'closed', closed_at = NOW()
            WHERE session_id = %s
            """,
            (row["session_id"],),
        )
    await cur.execute(
        """
        INSERT INTO channel_sessions (
            binding_id, binding_epoch, peer_lookup_hash, peer_ciphertext,
            status, last_inbound_at
        ) VALUES (%s, %s, %s, pgp_sym_encrypt(%s, %s), 'active', %s)
        RETURNING session_id
        """,
        (binding_id, binding_epoch, peer_lookup_hash, peer_ref, key, received_at),
    )
    created = await cur.fetchone()
    return created["session_id"]


async def claim_pending_inbound(limit: int, lease_seconds: int) -> list[ClaimedInbound]:
    """Claim pending inbound rows, keeping one live head per session."""
    key = get_encryption_key()
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    WITH heads AS (
                        SELECT i.inbound_message_id
                        FROM channel_inbound_messages i
                        WHERE (i.status = 'pending'
                               OR (i.status = 'claimed' AND i.lease_expires_at <= NOW()))
                          AND i.session_id IS NOT NULL
                          AND (i.next_retry_at IS NULL OR i.next_retry_at <= NOW())
                          AND EXISTS (
                              SELECT 1 FROM channel_bindings active_binding
                              WHERE active_binding.binding_id = i.binding_id
                                AND active_binding.status = 'active'
                                AND active_binding.binding_epoch = i.binding_epoch
                          )
                          AND NOT EXISTS (
                              SELECT 1 FROM channel_inbound_messages prior
                              WHERE prior.session_id = i.session_id
                                AND (prior.status = 'pending'
                                     OR (prior.status = 'claimed' AND prior.lease_expires_at > NOW()))
                                AND (prior.received_at, prior.inbound_message_id)
                                    < (i.received_at, i.inbound_message_id)
                          )
                        ORDER BY i.received_at, i.inbound_message_id
                        LIMIT %s
                        FOR UPDATE SKIP LOCKED
                    ),
                    claimed AS (
                        UPDATE channel_inbound_messages i
                    SET status = 'claimed', attempts = i.attempts + 1,
                            lease_expires_at = clock_timestamp() + make_interval(secs => %s),
                            lease_generation = i.lease_generation + 1
                        FROM heads h
                        WHERE i.inbound_message_id = h.inbound_message_id
                        RETURNING i.*
                    )
                    SELECT c.*,
                           pgp_sym_decrypt(c.media_ciphertext, %s) AS media_json,
                           pgp_sym_decrypt(c.reply_context_ciphertext, %s) AS reply_json,
                           b.user_id, b.channel_type, b.binding_epoch,
                           pgp_sym_decrypt(s.agent_session_ref_ciphertext, %s)
                               AS agent_session_ref,
                           pgp_sym_decrypt(s.peer_ciphertext, %s) AS peer_ref
                    FROM claimed c
                    JOIN channel_bindings b
                      ON b.binding_id = c.binding_id AND b.status = 'active'
                     AND b.binding_epoch = c.binding_epoch
                    LEFT JOIN channel_sessions s
                      ON s.session_id = c.session_id AND s.binding_epoch = c.binding_epoch
                    """,
                    (limit, float(lease_seconds), key, key, key, key),
                )
                rows = await cur.fetchall()
                result: list[ClaimedInbound] = []
                for row in rows:
                    media = tuple(
                        InboundMedia(**item)
                        for item in json.loads(row["media_json"] or "[]")
                    )
                    reply_data = (
                        json.loads(row["reply_json"]) if row["reply_json"] else None
                    )
                    reply = (
                        ReplyContext(
                            route_ref=reply_data["route_ref"],
                            values=tuple(
                                tuple(item) for item in reply_data.get("values", [])
                            ),
                        )
                        if reply_data
                        else None
                    )
                    result.append(
                        ClaimedInbound(
                            inbound_message_id=row["inbound_message_id"],
                            binding_id=row["binding_id"],
                            session_id=row["session_id"],
                            provider_message_id=row["provider_message_id"],
                            kind=InboundKind(row["kind"]),
                            text=row["text_content"],
                            media=media,
                            reply_context=reply,
                            request_key=str(row["inbound_message_id"]),
                            lease_generation=int(row["lease_generation"]),
                            user_id=row["user_id"],
                            agent_session_ref=row["agent_session_ref"],
                            peer_lookup_hash=str(row["peer_lookup_hash"] or ""),
                            peer_ref=(
                                str(row["peer_ref"]) if row["peer_ref"] else None
                            ),
                            attempts=int(row["attempts"]),
                            channel_type=str(row["channel_type"]),
                            binding_epoch=int(row["binding_epoch"]),
                        )
                    )
                return result


async def ack_inbound_and_enqueue_deliveries(
    claim: ClaimedInbound,
    result: AgentTurnResult,
) -> bool:
    """Atomically ack an inbound and create stable, ordered outbox parts."""
    key = get_encryption_key()
    parts = [
        {"text": part.text} if hasattr(part, "text") else {"media_ref": part.media_ref}
        for part in result.parts
    ]
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                if claim.session_id:
                    await cur.execute(
                        """
                        SELECT session_id
                        FROM channel_sessions
                        WHERE session_id = %s AND binding_epoch = %s
                        FOR UPDATE
                        """,
                        (claim.session_id, claim.binding_epoch),
                    )
                    if not await cur.fetchone():
                        return False
                await cur.execute(
                    """
                    UPDATE channel_inbound_messages i
                    SET status = 'done', processed_at = NOW(), lease_expires_at = NULL
                    FROM channel_bindings b
                    WHERE i.inbound_message_id = %s AND i.status = 'claimed'
                      AND i.lease_generation = %s
                      AND i.binding_epoch = %s
                      AND b.binding_id = i.binding_id
                      AND b.status = 'active'
                      AND b.binding_epoch = i.binding_epoch
                    """,
                    (
                        claim.inbound_message_id,
                        claim.lease_generation,
                        claim.binding_epoch,
                    ),
                )
                if cur.rowcount != 1:
                    return False
                if result.session_ref and claim.session_id:
                    await cur.execute(
                        """
                        UPDATE channel_sessions
                        SET agent_session_ref_ciphertext = pgp_sym_encrypt(%s, %s)
                        WHERE session_id = %s AND binding_epoch = %s
                        """,
                        (
                            result.session_ref,
                            key,
                            claim.session_id,
                            claim.binding_epoch,
                        ),
                    )
                next_delivery_order = 0
                if claim.session_id:
                    await cur.execute(
                        """
                        SELECT COALESCE(MAX(session_delivery_order), -1) + 1
                        FROM channel_delivery_outbox
                        WHERE session_id = %s
                        """,
                        (claim.session_id,),
                    )
                    order_row = await cur.fetchone()
                    next_delivery_order = int(order_row[0])
                for sequence_no, payload in enumerate(parts):
                    client_id = uuid5(
                        NAMESPACE_URL,
                        f"https://langalpha.local/channel-delivery/{claim.inbound_message_id}/{sequence_no}",
                    )
                    await cur.execute(
                        """
                        INSERT INTO channel_delivery_outbox (
                            inbound_message_id, session_id, binding_id, sequence_no,
                            client_id, payload_ciphertext, binding_epoch,
                            session_delivery_order
                        ) VALUES (%s, %s, %s, %s, %s, pgp_sym_encrypt(%s, %s), %s, %s)
                        ON CONFLICT (inbound_message_id, sequence_no) DO NOTHING
                        """,
                        (
                            claim.inbound_message_id,
                            claim.session_id,
                            claim.binding_id,
                            sequence_no,
                            client_id,
                            _json(payload),
                            key,
                            claim.binding_epoch,
                            next_delivery_order + sequence_no,
                        ),
                    )
                return True


async def nack_inbound(
    inbound_message_id: UUID | str,
    lease_generation: int,
    error_code: str,
    retry_seconds: int,
    max_attempts: int,
) -> bool:
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE channel_inbound_messages
                SET status = CASE WHEN attempts >= %s THEN 'dead' ELSE 'pending' END,
                    next_retry_at = CASE WHEN attempts >= %s THEN NULL
                                         ELSE clock_timestamp() + make_interval(secs => %s) END,
                    lease_expires_at = NULL, last_error_code = %s
                WHERE inbound_message_id = %s AND status = 'claimed'
                  AND lease_generation = %s
                """,
                (
                    max_attempts,
                    max_attempts,
                    float(retry_seconds),
                    error_code,
                    inbound_message_id,
                    lease_generation,
                ),
            )
            return cur.rowcount == 1


async def claim_due_deliveries(limit: int, lease_seconds: int) -> list[ClaimedDelivery]:
    """Claim ordered outbox rows and decrypt only their referenced context."""
    key = get_encryption_key()
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    WITH due AS (
                        SELECT o.delivery_id
                        FROM channel_delivery_outbox o
                        WHERE (o.status = 'pending'
                               OR (o.status = 'claimed' AND o.lease_expires_at <= NOW()))
                          AND (o.next_retry_at IS NULL OR o.next_retry_at <= NOW())
                          AND EXISTS (
                              SELECT 1 FROM channel_bindings active_binding
                              WHERE active_binding.binding_id = o.binding_id
                                AND active_binding.status = 'active'
                                AND active_binding.binding_epoch = o.binding_epoch
                          )
                          AND NOT EXISTS (
                              SELECT 1 FROM channel_delivery_outbox prior
                              WHERE prior.session_id = o.session_id
                                AND (prior.status = 'pending'
                                     OR (prior.status = 'claimed' AND prior.lease_expires_at > NOW()))
                                AND prior.session_delivery_order < o.session_delivery_order
                          )
                        ORDER BY o.created_at, o.delivery_id
                        LIMIT %s FOR UPDATE SKIP LOCKED
                    ),
                    claimed AS (
                        UPDATE channel_delivery_outbox o
                        SET status = 'claimed', attempts = o.attempts + 1,
                            lease_expires_at = clock_timestamp() + make_interval(secs => %s),
                            lease_generation = o.lease_generation + 1
                        FROM due d
                        WHERE o.delivery_id = d.delivery_id
                        RETURNING o.*
                    )
                    SELECT c.*,
                           pgp_sym_decrypt(c.payload_ciphertext, %s) AS payload,
                           pgp_sym_decrypt(i.reply_context_ciphertext, %s) AS reply_context,
                           b.user_id, b.channel_type, b.binding_epoch,
                           pgp_sym_decrypt(b.credentials_ciphertext, %s) AS credentials
                    FROM claimed c
                    JOIN channel_inbound_messages i
                      ON i.inbound_message_id = c.inbound_message_id
                    JOIN channel_bindings b
                      ON b.binding_id = c.binding_id AND b.status = 'active'
                     AND b.binding_epoch = c.binding_epoch
                    """,
                    (limit, float(lease_seconds), key, key, key),
                )
                rows = await cur.fetchall()
                deliveries: list[ClaimedDelivery] = []
                for row in rows:
                    reply_data = json.loads(row["reply_context"] or "{}")
                    payload = json.loads(row["payload"] or "{}")
                    credentials_data = json.loads(row["credentials"] or "{}")
                    deliveries.append(
                        ClaimedDelivery(
                            delivery_id=row["delivery_id"],
                            binding_id=row["binding_id"],
                            session_id=row["session_id"],
                            inbound_message_id=row["inbound_message_id"],
                            sequence_no=int(row["sequence_no"]),
                            client_id=row["client_id"],
                            payload=payload,
                            reply_context=ReplyContext(
                                route_ref=reply_data["route_ref"],
                                values=tuple(
                                    tuple(item) for item in reply_data.get("values", [])
                                ),
                            ),
                            lease_generation=int(row["lease_generation"]),
                            user_id=row["user_id"],
                            credentials=BindingCredentials(
                                binding_ref=str(row["binding_id"]),
                                channel_type=str(row["channel_type"]),
                                values=tuple(
                                    (str(k), str(v))
                                    for k, v in credentials_data.items()
                                ),
                            ),
                            attempts=int(row["attempts"]),
                            channel_type=str(row["channel_type"]),
                            binding_epoch=int(row["binding_epoch"]),
                        )
                    )
                return deliveries


async def ack_delivery(delivery_id: UUID | str, lease_generation: int) -> bool:
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE channel_delivery_outbox
                SET status = 'done', completed_at = NOW(), lease_expires_at = NULL
                WHERE delivery_id = %s AND status = 'claimed' AND lease_generation = %s
                """,
                (delivery_id, lease_generation),
            )
            return cur.rowcount == 1


async def nack_delivery(
    delivery_id: UUID | str,
    lease_generation: int,
    error_code: str,
    retry_seconds: int,
    max_attempts: int,
) -> bool:
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE channel_delivery_outbox
                SET status = CASE WHEN attempts >= %s THEN 'dead' ELSE 'pending' END,
                    next_retry_at = CASE WHEN attempts >= %s THEN NULL
                                         ELSE clock_timestamp() + make_interval(secs => %s) END,
                    lease_expires_at = NULL, last_error_code = %s
                WHERE delivery_id = %s AND status = 'claimed'
                  AND lease_generation = %s
                """,
                (
                    max_attempts,
                    max_attempts,
                    float(retry_seconds),
                    error_code,
                    delivery_id,
                    lease_generation,
                ),
            )
            return cur.rowcount == 1


async def disconnect_binding(binding_id: UUID | str, user_id: str) -> bool:
    """Retire a binding and fence every queued item from its old epoch."""
    return await _retire_binding(binding_id, status="disabled", user_id=user_id)


async def _retire_binding(
    binding_id: UUID | str,
    *,
    status: str,
    user_id: str | None = None,
    error_code: str | None = None,
) -> bool:
    """Clear secrets and prevent old work from crossing a binding transition."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                user_clause = "AND user_id = %s" if user_id is not None else ""
                params: list[Any] = [status, error_code, binding_id]
                if user_id is not None:
                    params.append(user_id)
                await cur.execute(
                    f"""
                    UPDATE channel_bindings
                    SET status = %s, binding_epoch = binding_epoch + 1,
                        credentials_ciphertext = NULL, cursor_ciphertext = NULL,
                        bound_peer_ciphertext = NULL, last_error_code = %s,
                        lease_owner = NULL, lease_expires_at = NULL, updated_at = NOW()
                    WHERE binding_id = %s {user_clause}
                      AND status <> 'disabled'
                    RETURNING binding_epoch
                    """,
                    tuple(params),
                )
                row = await cur.fetchone()
                if not row:
                    return False
                await cur.execute(
                    """
                    UPDATE channel_inbound_messages
                    SET status = CASE
                            WHEN status IN ('pending', 'claimed') THEN 'dead'
                            ELSE status
                        END,
                        media_ciphertext = NULL, reply_context_ciphertext = NULL,
                        lease_expires_at = NULL, last_error_code = 'binding_retired'
                    WHERE binding_id = %s
                    """,
                    (binding_id,),
                )
                await cur.execute(
                    """
                    UPDATE channel_delivery_outbox
                    SET status = CASE
                            WHEN status IN ('pending', 'claimed') THEN 'dead'
                            ELSE status
                        END,
                        payload_ciphertext = NULL, lease_expires_at = NULL,
                        last_error_code = 'binding_retired'
                    WHERE binding_id = %s
                    """,
                    (binding_id,),
                )
                await cur.execute(
                    """
                    UPDATE channel_sessions
                    SET status = 'closed', closed_at = COALESCE(closed_at, NOW()),
                        peer_ciphertext = NULL, agent_session_ref_ciphertext = NULL
                    WHERE binding_id = %s
                    """,
                    (binding_id,),
                )
                return True


async def mark_binding_reauth(
    binding_id: UUID | str, error_code: str = "session_expired"
) -> bool:
    return await _retire_binding(
        binding_id,
        status="reauth_required",
        error_code=error_code[:64],
    )


async def get_user_binding(user_id: str, channel_type: str) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT binding_id, status, idle_timeout_seconds, last_error_code
                FROM channel_bindings WHERE user_id = %s AND channel_type = %s
                """,
                (user_id, channel_type),
            )
            row = await cur.fetchone()
            return dict(row) if row else None


async def list_active_binding_ids(limit: int = 100) -> list[UUID]:
    """Return active binding IDs for a worker lease pass."""
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT binding_id FROM channel_bindings
                WHERE status = 'active'
                  AND (lease_expires_at IS NULL OR lease_expires_at <= NOW())
                ORDER BY updated_at, binding_id LIMIT %s
                """,
                (limit,),
            )
            return [row[0] for row in await cur.fetchall()]


@asynccontextmanager
async def hold_active_binding_epoch(
    binding_id: UUID | str,
    binding_epoch: int,
) -> AsyncIterator[bool]:
    """Linearize an external side effect with binding retirement.

    A normal binding update takes a conflicting row lock, so a disconnect or
    rebind either wins before this context starts or waits for its caller to
    finish the provider call. This closes the epoch check/use gap without
    making a process-local lock authoritative.
    """
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT 1 FROM channel_bindings
                    WHERE binding_id = %s AND status = 'active' AND binding_epoch = %s
                    FOR SHARE
                    """,
                    (binding_id, binding_epoch),
                )
                yield await cur.fetchone() is not None


async def create_link_attempt(
    *, user_id: str, channel_type: str, challenge: LinkChallenge
) -> UUID:
    key = get_encryption_key()
    state = _json(dict(challenge.provider_poll_state.values))
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE channel_link_attempts
                    SET status = 'cancelled', poll_state_ciphertext = NULL,
                        lease_owner = NULL, lease_expires_at = NULL, updated_at = NOW()
                    WHERE user_id = %s AND channel_type = %s
                      AND status IN ('waiting', 'scanned', 'verification_required')
                    """,
                    (user_id, channel_type),
                )
                await cur.execute(
                    """
                    INSERT INTO channel_link_attempts
                        (user_id, channel_type, qr_code_url, poll_state_ciphertext, expires_at)
                    VALUES (%s, %s, %s, pgp_sym_encrypt(%s, %s), %s)
                    RETURNING attempt_id
                    """,
                    (
                        user_id,
                        channel_type,
                        challenge.qr_code_url,
                        state,
                        key,
                        challenge.expires_at,
                    ),
                )
                row = await cur.fetchone()
                return row[0]


async def claim_link_attempt(
    user_id: str,
    attempt_id: UUID,
    worker_id: str,
    lease_seconds: int = 15,
) -> dict[str, Any] | None:
    """Claim one non-terminal QR attempt before calling the provider."""
    key = get_encryption_key()
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    UPDATE channel_link_attempts
                    SET status = 'expired', poll_state_ciphertext = NULL,
                        lease_owner = NULL, lease_expires_at = NULL, updated_at = NOW()
                    WHERE attempt_id = %s AND user_id = %s AND expires_at <= NOW()
                      AND status IN ('waiting', 'scanned', 'verification_required')
                    """,
                    (attempt_id, user_id),
                )
                await cur.execute(
                    """
                    UPDATE channel_link_attempts
                    SET lease_owner = %s,
                        lease_expires_at = clock_timestamp() + make_interval(secs => %s),
                        lease_generation = lease_generation + 1,
                        updated_at = NOW()
                    WHERE attempt_id = %s AND user_id = %s AND expires_at > NOW()
                      AND status IN ('waiting', 'scanned', 'verification_required')
                      AND (lease_expires_at IS NULL OR lease_expires_at <= NOW())
                    RETURNING attempt_id, user_id, channel_type, status, qr_code_url,
                              expires_at, lease_generation,
                              pgp_sym_decrypt(poll_state_ciphertext, %s) AS poll_state
                    """,
                    (worker_id, float(lease_seconds), attempt_id, user_id, key),
                )
                row = await cur.fetchone()
                return dict(row) if row else None


async def finalize_link_attempt(
    *,
    user_id: str,
    attempt_id: UUID,
    worker_id: str,
    lease_generation: int,
    result: LinkPollResult,
) -> bool:
    """Apply a QR poll result once and activate credentials atomically."""
    key = get_encryption_key()
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT channel_type, status
                    FROM channel_link_attempts
                    WHERE attempt_id = %s AND user_id = %s
                      AND lease_owner = %s AND lease_generation = %s
                    FOR UPDATE
                    """,
                    (attempt_id, user_id, worker_id, lease_generation),
                )
                attempt = await cur.fetchone()
                if not attempt or attempt["status"] not in {
                    "waiting",
                    "scanned",
                    "verification_required",
                }:
                    return False
                if result.status.value != "linked":
                    state = (
                        _json(dict(result.next_poll_state.values))
                        if result.next_poll_state
                        else None
                    )
                    await cur.execute(
                        """
                        UPDATE channel_link_attempts
                        SET status = %s,
                            poll_state_ciphertext = CASE
                                WHEN %s IS NULL THEN poll_state_ciphertext
                                ELSE pgp_sym_encrypt(%s, %s)
                            END,
                            lease_owner = NULL, lease_expires_at = NULL,
                            updated_at = NOW()
                        WHERE attempt_id = %s
                        """,
                        (
                            result.status.value,
                            state,
                            state,
                            key,
                            attempt_id,
                        ),
                    )
                    return True
                if not result.credentials or not result.routing or not result.binding:
                    raise RuntimeError("linked response missing credentials")
                await cur.execute(
                    """
                    SELECT binding_id
                    FROM channel_bindings
                    WHERE user_id = %s AND channel_type = %s
                    FOR UPDATE
                    """,
                    (user_id, attempt["channel_type"]),
                )
                existing = await cur.fetchone()
                values = _json(dict(result.credentials.values))
                if existing:
                    binding_id = existing["binding_id"]
                    await _retire_binding_rows(cur, binding_id)
                    await cur.execute(
                        """
                        UPDATE channel_bindings
                        SET status = 'active', credentials_ciphertext = pgp_sym_encrypt(%s, %s),
                            bound_peer_ciphertext = pgp_sym_encrypt(%s, %s),
                            cursor_ciphertext = pgp_sym_encrypt(%s, %s),
                            last_error_code = NULL, lease_owner = NULL,
                            lease_expires_at = NULL, updated_at = NOW()
                        WHERE binding_id = %s
                        """,
                        (
                            values,
                            key,
                            result.routing.peer_ref,
                            key,
                            "",
                            key,
                            binding_id,
                        ),
                    )
                else:
                    await cur.execute(
                        """
                        INSERT INTO channel_bindings (
                            user_id, channel_type, status, credentials_ciphertext,
                            bound_peer_ciphertext, cursor_ciphertext
                        ) VALUES (
                            %s, %s, 'active', pgp_sym_encrypt(%s, %s),
                            pgp_sym_encrypt(%s, %s), pgp_sym_encrypt(%s, %s)
                        )
                        """,
                        (
                            user_id,
                            attempt["channel_type"],
                            values,
                            key,
                            result.routing.peer_ref,
                            key,
                            "",
                            key,
                        ),
                    )
                await cur.execute(
                    """
                    UPDATE channel_link_attempts
                    SET status = 'linked', poll_state_ciphertext = NULL,
                        lease_owner = NULL, lease_expires_at = NULL, updated_at = NOW()
                    WHERE attempt_id = %s
                    """,
                    (attempt_id,),
                )
                return True


async def _retire_binding_rows(cur: Any, binding_id: UUID | str) -> None:
    """Retire a binding while its row lock is held by a link finalization."""
    await cur.execute(
        """
        UPDATE channel_bindings
        SET binding_epoch = binding_epoch + 1,
            credentials_ciphertext = NULL, cursor_ciphertext = NULL,
            bound_peer_ciphertext = NULL, lease_owner = NULL,
            lease_expires_at = NULL, updated_at = NOW()
        WHERE binding_id = %s
        """,
        (binding_id,),
    )
    await cur.execute(
        """
        UPDATE channel_inbound_messages
        SET status = CASE WHEN status IN ('pending', 'claimed') THEN 'dead' ELSE status END,
            media_ciphertext = NULL, reply_context_ciphertext = NULL,
            lease_expires_at = NULL, last_error_code = 'binding_retired'
        WHERE binding_id = %s
        """,
        (binding_id,),
    )
    await cur.execute(
        """
        UPDATE channel_delivery_outbox
        SET status = CASE WHEN status IN ('pending', 'claimed') THEN 'dead' ELSE status END,
            payload_ciphertext = NULL, lease_expires_at = NULL,
            last_error_code = 'binding_retired'
        WHERE binding_id = %s
        """,
        (binding_id,),
    )
    await cur.execute(
        """
        UPDATE channel_sessions
        SET status = 'closed', closed_at = COALESCE(closed_at, NOW()),
            peer_ciphertext = NULL, agent_session_ref_ciphertext = NULL
        WHERE binding_id = %s
        """,
        (binding_id,),
    )


async def get_link_attempt_for_user(
    user_id: str, attempt_id: UUID
) -> dict[str, Any] | None:
    key = get_encryption_key()
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT attempt_id, channel_type, status, qr_code_url, expires_at,
                       pgp_sym_decrypt(poll_state_ciphertext, %s) AS poll_state
                FROM channel_link_attempts WHERE attempt_id = %s AND user_id = %s
                """,
                (key, attempt_id, user_id),
            )
            row = await cur.fetchone()
            return dict(row) if row else None


def challenge_from_row(row: dict[str, Any]) -> LinkChallenge:
    state = json.loads(row["poll_state"] or "{}")
    return LinkChallenge(
        channel_type=row["channel_type"],
        challenge_ref=str(row["attempt_id"]),
        qr_code_url=row["qr_code_url"],
        expires_at=row["expires_at"],
        provider_poll_state=LinkPollState(
            values=tuple((str(k), str(v)) for k, v in state.items())
        ),
    )


async def cancel_link_attempt(user_id: str, attempt_id: UUID) -> bool:
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE channel_link_attempts
                SET status = 'cancelled', poll_state_ciphertext = NULL,
                    lease_owner = NULL, lease_expires_at = NULL, updated_at = NOW()
                WHERE attempt_id = %s AND user_id = %s
                  AND status NOT IN ('linked', 'expired', 'failed', 'cancelled')
                """,
                (attempt_id, user_id),
            )
            return cur.rowcount == 1


async def update_binding_timeout(user_id: str, channel_type: str, seconds: int) -> bool:
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE channel_bindings SET idle_timeout_seconds = %s, updated_at = NOW() WHERE user_id = %s AND channel_type = %s AND status = 'active'",
                (seconds, user_id, channel_type),
            )
            return cur.rowcount == 1
