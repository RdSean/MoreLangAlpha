"""HTTP contracts for textbook structure review."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from src.server.app.education.textbooks import router
from src.server.app.education.models import CreateBookPipelineRequest
from src.server.services import education_structure_progress as progress_service
from src.server.services.education_textbooks import (
    TextbookNotFoundError,
    TextbookPermissionError,
    TextbookTransitionError,
)
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
                **{
                    key: value
                    for key, value in structure["units"][0].items()
                    if key not in {"unit_id", "status", "knowledge_points"}
                },
                "knowledge_points": [
                    {
                        key: value
                        for key, value in structure["units"][0]["knowledge_points"][
                            0
                        ].items()
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
async def test_parent_reviews_updates_and_accepts_generated_candidates(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    structure_id = uuid4()
    candidate_id = uuid4()
    review = {
        "structure_id": structure_id,
        "version_id": uuid4(),
        "nodes": [
            {
                "node_id": uuid4(),
                "structure_id": structure_id,
                "parent_node_id": None,
                "node_key": "unit-1",
                "node_type": "unit",
                "label": None,
                "position": 1,
                "slug": "unit-1",
                "title": "Unit 1",
                "summary": "",
                "source_refs": [],
                "candidates": [
                    {
                        "knowledge_point_id": candidate_id,
                        "content_structure_id": structure_id,
                        "content_node_id": uuid4(),
                        "candidate_key": "unit-1-kp-1",
                        "point_type": "concept",
                        "origin": "generated",
                        "candidate_status": "pending",
                        "position": 1,
                        "slug": "world-game",
                        "title": "世界运动",
                        "summary": "",
                        "source_refs": [],
                        "confidence": 0.9,
                        "status": "review",
                        "created_at": None,
                    }
                ],
            }
        ],
    }
    accepted = {
        **review["nodes"][0]["candidates"][0],
        "candidate_status": "accepted",
        "status": "accepted",
    }
    updated = {**accepted, "title": "足球运动", "point_type": "reading_skill"}
    with (
        patch(
            "src.server.app.education.textbooks.list_knowledge_point_candidates_for_parent",
            new=AsyncMock(return_value=review),
        ) as list_candidates,
        patch(
            "src.server.app.education.textbooks.update_knowledge_point_candidate_for_parent",
            new=AsyncMock(return_value=updated),
        ) as update_candidate,
        patch(
            "src.server.app.education.textbooks.accept_knowledge_point_candidates_for_parent",
            new=AsyncMock(return_value=[accepted]),
        ) as accept_candidates,
    ):
        listed = await client.get(
            f"/api/v1/education/structures/{structure_id}/candidates"
        )
        changed = await client.patch(
            f"/api/v1/education/candidates/{candidate_id}",
            json={"title": "足球运动", "point_type": "reading_skill"},
        )
        accepted_response = await client.post(
            "/api/v1/education/candidates/accept",
            json={"candidate_ids": [str(candidate_id)]},
        )

    assert listed.status_code == 200
    assert listed.json()["nodes"][0]["candidates"][0]["candidate_status"] == "pending"
    assert changed.status_code == 200
    assert changed.json()["title"] == "足球运动"
    assert accepted_response.status_code == 200
    assert accepted_response.json()[0]["candidate_status"] == "accepted"
    list_candidates.assert_awaited_once_with(
        parent_user_id="parent-1", structure_id=str(structure_id)
    )
    update_candidate.assert_awaited_once_with(
        parent_user_id="parent-1",
        candidate_id=str(candidate_id),
        title="足球运动",
        summary=None,
        point_type="reading_skill",
    )
    accept_candidates.assert_awaited_once_with(
        parent_user_id="parent-1", candidate_ids=[str(candidate_id)]
    )


@pytest.mark.asyncio
async def test_parent_rejects_merges_and_splits_candidates(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    first_id = uuid4()
    second_id = uuid4()
    with (
        patch(
            "src.server.app.education.textbooks.reject_knowledge_point_candidates_for_parent",
            new=AsyncMock(return_value=[]),
        ) as reject_candidates,
        patch(
            "src.server.app.education.textbooks.merge_knowledge_point_candidates_for_parent",
            new=AsyncMock(return_value=[]),
        ) as merge_candidates,
        patch(
            "src.server.app.education.textbooks.split_knowledge_point_candidate_for_parent",
            new=AsyncMock(return_value=[]),
        ) as split_candidate,
    ):
        rejected = await client.post(
            "/api/v1/education/candidates/reject",
            json={"candidate_ids": [str(first_id)]},
        )
        merged = await client.post(
            "/api/v1/education/candidates/merge",
            json={
                "source_ids": [str(first_id), str(second_id)],
                "target_id": str(first_id),
                "title": "合并后的知识点",
                "point_type": "concept",
                "accept": True,
            },
        )
        split = await client.post(
            "/api/v1/education/candidates/split",
            json={
                "candidate_id": str(first_id),
                "items": [
                    {"title": "第一部分", "point_type": "concept"},
                    {"title": "第二部分", "point_type": "concept"},
                ],
            },
        )

    assert rejected.status_code == 200
    assert merged.status_code == 200
    assert split.status_code == 200
    reject_candidates.assert_awaited_once_with(
        parent_user_id="parent-1", candidate_ids=[str(first_id)]
    )
    merge_candidates.assert_awaited_once_with(
        parent_user_id="parent-1",
        source_ids=[str(first_id), str(second_id)],
        target_id=str(first_id),
        title="合并后的知识点",
        summary=None,
        point_type="concept",
        accept=True,
    )
    split_candidate.assert_awaited_once_with(
        parent_user_id="parent-1",
        candidate_id=str(first_id),
        items=[
            {
                "title": "第一部分",
                "summary": "",
                "point_type": "concept",
            },
            {
                "title": "第二部分",
                "summary": "",
                "point_type": "concept",
            },
        ],
    )


@pytest.mark.asyncio
async def test_merge_without_target_cannot_be_accepted_immediately(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    first_id = uuid4()
    second_id = uuid4()
    with patch(
        "src.server.app.education.textbooks.merge_knowledge_point_candidates_for_parent",
        new=AsyncMock(),
    ) as merge_candidates:
        response = await client.post(
            "/api/v1/education/candidates/merge",
            json={
                "source_ids": [str(first_id), str(second_id)],
                "title": "新建合并候选",
                "point_type": "concept",
                "accept": True,
            },
        )

    assert response.status_code == 422
    merge_candidates.assert_not_awaited()


@pytest.mark.asyncio
async def test_candidate_transition_errors_map_to_http_conflicts(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    candidate_id = uuid4()
    with patch(
        "src.server.app.education.textbooks.accept_knowledge_point_candidates_for_parent",
        new=AsyncMock(
            side_effect=TextbookTransitionError(
                "Generated knowledge-point candidate transition is not allowed"
            )
        ),
    ):
        conflict = await client.post(
            "/api/v1/education/candidates/accept",
            json={"candidate_ids": [str(candidate_id)]},
        )
    with patch(
        "src.server.app.education.textbooks.accept_knowledge_point_candidates_for_parent",
        new=AsyncMock(
            side_effect=TextbookNotFoundError(
                "Generated knowledge-point candidate not found"
            )
        ),
    ):
        missing = await client.post(
            "/api/v1/education/candidates/accept",
            json={"candidate_ids": [str(candidate_id)]},
        )

    assert conflict.status_code == 409
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_candidate_text_controls_are_rejected_before_persistence(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    first_id = uuid4()
    second_id = uuid4()
    with (
        patch(
            "src.server.app.education.textbooks.update_knowledge_point_candidate_for_parent",
            new=AsyncMock(),
        ) as update_candidate,
        patch(
            "src.server.app.education.textbooks.merge_knowledge_point_candidates_for_parent",
            new=AsyncMock(),
        ) as merge_candidates,
        patch(
            "src.server.app.education.textbooks.split_knowledge_point_candidate_for_parent",
            new=AsyncMock(),
        ) as split_candidate,
    ):
        updated = await client.patch(
            f"/api/v1/education/candidates/{first_id}",
            json={"title": "bad\u0000title"},
        )
        merged = await client.post(
            "/api/v1/education/candidates/merge",
            json={
                "source_ids": [str(first_id), str(second_id)],
                "target_id": str(first_id),
                "summary": "bad\u0000summary",
            },
        )
        split = await client.post(
            "/api/v1/education/candidates/split",
            json={
                "candidate_id": str(first_id),
                "items": [
                    {"title": "bad\u0001title", "point_type": "concept"},
                    {"title": "second", "point_type": "concept"},
                ],
            },
        )

    assert updated.status_code == 422
    assert merged.status_code == 422
    assert split.status_code == 422
    update_candidate.assert_not_awaited()
    merge_candidates.assert_not_awaited()
    split_candidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_candidate_summary_accepts_contract_line_breaks(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    first_id = uuid4()
    second_id = uuid4()
    with patch(
        "src.server.app.education.textbooks.merge_knowledge_point_candidates_for_parent",
        new=AsyncMock(return_value=[]),
    ) as merge_candidates:
        response = await client.post(
            "/api/v1/education/candidates/merge",
            json={
                "source_ids": [str(first_id), str(second_id)],
                "target_id": str(first_id),
                "summary": "第一行\n第二行\r\n第三行",
            },
        )

    assert response.status_code == 200
    assert merge_candidates.await_args.kwargs["summary"] == "第一行\n第二行\r\n第三行"


@pytest.mark.asyncio
async def test_student_cannot_access_candidate_review_endpoints(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"
    structure_id = uuid4()
    candidate_id = uuid4()
    other_id = uuid4()
    permission = TextbookPermissionError(
        "Only a parent can review knowledge-point candidates"
    )
    with (
        patch(
            "src.server.app.education.textbooks.list_knowledge_point_candidates_for_parent",
            new=AsyncMock(side_effect=permission),
        ),
        patch(
            "src.server.app.education.textbooks.update_knowledge_point_candidate_for_parent",
            new=AsyncMock(side_effect=permission),
        ),
        patch(
            "src.server.app.education.textbooks.accept_knowledge_point_candidates_for_parent",
            new=AsyncMock(side_effect=permission),
        ),
        patch(
            "src.server.app.education.textbooks.reject_knowledge_point_candidates_for_parent",
            new=AsyncMock(side_effect=permission),
        ),
        patch(
            "src.server.app.education.textbooks.merge_knowledge_point_candidates_for_parent",
            new=AsyncMock(side_effect=permission),
        ),
        patch(
            "src.server.app.education.textbooks.split_knowledge_point_candidate_for_parent",
            new=AsyncMock(side_effect=permission),
        ),
    ):
        responses = [
            await client.get(f"/api/v1/education/structures/{structure_id}/candidates"),
            await client.patch(
                f"/api/v1/education/candidates/{candidate_id}",
                json={"title": "新标题"},
            ),
            await client.post(
                "/api/v1/education/candidates/accept",
                json={"candidate_ids": [str(candidate_id)]},
            ),
            await client.post(
                "/api/v1/education/candidates/reject",
                json={"candidate_ids": [str(candidate_id)]},
            ),
            await client.post(
                "/api/v1/education/candidates/merge",
                json={
                    "source_ids": [str(candidate_id), str(other_id)],
                    "target_id": str(candidate_id),
                },
            ),
            await client.post(
                "/api/v1/education/candidates/split",
                json={
                    "candidate_id": str(candidate_id),
                    "items": [
                        {"title": "一", "point_type": "concept"},
                        {"title": "二", "point_type": "concept"},
                    ],
                },
            ),
        ]

    assert [response.status_code for response in responses] == [403] * 6


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
    assert publish.await_args.kwargs["structure_id"] == str(publication["structure_id"])


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
async def test_parent_reads_lesson_generation_status(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    knowledge_point_id = uuid4()
    status_payload = {
        "knowledge_point_id": knowledge_point_id,
        "generating": True,
        "generation_job_id": uuid4(),
        "status": "running",
        "attempt_count": 1,
        "auto_grading": False,
        "error_code": None,
        "error_message": None,
        "started_at": None,
        "heartbeat_at": None,
        "root_run_id": None,
    }
    with patch(
        "src.server.app.education.textbooks.get_lesson_generation_status_for_parent",
        new=AsyncMock(return_value=status_payload),
    ) as status_call:
        response = await client.get(
            f"/api/v1/education/knowledge-points/{knowledge_point_id}/lesson-generation"
        )

    assert response.status_code == 200
    assert response.json()["generating"] is True
    status_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_parent_reads_structure_generation_progress(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    generation_job_id = uuid4()
    progress = {
        "generation_job_id": generation_job_id,
        "run_id": uuid4(),
        "status": "running",
        "events": [
            {
                "sequence": 0,
                "kind": "tool",
                "label": "扫描源文档：01-rex.md",
                "detail": None,
                "status": "completed",
                "timestamp": "2026-09-21T04:45:46Z",
            }
        ],
        "truncated": False,
    }
    with patch(
        "src.server.app.education.textbooks.get_structure_progress_for_parent",
        new=AsyncMock(return_value=progress),
    ) as progress_call:
        response = await client.get(
            f"/api/v1/education/structure-generation-jobs/{generation_job_id}/progress"
        )

    assert response.status_code == 200
    assert response.json()["events"][0]["label"] == "扫描源文档：01-rex.md"
    progress_call.assert_awaited_once()


def test_build_book_pipeline_progress_keeps_fixed_order_and_completed_state():
    job = {
        "generation_job_id": uuid4(),
        "scope": "book_pipeline",
        "status": "running",
    }
    events = [
        {
            "attempt_id": "attempt-1",
            "sequence": 1,
            "event_key": "chapter:done",
            "stage": "chapter_analysis",
            "status": "completed",
            "label": "章节解析已完成",
            "detail": None,
            "current_value": 12,
            "total_value": 12,
            "metadata": {"source": "skill"},
            "created_at": "2026-09-22T01:00:00+00:00",
        },
        {
            "attempt_id": "attempt-1",
            "sequence": 2,
            "event_key": "content:unit-2",
            "stage": "content_processing",
            "status": "running",
            "label": "正在生成 Reading A 知识稿",
            "detail": "正在提取术语",
            "current_value": 2,
            "total_value": 12,
            "metadata": {},
            "created_at": "2026-09-22T01:01:00+00:00",
        },
        {
            "attempt_id": "attempt-1",
            "sequence": 3,
            "event_key": "knowledge:done",
            "stage": "knowledge_point_generation",
            "status": "completed",
            "label": "知识点候选已完成",
            "detail": None,
            "current_value": 22,
            "total_value": 22,
            "metadata": {},
            "created_at": "2026-09-22T01:02:00+00:00",
        },
        {
            "attempt_id": "attempt-1",
            "sequence": 4,
            "event_key": "chapter:fallback",
            "stage": "chapter_analysis",
            "status": "running",
            "label": "执行环境步骤",
            "detail": None,
            "current_value": None,
            "total_value": None,
            "metadata": {"fallback": True},
            "created_at": "2026-09-22T01:03:00+00:00",
        },
    ]

    progress = progress_service.build_book_pipeline_progress(job=job, events=events)

    assert [stage["name"] for stage in progress["stages"]] == [
        "chapter_analysis",
        "content_processing",
        "knowledge_point_generation",
        "lesson_preparation",
    ]
    assert [stage["label"] for stage in progress["stages"]] == [
        "教材章节解析",
        "内容智能处理",
        "知识点生成",
        "课程制作",
    ]
    assert [stage["status"] for stage in progress["stages"]] == [
        "completed",
        "running",
        "completed",
        "queued",
    ]
    assert progress["stages"][1]["current"] == 2
    assert progress["stages"][1]["total"] == 12
    assert progress["last_sequence"] == 4
    assert progress["stages"][1]["events"][-1]["label"] == "正在生成 Reading A 知识稿"
    assert "event_key" not in progress["stages"][1]["events"][-1]
    assert "metadata" not in progress["stages"][1]["events"][-1]


def test_build_book_pipeline_progress_derives_checkpoint_lifecycle_without_events():
    progress = progress_service.build_book_pipeline_progress(
        job={
            "generation_job_id": uuid4(),
            "scope": "book_pipeline",
            "status": "awaiting_review",
        },
        events=[],
    )

    assert [stage["status"] for stage in progress["stages"]] == [
        "completed",
        "queued",
        "queued",
        "queued",
    ]
    assert all(stage["events"] == [] for stage in progress["stages"])
    assert progress["last_sequence"] == 0


def test_build_book_pipeline_progress_derives_completed_import_lifecycle():
    progress = progress_service.build_book_pipeline_progress(
        job={
            "generation_job_id": uuid4(),
            "scope": "book_pipeline",
            "status": "completed",
        },
        events=[],
    )

    assert [stage["status"] for stage in progress["stages"]] == [
        "completed",
        "completed",
        "completed",
        "queued",
    ]
    assert progress["stages"][3]["label"] == "课程制作"


def test_build_book_pipeline_progress_uses_attempt_order_for_last_sequence():
    progress = progress_service.build_book_pipeline_progress(
        job={
            "generation_job_id": uuid4(),
            "scope": "book_pipeline",
            "status": "running",
        },
        events=[
            {
                "attempt_id": "old-attempt",
                "attempt_started_at": "2026-09-22T01:00:00+00:00",
                "sequence": 41,
                "stage": "content_processing",
                "status": "completed",
                "label": "旧 attempt 事件",
                "current_value": 12,
                "total_value": 12,
                "created_at": "2026-09-22T01:30:00+00:00",
            },
            {
                "attempt_id": "new-attempt",
                "attempt_started_at": "2026-09-22T02:00:00+00:00",
                "sequence": 2,
                "stage": "content_processing",
                "status": "running",
                "label": "新 attempt 事件",
                "current_value": 2,
                "total_value": 12,
                "created_at": "2026-09-22T02:01:00+00:00",
            },
        ],
    )

    stage = progress["stages"][1]
    assert progress["last_sequence"] == 2
    assert stage["status"] == "running"
    assert stage["current"] == 2
    assert [event["label"] for event in stage["events"]] == [
        "旧 attempt 事件",
        "新 attempt 事件",
    ]
    assert "_sse_cursor" not in progress
    assert (
        progress_service.build_book_pipeline_progress(
            job={
                "generation_job_id": uuid4(),
                "scope": "book_pipeline",
                "status": "running",
            },
            events=[
                {
                    "attempt_id": "new-attempt",
                    "attempt_started_at": "2026-09-22T02:00:00+00:00",
                    "sequence": 2,
                    "stage": "content_processing",
                    "status": "running",
                    "label": "新 attempt 事件",
                }
            ],
            include_sse_cursor=True,
        )["_sse_cursor"]
        == "new-attempt:2"
    )


def test_build_book_pipeline_progress_falls_back_to_latest_counted_event():
    progress = progress_service.build_book_pipeline_progress(
        job={
            "generation_job_id": uuid4(),
            "scope": "book_pipeline",
            "status": "running",
        },
        events=[
            {
                "attempt_id": "attempt-1",
                "attempt_started_at": "2026-09-22T01:00:00+00:00",
                "sequence": 1,
                "stage": "knowledge_point_generation",
                "status": "running",
                "label": "正在生成知识点",
                "current_value": 10,
                "total_value": 12,
            },
            {
                "attempt_id": "attempt-1",
                "attempt_started_at": "2026-09-22T01:00:00+00:00",
                "sequence": 2_000,
                "stage": "knowledge_point_generation",
                "status": "completed",
                "label": "知识点生成完成",
            },
        ],
        truncated=True,
    )

    stage = progress["stages"][2]
    assert progress["truncated"] is True
    assert stage["status"] == "completed"
    assert stage["current"] == 10
    assert stage["total"] == 12


def test_build_book_pipeline_progress_does_not_inherit_old_attempt_counts():
    progress = progress_service.build_book_pipeline_progress(
        job={
            "generation_job_id": uuid4(),
            "scope": "book_pipeline",
            "status": "running",
        },
        events=[
            {
                "attempt_id": "old-attempt",
                "attempt_started_at": "2026-09-22T01:00:00+00:00",
                "sequence": 10,
                "stage": "lesson_preparation",
                "status": "running",
                "label": "旧课程制作进度",
                "current_value": 10,
                "total_value": 12,
            },
            {
                "attempt_id": "new-attempt",
                "attempt_started_at": "2026-09-22T02:00:00+00:00",
                "sequence": 2,
                "stage": "lesson_preparation",
                "status": "running",
                "label": "新课程制作进度",
            },
        ],
    )

    stage = progress["stages"][3]
    assert stage["status"] == "running"
    assert stage["current"] is None
    assert stage["total"] is None


@pytest.mark.asyncio
async def test_book_pipeline_progress_rejects_other_scopes():
    with (
        patch.object(
            progress_service,
            "get_household_context_for_parent",
            new=AsyncMock(return_value={"household_id": "household-1"}),
        ),
        patch.object(
            progress_service,
            "get_generation_job_for_parent",
            new=AsyncMock(
                return_value={
                    "generation_job_id": uuid4(),
                    "scope": "structure",
                    "status": "running",
                }
            ),
        ),
    ):
        with pytest.raises(progress_service.TextbookNotFoundError):
            await progress_service.get_book_pipeline_progress_for_parent(
                parent_user_id="parent-1",
                generation_job_id=str(uuid4()),
            )


@pytest.mark.asyncio
async def test_parent_queues_gets_and_resumes_book_pipeline(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    generation_job_id = uuid4()
    version_id = uuid4()
    base_job = {
        "generation_job_id": generation_job_id,
        "version_id": version_id,
        "scope": "book_pipeline",
        "structure_id": None,
        "knowledge_point_id": None,
        "status": "queued",
        "attempt_count": 0,
        "pause_after_chapter_analysis": False,
        "error_code": None,
        "error_message": None,
        "created_at": None,
        "updated_at": None,
        "root_run_id": None,
        "started_at": None,
        "heartbeat_at": None,
        "reused_existing_job": False,
    }
    waiting = {
        **base_job,
        "status": "awaiting_review",
        "pause_after_chapter_analysis": True,
    }
    with (
        patch(
            "src.server.app.education.textbooks.queue_and_launch_book_pipeline_for_parent",
            new=AsyncMock(return_value=base_job),
        ) as queue,
        patch(
            "src.server.app.education.textbooks.get_book_pipeline_job_for_parent",
            new=AsyncMock(return_value=waiting),
        ) as get_job,
        patch(
            "src.server.app.education.textbooks.resume_book_pipeline_for_parent",
            new=AsyncMock(return_value=base_job),
        ) as resume,
    ):
        queued = await client.post(
            f"/api/v1/education/textbook-versions/{version_id}/book-pipeline-jobs",
            json={
                "processing_brief": " 法语教材，保留公式顺序。 ",
                "request_id": "ba8a3e5c-c0b4-4a40-95ec-349310992445",
                "pause_after_chapter_analysis": False,
            },
        )
        loaded = await client.get(
            f"/api/v1/education/book-pipeline-jobs/{generation_job_id}"
        )
        resumed = await client.post(
            f"/api/v1/education/book-pipeline-jobs/{generation_job_id}/resume"
        )

    assert queued.status_code == 202
    assert queued.json()["scope"] == "book_pipeline"
    assert queued.json()["reused_existing_job"] is False
    assert loaded.status_code == 200
    assert loaded.json()["status"] == "awaiting_review"
    assert resumed.status_code == 202
    assert queue.await_args.kwargs["processing_brief"] == "法语教材，保留公式顺序。"
    assert (
        queue.await_args.kwargs["request_id"] == "ba8a3e5c-c0b4-4a40-95ec-349310992445"
    )
    assert queue.await_args.kwargs["pause_after_chapter_analysis"] is False
    get_job.assert_awaited_once()
    resume.assert_awaited_once()


@pytest.mark.asyncio
async def test_parent_reads_book_pipeline_four_stage_progress(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    generation_job_id = uuid4()
    progress = {
        "job_id": generation_job_id,
        "status": "running",
        "stages": [
            {
                "name": "chapter_analysis",
                "label": "教材章节解析",
                "status": "completed",
                "current": 12,
                "total": 12,
                "events": [],
            },
            {
                "name": "content_processing",
                "label": "内容智能处理",
                "status": "running",
                "current": 2,
                "total": 12,
                "events": [],
            },
            {
                "name": "knowledge_point_generation",
                "label": "知识点生成",
                "status": "queued",
                "current": None,
                "total": None,
                "events": [],
            },
            {
                "name": "lesson_preparation",
                "label": "课程制作",
                "status": "queued",
                "current": None,
                "total": None,
                "events": [],
            },
        ],
        "last_sequence": 41,
        "truncated": True,
    }
    with patch(
        "src.server.app.education.textbooks.get_book_pipeline_progress_for_parent",
        new=AsyncMock(return_value=progress),
    ) as progress_call:
        response = await client.get(
            f"/api/v1/education/jobs/{generation_job_id}/progress"
        )

    assert response.status_code == 200
    payload = response.json()
    assert [stage["name"] for stage in payload["stages"]] == [
        "chapter_analysis",
        "content_processing",
        "knowledge_point_generation",
        "lesson_preparation",
    ]
    assert [stage["label"] for stage in payload["stages"]] == [
        "教材章节解析",
        "内容智能处理",
        "知识点生成",
        "课程制作",
    ]
    assert payload["last_sequence"] == 41
    assert payload["truncated"] is True
    progress_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_parent_streams_book_pipeline_progress_until_terminal(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    generation_job_id = uuid4()
    running = {
        "job_id": generation_job_id,
        "status": "running",
        "stages": [
            {
                "name": "chapter_analysis",
                "label": "教材章节解析",
                "status": "running",
                "current": None,
                "total": None,
                "events": [],
            }
        ],
        "last_sequence": 1,
        "_sse_cursor": "attempt-1:1",
    }
    completed = {
        **running,
        "status": "completed",
        "last_sequence": 2,
        "_sse_cursor": "attempt-2:2",
    }
    sleep = AsyncMock()
    with (
        patch(
            "src.server.app.education.textbooks.get_book_pipeline_progress_for_parent",
            new=AsyncMock(side_effect=[running, completed]),
        ) as progress_call,
        patch(
            "src.server.app.education.textbooks.asyncio.sleep",
            new=sleep,
        ),
    ):
        response = await client.get(
            f"/api/v1/education/jobs/{generation_job_id}/progress/stream",
            headers={"accept": "text/event-stream"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text.count("event: progress") == 2
    assert "id: attempt-1:1\nevent: progress" in response.text
    assert "id: attempt-2:2\nevent: progress" in response.text
    assert "_sse_cursor" not in response.text
    assert '"status":"running"' in response.text
    assert '"status":"completed"' in response.text
    assert progress_call.await_count == 2
    assert all(
        call.kwargs["include_sse_cursor"] is True
        for call in progress_call.await_args_list
    )
    sleep.assert_awaited_once_with(2.0)


@pytest.mark.asyncio
async def test_pause_checkpoint_request_is_accepted_and_launched(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    version_id = uuid4()
    queued = {
        "generation_job_id": str(uuid4()),
        "version_id": str(version_id),
        "scope": "book_pipeline",
        "structure_id": None,
        "knowledge_point_id": None,
        "status": "queued",
        "attempt_count": 0,
        "pause_after_chapter_analysis": True,
        "checkpoint_bundle_prefix": None,
        "error_code": None,
        "error_message": None,
        "created_at": None,
        "updated_at": None,
        "root_run_id": None,
        "started_at": None,
        "heartbeat_at": None,
        "reused_existing_job": False,
    }
    with patch(
        "src.server.app.education.textbooks.queue_and_launch_book_pipeline_for_parent",
        new=AsyncMock(return_value=queued),
    ) as queue_and_launch:
        response = await client.post(
            f"/api/v1/education/textbook-versions/{version_id}/book-pipeline-jobs",
            json={"pause_after_chapter_analysis": True},
        )

    assert response.status_code == 202
    assert response.json()["pause_after_chapter_analysis"] is True
    assert queue_and_launch.await_args.kwargs["pause_after_chapter_analysis"] is True


def test_book_pipeline_request_normalizes_optional_brief() -> None:
    request = CreateBookPipelineRequest(
        processing_brief="  这是一本法语教材；\r\n\t忽略教师指导页。  "
    )

    assert request.processing_brief == "这是一本法语教材；\r\n\t忽略教师指导页。"
    assert CreateBookPipelineRequest().processing_brief == ""
    assert CreateBookPipelineRequest().request_id is None


@pytest.mark.parametrize(
    "brief",
    [
        "bad\x00brief",
        "bad\x0bbreviation",
        "bad\x7fbrief",
        "\x85bad",
        "bad\x9bcontrol",
        "bad\x9f",
    ],
)
def test_book_pipeline_request_rejects_control_characters(brief: str) -> None:
    with pytest.raises(ValidationError):
        CreateBookPipelineRequest(processing_brief=brief)


def test_book_pipeline_request_rejects_more_than_4000_characters() -> None:
    with pytest.raises(ValidationError):
        CreateBookPipelineRequest(processing_brief="a" * 4_001)


@pytest.mark.asyncio
async def test_parent_reads_knowledge_point_source_preview(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    knowledge_point_id = uuid4()
    preview = {
        "knowledge_point_id": knowledge_point_id,
        "knowledge_point_title": "世界运动",
        "unit_id": uuid4(),
        "unit_title": "Unit 1: Sports and Fitness",
        "snippets": [
            {
                "source_id": "source-1",
                "source_title": "Reading Explorer",
                "start": 2,
                "end": 8,
                "quote": "Unit 1",
                "markdown": "# Unit 1\n\n正文内容",
                "truncated_before": False,
                "truncated_after": False,
            }
        ],
    }
    with patch(
        "src.server.app.education.textbooks.get_knowledge_point_source_preview",
        new=AsyncMock(return_value=preview),
    ) as source_preview:
        response = await client.get(
            f"/api/v1/education/knowledge-points/{knowledge_point_id}/source-preview"
        )

    assert response.status_code == 200
    assert response.json()["snippets"][0]["quote"] == "Unit 1"
    source_preview.assert_awaited_once()


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
    assert (
        structure_response.json()["units"][0]["knowledge_points"][0]["has_lesson"]
        is True
    )
    assert lesson_response.json()["content_markdown"] == "# 世界运动\n"
