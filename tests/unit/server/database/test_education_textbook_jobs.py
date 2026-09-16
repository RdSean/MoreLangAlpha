"""Durable processing-job persistence contracts."""

from contextlib import asynccontextmanager

import pytest

from src.server.database import education_textbooks


@pytest.mark.asyncio
async def test_publishing_freezes_a_reviewed_teaching_package_for_its_content_version(
    mock_connection, mock_cursor, monkeypatch
):
    """A content version cannot publish arbitrary or unfinished teaching material."""

    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"version_id": "version-1"},
        {"status": "review"},
        {"count": 1},
        {"teaching_package_id": "package-1", "chapter_count": 1, "question_count": 1},
        {
            "publication_id": "publication-1",
            "version_id": "version-1",
            "teaching_package_id": "package-1",
            "published_by_user_id": "parent-1",
        },
    ]

    publication = await education_textbooks.publish_textbook_version(
        parent_user_id="parent-1",
        textbook_id="textbook-1",
        version_id="version-1",
        teaching_package_id="package-1",
    )

    assert publication["teaching_package_id"] == "package-1"
    package_lookup_sql = mock_cursor.execute.call_args_list[3].args[0]
    assert "packages.status = 'review'" in package_lookup_sql
    assert "packages.content_version_id = %s" in package_lookup_sql


@pytest.mark.asyncio
async def test_student_learning_reads_material_and_questions_from_publication_package(
    mock_connection, mock_cursor, monkeypatch
):
    """Student learning must use the immutable package selected by publication."""

    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = {
        "assignment_id": "assignment-1",
        "publication_id": "publication-1",
        "textbook_title": "英语第二册",
        "textbook_slug": "english-2",
        "version_sequence": 1,
    }
    mock_cursor.fetchall.side_effect = [
        [
            {
                "chapter_id": "chapter-1",
                "position": 1,
                "slug": "01-overview",
                "title": "导读",
                "markdown": "# 内容",
                "teaching_material": "# 教学包",
                "progress_status": "not_started",
            }
        ],
        [],
    ]

    learning = await education_textbooks.get_student_learning(
        student_user_id="student-1", assignment_id="assignment-1"
    )

    assert learning is not None
    chapter_sql = mock_cursor.execute.call_args_list[1].args[0]
    question_sql = mock_cursor.execute.call_args_list[2].args[0]
    assert "education_teaching_package_chapters" in chapter_sql
    assert "education_teaching_package_questions" in question_sql


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
async def test_queue_processing_from_completed_artifacts_freezes_safe_provenance(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"textbook_id": "textbook-1", "slug": "reading-explorer-3"},
        {"sequence": 3},
        {
            "job_id": "job-3",
            "version_id": "version-3",
            "status": "queued",
            "attempt_count": 0,
            "created_at": None,
        },
    ]
    mock_cursor.fetchall.return_value = [
        {
            "producer_job_id": "job-parse-2",
            "document_id": "doc-2",
            "primary_artifact_id": "art-2",
            "source_filename": "workbook.pdf",
            "source_media_type": "application/pdf",
            "source_format": "pdf",
            "parser_id": "datalab",
            "parser_name": "Datalab",
            "parser_version": "2",
            "parse_completed_at": None,
        },
        {
            "producer_job_id": "job-parse-1",
            "document_id": "doc-1",
            "primary_artifact_id": "art-1",
            "source_filename": "textbook.pdf",
            "source_media_type": "application/pdf",
            "source_format": "pdf",
            "parser_id": "datalab",
            "parser_name": "Datalab",
            "parser_version": "2",
            "parse_completed_at": None,
        },
    ]

    job = await education_textbooks.queue_textbook_processing_from_artifacts(
        parent_user_id="parent-1",
        household_id="household-1",
        textbook_id="textbook-1",
        sources=[
            {
                "document_id": "doc-1",
                "producer_job_id": "job-parse-1",
                "primary_artifact_id": "art-1",
                "primary_sha256": "a" * 64,
                "snapshot_prefix": "education/attacker/other/v99/source-bundles/99/",
            },
            {
                "document_id": "doc-2",
                "producer_job_id": "job-parse-2",
                "primary_artifact_id": "art-2",
                "primary_sha256": "b" * 64,
            },
        ],
        extractor_name="managed_ptc",
        extractor_version="1",
    )

    assert job is not None and job["status"] == "queued"
    lock_sql, lock_params = mock_cursor.execute.call_args_list[0].args
    assert "education_textbooks" in lock_sql
    assert "household_id = %s" in lock_sql
    assert "FOR UPDATE" in lock_sql
    assert lock_params == ("textbook-1", "household-1")

    parse_sql, parse_params = mock_cursor.execute.call_args_list[1].args
    assert "FROM document_parse_jobs AS jobs" in parse_sql
    assert "JOIN document_artifacts AS artifacts" in parse_sql
    assert "jobs.status = 'completed'" in parse_sql
    assert "artifacts.artifact_kind = 'primary_document'" in parse_sql
    assert "documents.owner_user_id = %s" in parse_sql
    assert parse_params == (
        ["job-parse-1", "job-parse-2"],
        "parent-1",
    )

    version_sql, version_params = mock_cursor.execute.call_args_list[3].args
    assert "INSERT INTO education_textbook_versions" in version_sql
    assert "'processing'" in version_sql
    assert version_params[1:3] == ("textbook-1", 3)

    source_sql, source_rows = mock_cursor.executemany.call_args.args
    assert "INSERT INTO education_textbook_artifact_sources" in source_sql
    assert [row[4] for row in source_rows] == [1, 2]
    assert len({row[0] for row in source_rows}) == 1
    assert source_rows[0][0] == version_params[0]
    assert source_rows[0][5:14] == (
        "textbook.pdf",
        "application/pdf",
        "pdf",
        "datalab",
        "Datalab",
        "2",
        None,
        "a" * 64,
        "education/household-1/reading-explorer-3/v3/source-bundles/01/",
    )
    assert source_rows[1][5] == "workbook.pdf"
    assert (
        source_rows[1][-1]
        == "education/household-1/reading-explorer-3/v3/source-bundles/02/"
    )

    queue_sql = mock_cursor.execute.call_args_list[4].args[0]
    assert "INSERT INTO education_processing_jobs" in queue_sql


@pytest.mark.asyncio
async def test_queue_processing_from_artifacts_rejects_unsafe_path_components(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    source = {
        "document_id": "doc-1",
        "producer_job_id": "job-parse-1",
        "primary_artifact_id": "art-1",
        "primary_sha256": "a" * 64,
    }

    with pytest.raises(ValueError, match="household_id"):
        await education_textbooks.queue_textbook_processing_from_artifacts(
            parent_user_id="parent-1",
            household_id="../other",
            textbook_id="textbook-1",
            sources=[source],
            extractor_name="managed_ptc",
            extractor_version="1",
        )

    mock_cursor.fetchone.side_effect = [
        {"textbook_id": "textbook-1", "slug": "../other"},
        {"sequence": 1},
    ]
    mock_cursor.fetchall.return_value = [
        {
            "producer_job_id": "job-parse-1",
            "document_id": "doc-1",
            "primary_artifact_id": "art-1",
            "source_filename": "textbook.pdf",
            "source_media_type": "application/pdf",
            "source_format": "pdf",
            "parser_id": "datalab",
            "parser_name": "Datalab",
            "parser_version": "2",
            "parse_completed_at": None,
        }
    ]

    with pytest.raises(ValueError, match="textbook slug"):
        await education_textbooks.queue_textbook_processing_from_artifacts(
            parent_user_id="parent-1",
            household_id="household-1",
            textbook_id="textbook-1",
            sources=[source],
            extractor_name="managed_ptc",
            extractor_version="1",
        )

    assert mock_cursor.executemany.await_count == 0


@pytest.mark.asyncio
async def test_queue_processing_from_artifacts_rejects_invalid_primary_sha256(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)

    with pytest.raises(ValueError, match="primary_sha256"):
        await education_textbooks.queue_textbook_processing_from_artifacts(
            parent_user_id="parent-1",
            household_id="household-1",
            textbook_id="textbook-1",
            sources=[
                {
                    "document_id": "doc-1",
                    "producer_job_id": "job-parse-1",
                    "primary_artifact_id": "art-1",
                    "primary_sha256": "not-a-sha",
                }
            ],
            extractor_name="managed_ptc",
            extractor_version="1",
        )

    assert mock_cursor.execute.await_count == 0


@pytest.mark.asyncio
async def test_queue_processing_from_artifacts_rejects_foreign_household(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = None

    job = await education_textbooks.queue_textbook_processing_from_artifacts(
        parent_user_id="parent-1",
        household_id="household-2",
        textbook_id="textbook-1",
        sources=[
            {
                "document_id": "doc-1",
                "producer_job_id": "job-parse-1",
                "primary_artifact_id": "art-1",
                "primary_sha256": "a" * 64,
            }
        ],
        extractor_name="managed_ptc",
        extractor_version="1",
    )

    assert job is None
    assert mock_cursor.execute.await_count == 1
    assert mock_cursor.executemany.await_count == 0


@pytest.mark.asyncio
async def test_queue_processing_from_artifacts_rejects_duplicate_parse_jobs(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    source = {
        "document_id": "doc-1",
        "producer_job_id": "job-parse-1",
        "primary_artifact_id": "art-1",
        "primary_sha256": "a" * 64,
    }

    with pytest.raises(ValueError, match="Duplicate producer_job_id"):
        await education_textbooks.queue_textbook_processing_from_artifacts(
            parent_user_id="parent-1",
            household_id="household-1",
            textbook_id="textbook-1",
            sources=[source, dict(source, position=2)],
            extractor_name="managed_ptc",
            extractor_version="1",
        )

    assert mock_cursor.execute.await_count == 0
    assert mock_cursor.executemany.await_count == 0


@pytest.mark.asyncio
async def test_processing_claim_reads_frozen_sources_without_live_joins(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"job_id": "job-1", "version_id": "version-1"},
        {"attempt_count": 1},
    ]
    mock_cursor.fetchall.return_value = [
        {
            "document_id": "doc-1",
            "producer_job_id": "job-parse-1",
            "primary_artifact_id": "art-1",
            "position": 1,
            "source_filename": "textbook.pdf",
            "source_media_type": "application/pdf",
            "source_format": "pdf",
            "parser_id": "datalab",
            "parser_name": "Datalab",
            "parser_version": "2",
            "parse_completed_at": None,
            "primary_sha256": "a" * 64,
            "snapshot_prefix": "education/household-1/textbook/v1/source-bundles/1/",
        }
    ]

    job = await education_textbooks.claim_textbook_processing_job(job_id="job-1")

    assert job is not None
    assert job["sources"] == mock_cursor.fetchall.return_value
    source_sql = mock_cursor.execute.call_args_list[2].args[0]
    assert "FROM education_textbook_artifact_sources AS sources" in source_sql
    assert "ORDER BY sources.position" in source_sql
    assert "JOIN documents" not in source_sql
    assert "JOIN document_parse_jobs" not in source_sql
    assert "source_filename" in source_sql
    assert "parser_name" in source_sql
    assert "snapshot_prefix" in source_sql


@pytest.mark.asyncio
async def test_processing_claim_falls_back_to_legacy_asset_sources(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"job_id": "job-1", "version_id": "version-1"},
        {"attempt_count": 1},
    ]
    legacy_source = {
        "asset_id": "asset-1",
        "storage_key": "education/household-1/source.pdf",
        "original_filename": "source.pdf",
        "content_type": "application/pdf",
        "size_bytes": 1024,
    }
    mock_cursor.fetchall.side_effect = [[], [legacy_source]]

    job = await education_textbooks.claim_textbook_processing_job(job_id="job-1")

    assert job is not None
    assert job["sources"] == [legacy_source]
    artifact_sql = mock_cursor.execute.call_args_list[2].args[0]
    legacy_sql = mock_cursor.execute.call_args_list[3].args[0]
    assert "education_textbook_artifact_sources" in artifact_sql
    assert "FROM education_textbook_sources AS sources" in legacy_sql


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
async def test_parent_claims_a_pending_or_legacy_terminal_verified_archive_stage(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = {
        "attempt_id": "attempt-1",
        "job_id": "job-1",
        "root_run_id": "run-1",
        "validated_assets": {"format": "langalpha-family-teaching-assets/v2"},
        "output_bundle": b"service-owned-stage",
        "output_bundle_sha256": "a" * 64,
    }

    stage = await education_textbooks.claim_teaching_archive_stage_for_parent(
        parent_user_id="parent-1", job_id="job-1"
    )

    assert stage is not None
    claim_sql = mock_cursor.execute.call_args_list[0].args[0]
    assert "education_teaching_archive_staging" in claim_sql
    assert "memberships.household_id = textbooks.household_id" in claim_sql
    assert "attempts.error_code = 'managed_archive_pending'" in claim_sql
    assert "managed_terminal_unprojected" in claim_sql
    assert "FOR UPDATE OF stages, attempts, jobs, packages" in claim_sql
    lease_sql = mock_cursor.execute.call_args_list[1].args[0]
    assert "UPDATE education_teaching_archive_staging" in lease_sql
    assert "created_at = NOW()" in lease_sql
    assert "SET status = 'running'" in mock_cursor.execute.call_args_list[2].args[0]
    assert "SET status = 'validating'" in mock_cursor.execute.call_args_list[3].args[0]


@pytest.mark.asyncio
async def test_archive_stage_is_written_only_from_the_active_validation_attempt(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"attempt_id": "attempt-1"},
        {"attempt_id": "attempt-1"},
    ]

    stored = await education_textbooks.store_teaching_archive_stage(
        attempt_id="attempt-1",
        job_id="job-1",
        root_run_id="run-1",
        validated_assets={"format": "langalpha-family-teaching-assets/v2"},
        output_bundle=b"validated-candidate",
        output_bundle_sha256="a" * 64,
    )

    assert stored is True
    fence_sql = mock_cursor.execute.call_args_list[0].args[0]
    insert_sql = mock_cursor.execute.call_args_list[1].args[0]
    assert "jobs.latest_attempt_id = attempts.attempt_id" in fence_sql
    assert "jobs.status = 'validating'" in fence_sql
    assert "education_teaching_archive_staging" in insert_sql
    assert "ON CONFLICT (attempt_id) DO NOTHING" in insert_sql


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
