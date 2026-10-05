"""Provider-reported textbook usage, independent of billing and model settings."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.utils.tracking.per_call_token_tracker import PerCallTokenTracker

logger = logging.getLogger(__name__)


class BookTokenTracker(PerCallTokenTracker):
    def __init__(self) -> None:
        super().__init__()
        self._book_calls: set[str] = set()
        self._book_usage: dict[str, dict[str, int]] = {}

    def _capture_run_metadata(self, run_id: UUID, metadata: dict | None) -> None:
        super()._capture_run_metadata(run_id, metadata)
        with self._lock:
            self._book_calls.add(str(run_id))

    def on_llm_end(self, response: LLMResult, *, run_id: UUID, **kwargs: Any) -> None:
        super().on_llm_end(response, run_id=run_id, **kwargs)
        if not response.generations or not response.generations[0]:
            return
        generation = response.generations[0][0]
        if not isinstance(generation, ChatGeneration) or not isinstance(
            generation.message, AIMessage
        ):
            return
        message = generation.message
        keys = ("input_tokens", "output_tokens", "total_tokens")
        usage = message.usage_metadata
        if not isinstance(usage, dict) or not all(key in usage for key in keys):
            raw = message.response_metadata.get("token_usage")
            if not isinstance(raw, dict):
                return
            usage = {
                key: raw.get(source)
                for key, source in zip(
                    keys,
                    ("prompt_tokens", "completion_tokens", "total_tokens"),
                    strict=True,
                )
            }
        if any(type(usage.get(key)) is not int or usage[key] < 0 for key in keys):
            return
        # The billing extractor permits missing fields; this display snapshot does not.
        with self._lock:
            self._book_usage[str(run_id)] = {key: usage[key] for key in keys}

    def snapshot(self) -> dict[str, Any] | None:
        with self._lock:
            records = dict(self._book_usage)
            expected = set(self._book_calls)
        if not records:
            return None
        totals = {key: 0 for key in ("input_tokens", "output_tokens", "total_tokens")}
        recorded = 0
        for usage in records.values():
            for key in totals:
                totals[key] += usage[key]
            recorded += 1
        if not recorded:
            return None
        return {
            **totals,
            "recorded_calls": recorded,
            "status": "available" if set(records) == expected else "partial",
        }


async def persist_book_usage(
    *, item_id: UUID, attempt_token: UUID, tracker: BookTokenTracker
) -> None:
    from src.server.database.education_book_usage import record_book_usage

    usage = tracker.snapshot()
    if usage is None:
        return
    try:
        await record_book_usage(
            item_id=item_id, attempt_token=attempt_token, usage=usage
        )
    except Exception:
        # Telemetry failure must not turn a valid committed material into failure.
        logger.warning("Textbook token usage could not be recorded", exc_info=True)
