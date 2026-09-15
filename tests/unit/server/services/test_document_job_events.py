from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.server.services import document_job_events
from src.server.services.document_job_events import (
    DocumentJobEventService,
    publish_document_job_hint,
)


def _job(version: int, status: str = "running") -> dict[str, object]:
    return {
        "job_id": "job-A1b2C3d4E5f6",
        "status": status,
        "stage": "completed" if status == "completed" else "parsing",
        "percentage": 100 if status == "completed" else 40,
        "status_version": version,
    }


class _Repository:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = rows
        self.calls = 0
        self.cancel_calls = 0

    async def get_owned_job(self, **kwargs):
        index = min(self.calls, len(self.rows) - 1)
        self.calls += 1
        return dict(self.rows[index])


class _Subscription:
    def __init__(self, waits: list[tuple[str, dict | None]] | None) -> None:
        self.waits = list(waits) if waits is not None else None
        self.entered = False
        self.channels: list[str] = []

    @asynccontextmanager
    async def subscribe(self, channel: str):
        self.entered = True
        self.channels.append(channel)
        if self.waits is None:
            yield None
            return

        async def wait(timeout):
            if self.waits:
                return self.waits.pop(0)
            await asyncio.sleep(timeout or 0)
            return ("timeout", None)

        yield wait


@pytest.mark.asyncio
async def test_publish_hint_contains_only_job_identity_and_version(monkeypatch) -> None:
    publish = AsyncMock()
    cache = SimpleNamespace(enabled=True, client=SimpleNamespace(publish=publish))
    monkeypatch.setattr(document_job_events, "get_cache_client", lambda: cache)

    await publish_document_job_hint("job-A1b2C3d4E5f6", 7)

    channel, raw_payload = publish.await_args.args
    assert channel == "documents:jobs:job-A1b2C3d4E5f6"
    assert json.loads(raw_payload) == {
        "job_id": "job-A1b2C3d4E5f6",
        "status_version": 7,
    }


@pytest.mark.asyncio
async def test_sse_emits_database_snapshot_before_subscribing() -> None:
    repository = _Repository([_job(1)])
    subscription = _Subscription([])
    service = DocumentJobEventService(
        repository=repository,
        subscribe=subscription.subscribe,
        poll_interval_seconds=0.01,
    )
    stream = service.snapshots(
        owner_user_id="owner-1",
        job_id="job-A1b2C3d4E5f6",
    )

    first = await anext(stream)

    assert first["status_version"] == 1
    assert not subscription.entered
    await stream.aclose()


@pytest.mark.asyncio
async def test_redis_hint_causes_database_reread_not_payload_trust() -> None:
    repository = _Repository([_job(1), _job(1), _job(2)])
    subscription = _Subscription(
        [("message", {"job_id": "wrong", "status_version": 999})]
    )
    service = DocumentJobEventService(
        repository=repository,
        subscribe=subscription.subscribe,
        poll_interval_seconds=0.01,
    )
    stream = service.snapshots(
        owner_user_id="owner-1",
        job_id="job-A1b2C3d4E5f6",
    )

    assert (await anext(stream))["status_version"] == 1
    second = await anext(stream)

    assert second == _job(2)
    assert second["job_id"] == "job-A1b2C3d4E5f6"
    await stream.aclose()


@pytest.mark.asyncio
async def test_poll_fallback_observes_update_when_hint_is_lost() -> None:
    repository = _Repository([_job(1), _job(1), _job(2)])
    subscription = _Subscription([("timeout", None)])
    service = DocumentJobEventService(
        repository=repository,
        subscribe=subscription.subscribe,
        poll_interval_seconds=0.01,
    )
    stream = service.snapshots(
        owner_user_id="owner-1",
        job_id="job-A1b2C3d4E5f6",
    )

    await anext(stream)
    assert (await anext(stream))["status_version"] == 2
    await stream.aclose()


@pytest.mark.asyncio
async def test_sync_wait_returns_completed_snapshot_inside_deadline() -> None:
    repository = _Repository([_job(1), _job(1), _job(2, "completed")])
    subscription = _Subscription([("message", {"status_version": 2})])
    service = DocumentJobEventService(
        repository=repository,
        subscribe=subscription.subscribe,
        poll_interval_seconds=0.01,
        sync_wait_seconds=1,
    )

    result = await service.wait_for_terminal_job(
        owner_user_id="owner-1",
        job_id="job-A1b2C3d4E5f6",
    )

    assert result is not None and result["status"] == "completed"


@pytest.mark.asyncio
async def test_sync_wait_timeout_returns_pending_without_cancelling() -> None:
    repository = _Repository([_job(1)])
    subscription = _Subscription(None)
    service = DocumentJobEventService(
        repository=repository,
        subscribe=subscription.subscribe,
        poll_interval_seconds=0.01,
        sync_wait_seconds=0.02,
    )

    result = await service.wait_for_terminal_job(
        owner_user_id="owner-1",
        job_id="job-A1b2C3d4E5f6",
    )

    assert result is not None and result["status"] == "running"
    assert repository.cancel_calls == 0


@pytest.mark.asyncio
async def test_disconnect_does_not_cancel_durable_job() -> None:
    repository = _Repository([_job(1)])
    subscription = _Subscription([])
    service = DocumentJobEventService(
        repository=repository,
        subscribe=subscription.subscribe,
        poll_interval_seconds=0.01,
    )
    stream = service.snapshots(
        owner_user_id="owner-1",
        job_id="job-A1b2C3d4E5f6",
    )

    await anext(stream)
    await stream.aclose()

    assert repository.cancel_calls == 0
