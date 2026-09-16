"""Durable processing-job persistence contracts."""

from contextlib import asynccontextmanager
from hashlib import sha256

import pytest

from src.server.database import education_textbooks


@pytest.mark.asyncio
async def test_teaching_input_returns_artifact_backed_complete_sources_in_order(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    first_markdown = "# First complete source\n"
    second_markdown = "# Second complete source\n"
    mock_cursor.fetchone.return_value = {
        "content_version_id": "version-1",
        "content_version_sequence": 2,
        "household_id": "household-1",
        "slug": "english-2",
        "title": "英语第二册",
        "artifact_backed": True,
    }
    mock_cursor.fetchall.return_value = [
        {
            "content_chapter_id": "f5761267-11d1-4977-8107-e2671c99a2f0",
            "producer_job_id": "job-parse-1",
            "document_id": "doc-1",
            "position": 1,
            "slug": "reading-explorer",
            "title": "reading-explorer.pdf",
            "markdown": first_markdown,
            "snapshot_prefix": (
                "education/household-1/english-2/source-bundles/"
                "version-1/01/"
            ),
            "asset_manifest": [
                {
                    "artifact_id": "image-1",
                    "artifact_kind": "embedded_image",
                    "format": "png",
                    "media_type": "image/png",
                    "relative_path": "images/figure.png",
                    "sha256": "c" * 64,
                }
            ],
        },
        {
            "content_chapter_id": "8a77d086-0b23-4a1e-89d0-f163fa23d5d1",
            "producer_job_id": "job-parse-2",
            "document_id": "doc-2",
            "position": 2,
            "slug": "workbook",
            "title": "workbook.pdf",
            "markdown": second_markdown,
        },
    ]

    result = await education_textbooks.get_teaching_input_for_parent(
        parent_user_id="parent-1",
        content_version_id="version-1",
    )

    assert result is not None
    assert "chapters" not in result
    assert [source["position"] for source in result["sources"]] == [1, 2]
    assert [source["source_id"] for source in result["sources"]] == [
        "job-parse-1",
        "job-parse-2",
    ]
    assert [source["content_sha256"] for source in result["sources"]] == [
        sha256(first_markdown.encode()).hexdigest(),
        sha256(second_markdown.encode()).hexdigest(),
    ]
    assert result["sources"][0]["snapshot_prefix"].endswith("/01/")
    assert result["sources"][0]["asset_manifest"][0]["relative_path"] == (
        "images/figure.png"
    )
    source_sql = mock_cursor.execute.call_args_list[1].args[0]
    assert "education_textbook_artifact_sources" in source_sql
    assert "ORDER BY chapters.position" in source_sql


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
    version_id = "f5761267-11d1-4977-8107-e2671c99a2f0"
    job_id = "7bc1e58d-5a34-49d6-8c5c-70703e989bd4"
    mock_cursor.fetchone.side_effect = [
        {"textbook_id": "textbook-1", "slug": "reading-explorer-3"},
        {"sequence": 3},
        {
            "job_id": job_id,
            "version_id": version_id,
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
                "snapshot_prefix": (
                    "education/attacker/other/source-bundles/"
                    "f5761267-11d1-4977-8107-e2671c99a2f0/99/"
                ),
                "asset_manifest": [
                    {
                        "artifact_id": "image-1",
                        "artifact_kind": "embedded_image",
                        "format": "png",
                        "media_type": "image/png",
                        "relative_path": "images/figure.png",
                        "sha256": "c" * 64,
                    }
                ],
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
        version_id=version_id,
        job_id=job_id,
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
    assert version_params[0] == version_id
    assert version_params[1:3] == ("textbook-1", 3)

    source_sql, source_rows = mock_cursor.executemany.call_args.args
    assert "INSERT INTO education_textbook_artifact_sources" in source_sql
    assert "asset_manifest" in source_sql
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
        (
            "education/household-1/reading-explorer-3/source-bundles/"
            f"{version_id}/01/"
        ),
    )
    assert source_rows[1][5] == "workbook.pdf"
    assert (
        source_rows[1][13]
        == (
            "education/household-1/reading-explorer-3/source-bundles/"
            f"{version_id}/02/"
        )
    )
    assert source_rows[0][14].obj == [
        {
            "artifact_id": "image-1",
            "artifact_kind": "embedded_image",
            "format": "png",
            "media_type": "image/png",
            "relative_path": "images/figure.png",
            "sha256": "c" * 64,
        }
    ]
    assert source_rows[1][14].obj == []

    queue_sql, queue_params = mock_cursor.execute.call_args_list[4].args
    assert "INSERT INTO education_processing_jobs" in queue_sql
    assert queue_params == (job_id, version_id)


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

    with pytest.raises(
        education_textbooks.TextbookQueueValidationError, match="household_id"
    ):
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

    with pytest.raises(
        education_textbooks.TextbookQueueValidationError, match="textbook slug"
    ):
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

    with pytest.raises(
        education_textbooks.TextbookQueueValidationError, match="primary_sha256"
    ):
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

    with pytest.raises(
        education_textbooks.TextbookQueueValidationError, match="Textbook not found"
    ):
        await education_textbooks.queue_textbook_processing_from_artifacts(
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

    assert mock_cursor.execute.await_count == 1
    assert mock_cursor.executemany.await_count == 0


@pytest.mark.asyncio
async def test_queue_processing_from_artifacts_rejects_unavailable_source_ownership(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = {
        "textbook_id": "textbook-1",
        "slug": "reading-explorer-3",
    }
    mock_cursor.fetchall.return_value = []

    with pytest.raises(
        education_textbooks.TextbookQueueValidationError,
        match="unavailable or not owned",
    ):
        await education_textbooks.queue_textbook_processing_from_artifacts(
            parent_user_id="parent-1",
            household_id="household-1",
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

    assert mock_cursor.execute.await_count == 2
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

    with pytest.raises(
        education_textbooks.TextbookQueueValidationError,
        match="Duplicate producer_job_id",
    ):
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
            "snapshot_prefix": (
                "education/household-1/textbook/source-bundles/"
                "f5761267-11d1-4977-8107-e2671c99a2f0/01/"
            ),
            "asset_manifest": [
                {
                    "artifact_id": "image-1",
                    "artifact_kind": "embedded_image",
                    "format": "png",
                    "media_type": "image/png",
                    "relative_path": "images/figure.png",
                    "sha256": "b" * 64,
                }
            ],
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
    assert "asset_manifest" in source_sql


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


@pytest.mark.asyncio
async def test_completed_parse_job_candidates_are_safe_and_owner_scoped(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    completed = {
        "producer_job_id": "job-parse-1",
        "document_id": "doc-1",
        "primary_artifact_id": "art-1",
        "status": "completed",
        "owner_user_id": "parent-1",
        "filename": "textbook.pdf",
        "media_type": "application/pdf",
        "format": "pdf",
        "parser_id": "datalab",
        "parser_name": "Datalab",
        "parser_version": "2",
        "parse_completed_at": None,
        "size_bytes": 2048,
        "artifact_count": 4,
    }
    mock_cursor.fetchall.return_value = [
        completed,
        {**completed, "producer_job_id": "job-failed", "status": "failed"},
        {**completed, "producer_job_id": "job-queued", "status": "queued"},
        {**completed, "producer_job_id": "job-foreign", "owner_user_id": "parent-2"},
        {
            **completed,
            "producer_job_id": "job-no-artifact",
            "primary_artifact_id": None,
        },
    ]

    result = await education_textbooks.list_completed_parse_jobs_for_parent(
        parent_user_id="parent-1"
    )

    assert result == [
        {
            key: value
            for key, value in completed.items()
            if key not in {"status", "owner_user_id"}
        }
    ]
    sql, params = mock_cursor.execute.call_args.args
    assert "FROM document_parse_jobs AS jobs" in sql
    assert "JOIN document_artifacts AS primary_artifacts" in sql
    assert "jobs.status = 'completed'" in sql
    assert "documents.owner_user_id = %s" in sql
    assert "jobs.status," in sql
    assert "documents.owner_user_id," in sql
    assert "storage_key" not in sql
    assert params == ("parent-1",)


@pytest.mark.asyncio
async def test_parent_detail_projects_frozen_artifact_sources_without_storage_paths(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = {
        "textbook_id": "textbook-1",
        "household_id": "household-1",
        "title": "英语第二册",
        "slug": "english-2",
    }
    artifact_sources = [
        {
            "position": 1,
            "document_id": "doc-1",
            "producer_job_id": "job-parse-1",
            "primary_artifact_id": "art-1",
            "filename": "textbook.pdf",
            "media_type": "application/pdf",
            "format": "pdf",
            "parser_id": "datalab",
            "parser_name": "Datalab",
            "parser_version": "2",
            "parse_completed_at": None,
            "primary_sha256": "a" * 64,
            "document_deleted": False,
            "document_accessible": True,
            "legacy": False,
            "asset_id": None,
            "original_filename": None,
            "content_type": None,
            "size_bytes": None,
        },
        {
            "position": 2,
            "document_id": "doc-deleted",
            "producer_job_id": "job-parse-2",
            "primary_artifact_id": "art-2",
            "filename": "deleted.pdf",
            "media_type": "application/pdf",
            "format": "pdf",
            "parser_id": "datalab",
            "parser_name": "Datalab",
            "parser_version": "2",
            "parse_completed_at": None,
            "primary_sha256": "b" * 64,
            "document_deleted": True,
            "document_accessible": False,
            "legacy": False,
            "asset_id": None,
            "original_filename": None,
            "content_type": None,
            "size_bytes": None,
        },
    ]
    mock_cursor.fetchall.side_effect = [
        [
            {
                "version_id": "version-1",
                "sequence": 1,
                "status": "failed",
                "chapter_count": 0,
                "publication_id": None,
                "is_published": False,
            }
        ],
        artifact_sources,
        [],
        [],
    ]

    detail = await education_textbooks.get_textbook_for_parent(
        parent_user_id="parent-1", textbook_id="textbook-1"
    )

    assert detail is not None
    assert detail["versions"][0]["sources"] == artifact_sources
    source_sql = mock_cursor.execute.call_args_list[2].args[0]
    assert "education_textbook_artifact_sources" in source_sql
    assert "LEFT JOIN documents" in source_sql
    assert "documents.document_id IS NULL" in source_sql
    assert "documents.owner_user_id = %s" in source_sql
    assert "snapshot_prefix" not in source_sql
    assert "asset_manifest" not in source_sql
    assert "storage_key" not in source_sql
    assert mock_cursor.execute.call_args_list[2].args[1] == (
        "parent-1",
        "version-1",
        "version-1",
    )


@pytest.mark.asyncio
async def test_parent_detail_source_access_is_viewer_scoped_within_household(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    textbook = {
        "textbook_id": "textbook-1",
        "household_id": "household-1",
        "title": "英语第二册",
        "slug": "english-2",
    }
    version = {
        "version_id": "version-1",
        "sequence": 1,
        "status": "review",
        "chapter_count": 0,
        "publication_id": None,
        "is_published": False,
    }

    def source(*, accessible: bool) -> dict:
        return {
            "position": 1,
            "document_id": "doc-1",
            "producer_job_id": "job-parse-1",
            "primary_artifact_id": "art-1",
            "filename": "textbook.pdf",
            "media_type": "application/pdf",
            "format": "pdf",
            "parser_id": "datalab",
            "parser_name": "Datalab",
            "parser_version": "2",
            "parse_completed_at": None,
            "primary_sha256": "a" * 64,
            "document_deleted": False,
            "document_accessible": accessible,
            "legacy": False,
            "asset_id": None,
            "original_filename": None,
            "content_type": None,
            "size_bytes": None,
        }

    mock_cursor.fetchone.return_value = textbook
    mock_cursor.fetchall.side_effect = [
        [version],
        [source(accessible=True)],
        [],
        [],
        [version],
        [source(accessible=False)],
        [],
        [],
    ]

    owner_detail = await education_textbooks.get_textbook_for_parent(
        parent_user_id="parent-owner", textbook_id="textbook-1"
    )
    other_parent_detail = await education_textbooks.get_textbook_for_parent(
        parent_user_id="parent-other", textbook_id="textbook-1"
    )

    assert owner_detail is not None
    assert other_parent_detail is not None
    assert owner_detail["versions"][0]["sources"][0]["document_accessible"] is True
    assert other_parent_detail["versions"][0]["sources"][0]["document_accessible"] is False
    source_calls = [
        call
        for call in mock_cursor.execute.call_args_list
        if "FROM education_textbook_artifact_sources" in call.args[0]
    ]
    assert [call.args[1] for call in source_calls] == [
        ("parent-owner", "version-1", "version-1"),
        ("parent-other", "version-1", "version-1"),
    ]
