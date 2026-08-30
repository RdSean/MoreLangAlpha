"""Durable persistence for generic channel gateways.

This module is the only SQL boundary for channel state.  Provider adapters and
the gateway runner receive typed values, while credentials, cursors, routes,
media references, and reply contexts remain encrypted in PostgreSQL.
"""

from __future__ import annotations

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
    LinkPollState,
    BindingView,
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


@dataclass(frozen=True)
class PersistedInbound:
    provider_message_id: str
    session_id: UUID | None
    kind: InboundKind
    peer_lookup_hash: str | None
    text: str | None
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
                              lease_generation, idle_timeout_seconds
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
) -> int:
    """Persist a cursor and deduplicated inbound rows atomically."""
    key = get_encryption_key()
    inserted = 0
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                for message in messages:
                    await cur.execute(
                        """
                        INSERT INTO channel_inbound_messages (
                            binding_id, session_id, provider_message_id, kind, status,
                            peer_lookup_hash, text_content, media_ciphertext,
                            reply_context_ciphertext, received_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s, %s,
                            CASE WHEN %s IS NULL THEN NULL
                                 ELSE pgp_sym_encrypt(%s, %s) END,
                            CASE WHEN %s IS NULL THEN NULL
                                 ELSE pgp_sym_encrypt(%s, %s) END,
                            %s
                        )
                        ON CONFLICT (binding_id, provider_message_id) DO NOTHING
                        """,
                        (
                            binding_id,
                            message.session_id,
                            message.provider_message_id,
                            message.kind.value,
                            "ignored"
                            if message.kind is InboundKind.IGNORED
                            else "pending",
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
                        ),
                    )
                    inserted += int(cur.rowcount or 0)
                await cur.execute(
                    """
                    UPDATE channel_bindings
                    SET cursor_ciphertext = pgp_sym_encrypt(%s, %s), updated_at = NOW()
                    WHERE binding_id = %s
                    """,
                    (cursor, key, binding_id),
                )
    return inserted


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
                    )
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
                           b.user_id, b.channel_type,
                           pgp_sym_decrypt(s.agent_session_ref_ciphertext, %s)
                               AS agent_session_ref,
                           pgp_sym_decrypt(s.peer_ciphertext, %s) AS peer_ref
                    FROM claimed c
                    JOIN channel_bindings b ON b.binding_id = c.binding_id
                    LEFT JOIN channel_sessions s ON s.session_id = c.session_id
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
                            peer_ref=(str(row["peer_ref"]) if row["peer_ref"] else None),
                            attempts=int(row["attempts"]),
                            channel_type=str(row["channel_type"]),
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
                await cur.execute(
                    """
                    UPDATE channel_inbound_messages
                    SET status = 'done', processed_at = NOW(), lease_expires_at = NULL
                    WHERE inbound_message_id = %s AND status = 'claimed'
                      AND lease_generation = %s
                    """,
                    (claim.inbound_message_id, claim.lease_generation),
                )
                if cur.rowcount != 1:
                    return False
                if result.session_ref and claim.session_id:
                    await cur.execute(
                        """
                        UPDATE channel_sessions
                        SET agent_session_ref_ciphertext = pgp_sym_encrypt(%s, %s)
                        WHERE session_id = %s AND status = 'active'
                        """,
                        (result.session_ref, key, claim.session_id),
                    )
                for sequence_no, payload in enumerate(parts):
                    client_id = uuid5(
                        NAMESPACE_URL,
                        f"https://langalpha.local/channel-delivery/{claim.inbound_message_id}/{sequence_no}",
                    )
                    await cur.execute(
                        """
                        INSERT INTO channel_delivery_outbox (
                            inbound_message_id, session_id, binding_id, sequence_no,
                            client_id, payload_ciphertext
                        ) VALUES (%s, %s, %s, %s, %s, pgp_sym_encrypt(%s, %s))
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
                          AND NOT EXISTS (
                              SELECT 1 FROM channel_delivery_outbox prior
                              WHERE prior.session_id = o.session_id
                                AND (prior.status = 'pending'
                                     OR (prior.status = 'claimed' AND prior.lease_expires_at > NOW()))
                                AND prior.sequence_no < o.sequence_no
                          )
                        ORDER BY o.created_at, o.delivery_id
                        LIMIT %s FOR UPDATE SKIP LOCKED
                    )
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
                           b.user_id, b.channel_type,
                           pgp_sym_decrypt(b.credentials_ciphertext, %s) AS credentials
                    FROM claimed c
                    JOIN channel_inbound_messages i
                      ON i.inbound_message_id = c.inbound_message_id
                    JOIN channel_bindings b ON b.binding_id = c.binding_id
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
                                values=tuple((str(k), str(v)) for k, v in credentials_data.items()),
                            ),
                            attempts=int(row["attempts"]),
                            channel_type=str(row["channel_type"]),
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
    """Remove ciphertext while retaining the binding row as a minimal audit record."""
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE channel_bindings
                SET status = 'disabled', credentials_ciphertext = NULL,
                    cursor_ciphertext = NULL, bound_peer_ciphertext = NULL,
                    lease_owner = NULL, lease_expires_at = NULL, updated_at = NOW()
                WHERE binding_id = %s AND user_id = %s
                """,
                (binding_id, user_id),
            )
            return cur.rowcount == 1


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


@dataclass(frozen=True)
class ChannelSessionRecord:
    session_id: UUID
    peer_ref: str
    agent_session_ref: str | None
    last_inbound_at: datetime


async def get_or_rotate_session(
    *,
    binding_id: UUID | str,
    peer_ref: str,
    peer_lookup_hash: str,
    received_at: datetime,
    idle_timeout_seconds: int,
    external_thread_id: str,
) -> ChannelSessionRecord:
    """Select or create the active peer session under a binding row lock."""
    key = get_encryption_key()
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT binding_id FROM channel_bindings WHERE binding_id = %s FOR UPDATE",
                    (binding_id,),
                )
                if not await cur.fetchone():
                    raise LookupError("channel binding not found")
                await cur.execute(
                    """
                    SELECT session_id, peer_ciphertext, agent_session_ref_ciphertext,
                           last_inbound_at
                    FROM channel_sessions
                    WHERE binding_id = %s AND peer_lookup_hash = %s AND status = 'active'
                    FOR UPDATE
                    """,
                    (binding_id, peer_lookup_hash),
                )
                row = await cur.fetchone()
                if row:
                    last = row["last_inbound_at"]
                    elapsed = (received_at - last).total_seconds()
                    if elapsed <= idle_timeout_seconds:
                        await cur.execute(
                            "UPDATE channel_sessions SET last_inbound_at = %s WHERE session_id = %s",
                            (received_at, row["session_id"]),
                        )
                        peer = str(row["peer_ciphertext"] or "")
                        # Decrypt using SQL to avoid exposing ciphertext to callers.
                        await cur.execute(
                            "SELECT pgp_sym_decrypt(peer_ciphertext, %s) AS peer, pgp_sym_decrypt(agent_session_ref_ciphertext, %s) AS agent_ref FROM channel_sessions WHERE session_id = %s",
                            (key, key, row["session_id"]),
                        )
                        decrypted = await cur.fetchone()
                        return ChannelSessionRecord(
                            session_id=row["session_id"],
                            peer_ref=str(decrypted["peer"] or peer),
                            agent_session_ref=(str(decrypted["agent_ref"]) if decrypted and decrypted["agent_ref"] else None),
                            last_inbound_at=received_at,
                        )
                    await cur.execute(
                        "UPDATE channel_sessions SET status = 'closed', closed_at = NOW() WHERE session_id = %s",
                        (row["session_id"],),
                    )
                await cur.execute(
                    """
                    INSERT INTO channel_sessions
                      (binding_id, peer_lookup_hash, peer_ciphertext, status, last_inbound_at)
                    VALUES (%s, %s, pgp_sym_encrypt(%s, %s), 'active', %s)
                    RETURNING session_id, last_inbound_at
                    """,
                    (binding_id, peer_lookup_hash, peer_ref, key, received_at),
                )
                created = await cur.fetchone()
                return ChannelSessionRecord(
                    session_id=created["session_id"],
                    peer_ref=peer_ref,
                    agent_session_ref=None,
                    last_inbound_at=created["last_inbound_at"],
                )


async def set_agent_session_ref(session_id: UUID | str, ref: str) -> bool:
    key = get_encryption_key()
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE channel_sessions SET agent_session_ref_ciphertext = pgp_sym_encrypt(%s, %s) WHERE session_id = %s AND status = 'active'",
                (ref, key, session_id),
            )
            return cur.rowcount == 1


async def mark_binding_reauth(binding_id: UUID | str, error_code: str = "session_expired") -> bool:
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE channel_bindings
                SET status = 'reauth_required', credentials_ciphertext = NULL,
                    cursor_ciphertext = NULL, last_error_code = %s,
                    lease_owner = NULL, lease_expires_at = NULL, updated_at = NOW()
                WHERE binding_id = %s AND status <> 'disabled'
                """,
                (error_code[:64], binding_id),
            )
            return cur.rowcount == 1


async def create_link_attempt(*, user_id: str, channel_type: str, challenge: LinkChallenge) -> UUID:
    key = get_encryption_key()
    state = _json(dict(challenge.provider_poll_state.values))
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO channel_link_attempts
                    (user_id, channel_type, qr_code_url, poll_state_ciphertext, expires_at)
                VALUES (%s, %s, %s, pgp_sym_encrypt(%s, %s), %s)
                RETURNING attempt_id
                """,
                (user_id, channel_type, challenge.qr_code_url, state, key, challenge.expires_at),
            )
            row = await cur.fetchone()
            return row[0]


async def get_link_attempt_for_user(user_id: str, attempt_id: UUID) -> dict[str, Any] | None:
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
        provider_poll_state=LinkPollState(values=tuple((str(k), str(v)) for k, v in state.items())),
    )


async def update_link_poll_state(attempt_id: UUID, state: LinkPollState) -> bool:
    key = get_encryption_key()
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE channel_link_attempts SET poll_state_ciphertext = pgp_sym_encrypt(%s, %s), updated_at = NOW() WHERE attempt_id = %s",
                (_json(dict(state.values)), key, attempt_id),
            )
            return cur.rowcount == 1


async def update_link_attempt_status(attempt_id: UUID, status: str) -> bool:
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE channel_link_attempts SET status = %s, updated_at = NOW() WHERE attempt_id = %s",
                (status, attempt_id),
            )
            return cur.rowcount == 1


async def cancel_link_attempt(user_id: str, attempt_id: UUID) -> bool:
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE channel_link_attempts SET status = 'cancelled', updated_at = NOW() WHERE attempt_id = %s AND user_id = %s AND status NOT IN ('linked', 'expired', 'failed', 'cancelled')",
                (attempt_id, user_id),
            )
            return cur.rowcount == 1


async def activate_binding(*, user_id: str, channel_type: str, binding: BindingView, route: BindingRoute, credentials: BindingCredentials) -> None:
    key = get_encryption_key()
    values = dict(credentials.values)
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO channel_bindings
                    (user_id, channel_type, status, credentials_ciphertext,
                     bound_peer_ciphertext, cursor_ciphertext)
                VALUES (%s, %s, 'active', pgp_sym_encrypt(%s, %s), pgp_sym_encrypt(%s, %s), pgp_sym_encrypt(%s, %s))
                ON CONFLICT (user_id, channel_type) DO UPDATE SET status = 'active',
                    credentials_ciphertext = EXCLUDED.credentials_ciphertext,
                    bound_peer_ciphertext = EXCLUDED.bound_peer_ciphertext,
                    cursor_ciphertext = EXCLUDED.cursor_ciphertext, last_error_code = NULL,
                    updated_at = NOW()
                """,
                (user_id, channel_type, _json(values), key, route.peer_ref, key, "", key),
            )


async def update_binding_timeout(user_id: str, channel_type: str, seconds: int) -> bool:
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "UPDATE channel_bindings SET idle_timeout_seconds = %s, updated_at = NOW() WHERE user_id = %s AND channel_type = %s AND status = 'active'",
                (seconds, user_id, channel_type),
            )
            return cur.rowcount == 1
