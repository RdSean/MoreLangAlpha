"""Per-process claimant for database-authoritative document parse jobs."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol
from uuid import uuid4

from src.server.database import document_jobs as job_repository
from src.server.documents.executor import ClaimedDocumentJob, DocumentJobExecutor


logger = logging.getLogger(__name__)


class WorkerRepository(Protocol):
    async def claim_next_job(self, **kwargs: object) -> dict[str, Any] | None: ...

    async def renew_lease(self, **kwargs: object) -> dict[str, Any] | None: ...

    async def recover_expired_jobs(
        self, **kwargs: object
    ) -> list[dict[str, Any]]: ...


class DocumentJobWorker:
    """Run local execution tasks while leases and status remain in PostgreSQL."""

    def __init__(
        self,
        *,
        executor: DocumentJobExecutor,
        repository: WorkerRepository = job_repository,
        claimant_id: str | None = None,
        lease_seconds: int = 60,
        renew_interval_seconds: float = 20,
        poll_interval_seconds: float = 1,
        concurrency: int = 2,
    ) -> None:
        if (
            lease_seconds <= 0
            or renew_interval_seconds <= 0
            or poll_interval_seconds <= 0
            or concurrency <= 0
        ):
            raise ValueError("worker limits must be positive")
        if renew_interval_seconds >= lease_seconds:
            raise ValueError("renew interval must be shorter than the lease")
        self._repository = repository
        self._executor = executor
        self._claimant_id = claimant_id or f"document-worker-{uuid4()}"
        self._lease_seconds = lease_seconds
        self._renew_interval_seconds = renew_interval_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._semaphore = asyncio.Semaphore(concurrency)
        self._stop = asyncio.Event()
        self._poll_task: asyncio.Task[None] | None = None
        self._running: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        if self._poll_task is not None and not self._poll_task.done():
            return
        await self._repository.recover_expired_jobs(limit=100)
        self._stop.clear()
        self._poll_task = asyncio.create_task(
            self._poll_loop(),
            name="document_job_worker_poll",
        )

    async def shutdown(self) -> None:
        self._stop.set()
        if self._poll_task is not None:
            self._poll_task.cancel()
            await asyncio.gather(self._poll_task, return_exceptions=True)
            self._poll_task = None
        for task in tuple(self._running):
            task.cancel()
        if self._running:
            await asyncio.gather(*tuple(self._running), return_exceptions=True)

    async def run_once(self) -> bool:
        """Claim and schedule at most one job without waiting for a busy slot."""
        if self._semaphore.locked():
            return False
        await self._semaphore.acquire()
        try:
            row = await self._repository.claim_next_job(
                claimed_by=self._claimant_id,
                lease_seconds=self._lease_seconds,
            )
            if row is None:
                self._semaphore.release()
                return False
            claim = ClaimedDocumentJob.from_row(
                row,
                claimed_by=self._claimant_id,
            )
            task = asyncio.create_task(
                self._run_claim(claim),
                name=f"document_job_{claim.job_id}",
            )
            self._running.add(task)
            task.add_done_callback(self._running.discard)
            return True
        except BaseException:
            self._semaphore.release()
            raise

    async def wait_until_idle(self) -> None:
        while self._running:
            await asyncio.gather(*tuple(self._running), return_exceptions=True)

    async def _poll_loop(self) -> None:
        while not self._stop.is_set():
            try:
                claimed = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Document job claim failed")
                claimed = False
            if claimed:
                continue
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self._poll_interval_seconds,
                )
            except asyncio.TimeoutError:
                pass

    async def _run_claim(self, claim: ClaimedDocumentJob) -> None:
        execution = asyncio.create_task(
            self._executor.execute(claim),
            name=f"document_job_execution_{claim.job_id}",
        )
        try:
            while True:
                done, _ = await asyncio.wait(
                    {execution},
                    timeout=self._renew_interval_seconds,
                )
                if done:
                    await execution
                    return
                async with claim.lock:
                    renewed = await self._repository.renew_lease(
                        job_id=claim.job_id,
                        claimed_by=claim.claimed_by,
                        attempt_count=claim.attempt_count,
                        expected_status_version=claim.status_version,
                        lease_seconds=self._lease_seconds,
                    )
                    if renewed is None:
                        execution.cancel()
                        await asyncio.gather(execution, return_exceptions=True)
                        return
                    claim.status_version = int(renewed["status_version"])
        except asyncio.CancelledError:
            execution.cancel()
            await asyncio.gather(execution, return_exceptions=True)
            raise
        except Exception:
            execution.cancel()
            await asyncio.gather(execution, return_exceptions=True)
            logger.exception("Document job execution failed: %s", claim.job_id)
        finally:
            self._semaphore.release()
