"""Parent lesson review and structure publication service contracts."""

import pytest

from src.server.services import education_lesson_review
from src.server.services.education_textbooks import (
    TextbookNotFoundError,
    TextbookPermissionError,
)


LESSON = {
    "lesson_id": "lesson-1",
    "status": "review",
    "latest_revision_id": "revision-1",
    "knowledge_point_id": "kp-1",
    "knowledge_point_position": 2,
    "knowledge_point_slug": "world-game",
    "knowledge_point_title": "世界运动",
    "unit_position": 1,
    "unit_slug": "unit-1-sports",
    "unit_title": "Unit 1",
    "structure_sequence": 1,
    "content_version_sequence": 1,
    "household_id": "household-1",
    "slug": "english-2",
    "revisions": [
        {
            "revision_id": "revision-1",
            "revision": 1,
            "content_key": "education/lesson.md",
            "content_sha256": "a" * 64,
            "size_bytes": 10,
            "processing_profile_sha256": "b" * 64,
        }
    ],
}


@pytest.mark.asyncio
async def test_queue_lesson_requires_parent_and_launches(monkeypatch):
    launched: dict[str, object] = {}
    queued: dict[str, object] = {}

    async def household(_user_id):
        return {"household_id": "household-1"}

    async def queue(**kwargs):
        queued.update(kwargs)
        return {"generation_job_id": "generation-1", "scope": "lesson"}

    async def launch(**kwargs):
        launched.update(kwargs)

    async def projection(**_kwargs):
        return {"generation_job_id": "generation-1", "status": "queued"}

    monkeypatch.setattr(
        education_lesson_review,
        "get_household_context_for_parent",
        household,
    )
    monkeypatch.setattr(
        education_lesson_review,
        "queue_kp_lesson_generation_for_parent",
        queue,
    )
    monkeypatch.setattr(
        education_lesson_review,
        "launch_kp_lesson_generation",
        launch,
    )
    monkeypatch.setattr(
        education_lesson_review,
        "get_generation_job_for_parent",
        projection,
    )

    result = await education_lesson_review.queue_lesson_for_parent(
        parent_user_id="parent-1",
        knowledge_point_id="kp-1",
        auto_grading=False,
        prompt="  使用中文讲解。  ",
    )

    assert result["status"] == "queued"
    assert launched["generation_job_id"] == "generation-1"
    assert queued["prompt"] == "使用中文讲解。"


@pytest.mark.asyncio
async def test_queue_lesson_delegates_reused_job_to_launch_fence(monkeypatch):
    launched: list[dict[str, str]] = []

    async def household(_user_id):
        return {"household_id": "household-1"}

    async def queue(**_kwargs):
        return {
            "generation_job_id": "generation-active",
            "scope": "lesson",
            "status": "running",
            "reused_existing_job": True,
        }

    async def launch(**kwargs):
        launched.append(kwargs)

    async def projection(**_kwargs):
        return {
            "generation_job_id": "generation-active",
            "status": "running",
        }

    monkeypatch.setattr(
        education_lesson_review,
        "get_household_context_for_parent",
        household,
    )
    monkeypatch.setattr(
        education_lesson_review,
        "queue_kp_lesson_generation_for_parent",
        queue,
    )
    monkeypatch.setattr(
        education_lesson_review,
        "launch_kp_lesson_generation",
        launch,
    )
    monkeypatch.setattr(
        education_lesson_review,
        "get_generation_job_for_parent",
        projection,
    )

    result = await education_lesson_review.queue_lesson_for_parent(
        parent_user_id="parent-1",
        knowledge_point_id="kp-1",
    )

    assert result["status"] == "running"
    assert launched == [
        {
            "parent_user_id": "parent-1",
            "generation_job_id": "generation-active",
        }
    ]


@pytest.mark.asyncio
async def test_get_lesson_requires_parent_and_reads_latest_markdown(monkeypatch):
    async def missing(_user_id):
        return None

    monkeypatch.setattr(
        education_lesson_review,
        "get_household_context_for_parent",
        missing,
    )
    with pytest.raises(TextbookPermissionError):
        await education_lesson_review.get_lesson_for_parent(
            parent_user_id="parent-1",
            lesson_id="lesson-1",
        )

    async def household(_user_id):
        return {"household_id": "household-1"}

    async def get_lesson(**_kwargs):
        return LESSON

    async def read_revision(_key, **_kwargs):
        return "# 世界运动\n".encode()

    monkeypatch.setattr(
        education_lesson_review,
        "get_household_context_for_parent",
        household,
    )
    monkeypatch.setattr(
        education_lesson_review,
        "get_kp_lesson_for_parent",
        get_lesson,
    )
    monkeypatch.setattr(
        education_lesson_review,
        "read_kp_lesson_revision",
        read_revision,
    )

    result = await education_lesson_review.get_lesson_for_parent(
        parent_user_id="parent-1",
        lesson_id="lesson-1",
    )

    assert result["content_markdown"] == "# 世界运动\n"
    assert result["latest_revision_id"] == "revision-1"


@pytest.mark.asyncio
async def test_manual_revision_validates_and_creates_new_revision(monkeypatch):
    stored: dict[str, object] = {}

    async def household(_user_id):
        return {"household_id": "household-1"}

    async def get_lesson(**_kwargs):
        return LESSON

    async def write_revision(job, content):
        stored["write"] = (job, content)
        return {
            "content_key": "education/household-1/english-2/v1/lesson.md",
            "content_sha256": "c" * 64,
            "size_bytes": len(content),
        }

    async def create_revision(**kwargs):
        stored["revision"] = kwargs
        return {"lesson_id": "lesson-1", "revision_id": "revision-2"}

    monkeypatch.setattr(
        education_lesson_review,
        "get_household_context_for_parent",
        household,
    )
    monkeypatch.setattr(
        education_lesson_review,
        "get_kp_lesson_for_parent",
        get_lesson,
    )
    monkeypatch.setattr(
        education_lesson_review,
        "write_kp_lesson_revision",
        write_revision,
    )
    monkeypatch.setattr(
        education_lesson_review,
        "create_kp_lesson_revision",
        create_revision,
    )

    revision = await education_lesson_review.create_manual_lesson_revision(
        parent_user_id="parent-1",
        lesson_id="lesson-1",
        content_markdown="# 修订版\n",
    )

    assert revision["revision_id"] == "revision-2"
    assert stored["write"][0]["lesson_revision"] == 2


@pytest.mark.asyncio
async def test_approve_lesson_rejects_missing_revision(monkeypatch):
    async def household(_user_id):
        return {"household_id": "household-1"}

    async def get_lesson(**_kwargs):
        return LESSON

    monkeypatch.setattr(
        education_lesson_review,
        "get_household_context_for_parent",
        household,
    )
    monkeypatch.setattr(
        education_lesson_review,
        "get_kp_lesson_for_parent",
        get_lesson,
    )

    with pytest.raises(TextbookNotFoundError, match="revision"):
        await education_lesson_review.approve_lesson_for_parent(
            parent_user_id="parent-1",
            lesson_id="lesson-1",
            revision_id="missing",
        )


@pytest.mark.asyncio
async def test_lesson_generation_status_returns_persisted_prompt(monkeypatch):
    async def household(_user_id):
        return {"household_id": "household-1"}

    async def candidate(**_kwargs):
        return {"knowledge_point_id": "kp-1"}

    async def active(**_kwargs):
        return {
            "generation_job_id": "generation-1",
            "status": "running",
            "attempt_count": 1,
            "auto_grading": False,
            "processing_brief": "使用中文讲解。",
        }

    monkeypatch.setattr(
        education_lesson_review,
        "get_household_context_for_parent",
        household,
    )
    monkeypatch.setattr(
        education_lesson_review,
        "get_knowledge_point_for_parent",
        candidate,
    )
    monkeypatch.setattr(
        education_lesson_review,
        "get_active_lesson_generation_for_parent",
        active,
    )

    status = await education_lesson_review.get_lesson_generation_status_for_parent(
        parent_user_id="parent-1",
        knowledge_point_id="kp-1",
    )

    assert status["prompt"] == "使用中文讲解。"


@pytest.mark.asyncio
async def test_lesson_generation_status_restores_latest_prompt_after_job_ends(
    monkeypatch,
):
    async def household(_user_id):
        return {"household_id": "household-1"}

    async def candidate(**_kwargs):
        return {"knowledge_point_id": "kp-1"}

    async def no_active(**_kwargs):
        return None

    async def latest(**_kwargs):
        return {
            "generation_job_id": "generation-1",
            "status": "completed",
            "attempt_count": 1,
            "auto_grading": False,
            "processing_brief": "使用中文讲解，保留英文术语。",
        }

    monkeypatch.setattr(
        education_lesson_review,
        "get_household_context_for_parent",
        household,
    )
    monkeypatch.setattr(
        education_lesson_review,
        "get_knowledge_point_for_parent",
        candidate,
    )
    monkeypatch.setattr(
        education_lesson_review,
        "get_active_lesson_generation_for_parent",
        no_active,
    )
    monkeypatch.setattr(
        education_lesson_review,
        "get_latest_lesson_generation_for_parent",
        latest,
    )

    status = await education_lesson_review.get_lesson_generation_status_for_parent(
        parent_user_id="parent-1",
        knowledge_point_id="kp-1",
    )

    assert status["generating"] is False
    assert status["generation_job_id"] is None
    assert status["prompt"] == "使用中文讲解，保留英文术语。"
