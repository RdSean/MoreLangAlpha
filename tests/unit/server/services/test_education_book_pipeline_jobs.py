"""Managed unified book-pipeline job contracts."""

from unittest.mock import AsyncMock

import pytest

from src.server.services import education_book_pipeline_jobs
from src.server.services.education_textbooks import (
    TextbookNotFoundError,
    TextbookTransitionError,
)


def _job(*, status: str = "queued", pause: bool = False) -> dict:
    return {
        "generation_job_id": "4d0112f8-0e00-4f1f-990a-4bc1b1cc20f3",
        "version_id": "a8e02f20-b0d8-4f85-9282-d87a3aa54c83",
        "scope": "book_pipeline",
        "structure_id": None,
        "knowledge_point_id": None,
        "status": status,
        "attempt_count": 0,
        "pause_after_chapter_analysis": pause,
        "error_code": None,
        "error_message": None,
        "created_at": None,
        "updated_at": None,
        "latest_attempt_id": None,
        "root_run_id": None,
        "started_at": None,
        "heartbeat_at": None,
        "processing_profile_sha256": "b" * 64,
    }


@pytest.mark.asyncio
async def test_processing_profile_hash_ignores_checkpoint_mode(monkeypatch) -> None:
    hashes: list[str] = []

    async def parent(_parent_user_id):
        return {"household_id": "household-1"}

    async def queue(**kwargs):
        hashes.append(str(kwargs["processing_profile_sha256"]))
        return _job(pause=bool(kwargs["pause_after_chapter_analysis"]))

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        parent,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "queue_book_pipeline_job",
        queue,
    )

    await education_book_pipeline_jobs.queue_book_pipeline_for_parent(
        parent_user_id="parent-1",
        content_version_id=_job()["version_id"],
    )
    await education_book_pipeline_jobs.queue_book_pipeline_for_parent(
        parent_user_id="parent-1",
        content_version_id=_job()["version_id"],
        pause_after_chapter_analysis=True,
    )

    assert len(set(hashes)) == 1


@pytest.mark.asyncio
async def test_queue_book_pipeline_returns_persisted_queued_job(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def parent(_parent_user_id):
        return {"household_id": "household-1"}

    async def queue(**kwargs):
        captured.update(kwargs)
        return _job(pause=bool(kwargs["pause_after_chapter_analysis"]))

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        parent,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "queue_book_pipeline_job",
        queue,
    )

    job = await education_book_pipeline_jobs.queue_book_pipeline_for_parent(
        parent_user_id="parent-1",
        content_version_id=_job()["version_id"],
    )

    assert job["scope"] == "book_pipeline"
    assert job["status"] == "queued"
    assert job["pause_after_chapter_analysis"] is False
    assert captured["parent_user_id"] == "parent-1"
    assert len(str(captured["processing_profile_sha256"])) == 64


@pytest.mark.asyncio
async def test_queue_book_pipeline_persists_checkpoint_mode(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def parent(_parent_user_id):
        return {"household_id": "household-1"}

    async def queue(**kwargs):
        captured.update(kwargs)
        return _job(pause=True)

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        parent,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "queue_book_pipeline_job",
        queue,
    )

    job = await education_book_pipeline_jobs.queue_book_pipeline_for_parent(
        parent_user_id="parent-1",
        content_version_id=_job()["version_id"],
        pause_after_chapter_analysis=True,
    )

    assert job["pause_after_chapter_analysis"] is True
    assert captured["pause_after_chapter_analysis"] is True


@pytest.mark.asyncio
async def test_pause_checkpoint_closes_attempt_and_sets_awaiting_review(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    async def pause(**kwargs):
        captured.update(kwargs)
        return _job(status="awaiting_review", pause=True)

    async def parent(_parent_user_id):
        return {"household_id": "household-1"}

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        parent,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "pause_book_pipeline_for_chapter_review",
        pause,
    )

    job = await education_book_pipeline_jobs.pause_book_pipeline_for_parent(
        parent_user_id="parent-1",
        generation_job_id=_job()["generation_job_id"],
        attempt_id="attempt-1",
    )

    assert job["status"] == "awaiting_review"
    assert captured == {
        "parent_user_id": "parent-1",
        "generation_job_id": _job()["generation_job_id"],
        "attempt_id": "attempt-1",
    }


@pytest.mark.asyncio
async def test_resume_book_pipeline_requeues_only_waiting_checkpoint(
    monkeypatch,
) -> None:
    waiting = _job(status="awaiting_review", pause=True)
    resumed = _job(status="queued", pause=False)

    async def parent(_parent_user_id):
        return {"household_id": "household-1"}

    async def get_job(**_kwargs):
        return waiting

    async def resume(**kwargs):
        assert kwargs == {
            "parent_user_id": "parent-1",
            "generation_job_id": waiting["generation_job_id"],
        }
        return resumed

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        parent,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_generation_job_for_parent",
        get_job,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "resume_book_pipeline_job",
        resume,
    )

    job = await education_book_pipeline_jobs.resume_book_pipeline_for_parent(
        parent_user_id="parent-1",
        generation_job_id=waiting["generation_job_id"],
    )

    assert job["status"] == "queued"
    assert job["pause_after_chapter_analysis"] is False


@pytest.mark.asyncio
async def test_resume_book_pipeline_rejects_non_waiting_job(monkeypatch) -> None:
    async def parent(_parent_user_id):
        return {"household_id": "household-1"}

    async def get_job(**_kwargs):
        return _job(status="running")

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        parent,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_generation_job_for_parent",
        get_job,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "resume_book_pipeline_job",
        AsyncMock(side_effect=AssertionError("must not requeue")),
    )

    with pytest.raises(TextbookTransitionError):
        await education_book_pipeline_jobs.resume_book_pipeline_for_parent(
            parent_user_id="parent-1",
            generation_job_id=_job()["generation_job_id"],
        )


@pytest.mark.asyncio
async def test_get_book_pipeline_rejects_another_scope(monkeypatch) -> None:
    async def parent(_parent_user_id):
        return {"household_id": "household-1"}

    async def get_job(**_kwargs):
        return {**_job(), "scope": "structure"}

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        parent,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_generation_job_for_parent",
        get_job,
    )

    with pytest.raises(TextbookNotFoundError):
        await education_book_pipeline_jobs.get_book_pipeline_job_for_parent(
            parent_user_id="parent-1",
            generation_job_id=_job()["generation_job_id"],
        )
