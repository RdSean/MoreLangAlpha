"""Persistence contracts for versioned textbook processing profiles."""

from contextlib import asynccontextmanager

import pytest

from src.server.database import education_textbooks


@pytest.mark.asyncio
async def test_create_processing_profile_is_parent_and_version_scoped(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"version_id": "version-1", "household_id": "household-1"},
        {"version": 2},
        {
            "profile_id": "profile-2",
            "version_id": "version-1",
            "version": 2,
        },
    ]

    profile = await education_textbooks.create_processing_profile(
        parent_user_id="parent-1",
        version_id="version-1",
        subject="english",
        grade_band="middle",
        language="zh-CN",
        depth="standard",
        question_types=["choice", "fill"],
        prompt_fragment="",
        allowed_skills=["book-to-skill"],
        profile_sha256="a" * 64,
    )

    assert profile["profile_id"] == "profile-2"
    sql = mock_cursor.execute.call_args_list[0].args[0]
    assert "memberships.role = 'parent'" in sql


@pytest.mark.asyncio
async def test_get_processing_profile_requires_parent(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = None

    result = await education_textbooks.get_processing_profile_for_parent(
        parent_user_id="parent-1",
        profile_id="profile-1",
    )

    assert result is None
