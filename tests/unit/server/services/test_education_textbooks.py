"""Contract tests for versioned family textbook learning."""

from unittest.mock import AsyncMock
from types import SimpleNamespace
import sys

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
async def test_creating_chinese_textbooks_uses_distinct_storage_slugs(monkeypatch):
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    create = AsyncMock(return_value={"textbook_id": "textbook-1"})
    monkeypatch.setattr(education_textbooks, "create_textbook_record", create)

    await education_textbooks.create_textbook(
        parent_user_id="parent-1", title="语文上册"
    )
    await education_textbooks.create_textbook(
        parent_user_id="parent-1", title="数学上册"
    )

    slugs = [call.kwargs["slug"] for call in create.await_args_list]
    assert len(set(slugs)) == 2
    assert all(slug.startswith("textbook-") for slug in slugs)


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
        "attempt_count": 1,
        "sources": [{"asset_id": "asset-1", "original_filename": "book.pdf"}],
    }
    monkeypatch.setattr(
        education_textbooks,
        "claim_textbook_processing_job",
        AsyncMock(return_value=job),
    )
    bundle = AsyncMock(return_value="education/household-1/english-2/v1")
    complete = AsyncMock(return_value={"job_id": "job-1", "status": "completed"})
    monkeypatch.setattr(
        education_textbooks, "write_textbook_content_bundle", bundle, raising=False
    )
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
    assert complete.await_args.kwargs["extractor"] == {
        "name": "local_fixture",
        "version": "1",
    }


def test_local_fixture_processing_creates_content_without_teaching_material():
    package = education_textbooks.build_local_fixture_package(
        {
            "household_id": "household-1",
            "title": "英语第二册",
            "slug": "english-2",
            "version_sequence": 1,
            "sources": [{"original_filename": "book.pdf"}],
        }
    )

    chapter = package["chapters"][0]
    assert "teaching_material" not in chapter
    assert "teaching_material_key" not in chapter
    assert "questions" not in chapter


@pytest.mark.asyncio
async def test_content_bundle_uses_the_frozen_chapter_object_keys(monkeypatch):
    from src.server.services import education_textbook_storage

    uploads: list[str] = []

    async def put(key: str, _content: bytes, _content_type: str) -> None:
        uploads.append(key)

    monkeypatch.setattr(education_textbook_storage, "_put", put)
    monkeypatch.setattr(education_textbook_storage, "get_bytes", lambda _key: b"pdf")
    job = {
        "household_id": "household-1",
        "title": "英语第二册",
        "slug": "english-2",
        "version_sequence": 1,
        "sources": [
            {
                "asset_id": "asset-1",
                "original_filename": "book.pdf",
                "storage_key": "education/household-1/asset-1.pdf",
                "content_type": "application/pdf",
            }
        ],
    }
    package = education_textbooks.build_local_fixture_package(job)

    await education_textbook_storage.write_textbook_content_bundle(job, package)

    assert package["chapters"][0]["markdown_key"] in uploads


@pytest.mark.asyncio
async def test_parent_retry_requeues_only_a_failed_frozen_job(monkeypatch):
    retry = AsyncMock(
        return_value={"job_id": "job-1", "status": "queued", "attempt_count": 1}
    )
    monkeypatch.setattr(education_textbooks, "retry_textbook_processing_job", retry)

    result = await education_textbooks.retry_processing_for_parent(
        parent_user_id="parent-1", job_id="job-1"
    )

    assert result["status"] == "queued"
    retry.assert_awaited_once_with(parent_user_id="parent-1", job_id="job-1")


@pytest.mark.asyncio
async def test_local_processor_makes_stable_chapters_from_extractable_pdf_pages(monkeypatch):
    class Page:
        def extract_text(self):
            return "教材正文"

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=lambda _stream: SimpleNamespace(pages=[Page(), Page()])))
    monkeypatch.setattr(education_textbooks, "get_bytes", lambda _key: b"%PDF-1.7")
    job = {
        "household_id": "household-1",
        "title": "英语第二册",
        "slug": "english-2",
        "version_sequence": 1,
        "sources": [{"storage_key": "education/h/book.pdf", "content_type": "application/pdf", "original_filename": "book.pdf"}],
    }

    package = await education_textbooks.build_local_pdf_package(job)

    assert package["extractor"] == {"name": "local_pypdf", "version": "1"}
    assert package["knowledge_foundations"] == ["book-to-skill", "the-knowledge-guy"]
    assert package["chapters"][0]["markdown"].endswith("教材正文\n\n教材正文")
    assert "teaching_material" not in package["chapters"][0]
    assert "questions" not in package["chapters"][0]
