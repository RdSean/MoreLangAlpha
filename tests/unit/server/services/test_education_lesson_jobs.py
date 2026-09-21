"""Managed generation contracts for one knowledge-point lesson."""

import hashlib

import pytest

from src.server.services import education_lesson_jobs


FROZEN_INPUT = {
    "format": "langalpha-managed-textbook-input/v2",
    "job_id": "8a77d086-0b23-4a1e-89d0-f163fa23d5d1",
    "sources": [
        {
            "source_id": "source-1",
            "content_chapter_id": "f5761267-11d1-4977-8107-e2671c99a2f0",
            "position": 1,
            "slug": "reading-explorer",
            "title": "Reading Explorer",
            "content_sha256": "a" * 64,
            "path": "sources/01-reading-explorer.md",
            "markdown": (
                "# Unit 1\n\nThe first paragraph.\n\n"
                + ("filler sentence. " * 400)
                + "\n\nThe second paragraph.\n"
            ),
        }
    ],
}


LESSON_JOB = {
    "generation_job_id": "8a77d086-0b23-4a1e-89d0-f163fa23d5d1",
    "version_id": "version-1",
    "scope": "lesson",
    "knowledge_point_id": "kp-1",
    "knowledge_point_position": 2,
    "knowledge_point_slug": "world-game",
    "knowledge_point_title": "世界运动",
    "knowledge_point_source_refs": [
        {"source_id": "source-1", "start": 0, "end": 30}
    ],
    "unit_position": 1,
    "unit_slug": "unit-1-sports",
    "unit_title": "Unit 1: Sports and Fitness",
    "structure_id": "structure-1",
    "structure_sequence": 1,
    "household_id": "household-1",
    "slug": "english-2",
    "content_version_sequence": 1,
    "auto_grading": False,
    "processing_profile_sha256": "b" * 64,
}


def test_managed_lesson_prompt_contains_only_target_contract() -> None:
    prompt = education_lesson_jobs.managed_lesson_prompt(LESSON_JOB)

    assert "inputs/lesson-context.md" in prompt
    assert "outputs/lesson.md" in prompt
    assert "outputs/practice.json" in prompt
    assert "世界运动" in prompt
    assert "不要读取整本书" in prompt
    assert "vocabulary.json" in prompt
    assert "evidence.json" in prompt


def test_build_lesson_source_context_uses_only_target_offsets() -> None:
    context, warnings = education_lesson_jobs.build_lesson_source_context(
        LESSON_JOB,
        FROZEN_INPUT,
    )

    assert warnings == []
    assert context.startswith("## source-1 [0:")
    assert "# Unit 1" in context
    assert "The first paragraph." in context


def test_build_lesson_source_context_resolves_quote_when_offsets_are_missing() -> None:
    markdown = FROZEN_INPUT["sources"][0]["markdown"]
    quote = "The second paragraph."
    target_start = markdown.index(quote)
    job = {
        **LESSON_JOB,
        "knowledge_point_source_refs": [
            {
                "source_id": "source-1",
                "start": None,
                "end": None,
                "quote": quote,
            }
        ],
    }

    context, warnings = education_lesson_jobs.build_lesson_source_context(
        job,
        FROZEN_INPUT,
    )

    assert warnings == ["source_ref_resolved"]
    assert quote in context
    assert context.startswith("## source-1 [0:")


def test_build_lesson_source_context_approximates_wrapped_quote() -> None:
    job = {
        **LESSON_JOB,
        "knowledge_point_source_refs": [
            {
                "source_id": "source-1",
                "start": None,
                "end": None,
                "quote": "The first\n**paragraph**.",
            }
        ],
    }

    context, warnings = education_lesson_jobs.build_lesson_source_context(
        job,
        FROZEN_INPUT,
    )

    assert warnings == ["source_ref_approximate"]
    assert "The first" in context


def test_build_lesson_source_context_uses_document_prefix_as_last_resort() -> None:
    job = {
        **LESSON_JOB,
        "knowledge_point_source_refs": [
            {"source_id": "source-1", "start": None, "end": None, "quote": ""}
        ],
    }

    context, warnings = education_lesson_jobs.build_lesson_source_context(
        job,
        FROZEN_INPUT,
    )

    assert warnings == ["source_ref_document_prefix"]
    assert context.startswith("## source-1 [0:")
    assert "# Unit 1" in context


@pytest.mark.asyncio
async def test_queue_lesson_generation_creates_one_lesson_job(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def get_kp(**_kwargs):
        return dict(LESSON_JOB)

    async def create_job(**kwargs):
        captured.update(kwargs)
        return {
            "generation_job_id": "generation-1",
            "scope": "lesson",
            "status": "queued",
            "auto_grading": kwargs["auto_grading"],
        }

    monkeypatch.setattr(
        education_lesson_jobs,
        "get_knowledge_point_for_parent",
        get_kp,
    )
    monkeypatch.setattr(
        education_lesson_jobs,
        "create_generation_job",
        create_job,
    )

    queued = await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
        parent_user_id="parent-1",
        knowledge_point_id="kp-1",
        auto_grading=False,
    )

    assert queued["scope"] == "lesson"
    assert captured["scope"] == "lesson"
    assert captured["knowledge_point_id"] == "kp-1"
    assert captured["auto_grading"] is False


@pytest.mark.asyncio
async def test_finalize_lesson_generation_creates_immutable_revision(monkeypatch) -> None:
    stored: dict[str, object] = {}
    markdown = "# 世界运动\n\n课程内容。\n".encode()

    async def download(**_kwargs):
        return markdown, None

    async def write_revision(job, content):
        stored["write_job"] = job
        stored["content"] = content
        return {
            "content_key": "education/household-1/english-2/v1/lesson.md",
            "content_sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }

    async def create_revision(**kwargs):
        stored["create_revision"] = kwargs
        return {"lesson_id": "lesson-1", "revision_id": "revision-1"}

    async def settle(**kwargs):
        stored["settle"] = kwargs
        return {"status": kwargs["status"]}

    monkeypatch.setattr(education_lesson_jobs, "download_kp_lesson_outputs", download)
    monkeypatch.setattr(
        education_lesson_jobs,
        "write_kp_lesson_revision",
        write_revision,
    )
    monkeypatch.setattr(
        education_lesson_jobs,
        "create_kp_lesson_revision",
        create_revision,
    )
    monkeypatch.setattr(
        education_lesson_jobs,
        "settle_generation_job",
        settle,
    )

    result = await education_lesson_jobs.finalize_kp_lesson_generation(
        job=LESSON_JOB,
        attempt_id="attempt-1",
        root_run_id="run-1",
        sandbox=object(),
        terminal_status="completed",
        terminal_error=None,
    )

    assert result["lesson_id"] == "lesson-1"
    assert stored["content"] == markdown
    assert (
        stored["create_revision"]["generation_job_id"]
        == LESSON_JOB["generation_job_id"]
    )
    assert stored["settle"]["status"] == "completed"


@pytest.mark.asyncio
async def test_finalize_lesson_generation_fails_only_the_target_job(monkeypatch) -> None:
    settle_calls: list[dict[str, object]] = []

    async def download(**_kwargs):
        return b"", None

    async def settle(**kwargs):
        settle_calls.append(kwargs)
        return {"status": kwargs["status"]}

    monkeypatch.setattr(education_lesson_jobs, "download_kp_lesson_outputs", download)
    monkeypatch.setattr(education_lesson_jobs, "settle_generation_job", settle)

    result = await education_lesson_jobs.finalize_kp_lesson_generation(
        job=LESSON_JOB,
        attempt_id="attempt-1",
        root_run_id="run-1",
        sandbox=object(),
        terminal_status="completed",
        terminal_error=None,
    )

    assert result["status"] == "failed"
    assert settle_calls[0]["error_code"] == "managed_lesson_invalid"
