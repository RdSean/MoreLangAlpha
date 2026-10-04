"""Source IO must run independently of the runtime capacity and queue scanner."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_long_source_preparation_does_not_block_scans_or_reserve_ptc(monkeypatch):
    from src.server.services import education_book_jobs as jobs
    from src.server.services import education_book_preparation as prep

    item = {"item_id": uuid4(), "job_id": uuid4(), "attempt_token": uuid4()}
    entered = asyncio.Event()
    release = asyncio.Event()

    async def prepare(**kwargs):
        entered.set()
        await release.wait()

    claim = AsyncMock(side_effect=[item, None])
    monkeypatch.setattr(jobs, "claim_next_preparation_item", claim)
    monkeypatch.setattr(jobs, "has_book_runtime_work", AsyncMock(return_value=False))
    monkeypatch.setattr(prep, "prepare_book_item", prepare)
    reconcile = AsyncMock(return_value=0)
    monkeypatch.setattr(
        "src.server.services.education_book_recovery.reconcile_book_jobs_once",
        reconcile,
    )
    monkeypatch.setattr(
        jobs, "cleanup_settled_book_items_once", AsyncMock(return_value=0)
    )
    monkeypatch.setattr(
        "src.server.services.education_book_deletion.cleanup_deleted_textbooks_once",
        AsyncMock(return_value=0),
    )
    executor = AsyncMock()
    monkeypatch.setattr(jobs.LocalRunExecutor, "get_instance", lambda: executor)
    service = jobs.EducationBookJobService(
        worker_id="prep-a", lease_seconds=30, poll_interval=1
    )
    try:
        assert await asyncio.wait_for(service.scan_once(), 1) == 1
        await asyncio.wait_for(entered.wait(), 1)
        assert await asyncio.wait_for(service.scan_once(), 1) == 0
        assert reconcile.await_count == 2
        executor.reserve_capacity.assert_not_awaited()
    finally:
        release.set()
        await service.stop()


@pytest.mark.asyncio
async def test_no_run_preparation_recovery_requeues_instead_of_failing_runtime(
    monkeypatch,
):
    from src.server.services import education_book_recovery as recovery

    item = {
        "item_id": uuid4(),
        "attempt_token": uuid4(),
        "job_id": uuid4(),
        "execution_phase": "source_freezing",
        "run_id": None,
    }
    monkeypatch.setattr(
        recovery, "list_book_jobs_pending_cancellation", AsyncMock(return_value=[])
    )
    monkeypatch.setattr(
        recovery, "list_book_items_for_recovery", AsyncMock(return_value=[item])
    )
    requeue = AsyncMock(return_value=True)
    monkeypatch.setattr(recovery, "requeue_expired_book_preparation", requeue)
    fail = AsyncMock()
    monkeypatch.setattr(recovery, "fail_book_item", fail)
    monkeypatch.setattr(recovery, "publish_book_activity_hint", AsyncMock())
    assert (
        await recovery.reconcile_book_jobs_once(worker_id="prep-b", lease_seconds=30)
        == 1
    )
    fail.assert_not_awaited()
    requeue.assert_awaited_once_with(
        item_id=item["item_id"], attempt_token=item["attempt_token"]
    )
