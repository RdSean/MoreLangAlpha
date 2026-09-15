"""Database-authoritative snapshots with optional Redis wake hints."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol

from src.config.settings import get_document_parsing_config
from src.server.database import document_jobs as job_repository
from src.server.services.workspace_status_pubsub import (
    ChannelWaitFn,
    subscribe_to_channel,
)
from src.utils.cache.redis_cache import get_cache_client


logger = logging.getLogger(__name__)

_TERMINAL_STATUSES = frozenset({"completed", "failed", "cancelled"})


class EventRepository(Protocol):
    async def get_owned_job(self, **kwargs: str) -> dict[str, Any] | None: ...


class SubscribeFactory(Protocol):
    def __call__(
        self,
        channel: str,
    ) -> AbstractAsyncContextManager[ChannelWaitFn | None]: ...


def document_job_channel(job_id: str) -> str:
    return f"documents:jobs:{job_id}"


async def publish_document_job_hint(job_id: str, status_version: int) -> None:
    """Publish a compact best-effort wake hint after a committed DB update."""
    cache = get_cache_client()
    if not cache.enabled or not cache.client:
        return
    payload = {"job_id": job_id, "status_version": status_version}
    try:
        await cache.client.publish(
            document_job_channel(job_id),
            json.dumps(payload, separators=(",", ":")),
        )
    except Exception as error:
        logger.debug("Document job hint publish failed for %s: %s", job_id, error)


class DocumentJobEventService:
    """Read owned job snapshots; Redis only controls how soon DB is reread."""

    def __init__(
        self,
        *,
        repository: EventRepository = job_repository,
        subscribe: SubscribeFactory = subscribe_to_channel,
        poll_interval_seconds: float = 1,
        sync_wait_seconds: float | None = None,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        configured_wait = get_document_parsing_config().sync_wait_seconds
        self._repository = repository
        self._subscribe = subscribe
        self._poll_interval_seconds = poll_interval_seconds
        self._sync_wait_seconds = (
            float(configured_wait)
            if sync_wait_seconds is None
            else sync_wait_seconds
        )
        if self._sync_wait_seconds <= 0:
            raise ValueError("sync_wait_seconds must be positive")

    async def snapshots(
        self,
        *,
        owner_user_id: str,
        job_id: str,
        after_status_version: int = -1,
    ) -> AsyncIterator[dict[str, Any]]:
        last_version = after_status_version
        initial = await self._read(owner_user_id=owner_user_id, job_id=job_id)
        if initial is None:
            return
        if _version(initial) > last_version:
            last_version = _version(initial)
            yield initial
        if _is_terminal(initial):
            return

        async with self._subscribe(document_job_channel(job_id)) as subscribed:
            # Close the read-before-subscribe race with an authoritative reread.
            current = await self._read(
                owner_user_id=owner_user_id,
                job_id=job_id,
            )
            if current is None:
                return
            if _version(current) > last_version:
                last_version = _version(current)
                yield current
            if _is_terminal(current):
                return

            wait_for_hint = subscribed
            while True:
                if wait_for_hint is None:
                    await asyncio.sleep(self._poll_interval_seconds)
                else:
                    kind, _untrusted_payload = await wait_for_hint(
                        self._poll_interval_seconds
                    )
                    if kind == "error":
                        wait_for_hint = None
                        await asyncio.sleep(self._poll_interval_seconds)

                current = await self._read(
                    owner_user_id=owner_user_id,
                    job_id=job_id,
                )
                if current is None:
                    return
                if _version(current) <= last_version:
                    if _is_terminal(current):
                        return
                    continue
                last_version = _version(current)
                yield current
                if _is_terminal(current):
                    return

    async def wait_for_terminal_job(
        self,
        *,
        owner_user_id: str,
        job_id: str,
    ) -> dict[str, Any] | None:
        stream = self.snapshots(
            owner_user_id=owner_user_id,
            job_id=job_id,
        )
        latest: dict[str, Any] | None = None
        try:
            async with asyncio.timeout(self._sync_wait_seconds):
                async for snapshot in stream:
                    latest = snapshot
                    if _is_terminal(snapshot):
                        return snapshot
        except TimeoutError:
            pass
        finally:
            await stream.aclose()

        current = await self._read(owner_user_id=owner_user_id, job_id=job_id)
        return current or latest

    async def _read(
        self,
        *,
        owner_user_id: str,
        job_id: str,
    ) -> dict[str, Any] | None:
        return await self._repository.get_owned_job(
            owner_user_id=owner_user_id,
            job_id=job_id,
        )


def _version(snapshot: dict[str, Any]) -> int:
    return int(snapshot["status_version"])


def _is_terminal(snapshot: dict[str, Any]) -> bool:
    return snapshot.get("status") in _TERMINAL_STATUSES
