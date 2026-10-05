from uuid import uuid4
from unittest.mock import AsyncMock

import pytest

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from src.server.services.education_book_usage import BookTokenTracker


def report(tracker, run_id, *, input_tokens=10, output_tokens=4):
    tracker.on_chat_model_start({}, [], run_id=run_id)
    tracker.on_llm_end(
        LLMResult(
            generations=[
                [
                    ChatGeneration(
                        message=AIMessage(
                            content="done",
                            response_metadata={"model_name": "test-model"},
                            usage_metadata={
                                "input_tokens": input_tokens,
                                "output_tokens": output_tokens,
                                "total_tokens": input_tokens + output_tokens,
                            },
                        )
                    )
                ]
            ]
        ),
        run_id=run_id,
    )


def test_usage_is_missing_until_provider_reports_and_deduplicates_calls():
    tracker = BookTokenTracker()
    assert tracker.snapshot() is None
    run_id = uuid4()
    report(tracker, run_id)
    report(tracker, run_id)
    assert tracker.snapshot() == {
        "status": "available",
        "input_tokens": 10,
        "output_tokens": 4,
        "total_tokens": 14,
        "recorded_calls": 1,
    }


def test_missing_or_failed_call_keeps_reported_usage_partial():
    tracker = BookTokenTracker()
    report(tracker, uuid4())
    missing = uuid4()
    tracker.on_chat_model_start({}, [], run_id=missing)
    tracker.on_llm_error(RuntimeError("provider failed"), run_id=missing)
    assert tracker.snapshot()["status"] == "partial"
    assert tracker.snapshot()["total_tokens"] == 14


def test_independent_attempt_trackers_do_not_share_usage():
    first, second = BookTokenTracker(), BookTokenTracker()
    report(first, uuid4())
    assert second.snapshot() is None


@pytest.mark.parametrize(
    "usage", [{}, {"prompt_tokens": 10}, {"prompt_tokens": 10, "completion_tokens": 4}]
)
def test_partial_raw_provider_fields_are_not_defaulted_to_zero(usage):
    tracker = BookTokenTracker()
    run_id = uuid4()
    tracker.on_chat_model_start({}, [], run_id=run_id)
    tracker.on_llm_end(
        LLMResult(
            generations=[
                [
                    ChatGeneration(
                        message=AIMessage(
                            content="done",
                            response_metadata={
                                "model_name": "test-model",
                                "token_usage": usage,
                            },
                        )
                    )
                ]
            ]
        ),
        run_id=run_id,
    )
    assert tracker.snapshot() is None


@pytest.mark.asyncio
async def test_usage_storage_failure_does_not_change_business_outcome(
    monkeypatch, caplog
):
    from src.server.database import education_book_usage
    from src.server.services.education_book_usage import persist_book_usage

    tracker = BookTokenTracker()
    report(tracker, uuid4())
    writer = AsyncMock(side_effect=RuntimeError("storage unavailable"))
    monkeypatch.setattr(education_book_usage, "record_book_usage", writer)
    await persist_book_usage(item_id=uuid4(), attempt_token=uuid4(), tracker=tracker)
    writer.assert_awaited_once()
    assert "could not be recorded" in caplog.text
