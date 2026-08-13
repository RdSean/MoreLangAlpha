"""Durable teaching-package persistence contracts."""

from contextlib import asynccontextmanager

import pytest

from src.server.database import education_textbooks


@pytest.mark.asyncio
async def test_queue_teaching_package_freezes_a_parent_reviewable_content_version(
    mock_connection, mock_cursor, monkeypatch
):
    """Only a parent may queue a package for a content version ready for teaching."""

    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    mock_cursor.fetchone.side_effect = [
        {"version_id": "version-1", "household_id": "household-1"},
        {"sequence": 1},
        {
            "teaching_package_id": "package-1",
            "content_version_id": "version-1",
            "status": "queued",
            "sequence": 1,
        },
        {"job_id": "job-1", "teaching_package_id": "package-1", "status": "queued"},
    ]
    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    monkeypatch.setattr(education_textbooks, "uuid4", lambda: "generated-id")

    package = await education_textbooks.queue_teaching_package(
        parent_user_id="parent-1",
        content_version_id="version-1",
        hashes=education_textbooks.TeachingInputHashes(
            input_manifest_sha256="a" * 64,
            book_to_skill_sha256="b" * 64,
            knowledge_guy_sha256="c" * 64,
            adapter_prompt_sha256="d" * 64,
        ),
    )

    assert package == {
        "teaching_package_id": "package-1",
        "content_version_id": "version-1",
        "status": "queued",
        "sequence": 1,
        "job_id": "job-1",
    }
    version_lookup_sql = mock_cursor.execute.call_args_list[0].args[0]
    assert "memberships.role = 'parent'" in version_lookup_sql
    assert "versions.status = 'review'" in version_lookup_sql


@pytest.mark.asyncio
async def test_creating_teaching_attempt_binds_one_root_ptc_run_and_previous_attempt(
    mock_connection, mock_cursor, monkeypatch
):
    """A job attempt has explicit root-run and retry-chain identity."""

    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    mock_cursor.fetchone.side_effect = [
        {
            "job_id": "job-1",
            "teaching_package_id": "package-1",
            "attempt_count": 1,
            "previous_attempt_id": "attempt-1",
        },
        {
            "attempt_id": "attempt-2",
            "job_id": "job-1",
            "managed_workspace_id": "workspace-1",
            "managed_thread_id": "thread-1",
            "previous_attempt_id": "attempt-1",
        },
    ]
    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    monkeypatch.setattr(education_textbooks, "uuid4", lambda: "generated-id")

    attempt = await education_textbooks.create_teaching_attempt(
        job_id="job-1",
        managed_workspace_id="workspace-1",
        managed_thread_id="thread-1",
    )

    assert attempt["previous_attempt_id"] == "attempt-1"
    attempt_insert_sql = mock_cursor.execute.call_args_list[1].args[0]
    assert "previous_attempt_id" in attempt_insert_sql
    assert "root_run_id" in attempt_insert_sql


@pytest.mark.asyncio
async def test_parent_detail_selects_safe_teaching_package_projection(
    mock_connection, mock_cursor, monkeypatch
):
    """Teaching package summaries remain household-scoped and never select object keys."""

    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    mock_cursor.fetchone.side_effect = [
        {
            "textbook_id": "textbook-1",
            "household_id": "household-1",
            "title": "英语第二册",
            "slug": "english-2",
        }
    ]
    mock_cursor.fetchall.side_effect = [
        [
            {
                "version_id": "version-1",
                "sequence": 1,
                "status": "review",
                "chapter_count": 1,
                "publication_id": None,
                "is_published": False,
            }
        ],
        [],
        [],
        [
            {
                "teaching_package_id": "package-1",
                "sequence": 1,
                "status": "review",
                "chapter_count": 1,
                "question_count": 1,
            }
        ],
    ]
    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)

    detail = await education_textbooks.get_textbook_for_parent(
        parent_user_id="parent-1", textbook_id="textbook-1"
    )

    assert detail is not None
    assert detail["versions"][0]["teaching_packages"] == [
        {
            "teaching_package_id": "package-1",
            "sequence": 1,
            "status": "review",
            "chapter_count": 1,
            "question_count": 1,
        }
    ]
    package_select_sql = mock_cursor.execute.call_args_list[-1].args[0]
    assert "storage_key" not in package_select_sql
    assert "education_teaching_packages" in package_select_sql
