"""Correlated service timings, independent of the nested model trace spans."""

from collections.abc import Iterator, Mapping, AsyncIterator
from contextlib import contextmanager, asynccontextmanager
import asyncio
import json
import logging
from time import monotonic
from typing import Any
from uuid import UUID

from src.server.database.education_book_timing import begin_book_phase, end_book_phase


logger = logging.getLogger(__name__)


class BookPhaseRecorder:
    def __init__(self, item: Mapping[str, Any], phase: str):
        self.item, self.phase = item, phase
        self.segment_id: UUID | None = None
        self.started: float | None = None

    async def start(self) -> None:
        if self.started is not None:
            return
        try:
            self.segment_id = await begin_book_phase(
                item_id=self.item["item_id"],
                attempt_token=self.item["attempt_token"],
                phase=self.phase,
            )
        except Exception:
            logger.warning("Book timing start unavailable for phase %s", self.phase)
        self.started = monotonic()

    async def finish(self, status: str) -> None:
        if self.started is None:
            return
        elapsed = monotonic() - self.started
        self.started = None
        if self.segment_id is not None:
            try:
                await end_book_phase(
                    segment_id=self.segment_id,
                    measured_ms=round(elapsed * 1000) if elapsed >= 0 else None,
                    status=status,
                )
            except Exception:
                logger.warning("Book timing end unavailable for phase %s", self.phase)


@asynccontextmanager
async def measured_book_phase(
    item: Mapping[str, Any], phase: str
) -> AsyncIterator[None]:
    """Durable boundaries are best effort; business fences remain mandatory elsewhere."""
    recorder = BookPhaseRecorder(item, phase)
    await recorder.start()
    status = "succeeded"
    try:
        yield
    except asyncio.CancelledError:
        status = "cancelled"
        raise
    except BaseException:
        status = "failed"
        raise
    finally:
        await recorder.finish(status)


async def get_book_job_statistics(
    *, job_id: UUID, parent_user_id: str, cursor: str | None = None, limit: int = 50
) -> dict[str, Any] | None:
    from src.server.database.education_book_timing import get_statistics_snapshot

    after = None
    if cursor is not None:
        try:
            item, attempt = cursor.split(":")
            after = UUID(item), int(attempt)
            if after[1] < 1:
                raise ValueError
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid statistics cursor") from exc
    if not 1 <= limit <= 100:
        raise ValueError("statistics limit must be between 1 and 100")
    snapshot = await get_statistics_snapshot(
        job_id=job_id, parent_user_id=parent_user_id, after=after, limit=limit + 1
    )
    if snapshot is None:
        return None
    summary, rows = snapshot
    page = rows[:limit]
    return {
        **summary,
        "attempts": page,
        "next_cursor": f"{page[-1]['item_id']}:{page[-1]['timing']['attempt']}"
        if len(rows) > limit
        else None,
    }


@contextmanager
def book_phase(
    item: Mapping[str, Any],
    phase: str,
    *,
    measurements: dict[str, float] | None = None,
) -> Iterator[None]:
    """Measure one boundary; never log content or interfere with its outcome."""
    started = monotonic()
    outcome = "error"
    try:
        yield
        outcome = "ok"
    finally:
        try:
            duration = round((monotonic() - started) * 1000, 3)
            if measurements is not None:
                measurements[phase] = duration
            record = {
                key: str(item[key])
                for key in (
                    "textbook_id",
                    "job_id",
                    "item_id",
                    "execution_id",
                    "attempt_token",
                    "run_id",
                    "operation",
                    "kind",
                    "attempt",
                )
                if item.get(key) is not None
            }
            record.update(phase=phase, duration_ms=duration, outcome=outcome)
            logger.info("education_book_timing %s", json.dumps(record, sort_keys=True))
        except Exception:
            # Telemetry must not replace the work's result or original exception.
            pass
