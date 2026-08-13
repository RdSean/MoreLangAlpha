"""Durable processing-job persistence contracts."""

from contextlib import asynccontextmanager

import pytest

from src.server.database import education_textbooks


@pytest.mark.asyncio
async def test_retry_reclaims_only_an_expired_processing_lease(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = {
        "job_id": "job-1",
        "version_id": "version-1",
        "status": "queued",
        "attempt_count": 2,
        "created_at": None,
    }

    job = await education_textbooks.retry_textbook_processing_job(
        parent_user_id="parent-1", job_id="job-1"
    )

    assert job["status"] == "queued"
    retry_sql = mock_cursor.execute.call_args_list[0].args[0]
    assert "jobs.status = 'processing'" in retry_sql
    assert "jobs.claim_expires_at <= NOW()" in retry_sql


@pytest.mark.asyncio
async def test_student_assignment_queries_scope_membership_to_the_textbook_household(
    mock_connection, mock_cursor, monkeypatch
):
    """A student membership in another household must never authorize an assignment."""

    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    operations = [
        lambda: education_textbooks.list_student_assignments("student-1"),
        lambda: education_textbooks.get_student_learning(
            student_user_id="student-1", assignment_id="assignment-1"
        ),
        lambda: education_textbooks.get_student_chapter_context_record(
            student_user_id="student-1",
            assignment_id="assignment-1",
            chapter_id="chapter-1",
        ),
        lambda: education_textbooks.update_student_progress(
            student_user_id="student-1",
            assignment_id="assignment-1",
            chapter_id="chapter-1",
            status="learning",
        ),
        lambda: education_textbooks.submit_student_answer(
            student_user_id="student-1",
            assignment_id="assignment-1",
            question_id="question-1",
            selected_option="A",
        ),
        lambda: education_textbooks.get_student_learning_space(
            student_user_id="student-1", assignment_id="assignment-1"
        ),
        lambda: education_textbooks.get_student_learning_space_for_thread(
            student_user_id="student-1", conversation_thread_id="thread-1"
        ),
    ]

    for make_operation in operations:
        mock_cursor.execute.reset_mock()
        await make_operation()
        sql = mock_cursor.execute.call_args.args[0]
        assert "memberships.household_id = textbooks.household_id" in sql


@pytest.mark.asyncio
async def test_processing_claim_returns_an_attempt_fence(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = {
        "job_id": "job-1",
        "version_id": "version-1",
        "attempt_count": 0,
    }

    await education_textbooks.claim_textbook_processing_job(job_id="job-1")

    update_sql = mock_cursor.execute.call_args_list[1].args[0]
    assert "RETURNING attempt_count" in update_sql


@pytest.mark.asyncio
async def test_processing_completion_is_fenced_to_its_claimed_attempt(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    await education_textbooks.complete_textbook_processing_job(
        job_id="job-1",
        version_id="version-1",
        attempt_count=2,
        bundle_prefix="education/household-1/textbook/v1",
        extractor={"name": "local_pypdf", "version": "1"},
        chapters=[],
    )

    claim_sql = mock_cursor.execute.call_args_list[0].args[0]
    settle_sql = mock_cursor.execute.call_args_list[-1].args[0]
    assert "attempt_count = %s" in claim_sql
    assert "attempt_count = %s" in settle_sql


@pytest.mark.asyncio
async def test_published_textbook_detail_reads_assignment_names_from_household_memberships(
    mock_connection, mock_cursor, monkeypatch
):
    """Published parent detail must not depend on the removed auth_accounts table."""

    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = {
        "textbook_id": "textbook-1",
        "household_id": "household-1",
        "title": "英语第二册",
        "slug": "english-2",
        "created_by_user_id": "parent-1",
        "created_at": None,
    }
    mock_cursor.fetchall.side_effect = [
        [
            {
                "version_id": "version-1",
                "publication_id": "publication-1",
                "status": "published",
            }
        ],
        [],
        [],
        [
            {
                "assignment_id": "assignment-1",
                "student_user_id": "student-1",
                "student_name": "小林",
                "created_at": None,
            }
        ],
    ]

    detail = await education_textbooks.get_textbook_for_parent(
        parent_user_id="parent-1", textbook_id="textbook-1"
    )

    assignment_sql = mock_cursor.execute.call_args_list[-1].args[0]
    assert "education_memberships AS student_memberships" in assignment_sql
    assert "student_memberships.display_name AS student_name" in assignment_sql
    assert "student_memberships.household_id = %s" in assignment_sql
    assert "auth_accounts" not in assignment_sql
    assert detail["versions"][0]["assignments"] == [
        {
            "assignment_id": "assignment-1",
            "student_user_id": "student-1",
            "student_name": "小林",
            "created_at": None,
        }
    ]
