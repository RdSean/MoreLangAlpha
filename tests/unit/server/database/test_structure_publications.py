"""Persistence contracts for structure-backed textbook publications."""

from contextlib import asynccontextmanager

import pytest

from src.server.database import education_textbooks


@pytest.mark.asyncio
async def test_publish_structure_requires_every_kp_to_have_approved_lesson(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"version_id": "version-1", "structure_id": "structure-1"},
        {"count": 2},
        {"count": 1},
    ]

    published = await education_textbooks.publish_textbook_structure(
        parent_user_id="parent-1",
        version_id="version-1",
        structure_id="structure-1",
    )

    assert published is None
    count_sql = mock_cursor.execute.call_args_list[-1].args[0]
    assert "lessons.status = 'approved'" in count_sql


@pytest.mark.asyncio
async def test_publish_structure_freezes_lesson_revisions(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"version_id": "version-1", "structure_id": "structure-1"},
        {"count": 1},
        {"count": 1},
        {
            "publication_id": "publication-1",
            "version_id": "version-1",
            "structure_id": "structure-1",
        },
    ]
    mock_cursor.fetchall.return_value = [
        {
            "knowledge_point_id": "kp-1",
            "lesson_revision_id": "revision-1",
        }
    ]

    published = await education_textbooks.publish_textbook_structure(
        parent_user_id="parent-1",
        version_id="version-1",
        structure_id="structure-1",
    )

    assert published["publication_id"] == "publication-1"
    insert_sqls = [
        call.args[0] for call in mock_cursor.execute.call_args_list
    ]
    assert any(
        "INSERT INTO education_publication_kp_lessons" in sql
        for sql in insert_sqls
    )
