"""Phase timings are correlated and cannot interfere with content processing."""

import json

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
