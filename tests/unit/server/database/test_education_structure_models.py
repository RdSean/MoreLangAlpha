"""Persistence contracts for reviewable textbook structures."""

from contextlib import asynccontextmanager
from uuid import UUID

import pytest

from src.server.database import education_textbooks


@pytest.mark.asyncio
async def test_queue_structure_authorizes_parent_and_creates_generation_job(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"version_id": "version-1"},
        {"sequence": 1},
        {
            "structure_id": "structure-1",
            "version_id": "version-1",
            "sequence": 1,
            "status": "queued",
        },
        {
            "generation_job_id": "generation-1",
            "scope": "structure",
            "status": "queued",
        },
    ]

    result = await education_textbooks.queue_textbook_structure(
        parent_user_id="parent-1",
        content_version_id="version-1",
        processing_profile_id=None,
        processing_profile_sha256="a" * 64,
        input_manifest_sha256="b" * 64,
        source_revision="source-v1",
    )

    assert result is not None
    assert result["structure_id"] == "structure-1"
    assert result["generation_job_id"] == "generation-1"
    authorization_sql = mock_cursor.execute.call_args_list[0].args[0]
    assert "education_memberships" in authorization_sql
    assert "memberships.role = 'parent'" in authorization_sql
    job_sql = mock_cursor.execute.call_args_list[-1].args[0]
    assert "INSERT INTO education_generation_jobs" in job_sql
    assert "'structure'" in job_sql


@pytest.mark.asyncio
async def test_get_structure_returns_units_and_knowledge_points_for_parent(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = {
        "structure_id": "structure-1",
        "version_id": "version-1",
        "sequence": 1,
        "status": "review",
    }
    mock_cursor.fetchall.side_effect = [
        [
            {
                "unit_id": "unit-1",
                "position": 1,
                "slug": "unit-1",
                "title": "Unit 1",
                "unit_type": "teaching",
                "status": "review",
            }
        ],
        [
            {
                "knowledge_point_id": "kp-1",
                "unit_id": "unit-1",
                "position": 1,
                "slug": "world-game",
                "title": "世界运动",
                "status": "review",
            }
        ],
    ]

    result = await education_textbooks.get_textbook_structure_for_parent(
        parent_user_id="parent-1",
        structure_id="structure-1",
    )

    assert result is not None
    assert result["units"][0]["knowledge_points"][0]["knowledge_point_id"] == "kp-1"
    structure_sql = mock_cursor.execute.call_args_list[0].args[0]
    assert "education_textbook_structures" in structure_sql
    assert "memberships.role = 'parent'" in structure_sql


@pytest.mark.asyncio
async def test_replace_structure_contents_generates_service_owned_ids(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"structure_id": "structure-1"},
        {"unit_id": "unit-1"},
        {"knowledge_point_id": "kp-1"},
    ]

    result = await education_textbooks.replace_structure_contents(
        structure_id="structure-1",
        units=[
            {
                "position": 1,
                "slug": "unit-1",
                "title": "Unit 1",
                "summary": "",
                "unit_type": "teaching",
                "source_refs": [],
                "confidence": 0.9,
                "status": "review",
                "knowledge_points": [
                    {
                        "position": 1,
                        "slug": "world-game",
                        "title": "世界运动",
                        "summary": "",
                        "source_refs": [],
                        "confidence": 0.9,
                        "status": "review",
                    }
                ],
            }
        ],
    )

    UUID(result[0]["unit_id"])
    UUID(result[0]["knowledge_points"][0]["knowledge_point_id"])


@pytest.mark.asyncio
async def test_create_generation_job_requires_exactly_one_target(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)

    with pytest.raises(ValueError, match="exactly one target"):
        await education_textbooks.create_generation_job(
            version_id="version-1",
            scope="lesson",
            structure_id="structure-1",
            knowledge_point_id="kp-1",
            processing_profile_sha256="a" * 64,
        )

    mock_cursor.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_lesson_generation_job_persists_one_target(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = {
        "generation_job_id": "generation-lesson-1",
        "version_id": "version-1",
        "scope": "lesson",
        "knowledge_point_id": "kp-1",
        "status": "queued",
    }

    result = await education_textbooks.create_generation_job(
        version_id="version-1",
        scope="lesson",
        structure_id=None,
        knowledge_point_id="kp-1",
        processing_profile_sha256="a" * 64,
    )

    assert result["knowledge_point_id"] == "kp-1"
    insert_sql = mock_cursor.execute.call_args.args[0]
    assert "INSERT INTO education_generation_jobs" in insert_sql
    assert "scope" in insert_sql
    assert mock_cursor.execute.call_args.args[1][2] == "lesson"
