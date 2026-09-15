from __future__ import annotations

import asyncio

import pytest

from src.server.services.document_job_worker import DocumentJobWorker


def _job() -> dict[str, object]:
    return {
        "job_id": "job-A1b2C3d4E5f6",
        "attempt_count": 1,
        "status_version": 1,
    }


class _Repository:
    def __init__(self) -> None:
        self.claims = [_job()]
        self.renewals: list[dict[str, object]] = []
        self.recovered = False

    async def claim_next_job(self, **kwargs):
        return self.claims.pop(0) if self.claims else None

    async def renew_lease(self, **kwargs):
        self.renewals.append(kwargs)
        return {
            **_job(),
            "status": "running",
            "status_version": kwargs["expected_status_version"],
        }

    async def recover_expired_jobs(self, **kwargs):
        self.recovered = True
        return []


class _Executor:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(self, claim):
        self.started.set()
        await self.release.wait()
        return {"status": "completed"}


class _FailingRenewRepository(_Repository):
    async def renew_lease(self, **kwargs):
        raise RuntimeError("database unavailable")


class _CancellableExecutor(_Executor):
    def __init__(self) -> None:
        super().__init__()
        self.cancelled = asyncio.Event()

    async def execute(self, claim):
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


@pytest.mark.asyncio
async def test_worker_renews_lease_until_execution_finishes() -> None:
    repository = _Repository()
    executor = _Executor()
    worker = DocumentJobWorker(
        repository=repository,
        executor=executor,
        claimant_id="worker-1",
        lease_seconds=10,
        renew_interval_seconds=0.01,
        poll_interval_seconds=1,
        concurrency=1,
    )

    assert await worker.run_once()
    await executor.started.wait()
    await asyncio.sleep(0.03)
    executor.release.set()
    await worker.wait_until_idle()

    assert len(repository.renewals) >= 2
    assert all(call["claimed_by"] == "worker-1" for call in repository.renewals)


@pytest.mark.asyncio
async def test_worker_start_recovers_expired_claims_before_polling() -> None:
    repository = _Repository()
    repository.claims.clear()
    worker = DocumentJobWorker(
        repository=repository,
        executor=_Executor(),
        claimant_id="worker-1",
        lease_seconds=10,
        renew_interval_seconds=1,
        poll_interval_seconds=1,
        concurrency=1,
    )

    await worker.start()
    await worker.shutdown()

    assert repository.recovered


@pytest.mark.asyncio
async def test_lease_error_cancels_the_managed_execution_task() -> None:
    repository = _FailingRenewRepository()
    executor = _CancellableExecutor()
    worker = DocumentJobWorker(
        repository=repository,
        executor=executor,
        claimant_id="worker-1",
        lease_seconds=10,
        renew_interval_seconds=0.01,
        poll_interval_seconds=1,
        concurrency=1,
    )

    assert await worker.run_once()
    await executor.started.wait()
    await worker.wait_until_idle()

    assert executor.cancelled.is_set()
