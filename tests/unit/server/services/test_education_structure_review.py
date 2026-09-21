"""Parent-facing structure review service contracts."""

import pytest

from src.server.services import education_structure_review
from src.server.services.education_textbooks import (
    TextbookNotFoundError,
    TextbookPermissionError,
    TextbookTransitionError,
)


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
            "markdown": "# Unit 1\n\n" + ("content " * 1_000),
        }
    ],
}


STRUCTURE = {
    "structure_id": "structure-1",
    "version_id": "version-1",
    "sequence": 1,
    "status": "review",
    "units": [
        {
            "unit_id": "unit-1",
            "position": 1,
            "slug": "unit-1-sports",
            "title": "Unit 1: Sports and Fitness",
            "summary": "",
            "unit_type": "teaching",
            "confidence": 0.96,
            "status": "review",
            "source_refs": [
                {
                    "source_id": "source-1",
                    "start": 0,
                    "end": 50,
                }
            ],
            "knowledge_points": [
                {
                    "knowledge_point_id": "kp-1",
                    "position": 1,
                    "slug": "world-game",
                    "title": "世界运动：足球的历史与流行原因",
                    "summary": "",
                    "confidence": 0.93,
                    "status": "review",
                    "source_refs": [
                        {
                            "source_id": "source-1",
                            "start": 0,
                            "end": 40,
                        }
                    ],
                }
            ],
        }
    ],
}


@pytest.mark.asyncio
async def test_queue_structure_requires_parent_and_launches_new_job(monkeypatch):
    launched: dict[str, str] = {}

    async def household(_user_id: str):
        return {"household_id": "household-1"}

    async def queue(**kwargs):
        return {
            "structure_id": "structure-1",
            "generation_job_id": "generation-1",
            "status": "queued",
        }

    async def launch(**kwargs):
        launched.update(kwargs)
        return {"root_run_id": "run-1"}

    async def no_job(**_kwargs):
        return None

    monkeypatch.setattr(
        education_structure_review,
        "get_household_context_for_parent",
        household,
    )
    monkeypatch.setattr(
        education_structure_review,
        "queue_structure_generation_for_parent",
        queue,
    )
    monkeypatch.setattr(
        education_structure_review,
        "launch_structure_generation",
        launch,
    )
    monkeypatch.setattr(
        education_structure_review,
        "get_structure_generation_job_for_parent",
        no_job,
    )

    result = await education_structure_review.queue_structure_for_parent(
        parent_user_id="parent-1",
        content_version_id="version-1",
    )

    assert result["generation_job_id"] == "generation-1"
    assert launched["generation_job_id"] == "generation-1"


@pytest.mark.asyncio
async def test_structure_read_and_replace_require_parent(monkeypatch):
    async def no_household(_user_id: str):
        return None

    monkeypatch.setattr(
        education_structure_review,
        "get_household_context_for_parent",
        no_household,
    )

    with pytest.raises(TextbookPermissionError):
        await education_structure_review.get_structure_for_parent(
            parent_user_id="parent-1",
            structure_id="structure-1",
        )

    with pytest.raises(TextbookPermissionError):
        await education_structure_review.replace_structure_for_parent(
            parent_user_id="parent-1",
            structure_id="structure-1",
            units=[],
        )


@pytest.mark.asyncio
async def test_source_preview_returns_markdown_context_for_review_point(monkeypatch):
    async def household(_user_id: str):
        return {"household_id": "household-1"}

    async def point_for_parent(**_kwargs):
        return {
            "knowledge_point_id": "kp-1",
            "knowledge_point_title": "世界运动",
            "knowledge_point_source_refs": [
                {"source_id": "source-1", "quote": "Unit 1"}
            ],
            "unit_id": "unit-1",
            "unit_title": "Unit 1: Sports",
            "version_id": "version-1",
            "structure_id": "structure-1",
        }

    async def frozen_input(**_kwargs):
        return FROZEN_INPUT

    monkeypatch.setattr(
        education_structure_review,
        "get_household_context_for_parent",
        household,
    )
    monkeypatch.setattr(
        education_structure_review,
        "get_knowledge_point_source_preview_for_parent",
        point_for_parent,
    )
    monkeypatch.setattr(
        education_structure_review,
        "get_teaching_input_for_parent",
        frozen_input,
    )

    preview = await education_structure_review.get_knowledge_point_source_preview(
        parent_user_id="parent-1",
        knowledge_point_id="kp-1",
    )

    assert preview["knowledge_point_title"] == "世界运动"
    assert preview["unit_title"] == "Unit 1: Sports"
    assert len(preview["snippets"]) == 1
    snippet = preview["snippets"][0]
    assert snippet["source_id"] == "source-1"
    assert snippet["markdown"].startswith("# Unit 1")
    assert snippet["start"] == 2
    assert snippet["end"] == 8


def test_locate_normalized_quote_handles_markdown_and_line_wrapping():
    markdown = "## **Soccer** is popular\nfor all of these reasons.\n\nNext."
    located = education_structure_review._locate_normalized_quote(
        markdown,
        "Soccer is popular for all of these reasons.",
    )

    assert located is not None
    start, end = located
    span = markdown[start:end]
    assert "Soccer" in span
    assert "reasons" in span
    assert "Next." not in span


@pytest.mark.asyncio
async def test_resume_structure_requeues_same_job_and_launches(monkeypatch):
    launched: dict[str, str] = {}

    async def household(_user_id: str):
        return {"household_id": "household-1"}

    async def get_job(**_kwargs):
        return {
            "generation_job_id": "generation-1",
            "scope": "structure",
            "status": "failed",
        }

    async def requeue(**kwargs):
        launched["requeue"] = kwargs["generation_job_id"]
        return True

    async def launch(**kwargs):
        launched["launch"] = kwargs["generation_job_id"]
        return {"root_run_id": "run-2"}

    async def projection(**_kwargs):
        return {
            "generation_job_id": "generation-1",
            "scope": "structure",
            "status": "queued",
        }

    monkeypatch.setattr(
        education_structure_review,
        "get_household_context_for_parent",
        household,
    )
    monkeypatch.setattr(
        education_structure_review,
        "get_generation_job_for_parent",
        get_job,
    )
    monkeypatch.setattr(
        education_structure_review,
        "requeue_structure_generation",
        requeue,
    )
    monkeypatch.setattr(
        education_structure_review,
        "launch_structure_generation",
        launch,
    )
    monkeypatch.setattr(
        education_structure_review,
        "get_structure_generation_job_for_parent",
        projection,
    )

    result = await education_structure_review.resume_structure_generation_for_parent(
        parent_user_id="parent-1",
        generation_job_id="generation-1",
    )

    assert launched == {
        "requeue": "generation-1",
        "launch": "generation-1",
    }
    assert result["status"] == "queued"


@pytest.mark.asyncio
async def test_replace_structure_validates_edit_and_persists_units(monkeypatch):
    stored: dict[str, object] = {}

    async def household(_user_id: str):
        return {"household_id": "household-1"}

    async def get_job(**_kwargs):
        return {"version_id": "version-1"}

    async def get_structure(**_kwargs):
        return STRUCTURE

    async def get_input(**_kwargs):
        return FROZEN_INPUT

    async def replace(**kwargs):
        stored.update(kwargs)
        return kwargs["units"]

    monkeypatch.setattr(
        education_structure_review,
        "get_household_context_for_parent",
        household,
    )
    monkeypatch.setattr(
        education_structure_review,
        "get_generation_job_for_parent",
        get_job,
    )
    monkeypatch.setattr(
        education_structure_review,
        "get_textbook_structure_for_parent",
        get_structure,
    )
    monkeypatch.setattr(
        education_structure_review,
        "get_teaching_input_for_parent",
        get_input,
    )
    monkeypatch.setattr(
        education_structure_review,
        "replace_structure_contents",
        replace,
    )

    result = await education_structure_review.replace_structure_for_parent(
        parent_user_id="parent-1",
        structure_id="structure-1",
        units=[STRUCTURE["units"][0]],
    )

    assert result[0]["slug"] == "unit-1-sports"
    assert stored["structure_id"] == "structure-1"


@pytest.mark.asyncio
async def test_accept_structure_requires_at_least_one_knowledge_point(monkeypatch):
    empty = {
        **STRUCTURE,
        "units": [
            {
                **STRUCTURE["units"][0],
                "knowledge_points": [],
            }
        ],
    }

    async def household(_user_id: str):
        return {"household_id": "household-1"}

    async def get_structure(**_kwargs):
        return empty

    monkeypatch.setattr(
        education_structure_review,
        "get_household_context_for_parent",
        household,
    )
    monkeypatch.setattr(
        education_structure_review,
        "get_textbook_structure_for_parent",
        get_structure,
    )

    with pytest.raises(TextbookTransitionError, match="knowledge point"):
        await education_structure_review.accept_structure_for_parent(
            parent_user_id="parent-1",
            structure_id="structure-1",
        )


@pytest.mark.asyncio
async def test_accept_structure_projects_not_found_and_success(monkeypatch):
    async def household(_user_id: str):
        return {"household_id": "household-1"}

    async def missing(**_kwargs):
        return None

    monkeypatch.setattr(
        education_structure_review,
        "get_household_context_for_parent",
        household,
    )
    monkeypatch.setattr(
        education_structure_review,
        "get_textbook_structure_for_parent",
        missing,
    )

    with pytest.raises(TextbookNotFoundError):
        await education_structure_review.accept_structure_for_parent(
            parent_user_id="parent-1",
            structure_id="missing",
        )

    async def found(**_kwargs):
        return STRUCTURE

    async def accept(**_kwargs):
        return {"structure_id": "structure-1", "status": "accepted"}

    monkeypatch.setattr(
        education_structure_review,
        "get_textbook_structure_for_parent",
        found,
    )
    monkeypatch.setattr(
        education_structure_review,
        "accept_textbook_structure",
        accept,
    )

    accepted = await education_structure_review.accept_structure_for_parent(
        parent_user_id="parent-1",
        structure_id="structure-1",
    )

    assert accepted["status"] == "accepted"
