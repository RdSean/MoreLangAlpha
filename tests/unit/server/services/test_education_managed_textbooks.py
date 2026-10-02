"""Managed textbook facade contracts over the new more-to-skills tables."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from src.server.app.education.book_models import BookJobCreateRequest
from src.server.services import education_textbooks as textbooks


TEXTBOOK_ID = UUID("bc5734a8-8a30-459f-a1f3-8551feb4c169")
HOUSEHOLD_ID = UUID("6eebf7fb-9579-4c5d-825a-2e595b7f1b18")
KNOWLEDGE_POINT_ID = UUID("4c3f4d0c-a508-4bff-a89f-a3a584a2fe86")


@pytest.mark.asyncio
async def test_create_managed_textbook_freezes_identity_and_household(monkeypatch):
    identity = SimpleNamespace(
        version="1.0.0",
        skill_sha256="a" * 64,
        schema_sha256="b" * 64,
    )
    create = AsyncMock(
        return_value={
            "textbook_id": TEXTBOOK_ID,
            "job_id": UUID("9998bb1a-687a-4d45-815d-5b1dd6ed2f17"),
            "item_id": UUID("86f03a73-7604-4097-905b-768e6ad0f644"),
        }
    )
    monkeypatch.setattr(
        textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": HOUSEHOLD_ID}),
    )
    monkeypatch.setattr(
        textbooks, "get_more_to_skills_identity", lambda: identity, raising=False
    )
    monkeypatch.setattr(
        textbooks,
        "create_textbook_from_library_source",
        create,
        raising=False,
    )

    result = await textbooks.create_managed_textbook(
        parent_user_id="parent-1",
        parse_job_id="job-A1b2C3d4E5f6",
        primary_artifact_id="art-A1b2C3d4E5f6",
        title="  英语第二册  ",
        idempotency_key="create-english-2",
    )

    assert result == {
        "textbook_id": str(TEXTBOOK_ID),
        "job_id": "9998bb1a-687a-4d45-815d-5b1dd6ed2f17",
    }
    assert create.await_args.kwargs["household_id"] == str(HOUSEHOLD_ID)
    assert create.await_args.kwargs["title"] == "英语第二册"
    assert create.await_args.kwargs["identity"] is identity
    assert create.await_args.kwargs["slug"].startswith("textbook-")


@pytest.mark.asyncio
async def test_source_slice_reads_verified_frozen_markdown(monkeypatch):
    prefix = f"education/{HOUSEHOLD_ID}/textbooks/{TEXTBOOK_ID}/source/"
    markdown = b"first\nsecond ![Figure](images/figure.png)\nthird\nfourth\n"
    source = {
        "textbook_id": TEXTBOOK_ID,
        "source_snapshot_prefix": prefix,
        "source_markdown_key": f"{prefix}artifacts/document.md",
        "source_content_sha256": "a" * 64,
        "source_size_bytes": len(markdown),
        "source_asset_manifest": [
            {
                "artifact_id": "art-I1m2A3g4E5f6",
                "artifact_kind": "embedded_image",
                "format": "png",
                "media_type": "image/png",
                "relative_path": "images/figure.png",
                "sha256": "d" * 64,
            }
        ],
    }
    read = AsyncMock(return_value=(markdown, source["source_markdown_key"]))
    monkeypatch.setattr(
        textbooks,
        "get_managed_source_for_parent",
        AsyncMock(return_value=source),
        raising=False,
    )
    monkeypatch.setattr(textbooks, "read_snapshot_artifact_bytes", read, raising=False)

    result = await textbooks.get_managed_textbook_source(
        parent_user_id="parent-1",
        textbook_id=TEXTBOOK_ID,
        start_line=2,
        end_line=99,
    )

    assert result == {
        "textbook_id": str(TEXTBOOK_ID),
        "start_line": 2,
        "end_line": 4,
        "total_lines": 4,
        "markdown": (
            "second ![Figure](/api/v1/education/textbooks/"
            f"{TEXTBOOK_ID}/assets/art-I1m2A3g4E5f6)\nthird\nfourth"
        ),
    }
    read.assert_awaited_once_with(
        snapshot_prefix=prefix,
        relative_path="artifacts/document.md",
        expected_sha256="a" * 64,
        max_bytes=len(markdown),
    )


@pytest.mark.asyncio
async def test_structure_projects_only_current_material_pointers(monkeypatch):
    raw = {
        "textbook_id": TEXTBOOK_ID,
        "structure_id": UUID("0cf0c918-23dc-44a2-8ad7-6a8788279f3e"),
        "schema_version": "1.0.0",
        "structure_json": {
            "schema_version": "1.0.0",
            "nodes": [],
            "knowledge_points": [
                {"id": "unit-1-k1", "title": "Old", "content_file": "stale.md"}
            ],
        },
        "validation_warnings": [],
        "knowledge_points": [
            {
                "knowledge_point_id": KNOWLEDGE_POINT_ID,
                "skill_kp_id": "unit-1-k1",
                "position": 1,
                "title": "Vocabulary",
                "unit_skill_node_id": None,
                "node_skill_ids": ["unit-1"],
                "start_line": 2,
                "end_line": 4,
                "content_key": "education/current.md",
            }
        ],
    }
    monkeypatch.setattr(
        textbooks,
        "get_managed_structure_for_parent",
        AsyncMock(return_value=raw),
        raising=False,
    )

    result = await textbooks.get_managed_textbook_structure(
        parent_user_id="parent-1", textbook_id=TEXTBOOK_ID
    )

    expected_path = f"materials/{KNOWLEDGE_POINT_ID}.md"
    assert result["structure"]["knowledge_points"][0]["content_file"] == expected_path
    assert result["knowledge_points"][0]["content_file"] == expected_path
    assert result["knowledge_points"][0]["material_available"] is True
    assert "content_key" not in result["knowledge_points"][0]


@pytest.mark.asyncio
async def test_material_read_uses_authorized_current_pointer(monkeypatch):
    now = datetime.now(timezone.utc)
    markdown = b"# Lesson\n\n![Figure](images/figure.png)"
    material = {
        "textbook_id": TEXTBOOK_ID,
        "household_id": HOUSEHOLD_ID,
        "knowledge_point_id": KNOWLEDGE_POINT_ID,
        "skill_kp_id": "unit-1-k1",
        "content_key": (
            f"education/{HOUSEHOLD_ID}/textbooks/{TEXTBOOK_ID}/materials/"
            f"{KNOWLEDGE_POINT_ID}/attempts/2b72201a-e369-49d4-8878-47bbf2bd9cf8/"
            f"{'c' * 64}.md"
        ),
        "content_sha256": "c" * 64,
        "size_bytes": len(markdown),
        "depth": "lesson",
        "requirements": None,
        "updated_at": now,
        "source_asset_manifest": [
            {
                "artifact_id": "art-I1m2A3g4E5f6",
                "artifact_kind": "embedded_image",
                "format": "png",
                "media_type": "image/png",
                "relative_path": "images/figure.png",
                "sha256": "d" * 64,
            }
        ],
    }
    read = AsyncMock(return_value=markdown)
    monkeypatch.setattr(
        textbooks,
        "get_managed_material_for_parent",
        AsyncMock(return_value=material),
        raising=False,
    )
    monkeypatch.setattr(textbooks, "read_material_bytes", read, raising=False)

    result = await textbooks.get_managed_knowledge_point_material(
        parent_user_id="parent-1",
        textbook_id=TEXTBOOK_ID,
        knowledge_point_id=KNOWLEDGE_POINT_ID,
    )

    assert result["markdown"] == (
        "# Lesson\n\n![Figure](/api/v1/education/textbooks/"
        f"{TEXTBOOK_ID}/assets/art-I1m2A3g4E5f6)"
    )
    assert result["material_available"] is True
    assert "content_key" not in result
    read.assert_awaited_once_with(
        household_id=HOUSEHOLD_ID,
        textbook_id=TEXTBOOK_ID,
        knowledge_point_id=KNOWLEDGE_POINT_ID,
        content_key=material["content_key"],
        expected_sha256="c" * 64,
        expected_size=len(markdown),
    )


@pytest.mark.asyncio
async def test_asset_read_resolves_only_database_manifest_entry(monkeypatch):
    prefix = f"education/{HOUSEHOLD_ID}/textbooks/{TEXTBOOK_ID}/source/"
    asset = {
        "textbook_id": TEXTBOOK_ID,
        "source_snapshot_prefix": prefix,
        "manifest_entry": {
            "artifact_id": "art-I1m2A3g4E5f6",
            "artifact_kind": "embedded_image",
            "format": "png",
            "media_type": "image/png",
            "relative_path": "images/figure.png",
            "sha256": "d" * 64,
        },
    }
    read = AsyncMock(
        return_value=(b"png-bytes", f"{prefix}artifacts/images/figure.png")
    )
    lookup = AsyncMock(return_value=asset)
    monkeypatch.setattr(
        textbooks, "get_managed_asset_for_parent", lookup, raising=False
    )
    monkeypatch.setattr(textbooks, "read_snapshot_artifact_bytes", read, raising=False)

    result = await textbooks.open_managed_textbook_asset(
        parent_user_id="parent-1",
        textbook_id=TEXTBOOK_ID,
        asset_id="art-I1m2A3g4E5f6",
    )

    assert result == {
        "content": b"png-bytes",
        "media_type": "image/png",
        "sha256": "d" * 64,
    }
    lookup.assert_awaited_once_with(
        parent_user_id="parent-1",
        textbook_id=TEXTBOOK_ID,
        asset_id="art-I1m2A3g4E5f6",
    )
    read.assert_awaited_once_with(
        snapshot_prefix=prefix,
        relative_path="images/figure.png",
        expected_sha256="d" * 64,
        max_bytes=textbooks.get_document_parsing_config().max_upload_bytes,
    )


def _job_snapshot(*, job_id: UUID | None = None) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "job_id": str(job_id or UUID("9998bb1a-687a-4d45-815d-5b1dd6ed2f17")),
        "textbook_id": str(TEXTBOOK_ID),
        "kind": "materials",
        "status": "queued",
        "total_items": 1,
        "succeeded_items": 0,
        "failed_items": 0,
        "cancelled_items": 0,
        "not_run_items": 0,
        "high_water_seq": 0,
        "activity_status": "available",
        "created_at": now,
        "started_at": None,
        "finished_at": None,
        "safe_error": None,
        "depth": "lesson",
        "requirements": None,
        "replace_existing": False,
        "include_supplementary": False,
        "items": [],
    }


@pytest.mark.asyncio
async def test_create_managed_material_job_freezes_current_identity(monkeypatch):
    identity = SimpleNamespace(
        version="1.0.0",
        skill_sha256="a" * 64,
        schema_sha256="b" * 64,
    )
    job_id = UUID("9998bb1a-687a-4d45-815d-5b1dd6ed2f17")
    create = AsyncMock(return_value={"job_id": job_id})
    read = AsyncMock(return_value=_job_snapshot(job_id=job_id))
    monkeypatch.setattr(
        textbooks,
        "get_managed_textbook_for_parent",
        AsyncMock(return_value={"textbook_id": TEXTBOOK_ID}),
    )
    monkeypatch.setattr(textbooks, "create_materials_job", create, raising=False)
    monkeypatch.setattr(textbooks, "get_book_job_for_parent", read, raising=False)
    monkeypatch.setattr(textbooks, "get_more_to_skills_identity", lambda: identity)
    request = BookJobCreateRequest(
        kind="materials",
        knowledge_point_ids=[KNOWLEDGE_POINT_ID],
        depth="lesson",
        requirements=None,
        replace_existing=False,
        include_supplementary=False,
        idempotency_key="materials-1",
    )

    result = await textbooks.create_managed_textbook_job(
        parent_user_id="parent-1",
        textbook_id=TEXTBOOK_ID,
        request=request,
    )

    assert result["job_id"] == str(job_id)
    assert create.await_args.kwargs["identity"] is identity
    assert create.await_args.kwargs["knowledge_point_ids"] == [KNOWLEDGE_POINT_ID]
    read.assert_awaited_once_with(
        job_id=job_id,
        parent_user_id="parent-1",
    )


@pytest.mark.asyncio
async def test_cancel_managed_job_checks_parent_acl_before_runtime_cancel(monkeypatch):
    cancel = AsyncMock()
    monkeypatch.setattr(
        textbooks,
        "get_book_job_for_parent",
        AsyncMock(return_value=None),
        raising=False,
    )
    monkeypatch.setattr(textbooks, "cancel_book_job", cancel, raising=False)

    with pytest.raises(textbooks.TextbookNotFoundError, match="Book job not found"):
        await textbooks.cancel_managed_textbook_job(
            parent_user_id="other-user",
            job_id=UUID("9998bb1a-687a-4d45-815d-5b1dd6ed2f17"),
        )

    cancel.assert_not_awaited()


@pytest.mark.asyncio
async def test_retry_managed_job_uses_source_job_as_idempotency_scope(monkeypatch):
    source_job_id = UUID("9998bb1a-687a-4d45-815d-5b1dd6ed2f17")
    new_job_id = UUID("e8805482-3021-4035-8c7d-fb8c2b1ebf31")
    source = _job_snapshot(job_id=source_job_id)
    retried = _job_snapshot(job_id=new_job_id)
    read = AsyncMock(side_effect=[source, retried])
    retry = AsyncMock(return_value={"job_id": new_job_id})
    monkeypatch.setattr(textbooks, "get_book_job_for_parent", read, raising=False)
    monkeypatch.setattr(textbooks, "retry_book_job", retry, raising=False)

    result = await textbooks.retry_managed_textbook_job(
        parent_user_id="parent-1", job_id=source_job_id
    )

    assert result["job_id"] == str(new_job_id)
    assert retry.await_args.kwargs["idempotency_key"] == f"retry:{source_job_id}"
