"""Correlated service timings, independent of the nested model trace spans."""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
import json
import logging
from time import monotonic
from typing import Any


logger = logging.getLogger(__name__)


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
