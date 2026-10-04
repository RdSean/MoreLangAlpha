"""Phase timings are correlated and cannot interfere with content processing."""

import json
import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.server.services import education_book_timing as timing


def test_phase_records_monotonic_elapsed_and_only_safe_identity(monkeypatch, caplog):
    ticks = iter([10.0, 10.25])
    monkeypatch.setattr(timing, "monotonic", lambda: next(ticks))
    item = {
        "job_id": "job",
        "execution_id": "execution",
        "run_id": "run",
        "requirements": "private content",
        "attempt": 2,
    }
    values = {}
    with (
        caplog.at_level("INFO"),
        timing.book_phase(item, "input_staging", measurements=values),
    ):
        pass
    assert values == {"input_staging": 250.0}
    record = json.loads(caplog.messages[-1].removeprefix("education_book_timing "))
    assert record["duration_ms"] == 250.0
    assert record["run_id"] == "run"
    assert record["outcome"] == "ok"
    assert "private content" not in caplog.text


def test_failed_work_is_timed_without_changing_exception(monkeypatch, caplog):
    ticks = iter([2.0, 2.1])
    monkeypatch.setattr(timing, "monotonic", lambda: next(ticks))
    error = ValueError("private failure")
    with caplog.at_level("INFO"), pytest.raises(ValueError) as caught:
        with timing.book_phase({}, "finalization"):
            raise error
    assert caught.value is error
    assert '"outcome": "error"' in caplog.text
    assert "private failure" not in caplog.text


def test_telemetry_failure_does_not_replace_result_or_exception(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise RuntimeError("logging unavailable")

    monkeypatch.setattr(timing.logger, "info", unavailable)
    with timing.book_phase({}, "preparation"):
        result = "delivered"
    assert result == "delivered"
    with pytest.raises(ValueError, match="source invalid"):
        with timing.book_phase({}, "finalization"):
            raise ValueError("source invalid")


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["succeeded", "failed", "cancelled"])
async def test_durable_phase_records_actual_interval_and_preserves_outcome(
    monkeypatch, outcome
):
    item = {"item_id": uuid4(), "attempt_token": uuid4()}
    segment = uuid4()
    begin, end = AsyncMock(return_value=segment), AsyncMock()
    monkeypatch.setattr(timing, "begin_book_phase", begin, raising=False)
    monkeypatch.setattr(timing, "end_book_phase", end, raising=False)
    ticks = iter([10, 10.375])
    monkeypatch.setattr(timing, "monotonic", lambda: next(ticks))
    error = ValueError("original") if outcome == "failed" else asyncio.CancelledError()

    async def work():
        async with timing.measured_book_phase(item, "input_staging"):
            if outcome != "succeeded":
                raise error
            return "ready"

    if outcome == "succeeded":
        assert await work() == "ready"
    else:
        with pytest.raises(type(error)) as caught:
            await work()
        assert caught.value is error
    begin.assert_awaited_once_with(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        phase="input_staging",
    )
    end.assert_awaited_once_with(segment_id=segment, measured_ms=375, status=outcome)


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_boundary", ["begin", "end"])
async def test_metrics_failure_does_not_replace_committed_business_result(
    monkeypatch, failed_boundary
):
    begin, end = AsyncMock(return_value=uuid4()), AsyncMock()
    (begin if failed_boundary == "begin" else end).side_effect = RuntimeError(
        "metrics unavailable"
    )
    monkeypatch.setattr(timing, "begin_book_phase", begin, raising=False)
    monkeypatch.setattr(timing, "end_book_phase", end, raising=False)
    async with timing.measured_book_phase(
        {"item_id": uuid4(), "attempt_token": uuid4()}, "finalization"
    ):
        result = "committed"
    assert result == "committed"


@pytest.mark.asyncio
async def test_workflow_interval_starts_when_consumed_and_ends_only_at_terminal_callback(
    monkeypatch,
):
    monkeypatch.setattr(timing, "begin_book_phase", AsyncMock(return_value=uuid4()))
    end = AsyncMock()
    monkeypatch.setattr(timing, "end_book_phase", end)
    ticks = iter([5, 7])
    monkeypatch.setattr(timing, "monotonic", lambda: next(ticks))
    recorder = timing.BookPhaseRecorder(
        {"item_id": uuid4(), "attempt_token": uuid4()}, "ptc_execution"
    )
    end.assert_not_awaited()
    await recorder.start()
    end.assert_not_awaited()
    await recorder.finish("succeeded")
    await recorder.finish("failed")
    assert end.await_count == 1
    assert end.await_args.kwargs["measured_ms"] == 2000


@pytest.mark.asyncio
async def test_recovery_starts_new_finalization_before_sandbox_reconnect(monkeypatch):
    from unittest.mock import Mock
    from src.server.services import education_book_recovery as recovery

    order = []

    async def begin(**kwargs):
        assert kwargs["phase"] == "finalization"
        order.append("start")
        return uuid4()

    async def reconnect(**kwargs):
        assert order == ["start"]
        order.append("reconnect")
        return Mock(sandbox=Mock())

    monkeypatch.setattr(timing, "begin_book_phase", begin)
    monkeypatch.setattr(timing, "end_book_phase", AsyncMock())
    monkeypatch.setattr(
        recovery.WorkspaceManager,
        "get_instance",
        lambda: Mock(recover_managed_textbook_session=reconnect),
    )
    monkeypatch.setattr(recovery, "build_execution_task", Mock())
    monkeypatch.setattr(
        recovery, "finalize_book_item", AsyncMock(return_value={"status": "succeeded"})
    )
    result = await recovery.recover_completed_book_item(
        {
            "managed_workspace_id": uuid4(),
            "execution_id": uuid4(),
            "item_id": uuid4(),
            "attempt_token": uuid4(),
            "operation": "material",
        }
    )
    assert result == {"status": "succeeded"}
    assert order == ["start", "reconnect"]
