"""Contract tests for versioned family textbook learning."""

from unittest.mock import AsyncMock
from types import SimpleNamespace
import sys
from hashlib import sha256

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
async def test_managed_teaching_queue_freezes_input_and_skill_contracts_before_launch(
    monkeypatch,
):
    """A parent request persists exact inputs before the long-running PTC root starts."""
    content_version_id = "f5761267-11d1-4977-8107-e2671c99a2f0"
    job_id = "7bc1e58d-5a34-49d6-8c5c-70703e989bd4"
    frozen = {
        "content_version_id": content_version_id,
        "content_version_sequence": 1,
        "household_id": "household-1",
        "slug": "english-2",
        "title": "英语第二册",
        "chapters": [
            {
                "content_chapter_id": "8a77d086-0b23-4a1e-89d0-f163fa23d5d1",
                "position": 1,
                "slug": "overview",
                "title": "导读",
                "markdown": "# 导读\n\n教材正文。",
            }
        ],
    }
    queued = AsyncMock(
        return_value={
            "job_id": job_id,
            "teaching_package_id": "5e3a0b43-8378-4b6c-926f-0f053577501d",
            "content_version_id": content_version_id,
            "status": "queued",
        }
    )
    launched = AsyncMock(return_value={"root_run_id": "root-1"})
    projected = {
        "job_id": job_id,
        "teaching_package_id": "5e3a0b43-8378-4b6c-926f-0f053577501d",
        "content_version_id": content_version_id,
        "status": "running",
        "phase": "preparing",
        "attempt_count": 1,
        "completed_chapter_count": 0,
        "total_chapter_count": 1,
        "events": [],
        "attempts": [],
    }
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_teaching_input_for_parent",
        AsyncMock(return_value=frozen),
    )
    monkeypatch.setattr(education_textbooks, "queue_teaching_package", queued)
    monkeypatch.setattr(
        education_textbooks,
        "get_teaching_job_projection",
        AsyncMock(return_value=projected),
    )
    monkeypatch.setattr(education_textbooks, "uuid4", lambda: job_id)
    monkeypatch.setattr(
        education_textbooks,
        "_managed_skill_hash",
        lambda skill: {"book-to-skill": "a" * 64, "the-knowledge-guy": "b" * 64}[skill],
    )
    from src.server.services import education_managed_ptc

    monkeypatch.setattr(education_managed_ptc, "launch_teaching_attempt", launched)

    result = await education_textbooks.queue_teaching_package_for_parent(
        parent_user_id="parent-1", content_version_id=content_version_id
    )

    assert result == projected
    queued.assert_awaited_once()
    queue_args = queued.await_args.kwargs
    assert queue_args["parent_user_id"] == "parent-1"
    assert queue_args["content_version_id"] == content_version_id
    assert queue_args["job_id"] == job_id
    assert queue_args["hashes"].input_manifest_sha256
    assert queue_args["hashes"].book_to_skill_sha256 == "a" * 64
    assert queue_args["hashes"].knowledge_guy_sha256 == "b" * 64
    assert queue_args["hashes"].adapter_prompt_sha256
    launched.assert_awaited_once_with(parent_user_id="parent-1", job_id=job_id)


@pytest.mark.asyncio
async def test_parent_can_cancel_and_resume_only_via_the_managed_job_state_machine(
    monkeypatch,
):
    """Public controls delegate to the existing durable cancellation and retry paths."""
    projection = {
        "job_id": "job-1",
        "teaching_package_id": "package-1",
        "content_version_id": "version-1",
        "status": "cancelled",
        "phase": "cancelled",
        "attempt_count": 1,
        "completed_chapter_count": 0,
        "total_chapter_count": 1,
        "events": [],
        "attempts": [],
    }
    get_projection = AsyncMock(return_value=projection)
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(education_textbooks, "get_teaching_job_projection", get_projection)
    from src.server.services import education_managed_ptc, education_teaching_jobs

    cancel = AsyncMock()
    resume = AsyncMock(return_value={"root_run_id": "root-2"})
    monkeypatch.setattr(education_teaching_jobs, "cancel_teaching_job", cancel)
    monkeypatch.setattr(education_managed_ptc, "resume_teaching_job", resume)

    cancelled = await education_textbooks.cancel_teaching_job_for_parent(
        parent_user_id="parent-1", job_id="job-1"
    )
    resumed = await education_textbooks.resume_teaching_job_for_parent(
        parent_user_id="parent-1", job_id="job-1"
    )

    assert cancelled == projection
    assert resumed == projection
    cancel.assert_awaited_once_with(parent_user_id="parent-1", job_id="job-1")
    resume.assert_awaited_once_with(parent_user_id="parent-1", job_id="job-1")


@pytest.mark.asyncio
async def test_parent_resume_returns_failed_safe_projection_when_managed_launch_fails(
    monkeypatch,
):
    projection = {
        "job_id": "job-1",
        "teaching_package_id": "package-1",
        "content_version_id": "version-1",
        "status": "failed",
        "phase": "failed",
        "attempt_count": 2,
        "completed_chapter_count": 0,
        "total_chapter_count": 1,
        "actions": ["resume"],
        "events": [],
        "attempts": [],
    }
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_teaching_job_projection_for_parent",
        AsyncMock(return_value=projection),
    )
    from src.server.services import education_managed_ptc

    monkeypatch.setattr(
        education_managed_ptc,
        "resume_teaching_job",
        AsyncMock(side_effect=RuntimeError("no credential available")),
    )

    resumed = await education_textbooks.resume_teaching_job_for_parent(
        parent_user_id="parent-1", job_id="job-1"
    )

    assert resumed["status"] == "failed"
    assert resumed["actions"] == ["resume"]


def test_safe_teaching_projection_never_relays_managed_runtime_fields():
    job = {
        "job_id": "job-1",
        "teaching_package_id": "package-1",
        "content_version_id": "version-1",
        "status": "running",
        "phase": "generating_teaching",
        "attempt_count": 1,
        "completed_chapter_count": 1,
        "total_chapter_count": 2,
        "storage_key": "education/private/key",
        "events": [
            {
                "sequence": 1,
                "phase": "generating_teaching",
                "summary": "已完成第 1 章教学材料生成",
                "managed_path": "/managed/private",
            }
        ],
        "attempts": [
            {
                "attempt_id": "attempt-1",
                "status": "running",
                "managed_workspace_id": "workspace-1",
            }
        ],
    }

    projected = education_textbooks._safe_teaching_projection(job)

    assert projected["actions"] == ["cancel"]
    assert "storage_key" not in repr(projected)
    assert "/managed/" not in repr(projected)


def test_active_teaching_projection_uses_latest_autonomous_milestone_but_review_is_verified():
    active = education_textbooks._safe_teaching_projection(
        {
            "job_id": "job-1",
            "teaching_package_id": "package-1",
            "content_version_id": "version-1",
            "status": "running",
            "phase": "building_skill",
            "attempt_count": 1,
            "completed_chapter_count": 1,
            "total_chapter_count": 2,
            "events": [
                {"sequence": 1, "phase": "planning", "summary": "Agent 已报告：正在规划"},
                {"sequence": 2, "phase": "practice_build", "summary": "Agent 已报告：第 1 章已完成练习构建"},
            ],
            "attempts": [],
        }
    )
    completed = education_textbooks._safe_teaching_projection(
        {
            "job_id": "job-1",
            "teaching_package_id": "package-1",
            "content_version_id": "version-1",
            "status": "completed",
            "phase": "review",
            "attempt_count": 1,
            "completed_chapter_count": 2,
            "total_chapter_count": 2,
            "events": [{"sequence": 2, "phase": "validating_bundle", "summary": "Agent 已报告：正在校验"}],
            "attempts": [],
        }
    )

    assert active["phase"] == "practice_build"
    assert completed["phase"] == "review"


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


@pytest.mark.asyncio
async def test_parent_reads_only_manifest_verified_private_teaching_asset(monkeypatch):
    package_id = "5e3a0b43-8378-4b6c-926f-0f053577501d"
    chapter_id = "f5761267-11d1-4977-8107-e2671c99a2f0"
    toolkit = "# 导读工具包\n\n核心概念".encode("utf-8")
    review = {
        "teaching_package_id": package_id,
        "bundle_prefix": "education/household-1/english-2/v1/teaching/v2",
        "asset_manifest": {
            "format": "langalpha-family-teaching-assets/v2",
            "concept_index": {"size_bytes": 2, "concept_count": 1},
            "coverage_audit": {"size_bytes": 2, "status": "complete"},
            "chapters": [
                {
                    "content_chapter_id": chapter_id,
                    "content_sha256": "a" * 64,
                    "coverage_status": "complete",
                    "concept_count": 1,
                    "assets": [
                        {"kind": "knowledge", "size_bytes": 2, "sha256": "b" * 64},
                        {
                            "kind": "toolkit",
                            "size_bytes": len(toolkit),
                            "sha256": sha256(toolkit).hexdigest(),
                        },
                        {"kind": "practice", "size_bytes": 2, "sha256": "c" * 64},
                    ],
                }
            ],
        },
        "chapters": [
            {
                "content_chapter_id": chapter_id,
                "position": 1,
                "slug": "overview",
                "title": "导读",
            }
        ],
    }
    get_review = AsyncMock(return_value=review)
    requested_keys: list[str] = []

    def get_asset(key: str):
        requested_keys.append(key)
        return toolkit

    monkeypatch.setattr(education_textbooks, "get_teaching_asset_review_for_parent", get_review)
    monkeypatch.setattr(education_textbooks, "get_bytes", get_asset)

    asset = await education_textbooks.get_teaching_chapter_asset(
        parent_user_id="parent-1",
        teaching_package_id=package_id,
        chapter_id=chapter_id,
        kind="toolkit",
    )

    assert asset == {
        "teaching_package_id": package_id,
        "chapter_id": chapter_id,
        "kind": "toolkit",
        "content": toolkit.decode("utf-8"),
    }
    assert requested_keys == [
        "education/household-1/english-2/v1/teaching/v2/chapters/01-overview-toolkit.md"
    ]
    assert "education/" not in repr(asset)


@pytest.mark.asyncio
async def test_parent_asset_read_rejects_bytes_that_do_not_match_manifest(monkeypatch):
    chapter_id = "f5761267-11d1-4977-8107-e2671c99a2f0"
    review = {
        "teaching_package_id": "5e3a0b43-8378-4b6c-926f-0f053577501d",
        "bundle_prefix": "education/household-1/english-2/v1/teaching/v2",
        "asset_manifest": {
            "format": "langalpha-family-teaching-assets/v2",
            "concept_index": {"size_bytes": 2, "concept_count": 1},
            "coverage_audit": {"size_bytes": 2, "status": "complete"},
            "chapters": [
                {
                    "content_chapter_id": chapter_id,
                    "content_sha256": "a" * 64,
                    "coverage_status": "complete",
                    "concept_count": 1,
                    "assets": [
                        {"kind": "knowledge", "size_bytes": 2, "sha256": "b" * 64},
                        {"kind": "toolkit", "size_bytes": 1, "sha256": "c" * 64},
                        {"kind": "practice", "size_bytes": 2, "sha256": "d" * 64},
                    ],
                }
            ],
        },
        "chapters": [
            {"content_chapter_id": chapter_id, "position": 1, "slug": "overview", "title": "导读"}
        ],
    }
    monkeypatch.setattr(
        education_textbooks, "get_teaching_asset_review_for_parent", AsyncMock(return_value=review)
    )
    monkeypatch.setattr(education_textbooks, "get_bytes", lambda _key: b"tampered")

    with pytest.raises(education_textbooks.TextbookNotFoundError):
        await education_textbooks.get_teaching_chapter_asset(
            parent_user_id="parent-1",
            teaching_package_id=review["teaching_package_id"],
            chapter_id=chapter_id,
            kind="toolkit",
        )
