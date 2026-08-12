"""Contract tests for versioned family textbook learning."""

from unittest.mock import AsyncMock

import pytest

from src.server.services import education_textbooks


def test_version_transition_requires_review_before_publication():
    education_textbooks.assert_version_transition(current="review", target="published")

    with pytest.raises(education_textbooks.TextbookTransitionError):
        education_textbooks.assert_version_transition(
            current="draft", target="published"
        )


@pytest.mark.asyncio
async def test_only_parent_can_start_a_frozen_textbook_processing_job(monkeypatch):
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value=None),
    )

    with pytest.raises(education_textbooks.TextbookPermissionError):
        await education_textbooks.start_processing(
            parent_user_id="student-1",
            textbook_id="textbook-1",
            source_asset_ids=["asset-1"],
        )


@pytest.mark.asyncio
async def test_start_processing_freezes_sources_before_queueing(monkeypatch):
    context = {"household_id": "household-1", "timezone": "Asia/Tokyo"}
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value=context),
    )
    queue = AsyncMock(return_value={"job_id": "job-1", "status": "queued"})
    monkeypatch.setattr(education_textbooks, "queue_textbook_processing", queue)

    result = await education_textbooks.start_processing(
        parent_user_id="parent-1",
        textbook_id="textbook-1",
        source_asset_ids=["asset-1", "asset-2"],
    )

    assert result == {"job_id": "job-1", "status": "queued"}
    assert queue.await_args.kwargs == {
        "parent_user_id": "parent-1",
        "household_id": "household-1",
        "textbook_id": "textbook-1",
        "source_asset_ids": ["asset-1", "asset-2"],
        "extractor_name": "local_fixture",
        "extractor_version": "1",
    }


@pytest.mark.asyncio
async def test_processing_job_writes_a_bundle_before_making_a_version_reviewable(
    monkeypatch,
):
    job = {
        "job_id": "job-1",
        "version_id": "version-1",
        "textbook_id": "textbook-1",
        "household_id": "household-1",
        "title": "英语第二册",
        "slug": "english-2",
        "version_sequence": 1,
        "sources": [{"asset_id": "asset-1", "original_filename": "book.pdf"}],
    }
    monkeypatch.setattr(
        education_textbooks,
        "claim_textbook_processing_job",
        AsyncMock(return_value=job),
    )
    bundle = AsyncMock(return_value="education/household-1/english-2/v1")
    complete = AsyncMock(return_value={"job_id": "job-1", "status": "completed"})
    monkeypatch.setattr(education_textbooks, "write_textbook_bundle", bundle)
    monkeypatch.setattr(
        education_textbooks, "complete_textbook_processing_job", complete
    )

    result = await education_textbooks.process_textbook_job(job_id="job-1")

    assert result["status"] == "completed"
    assert bundle.await_args.args[0] == job
    assert (
        complete.await_args.kwargs["bundle_prefix"]
        == "education/household-1/english-2/v1"
    )
