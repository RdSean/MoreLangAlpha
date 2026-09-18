"""Bounded retry contracts for per-knowledge-point lesson generation."""

from unittest.mock import AsyncMock

import pytest

from src.server.services import education_lesson_jobs


JOB = {
    "generation_job_id": "generation-1",
    "knowledge_point_id": "kp-1",
    "attempt_count": 1,
    "auto_grading": False,
    "processing_profile_sha256": "a" * 64,
}


@pytest.mark.asyncio
async def test_invalid_lesson_requeues_only_its_generation_job(monkeypatch):
    monkeypatch.setattr(
        education_lesson_jobs,
        "download_kp_lesson_outputs",
        AsyncMock(return_value=(b"", None)),
    )
    settle = AsyncMock(return_value={"status": "failed"})
    requeue = AsyncMock(return_value=True)
    launch = AsyncMock(return_value={"root_run_id": "run-2"})
    monkeypatch.setattr(education_lesson_jobs, "settle_generation_job", settle)
    monkeypatch.setattr(education_lesson_jobs, "requeue_generation_job", requeue)
    monkeypatch.setattr(
        education_lesson_jobs,
        "launch_kp_lesson_generation",
        launch,
    )

    result = await education_lesson_jobs.finalize_kp_lesson_generation(
        job=JOB,
        attempt_id="attempt-1",
        root_run_id="run-1",
        sandbox=object(),
        terminal_status="completed",
        terminal_error=None,
        parent_user_id="parent-1",
    )

    assert result["status"] == "retrying"
    requeue.assert_awaited_once_with(generation_job_id="generation-1")
    launch.assert_awaited_once_with(
        parent_user_id="parent-1",
        generation_job_id="generation-1",
    )


@pytest.mark.asyncio
async def test_invalid_lesson_stops_after_three_attempts(monkeypatch):
    monkeypatch.setattr(
        education_lesson_jobs,
        "download_kp_lesson_outputs",
        AsyncMock(return_value=(b"", None)),
    )
    settle = AsyncMock(return_value={"status": "failed"})
    requeue = AsyncMock(return_value=False)
    launch = AsyncMock()
    monkeypatch.setattr(education_lesson_jobs, "settle_generation_job", settle)
    monkeypatch.setattr(education_lesson_jobs, "requeue_generation_job", requeue)
    monkeypatch.setattr(
        education_lesson_jobs,
        "launch_kp_lesson_generation",
        launch,
    )

    result = await education_lesson_jobs.finalize_kp_lesson_generation(
        job={**JOB, "attempt_count": 3},
        attempt_id="attempt-3",
        root_run_id="run-3",
        sandbox=object(),
        terminal_status="completed",
        terminal_error=None,
        parent_user_id="parent-1",
    )

    assert result["status"] == "failed"
    requeue.assert_not_awaited()
    launch.assert_not_awaited()
