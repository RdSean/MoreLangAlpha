"""HTTP contracts for textbook structure review."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.server.app.education.textbooks import router
from src.server.services.education_textbooks import TextbookPermissionError
from src.server.utils.api import get_current_user_id


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as session:
        yield session


def _structure() -> dict:
    structure_id = uuid4()
    version_id = uuid4()
    unit_id = uuid4()
    knowledge_point_id = uuid4()
    return {
        "structure_id": structure_id,
        "version_id": version_id,
        "sequence": 1,
        "status": "review",
        "schema_version": "langalpha-managed-textbook-structure/v1",
        "processing_profile_id": None,
        "processing_profile_sha256": "a" * 64,
        "input_manifest_sha256": "b" * 64,
        "source_revision": "c" * 64,
        "created_at": None,
        "reviewed_at": None,
        "validation_warnings": ["source_quote_unresolved"],
        "units": [
            {
                "unit_id": unit_id,
                "position": 1,
                "slug": "unit-1-sports",
                "title": "Unit 1: Sports and Fitness",
                "summary": "",
                "unit_type": "teaching",
                "source_refs": [
                    {
                        "source_id": "source-1",
                        "start": 0,
                        "end": 50,
                        "quote": None,
                        "heading_path": [],
                    }
                ],
                "confidence": 0.96,
                "status": "review",
                "knowledge_points": [
                    {
                        "knowledge_point_id": knowledge_point_id,
                        "position": 1,
                        "slug": "world-game",
                        "title": "世界运动",
                        "summary": "",
                        "source_refs": [
                            {
                                "source_id": "source-1",
                                "start": None,
                                "end": None,
                                "quote": None,
                                "heading_path": [],
                            }
                        ],
                        "confidence": 0.93,
                        "status": "review",
                    }
                ],
            }
        ],
    }


@pytest.mark.asyncio
async def test_parent_queues_reads_edits_and_accepts_structure(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    structure = _structure()
    job = {
        "generation_job_id": uuid4(),
        "version_id": structure["version_id"],
        "scope": "structure",
        "structure_id": structure["structure_id"],
        "status": "queued",
        "attempt_count": 0,
    }
    update_body = {
        "units": [
            {
                **{key: value for key, value in structure["units"][0].items() if key not in {"unit_id", "status", "knowledge_points"}},
                "knowledge_points": [
                    {
                        key: value
                        for key, value in structure["units"][0]["knowledge_points"][0].items()
                        if key not in {"knowledge_point_id", "status"}
                    }
                ],
            }
        ]
    }
    with (
        patch(
            "src.server.app.education.textbooks.queue_structure_for_parent",
            new=AsyncMock(return_value=job),
        ) as queue,
        patch(
            "src.server.app.education.textbooks.get_structure_for_parent",
            new=AsyncMock(return_value=structure),
        ),
        patch(
            "src.server.app.education.textbooks.replace_structure_for_parent",
            new=AsyncMock(return_value=structure["units"]),
        ) as replace,
        patch(
            "src.server.app.education.textbooks.accept_structure_for_parent",
            new=AsyncMock(return_value={"status": "accepted"}),
        ) as accept,
    ):
        queued = await client.post(
            f"/api/v1/education/textbook-versions/{structure['version_id']}/structures",
            json={
                "profile": {
                    "subject": "english",
                    "grade_band": "middle",
                    "language": "zh-CN",
                    "depth": "deep",
                    "question_types": ["choice", "fill"],
                    "prompt_fragment": "强调阅读策略",
                    "allowed_skills": ["book-to-skill"],
                }
            },
        )
        loaded = await client.get(
            f"/api/v1/education/textbook-structures/{structure['structure_id']}"
        )
        updated = await client.put(
            f"/api/v1/education/textbook-structures/{structure['structure_id']}",
            json=update_body,
        )
        accepted = await client.post(
            f"/api/v1/education/textbook-structures/{structure['structure_id']}/review"
        )

    assert queued.status_code == 202
    assert loaded.status_code == 200
    assert loaded.json()["validation_warnings"] == ["source_quote_unresolved"]
    assert updated.status_code == 200
    assert accepted.status_code == 200
    queue.assert_awaited_once()
    assert queue.await_args.kwargs["profile_input"]["subject"] == "english"
    assert replace.await_args.kwargs["units"][0]["slug"] == "unit-1-sports"
    assert accept.await_args.kwargs["structure_id"] == str(structure["structure_id"])


@pytest.mark.asyncio
async def test_student_cannot_create_structure(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"
    version_id = uuid4()
    with patch(
        "src.server.app.education.textbooks.queue_structure_for_parent",
        new=AsyncMock(
            side_effect=TextbookPermissionError(
                "Only a parent can create textbook structures"
            )
        ),
    ):
        response = await client.post(
            f"/api/v1/education/textbook-versions/{version_id}/structures"
        )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_structure_update_rejects_missing_units(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"

    response = await client.put(
        f"/api/v1/education/textbook-structures/{uuid4()}",
        json={"units": []},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_parent_generates_reviews_and_publishes_lesson(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    lesson_id = uuid4()
    revision_id = uuid4()
    knowledge_point_id = uuid4()
    unit_id = uuid4()
    lesson = {
        "lesson_id": lesson_id,
        "status": "review",
        "latest_revision_id": revision_id,
        "knowledge_point_id": knowledge_point_id,
        "knowledge_point_title": "世界运动",
        "structure_id": uuid4(),
        "unit_id": unit_id,
        "unit_title": "Unit 1",
        "content_markdown": "# 世界运动\n",
        "revisions": [
            {
                "revision_id": revision_id,
                "revision": 1,
                "format": "markdown",
                "content_sha256": "a" * 64,
                "size_bytes": 20,
                "processing_profile_sha256": "b" * 64,
                "created_at": None,
            }
        ],
    }
    job = {
        "generation_job_id": uuid4(),
        "version_id": uuid4(),
        "scope": "lesson",
        "knowledge_point_id": knowledge_point_id,
        "status": "queued",
        "attempt_count": 0,
        "auto_grading": False,
    }
    publication = {
        "publication_id": uuid4(),
        "version_id": job["version_id"],
        "structure_id": uuid4(),
    }
    with (
        patch(
            "src.server.app.education.textbooks.queue_lesson_for_parent",
            new=AsyncMock(return_value=job),
        ) as queue,
        patch(
            "src.server.app.education.textbooks.get_lesson_for_parent",
            new=AsyncMock(return_value=lesson),
        ),
        patch(
            "src.server.app.education.textbooks.create_manual_lesson_revision",
            new=AsyncMock(return_value={"revision_id": revision_id}),
        ) as revise,
        patch(
            "src.server.app.education.textbooks.approve_lesson_for_parent",
            new=AsyncMock(return_value={"status": "approved"}),
        ) as approve,
        patch(
            "src.server.app.education.textbooks.publish_structure_for_parent",
            new=AsyncMock(return_value=publication),
        ) as publish,
    ):
        queued = await client.post(
            f"/api/v1/education/knowledge-points/{knowledge_point_id}/lessons",
            json={"auto_grading": False},
        )
        loaded = await client.get(
            f"/api/v1/education/knowledge-point-lessons/{lesson_id}"
        )
        revised = await client.post(
            f"/api/v1/education/knowledge-point-lessons/{lesson_id}/revisions",
            json={"content_markdown": "# 修订版\n"},
        )
        approved = await client.post(
            f"/api/v1/education/knowledge-point-lessons/{lesson_id}/review",
            json={"revision_id": str(revision_id)},
        )
        published = await client.post(
            f"/api/v1/education/textbook-versions/{job['version_id']}/structure-publications",
            json={"structure_id": str(publication["structure_id"])},
        )

    assert queued.status_code == 202
    assert loaded.status_code == 200
    assert revised.status_code == 200
    assert approved.status_code == 200
    assert published.status_code == 201
    assert queue.await_args.kwargs["knowledge_point_id"] == str(knowledge_point_id)
    assert revise.await_args.kwargs["content_markdown"] == "# 修订版\n"
    assert approve.await_args.kwargs["revision_id"] == str(revision_id)
    assert publish.await_args.kwargs["structure_id"] == str(
        publication["structure_id"]
    )


@pytest.mark.asyncio
async def test_parent_reads_latest_structure_and_lesson_by_knowledge_point(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    structure = _structure()
    knowledge_point_id = uuid4()
    with (
        patch(
            "src.server.app.education.textbooks.get_latest_structure_for_parent",
            new=AsyncMock(return_value=structure),
        ) as latest,
        patch(
            "src.server.app.education.textbooks.get_lesson_for_knowledge_point",
            new=AsyncMock(return_value=None),
        ) as lesson,
    ):
        structure_response = await client.get(
            f"/api/v1/education/textbook-versions/{structure['version_id']}/structure"
        )
        lesson_response = await client.get(
            f"/api/v1/education/knowledge-points/{knowledge_point_id}/lesson"
        )

    assert structure_response.status_code == 200
    assert lesson_response.status_code == 200
    assert lesson_response.json() is None
    latest.assert_awaited_once()
    lesson.assert_awaited_once()


@pytest.mark.asyncio
async def test_student_reads_only_published_structure_and_lesson(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"
    assignment_id = uuid4()
    structure_id = uuid4()
    unit_id = uuid4()
    knowledge_point_id = uuid4()
    revision_id = uuid4()
    structure = {
        "assignment_id": assignment_id,
        "publication_id": uuid4(),
        "textbook_id": uuid4(),
        "textbook_title": "Reading Explorer 3",
        "textbook_slug": "re3",
        "version_sequence": 1,
        "structure_id": structure_id,
        "structure_sequence": 1,
        "units": [
            {
                "unit_id": unit_id,
                "position": 1,
                "slug": "unit-1",
                "title": "Unit 1",
                "summary": "",
                "unit_type": "teaching",
                "knowledge_points": [
                    {
                        "knowledge_point_id": knowledge_point_id,
                        "position": 1,
                        "slug": "world-game",
                        "title": "世界运动",
                        "summary": "",
                        "has_lesson": True,
                    }
                ],
            }
        ],
    }
    lesson = {
        "assignment_id": assignment_id,
        "knowledge_point_id": knowledge_point_id,
        "knowledge_point_title": "世界运动",
        "unit_id": unit_id,
        "unit_title": "Unit 1",
        "revision_id": revision_id,
        "revision": 1,
        "format": "markdown",
        "content_sha256": "a" * 64,
        "size_bytes": 20,
        "content_markdown": "# 世界运动\n",
    }
    with (
        patch(
            "src.server.app.education.textbooks.get_student_structure",
            new=AsyncMock(return_value=structure),
        ),
        patch(
            "src.server.app.education.textbooks.get_student_kp_lesson",
            new=AsyncMock(return_value=lesson),
        ),
    ):
        structure_response = await client.get(
            f"/api/v1/education/learning/{assignment_id}/structure"
        )
        lesson_response = await client.get(
            f"/api/v1/education/learning/{assignment_id}/knowledge-points/{knowledge_point_id}"
        )

    assert structure_response.status_code == 200
    assert lesson_response.status_code == 200
    assert structure_response.json()["units"][0]["knowledge_points"][0]["has_lesson"] is True
    assert lesson_response.json()["content_markdown"] == "# 世界运动\n"
