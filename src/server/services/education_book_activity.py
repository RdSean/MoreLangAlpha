"""Safe public activity projection and PostgreSQL-backed reconnect service."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from typing import Any, Protocol
from uuid import UUID

from src.server.database import education_book_activity as activity_repository
from src.server.services.workspace_status_pubsub import (
    ChannelWaitFn,
    subscribe_to_channel,
)
from src.utils.cache.redis_cache import get_cache_client


logger = logging.getLogger(__name__)


def book_activity_channel(job_id: str | UUID) -> str:
    return f"education:book-activity:{UUID(str(job_id))}"


async def publish_book_activity_hint(
    job_id: str | UUID,
    high_water_seq: int | None = None,
) -> None:
    """Best-effort compact wake hint; PostgreSQL remains authoritative."""
    cache = get_cache_client()
    if not cache.enabled or not cache.client:
        return
    payload = {
        "job_id": str(UUID(str(job_id))),
        "high_water_seq": high_water_seq,
    }
    try:
        await cache.client.publish(
            book_activity_channel(job_id),
            json.dumps(payload, separators=(",", ":")),
        )
    except Exception as exc:
        logger.debug("Book activity hint publish failed for %s: %s", job_id, exc)


class AppendFn(Protocol):
    async def __call__(self, **kwargs: Any) -> dict[str, Any]: ...


class BookActivityObserver:
    """Project raw run events to a deliberately small public vocabulary."""

    def __init__(
        self,
        *,
        job_id: str | UUID,
        item_id: str | UUID,
        attempt_token: UUID,
        append: AppendFn = activity_repository.append_book_activity_event,
        record_drops: AppendFn = activity_repository.record_book_activity_drops,
        mark_unavailable: AppendFn = activity_repository.mark_book_activity_unavailable,
        publish: Callable[
            [str | UUID, int | None], Awaitable[None]
        ] = publish_book_activity_hint,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.job_id = UUID(str(job_id))
        self.item_id = UUID(str(item_id))
        self.attempt_token = attempt_token
        self._append = append
        self._record_drops = record_drops
        self._mark_unavailable = mark_unavailable
        self._publish = publish
        self._monotonic = monotonic
        self._tool_names: dict[str, str] = {}
        self._progress_at: dict[str, float] = {}
        self._details_disabled = False
        self._unavailable_report_pending = False
        self._budget_exhausted = False
        self._pending_drops = 0
        self._last_drop_flush_at: float | None = None

    async def __call__(self, event_type: str, data: Mapping[str, Any]) -> None:
        if self._details_disabled:
            return
        if self._budget_exhausted:
            await self._record_omitted(event_type, data)
            return
        if event_type == "tool_calls":
            await self._observe_tool_calls(data)
        elif event_type == "tool_call_result":
            await self._observe_tool_result(data)
        elif event_type == "artifact":
            await self._observe_public_progress(data)

    async def _observe_tool_calls(self, data: Mapping[str, Any]) -> None:
        calls = data.get("tool_calls")
        if not isinstance(calls, list):
            return
        for index, tool_call in enumerate(calls):
            if not isinstance(tool_call, Mapping):
                continue
            call_id = str(tool_call.get("id") or "")
            name = str(tool_call.get("name") or "")
            if not call_id or not name:
                continue
            self._tool_names[call_id] = name
            await self._store(
                dedupe_key=f"tool-start:{self.item_id}:{self.attempt_token}:{call_id}",
                kind="tool",
                status="running",
                message=f"Running {name}"[:512],
                metadata={"tool_call_id": call_id, "tool_name": name},
            )
            if self._budget_exhausted:
                remaining = sum(
                    1
                    for call in calls[index + 1 :]
                    if isinstance(call, Mapping) and call.get("id") and call.get("name")
                )
                await self._queue_drops(remaining)
                break

    async def _observe_tool_result(self, data: Mapping[str, Any]) -> None:
        call_id = str(data.get("tool_call_id") or "")
        if not call_id:
            return
        name = self._tool_names.get(call_id, "Tool")
        failed = str(data.get("status") or "").lower() in {"error", "failed"}
        await self._store(
            dedupe_key=f"tool-finish:{self.item_id}:{self.attempt_token}:{call_id}",
            kind="tool",
            status="failed" if failed else "succeeded",
            message=(f"{name} failed" if failed else f"Finished {name}")[:512],
            metadata={"tool_call_id": call_id, "tool_name": name},
        )

    async def _observe_public_progress(self, data: Mapping[str, Any]) -> None:
        if data.get("artifact_type") != "report_progress":
            return
        payload = data.get("payload")
        if not isinstance(payload, Mapping):
            return
        event_key = str(data.get("artifact_id") or payload.get("event_key") or "")
        message = str(payload.get("message") or "").strip()
        if not event_key or not message:
            return
        now = self._monotonic()
        previous = self._progress_at.get(event_key)
        if previous is not None and now - previous < 1.0:
            return
        self._progress_at[event_key] = now
        await self._store(
            dedupe_key=(
                f"progress:{self.item_id}:{self.attempt_token}:{event_key}:{int(now)}"
            ),
            kind="progress",
            status=str(payload.get("status") or "running")[:32],
            message=message[:512],
            metadata={"stage": str(payload.get("stage") or "")[:128]},
        )

    async def _store(self, **event: Any) -> None:
        try:
            result = await self._append(
                job_id=self.job_id,
                item_id=self.item_id,
                attempt_token=self.attempt_token,
                **event,
            )
        except Exception:
            await self._disable_details()
            raise
        if result.get("outcome") == "budget_exhausted":
            self._budget_exhausted = True
            self._last_drop_flush_at = self._monotonic()
            high_water_seq = result.get("high_water_seq")
            if high_water_seq is not None:
                await self._publish(self.job_id, high_water_seq)
            return
        if result.get("outcome") == "stored":
            await self._publish(self.job_id, result.get("high_water_seq"))

    async def _record_omitted(self, event_type: str, data: Mapping[str, Any]) -> None:
        dropped = self._projected_event_count(event_type, data)
        await self._queue_drops(dropped)

    async def _queue_drops(self, dropped: int) -> None:
        if dropped <= 0:
            return
        self._pending_drops += dropped
        now = self._monotonic()
        if self._last_drop_flush_at is None or now - self._last_drop_flush_at >= 1.0:
            await self._flush_drops(now=now)

    @staticmethod
    def _projected_event_count(event_type: str, data: Mapping[str, Any]) -> int:
        if event_type == "tool_calls":
            calls = data.get("tool_calls")
            if not isinstance(calls, list):
                return 0
            return sum(
                1
                for call in calls
                if isinstance(call, Mapping) and call.get("id") and call.get("name")
            )
        if event_type == "tool_call_result":
            return int(bool(data.get("tool_call_id")))
        if event_type != "artifact" or data.get("artifact_type") != "report_progress":
            return 0
        payload = data.get("payload")
        return int(
            isinstance(payload, Mapping)
            and bool(data.get("artifact_id") or payload.get("event_key"))
            and bool(str(payload.get("message") or "").strip())
        )

    async def _flush_drops(self, *, now: float) -> None:
        if self._pending_drops == 0:
            return
        dropped_count = self._pending_drops
        try:
            result = await self._record_drops(
                job_id=self.job_id,
                item_id=self.item_id,
                attempt_token=self.attempt_token,
                dropped_count=dropped_count,
            )
        except Exception:
            await self._disable_details()
            raise
        self._pending_drops = 0
        self._last_drop_flush_at = now
        if result.get("outcome") == "stored":
            await self._publish(self.job_id, result.get("high_water_seq"))
        elif result.get("outcome") == "stale":
            self._details_disabled = True

    async def flush(self) -> None:
        """Persist a final coalesced dropped count before terminal callbacks run."""
        if self._unavailable_report_pending:
            await self._report_unavailable()
        if self._details_disabled:
            return
        await self._flush_drops(now=self._monotonic())

    async def _disable_details(self) -> None:
        self._details_disabled = True
        self._unavailable_report_pending = True
        await self._report_unavailable()

    async def _report_unavailable(self) -> None:
        try:
            result = await self._mark_unavailable(
                job_id=self.job_id,
                item_id=self.item_id,
                attempt_token=self.attempt_token,
            )
            if result.get("outcome") == "stored":
                self._unavailable_report_pending = False
                await self._publish(self.job_id, result.get("high_water_seq"))
            elif result.get("outcome") == "stale":
                self._unavailable_report_pending = False
        except Exception:
            logger.exception(
                "Could not mark textbook activity unavailable for job %s",
                self.job_id,
            )


class ActivityRepository(Protocol):
    async def get_book_activity_page(self, **kwargs: Any) -> dict[str, Any] | None: ...


class SubscribeFactory(Protocol):
    def __call__(
        self, channel: str
    ) -> AbstractAsyncContextManager[ChannelWaitFn | None]: ...


class BookActivityService:
    """Stream snapshot-bounded pages; Redis only decides when PG is reread."""

    def __init__(
        self,
        *,
        repository: ActivityRepository = activity_repository,
        subscribe: SubscribeFactory = subscribe_to_channel,
        poll_interval_seconds: float = 1.0,
        page_size: int = 200,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if page_size <= 0 or page_size > 2_100:
            raise ValueError("page_size is invalid")
        self._repository = repository
        self._subscribe = subscribe
        self._poll_interval_seconds = poll_interval_seconds
        self._page_size = page_size

    async def pages(
        self,
        *,
        job_id: str | UUID,
        parent_user_id: str,
        after_seq: int,
    ) -> AsyncIterator[dict[str, Any]]:
        cursor = after_seq
        initial = await self._read(
            job_id=job_id,
            parent_user_id=parent_user_id,
            after_seq=cursor,
        )
        if initial is None:
            return
        cursor = self._advance(cursor, initial)
        last_snapshot_state = (
            initial.get("status"),
            initial.get("activity_status"),
        )
        yield initial
        if self._finished(cursor, initial):
            return

        async with self._subscribe(book_activity_channel(job_id)) as wait_for_hint:
            while True:
                current = await self._read(
                    job_id=job_id,
                    parent_user_id=parent_user_id,
                    after_seq=cursor,
                )
                if current is None:
                    return
                current_snapshot_state = (
                    current.get("status"),
                    current.get("activity_status"),
                )
                if (
                    current["events"]
                    or current["cursor_expired"]
                    or current_snapshot_state != last_snapshot_state
                ):
                    cursor = self._advance(cursor, current)
                    yield current
                    last_snapshot_state = current_snapshot_state
                if self._finished(cursor, current):
                    return
                if current.get("has_more"):
                    continue
                if wait_for_hint is None:
                    await asyncio.sleep(self._poll_interval_seconds)
                else:
                    kind, _payload = await wait_for_hint(self._poll_interval_seconds)
                    if kind == "error":
                        wait_for_hint = None
                        await asyncio.sleep(self._poll_interval_seconds)

    async def _read(self, **kwargs: Any) -> dict[str, Any] | None:
        return await self._repository.get_book_activity_page(
            **kwargs,
            limit=self._page_size,
        )

    @staticmethod
    def _advance(cursor: int, page: Mapping[str, Any]) -> int:
        events = page.get("events") or []
        if not events:
            return cursor
        return max(cursor, max(int(event["seq"]) for event in events))

    @staticmethod
    def _finished(cursor: int, page: Mapping[str, Any]) -> bool:
        return bool(page.get("cursor_expired")) or (
            activity_repository.is_terminal_book_job_status(str(page.get("status")))
            and cursor >= int(page.get("high_water_seq") or 0)
        )
