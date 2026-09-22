"""Collect append-only managed progress while a generation run is live."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping
from contextlib import suppress
import logging
from time import monotonic
from typing import Any, Protocol

from src.server.database.education_textbooks import (
    ProgressEventPersistenceOutcome,
    persist_generation_progress_event,
)
from src.server.services.education_generation_progress import (
    ProgressEventValidationError,
    parse_progress_json_line,
)
from src.server.services.education_teaching_storage import managed_job_root


logger = logging.getLogger(__name__)

MAX_PROGRESS_FILE_BYTES = 16 * 1024 * 1024
DEFAULT_POLL_INTERVAL_SECONDS = 0.5
DEFAULT_FALLBACK_AFTER_SECONDS = 15.0
_PROGRESS_RELATIVE_PATH = ".langalpha/progress.jsonl"


class ManagedProgressSandbox(Protocol):
    async def adownload_file_bytes(self, path: str) -> bytes | None: ...


class ManagedProgressCollector:
    """Persist semantic progress independently of model/tool SSE activity."""

    def __init__(
        self,
        *,
        sandbox: ManagedProgressSandbox,
        generation_job_id: str,
        attempt_id: str,
        run_id: str | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL_SECONDS,
        fallback_after: float = DEFAULT_FALLBACK_AFTER_SECONDS,
        clock: Callable[[], float] = monotonic,
        checkpoint_stop_event: asyncio.Event | None = None,
    ) -> None:
        if poll_interval <= 0:
            raise ValueError("progress poll interval must be positive")
        if fallback_after <= 0:
            raise ValueError("progress fallback interval must be positive")
        self._sandbox = sandbox
        self._generation_job_id = generation_job_id
        self._attempt_id = attempt_id
        self._run_id = run_id
        self._poll_interval = poll_interval
        self._fallback_after = fallback_after
        self._clock = clock or monotonic
        self._path = f"{managed_job_root(generation_job_id)}/{_PROGRESS_RELATIVE_PATH}"
        self._checkpoint_stop_event = checkpoint_stop_event
        self._checkpoint_requested = False

        self._task: asyncio.Task[None] | None = None
        self._stopping = False
        self._offset = 0
        self._next_sequence = 0
        self._retry_backoff_seconds = 0.0
        self._last_semantic_at = self._clock()
        self._last_activity_at: float | None = None
        self._fallback_emitted_after: float | None = None

        self.latest_event_by_key: dict[str, dict[str, Any]] = {}
        self.errors: list[str] = []

    @property
    def checkpoint_requested(self) -> bool:
        return self._checkpoint_requested

    async def start(self) -> None:
        """Start the polling task once."""
        if self._task is not None and not self._task.done():
            return
        self._stopping = False
        self._task = asyncio.create_task(
            self._poll_loop(),
            name=f"education-progress-{self._attempt_id}",
        )

    async def poll_once(self) -> None:
        """Read newly appended bytes and persist each complete event."""
        try:
            content = await self._sandbox.adownload_file_bytes(self._path)
            if not isinstance(content, bytes):
                return
            if len(content) > MAX_PROGRESS_FILE_BYTES:
                self._record_error("managed progress file exceeds the size limit")
                return
            if len(content) < self._offset:
                self._record_error("managed progress file shrank unexpectedly")
                return
            if len(content) == self._offset:
                await self._maybe_emit_fallback()
                return
            persisted = await self._consume_available_bytes(content)
            if persisted:
                await self._maybe_emit_fallback()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._record_error(f"managed progress poll failed: {type(exc).__name__}")
            logger.warning(
                "Managed progress poll failed",
                extra={
                    "generation_job_id": self._generation_job_id,
                    "attempt_id": self._attempt_id,
                },
                exc_info=True,
            )

    async def flush(self) -> None:
        """Perform one final bounded read without changing the polling lifecycle."""
        await self.poll_once()

    async def stop(self) -> None:
        """Stop polling and flush bytes appended immediately before finalization."""
        if self._stopping:
            return
        self._stopping = True
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        await self.flush()

    def note_activity(self) -> None:
        """Record sanitized workflow activity for idle fallback projection."""
        self._last_activity_at = self._clock()

    async def _poll_loop(self) -> None:
        while not self._stopping:
            await self.poll_once()
            try:
                await asyncio.sleep(
                    max(self._poll_interval, self._retry_backoff_seconds)
                )
            except asyncio.CancelledError:
                raise

    async def _consume_available_bytes(self, content: bytes) -> bool:
        cursor = self._offset
        while cursor < len(content):
            newline = content.find(b"\n", cursor)
            if newline < 0:
                break
            raw_line = content[cursor:newline]
            next_sequence = self._next_sequence + 1
            next_offset = newline + 1
            if not raw_line.strip():
                self._next_sequence = next_sequence
                self._offset = next_offset
                cursor = next_offset
                continue
            try:
                event = parse_progress_json_line(raw_line)
            except ProgressEventValidationError:
                self._record_error(
                    f"managed progress line {next_sequence} is invalid"
                )
                self._next_sequence = next_sequence
                self._offset = next_offset
                cursor = next_offset
                continue
            acknowledged = await self._persist_event(next_sequence, event)
            if not acknowledged:
                self._retry_backoff_seconds = min(
                    max(self._poll_interval, self._retry_backoff_seconds * 2),
                    8.0,
                )
                return False
            self._retry_backoff_seconds = 0.0
            self._next_sequence = next_sequence
            self._offset = next_offset
            cursor = next_offset
        return True

    async def _persist_event(
        self,
        sequence: int,
        event: Mapping[str, Any],
    ) -> bool:
        try:
            result = await persist_generation_progress_event(
                generation_job_id=self._generation_job_id,
                attempt_id=self._attempt_id,
                run_id=self._run_id,
                sequence=sequence,
                event=event,
            )
        except Exception:
            self._record_error("managed progress persistence is unavailable")
            logger.warning(
                "Managed progress persistence failed",
                extra={
                    "generation_job_id": self._generation_job_id,
                    "attempt_id": self._attempt_id,
                    "sequence": sequence,
                },
                exc_info=True,
            )
            return False

        if result.outcome is ProgressEventPersistenceOutcome.REJECTED:
            self._record_error(
                f"managed progress sequence {sequence} conflicts with durable state"
            )
            return False
        row = result.event
        if not isinstance(row, Mapping):
            self._record_error(
                f"managed progress sequence {sequence} has no durable projection"
            )
            return False

        projected = {
            **dict(row),
            **dict(event),
            "sequence": sequence,
        }
        self.latest_event_by_key[str(event["event_key"])] = projected
        self._last_semantic_at = self._clock()
        self._fallback_emitted_after = None
        self._maybe_trigger_checkpoint(event)
        return True

    def _maybe_trigger_checkpoint(self, event: Mapping[str, Any]) -> None:
        if (
            self._checkpoint_requested
            or self._checkpoint_stop_event is None
            or event.get("stage") != "chapter_analysis"
            or event.get("status") != "completed"
        ):
            return
        self._checkpoint_requested = True
        self._checkpoint_stop_event.set()

    async def _maybe_emit_fallback(self) -> None:
        now = self._clock()
        if self._last_activity_at is None:
            return
        if now - self._last_semantic_at < self._fallback_after:
            return
        if self._last_activity_at <= self._last_semantic_at:
            return
        if self._fallback_emitted_after == self._last_semantic_at:
            return

        latest_by_stage: dict[str, Mapping[str, Any]] = {}
        for event in self.latest_event_by_key.values():
            stage = str(event.get("stage") or "")
            if not stage:
                continue
            previous = latest_by_stage.get(stage)
            if previous is None or int(event.get("sequence") or 0) > int(
                previous.get("sequence") or 0
            ):
                latest_by_stage[stage] = event
        running_events = [
            event
            for event in latest_by_stage.values()
            if event.get("status") in {"queued", "running"}
        ]
        if not running_events:
            return
        latest = max(
            running_events,
            key=lambda event: int(event.get("sequence") or 0),
        )
        self._fallback_emitted_after = self._last_semantic_at
        self._next_sequence += 1
        sequence = self._next_sequence
        event = {
            "event_key": f"fallback:{latest['stage']}:executing",
            "stage": str(latest["stage"]),
            "substage": "executing",
            "status": "running",
            "label": "执行环境步骤",
            "metadata": {"fallback": True},
        }
        await self._persist_event(sequence, event)

    def _record_error(self, message: str) -> None:
        self.errors.append(message)
        if len(self.errors) > 100:
            del self.errors[: len(self.errors) - 100]
