"""Persistence contracts for reviewable textbook structures."""

from contextlib import asynccontextmanager
from uuid import UUID

import pytest

from src.server.database import education_textbooks

CHECKPOINT_PREFIX = (
    "education/household/textbook/v1/book-pipeline-checkpoints/"
    "4d0112f8-0e00-4f1f-990a-4bc1b1cc20f3/"
    "6f3f2de2-5c58-4bc2-84bc-95e97acd37f6"
)


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
        None,
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
    authorization_sql = next(
        call.args[0]
        for call in mock_cursor.execute.call_args_list
        if "education_memberships" in call.args[0]
    )
    assert "education_memberships" in authorization_sql
    assert "memberships.role = 'parent'" in authorization_sql
    job_sql = mock_cursor.execute.call_args_list[-1].args[0]
    assert "INSERT INTO education_generation_jobs" in job_sql
    assert "'structure'" in job_sql


@pytest.mark.asyncio
async def test_queue_structure_reuses_active_job_without_inserting_another(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"version_id": "version-1"},
        {
            "generation_job_id": "generation-existing",
            "version_id": "version-1",
            "scope": "structure",
            "structure_id": "structure-existing",
            "status": "running",
            "attempt_count": 1,
            "structure_sequence": 2,
            "structure_status": "running",
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
    assert result["generation_job_id"] == "generation-existing"
    assert result["status"] == "running"
    executed = "\n".join(call.args[0] for call in mock_cursor.execute.call_args_list)
    assert "pg_advisory_xact_lock" in executed
    assert "INSERT INTO education_textbook_structures" not in executed
    assert "INSERT INTO education_generation_jobs" not in executed


@pytest.mark.asyncio
async def test_get_structure_returns_units_and_knowledge_points_for_parent(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {
            "structure_id": "structure-1",
            "version_id": "version-1",
            "sequence": 1,
            "status": "review",
        },
        {"total": 1, "accepted": 0, "generated": 0, "approved": 0},
        {
            "generation_job_id": "generation-1",
            "status": "review",
            "attempt_count": 1,
            "error_message": None,
            "created_at": None,
            "updated_at": None,
            "root_run_id": None,
            "started_at": None,
            "heartbeat_at": None,
        },
    ]
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
                "unit_id": "unit-1",
                "slot": "reading_a",
                "title": "The World's Game",
                "summary": "Reading summary",
                "reading_skill": "Analyzing Infographics",
                "vocabulary_building": "Prefix uni-",
                "critical_thinking": "Evaluating Evidence",
                "source_id": "source-1",
                "line_start": 10,
                "line_end": 40,
                "char_start": 100,
                "char_end": 900,
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
                "lesson_status": "approved",
                "lesson_revision_id": "revision-1",
            }
        ],
    ]

    result = await education_textbooks.get_textbook_structure_for_parent(
        parent_user_id="parent-1",
        structure_id="structure-1",
    )

    assert result is not None
    assert result["units"][0]["knowledge_points"][0]["knowledge_point_id"] == "kp-1"
    assert result["units"][0]["knowledge_points"][0]["lesson_status"] == "approved"
    assert (
        result["units"][0]["knowledge_points"][0]["lesson_revision_id"] == "revision-1"
    )
    assert result["units"][0]["scopes"] == [
        {
            "unit_id": "unit-1",
            "slot": "reading_a",
            "title": "The World's Game",
            "summary": "Reading summary",
            "reading_skill": "Analyzing Infographics",
            "vocabulary_building": "Prefix uni-",
            "critical_thinking": "Evaluating Evidence",
            "source_id": "source-1",
            "line_start": 10,
            "line_end": 40,
            "char_start": 100,
            "char_end": 900,
            "verified": True,
        }
    ]
    structure_sql = mock_cursor.execute.call_args_list[0].args[0]
    assert "education_textbook_structures" in structure_sql
    assert "memberships.role = 'parent'" in structure_sql
    knowledge_point_sql = next(
        call.args[0]
        for call in mock_cursor.execute.call_args_list
        if "LEFT JOIN education_kp_lessons AS lessons" in call.args[0]
    )
    assert "LEFT JOIN education_kp_lessons AS lessons" in knowledge_point_sql


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
async def test_replace_structure_contents_persists_reading_scopes(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"structure_id": "structure-1"},
        {"unit_id": "unit-1"},
    ]

    await education_textbooks.replace_structure_contents(
        structure_id="structure-1",
        units=[
            {
                "position": 1,
                "slug": "unit-1",
                "title": "Unit 1",
                "summary": "",
                "unit_type": "teaching",
                "source_refs": [],
                "confidence": 1.0,
                "status": "review",
                "knowledge_points": [],
            }
        ],
        scopes=[
            {
                "unit_index": 0,
                "slot": "reading_a",
                "title": "The World's Game",
                "source_id": "source-1",
                "line_start": 10,
                "line_end": 40,
                "char_start": 100,
                "char_end": 900,
            }
        ],
    )

    statements = [call.args[0] for call in mock_cursor.execute.call_args_list]
    assert any(
        "DELETE FROM education_textbook_scopes" in statement for statement in statements
    )
    scope_inserts = [
        call
        for call in mock_cursor.execute.call_args_list
        if "INSERT INTO education_textbook_scopes" in call.args[0]
    ]
    assert len(scope_inserts) == 1
    assert scope_inserts[0].args[1][3] == "reading_a"
    assert scope_inserts[0].args[1][10:14] == (10, 40, 100, 900)


@pytest.mark.asyncio
async def test_replace_structure_contents_preserves_ids_for_matching_slugs(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"structure_id": "structure-1"},
        {"unit_id": "existing-unit"},
        {"knowledge_point_id": "existing-kp"},
    ]
    mock_cursor.fetchall.return_value = [
        {
            "unit_id": "existing-unit",
            "unit_slug": "unit-1",
            "knowledge_point_id": "existing-kp",
            "knowledge_point_slug": "world-game",
        }
    ]

    result = await education_textbooks.replace_structure_contents(
        structure_id="structure-1",
        units=[
            {
                "position": 1,
                "slug": "unit-1",
                "title": "Renamed Unit",
                "summary": "",
                "unit_type": "teaching",
                "source_refs": [],
                "confidence": 0.9,
                "status": "review",
                "knowledge_points": [
                    {
                        "position": 1,
                        "slug": "world-game",
                        "title": "Renamed Knowledge Point",
                        "summary": "",
                        "source_refs": [],
                        "confidence": 0.9,
                        "status": "review",
                    }
                ],
            }
        ],
    )

    assert result[0]["unit_id"] == "existing-unit"
    assert result[0]["knowledge_points"][0]["knowledge_point_id"] == "existing-kp"


@pytest.mark.asyncio
async def test_replace_structure_contents_preserves_existing_reading_scopes(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"structure_id": "structure-1"},
        {"unit_id": "unit-1"},
    ]
    mock_cursor.fetchall.side_effect = [
        [
            {
                "unit_id": "unit-1",
                "unit_slug": "unit-1",
                "knowledge_point_id": None,
                "knowledge_point_slug": None,
            }
        ],
        [
            {
                "unit_id": "unit-1",
                "slot": "reading_a",
                "title": "The World's Game",
                "summary": "Reading summary",
                "reading_skill": "Analyzing Infographics",
                "vocabulary_building": "Prefix uni-",
                "critical_thinking": "Evaluating Evidence",
                "source_id": "source-1",
                "line_start": 10,
                "line_end": 40,
                "char_start": 100,
                "char_end": 900,
            }
        ],
    ]

    await education_textbooks.replace_structure_contents(
        structure_id="structure-1",
        units=[
            {
                "position": 1,
                "slug": "unit-1",
                "title": "Unit 1",
                "summary": "",
                "unit_type": "teaching",
                "source_refs": [],
                "confidence": 1.0,
                "status": "review",
                "knowledge_points": [],
            }
        ],
    )

    scope_insert = next(
        call
        for call in mock_cursor.execute.call_args_list
        if "INSERT INTO education_textbook_scopes" in call.args[0]
    )
    assert scope_insert.args[1][2] == "unit-1"
    assert scope_insert.args[1][3] == "reading_a"


@pytest.mark.asyncio
async def test_replace_structure_contents_persists_validation_warnings(
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

    await education_textbooks.replace_structure_contents(
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
        warnings=["source_quote_unresolved"],
    )

    warning_call = next(
        call
        for call in mock_cursor.execute.call_args_list
        if "SET validation_warnings = %s" in call.args[0]
    )
    warning_payload = warning_call.args[1][0]
    assert warning_payload.obj == ["source_quote_unresolved"]


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
async def test_create_generation_job_rejects_book_pipeline_bypass(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)

    with pytest.raises(
        ValueError,
        match=r"book_pipeline jobs must use queue_book_pipeline_job\(\)",
    ):
        await education_textbooks.create_generation_job(
            version_id="version-1",
            scope="book_pipeline",
            structure_id=None,
            knowledge_point_id=None,
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


@pytest.mark.asyncio
async def test_queue_book_pipeline_is_parent_scoped_and_deduplicated(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"version_id": "version-1"},
        {
            "generation_job_id": "generation-active",
            "version_id": "version-1",
            "scope": "book_pipeline",
            "structure_id": None,
            "knowledge_point_id": None,
            "status": "running",
            "attempt_count": 1,
            "pause_after_chapter_analysis": False,
        },
    ]

    result = await education_textbooks.queue_book_pipeline_job(
        parent_user_id="parent-1",
        content_version_id="version-1",
        processing_profile_sha256="a" * 64,
    )

    assert result is not None
    assert result["generation_job_id"] == "generation-active"
    executed = "\n".join(call.args[0] for call in mock_cursor.execute.call_args_list)
    assert "pg_advisory_xact_lock" in executed
    assert "memberships.role = 'parent'" in executed
    assert "INSERT INTO education_generation_jobs" not in executed


@pytest.mark.asyncio
async def test_queue_book_pipeline_reuses_matching_request_id(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"version_id": "version-1"},
        {
            "generation_job_id": "generation-existing",
            "version_id": "version-1",
            "scope": "book_pipeline",
            "structure_id": None,
            "knowledge_point_id": None,
            "status": "queued",
            "attempt_count": 0,
            "pause_after_chapter_analysis": False,
            "reused_existing_job": True,
        },
    ]

    result = await education_textbooks.queue_book_pipeline_job(
        parent_user_id="parent-1",
        content_version_id="version-1",
        processing_profile_sha256="a" * 64,
        processing_brief="只提取学生活动页。",
        request_id="ba8a3e5c-c0b4-4a40-95ec-349310992445",
    )

    assert result is not None
    assert result["generation_job_id"] == "generation-existing"
    assert result["reused_existing_job"] is True
    executed = "\n".join(call.args[0] for call in mock_cursor.execute.call_args_list)
    assert "jobs.request_id = %s" in executed
    assert "jobs.scope = 'book_pipeline'" in executed
    assert "INSERT INTO education_generation_jobs" not in executed
    assert mock_cursor.execute.call_args_list[2].args[1] == (
        "version-1",
        "ba8a3e5c-c0b4-4a40-95ec-349310992445",
    )


@pytest.mark.asyncio
async def test_queue_book_pipeline_creates_untargeted_job(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"version_id": "version-1"},
        None,
        None,
        {
            "generation_job_id": "generation-pipeline-1",
            "version_id": "version-1",
            "scope": "book_pipeline",
            "structure_id": None,
            "knowledge_point_id": None,
            "status": "queued",
            "attempt_count": 0,
            "pause_after_chapter_analysis": True,
        },
    ]

    result = await education_textbooks.queue_book_pipeline_job(
        parent_user_id="parent-1",
        content_version_id="version-1",
        processing_profile_sha256="a" * 64,
        processing_brief="保留公式顺序。",
        request_id="ba8a3e5c-c0b4-4a40-95ec-349310992445",
        pause_after_chapter_analysis=True,
    )

    assert result is not None
    assert result["status"] == "queued"
    insert_sql, parameters = mock_cursor.execute.call_args.args
    assert "VALUES (" in insert_sql
    assert parameters[2] == "保留公式顺序。"
    assert parameters[3] == "ba8a3e5c-c0b4-4a40-95ec-349310992445"
    assert parameters[4] is True
    assert parameters[5] == "a" * 64


@pytest.mark.asyncio
async def test_checkpoint_pause_closes_attempt_then_waits_for_review(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"attempt_id": "attempt-1"},
        {"attempt_id": "attempt-1"},
        {
            "generation_job_id": "generation-pipeline-1",
            "version_id": "version-1",
            "scope": "book_pipeline",
            "structure_id": None,
            "knowledge_point_id": None,
            "status": "awaiting_review",
            "attempt_count": 1,
            "pause_after_chapter_analysis": True,
        },
    ]

    result = await education_textbooks.pause_book_pipeline_for_chapter_review(
        parent_user_id="parent-1",
        generation_job_id="generation-pipeline-1",
        attempt_id="attempt-1",
        checkpoint_bundle_prefix=CHECKPOINT_PREFIX,
    )

    assert result is not None
    assert result["status"] == "awaiting_review"
    lock_sql = mock_cursor.execute.call_args_list[0].args[0]
    attempt_sql = mock_cursor.execute.call_args_list[1].args[0]
    job_sql = mock_cursor.execute.call_args_list[2].args[0]
    assert "FOR UPDATE OF attempts" in lock_sql
    assert "JOIN education_generation_jobs AS jobs" in lock_sql
    assert "SET status = 'completed'" in attempt_sql
    assert "status = 'awaiting_review'" in job_sql
    assert "pause_after_chapter_analysis IS TRUE" in job_sql
    assert "education_memberships AS memberships" in job_sql
    assert "memberships.user_id = %s" in job_sql
    assert "memberships.role = 'parent'" in job_sql
    assert "jobs.version_id = versions.version_id" in job_sql
    assert mock_cursor.execute.call_args_list[0].args[1] == (
        "generation-pipeline-1",
        "attempt-1",
        "attempt-1",
        "parent-1",
    )


@pytest.mark.asyncio
async def test_checkpoint_pause_rejects_foreign_or_invalid_job(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = None

    result = await education_textbooks.pause_book_pipeline_for_chapter_review(
        parent_user_id="parent-1",
        generation_job_id="generation-pipeline-1",
        attempt_id="attempt-1",
        checkpoint_bundle_prefix=CHECKPOINT_PREFIX,
    )

    assert result is None
    job_sql = mock_cursor.execute.call_args.args[0]
    assert "FOR UPDATE OF attempts" in job_sql
    assert "memberships.user_id = %s" in job_sql
    assert "memberships.role = 'parent'" in job_sql
    assert "jobs.scope = 'book_pipeline'" in job_sql
    assert "jobs.status = 'running'" in job_sql
    assert "jobs.latest_attempt_id = %s" in job_sql


@pytest.mark.asyncio
async def test_checkpoint_pause_fails_if_attempt_transition_is_lost(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"attempt_id": "attempt-1"},
        None,
    ]

    with pytest.raises(RuntimeError, match="checkpoint transition was lost"):
        await education_textbooks.pause_book_pipeline_for_chapter_review(
            parent_user_id="parent-1",
            generation_job_id="generation-pipeline-1",
            attempt_id="attempt-1",
            checkpoint_bundle_prefix=CHECKPOINT_PREFIX,
        )


@pytest.mark.asyncio
async def test_checkpoint_pause_rejects_empty_bundle_prefix_before_database(
    mock_cursor,
) -> None:
    with pytest.raises(ValueError, match="checkpoint bundle prefix"):
        await education_textbooks.pause_book_pipeline_for_chapter_review(
            parent_user_id="parent-1",
            generation_job_id="generation-pipeline-1",
            attempt_id="attempt-1",
            checkpoint_bundle_prefix="",
        )

    mock_cursor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_checkpoint_resume_consumes_pause_flag(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = {
        "generation_job_id": "generation-pipeline-1",
        "version_id": "version-1",
        "scope": "book_pipeline",
        "structure_id": None,
        "knowledge_point_id": None,
        "status": "queued",
        "attempt_count": 1,
        "pause_after_chapter_analysis": False,
    }

    result = await education_textbooks.resume_book_pipeline_job(
        parent_user_id="parent-1", generation_job_id="generation-pipeline-1"
    )

    assert result is not None
    resume_sql = mock_cursor.execute.call_args.args[0]
    assert "pause_after_chapter_analysis = FALSE" in resume_sql
    assert "status = 'awaiting_review'" in resume_sql
    assert "education_memberships AS memberships" in resume_sql
    assert "memberships.user_id = %s" in resume_sql
    assert "memberships.role = 'parent'" in resume_sql
    assert "jobs.checkpoint_bundle_prefix IS NOT NULL" in resume_sql
    assert "btrim(jobs.checkpoint_bundle_prefix) <> ''" in resume_sql
    assert mock_cursor.execute.call_args.args[1] == (
        "generation-pipeline-1",
        "parent-1",
    )


@pytest.mark.asyncio
async def test_generation_job_parent_projection_includes_frozen_dispatch_context(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = {
        "generation_job_id": "generation-1",
        "version_id": "version-1",
        "scope": "structure",
        "structure_id": "structure-1",
        "status": "queued",
        "pause_after_chapter_analysis": True,
        "content_version_sequence": 1,
        "structure_sequence": 1,
        "slug": "textbook",
    }

    job = await education_textbooks.get_generation_job_for_parent(
        parent_user_id="parent-1",
        generation_job_id="generation-1",
    )

    assert job is not None
    assert job["pause_after_chapter_analysis"] is True
    assert job["structure_sequence"] == 1
    sql = mock_cursor.execute.call_args.args[0]
    assert "education_generation_jobs" in sql
    assert "jobs.pause_after_chapter_analysis" in sql
    assert "jobs.processing_brief" in sql
    assert "memberships.role = 'parent'" in sql


@pytest.mark.asyncio
async def test_requeue_structure_generation_reuses_same_structure(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = {"structure_id": "structure-1"}

    requeued = await education_textbooks.requeue_structure_generation(
        generation_job_id="generation-1"
    )

    assert requeued is True
    assert "scope = 'structure'" in mock_cursor.execute.call_args_list[0].args[0]
    structure_sql = mock_cursor.execute.call_args_list[1].args[0]
    assert "UPDATE education_textbook_structures" in structure_sql
    assert "status = 'queued'" in structure_sql
    assert mock_cursor.execute.call_args_list[1].args[1] == ("structure-1",)


@pytest.mark.asyncio
async def test_mark_and_complete_generation_attempt_fence_the_root_run(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {
            "attempt_id": "attempt-1",
            "generation_job_id": "generation-1",
            "root_run_id": "run-1",
            "status": "running",
        },
        {
            "generation_job_id": "generation-1",
            "scope": "structure",
            "structure_id": "structure-1",
            "status": "running",
        },
        {"structure_id": "structure-1", "status": "review"},
        {"attempt_id": "attempt-1"},
        {"generation_job_id": "generation-1", "status": "completed"},
    ]

    running = await education_textbooks.mark_generation_attempt_running(
        generation_job_id="generation-1",
        attempt_id="attempt-1",
        root_run_id="run-1",
    )
    completed = await education_textbooks.complete_structure_generation(
        generation_job_id="generation-1",
        attempt_id="attempt-1",
        structure_id="structure-1",
        bundle_prefix="education/household/textbook/v1/structures/v1",
    )

    assert running["root_run_id"] == "run-1"
    assert completed["structure_status"] == "review"
    assert completed["job_status"] == "completed"
    running_sql = mock_cursor.execute.call_args_list[0].args[0]
    assert "root_run_id = %s" in running_sql
    running_structure_sql = mock_cursor.execute.call_args_list[2].args[0]
    assert "UPDATE education_textbook_structures" in running_structure_sql
    complete_sql = mock_cursor.execute.call_args_list[3].args[0]
    assert "status = 'review'" in complete_sql


@pytest.mark.asyncio
async def test_accept_structure_authorizes_parent_and_updates_children(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"structure_id": "structure-1"},
        {"structure_id": "structure-1", "status": "accepted"},
    ]

    accepted = await education_textbooks.accept_textbook_structure(
        parent_user_id="parent-1",
        structure_id="structure-1",
    )

    assert accepted["status"] == "accepted"
    authorization_sql = mock_cursor.execute.call_args_list[0].args[0]
    assert "memberships.role = 'parent'" in authorization_sql
    assert "status = 'review'" in authorization_sql
    child_sql = mock_cursor.execute.call_args_list[1].args[0]
    assert "education_structure_knowledge_points" in child_sql


@pytest.mark.asyncio
async def test_create_kp_lesson_revision_updates_stable_lesson_latest_revision(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"knowledge_point_id": "kp-1"},
        None,
        {"revision": 1},
        {"revision_id": "revision-1"},
        {"lesson_id": "lesson-1", "latest_revision_id": "revision-1"},
    ]

    result = await education_textbooks.create_kp_lesson_revision(
        knowledge_point_id="kp-1",
        content_key="education/household/book/v1/structures/v1/lesson.md",
        content_sha256="a" * 64,
        size_bytes=100,
        processing_profile_sha256="b" * 64,
        generation_job_id="generation-1",
    )

    assert result["lesson_id"] == "lesson-1"
    UUID(result["revision_id"])
    revision_sql = mock_cursor.execute.call_args_list[4].args[0]
    assert "INSERT INTO education_kp_lesson_revisions" in revision_sql
    update_sql = mock_cursor.execute.call_args_list[5].args[0]
    assert "latest_revision_id = %s" in update_sql


@pytest.mark.asyncio
async def test_freeze_publication_lessons_rejects_cross_structure_revision(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {"publication_id": "publication-1", "version_id": "version-1"},
        None,
    ]

    frozen = await education_textbooks.freeze_publication_lessons(
        publication_id="publication-1",
        lessons=[
            {
                "knowledge_point_id": "kp-1",
                "lesson_revision_id": "revision-other-version",
            }
        ],
    )

    assert frozen is False
    validation_sql = mock_cursor.execute.call_args_list[1].args[0]
    assert "revisions.revision_id = %s" in validation_sql
    assert "structures.version_id = %s" in validation_sql


@pytest.mark.asyncio
async def test_complete_book_pipeline_import_persists_topology_and_candidates(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {
            "generation_job_id": "generation-1",
            "version_id": "version-1",
            "processing_profile_sha256": "a" * 64,
            "input_manifest_sha256": "b" * 64,
            "source_revision": "revision-1",
        },
        {"version_id": "version-1"},
        {"sequence": 2},
        {
            "structure_id": "structure-2",
            "version_id": "version-1",
            "sequence": 2,
            "status": "review",
        },
        {"attempt_id": "attempt-1"},
        {"generation_job_id": "generation-1", "status": "completed"},
    ]

    result = await education_textbooks.complete_book_pipeline_import(
        parent_user_id="parent-1",
        generation_job_id="generation-1",
        attempt_id="attempt-1",
        package={
            "format": "langalpha-book-package/v1",
            "source_revision": "revision-1",
            "content_nodes": [
                {
                    "node_key": "node-1",
                    "parent_key": None,
                    "node_type": "unit",
                    "position": 1,
                    "slug": "node-1",
                    "title": "Node 1",
                    "summary": "",
                    "source_refs": [],
                    "metadata": {},
                },
                {
                    "node_key": "node-2",
                    "parent_key": "node-1",
                    "node_type": "reading",
                    "position": 1,
                    "slug": "node-2",
                    "title": "Node 2",
                    "summary": "",
                    "source_refs": [],
                    "metadata": {},
                },
            ],
            "knowledge_points": [
                {
                    "candidate_key": "candidate-1",
                    "node_key": "node-2",
                    "point_type": "concept",
                    "title": "Candidate",
                    "summary": "",
                    "source_refs": [],
                    "confidence": 0.8,
                    "metadata": {},
                }
            ],
            "assets": [
                {
                    "node_key": "node-2",
                    "kind": "knowledge",
                    "path": "outputs/node-2.md",
                    "content_sha256": "c" * 64,
                    "size_bytes": 10,
                    "metadata": {},
                }
            ],
        },
        bundle_prefix="education/household/textbook/v1/book-packages/job-1",
        bundle_manifest={"format": "langalpha-book-package-bundle/v1"},
        asset_content_keys={"outputs/node-2.md": "education/.../node-2.md"},
        warnings=["no_reading_nodes"],
    )

    assert result is not None
    assert result["structure_id"] == "structure-2"
    assert result["node_count"] == 2
    assert result["knowledge_point_count"] == 1
    executed = mock_cursor.execute.call_args_list
    authorization_sql = executed[0].args[0]
    assert "memberships.role = 'parent'" in authorization_sql
    version_lock_sql = executed[1].args[0]
    assert "FROM education_textbook_versions" in version_lock_sql
    assert "FOR UPDATE" in version_lock_sql
    node_inserts = [
        call
        for call in executed
        if "INSERT INTO education_content_nodes" in call.args[0]
    ]
    assert len(node_inserts) == 2
    assert node_inserts[0].args[1][2] is None
    assert node_inserts[1].args[1][2] is not None
    candidate_insert = next(
        call
        for call in executed
        if "INSERT INTO education_structure_knowledge_points" in call.args[0]
    )
    UUID(candidate_insert.args[1][1])
    UUID(candidate_insert.args[1][2])
    assert candidate_insert.args[1][3:5] == ("candidate-1", "concept")
    assert "'generated'" in candidate_insert.args[0]
    assert "'pending'" in candidate_insert.args[0]
    asset_insert = next(
        call
        for call in executed
        if "INSERT INTO education_content_assets" in call.args[0]
    )
    assert asset_insert.args[1][2] is not None
    job_update = next(
        call
        for call in reversed(executed)
        if "UPDATE education_generation_jobs" in call.args[0]
    )
    assert "structure_id = %s" in job_update.args[0]
    UUID(job_update.args[1][0])


@pytest.mark.asyncio
async def test_claim_book_pipeline_launch_serializes_queued_to_preparing(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = {
        "generation_job_id": "generation-1",
        "version_id": "version-1",
        "scope": "book_pipeline",
        "status": "preparing",
    }

    claimed = await education_textbooks.claim_book_pipeline_launch(
        parent_user_id="parent-1",
        generation_job_id="generation-1",
    )

    assert claimed is not None
    assert claimed["status"] == "preparing"
    sql = mock_cursor.execute.call_args.args[0]
    assert "UPDATE education_generation_jobs" in sql
    assert "jobs.status = 'queued'" in sql
    assert "status = 'preparing'" in sql
    assert "memberships.role = 'parent'" in sql


@pytest.mark.asyncio
async def test_fail_claimed_book_pipeline_launch_closes_preparing_job(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = {
        "generation_job_id": "generation-1",
        "status": "failed",
        "error_code": "managed_book_pipeline_start_failed",
    }

    failed = await education_textbooks.fail_claimed_book_pipeline_launch(
        generation_job_id="generation-1",
        expected_latest_attempt_id=None,
        error_code="managed_book_pipeline_start_failed",
        error_message="start failed",
    )

    assert failed is not None
    sql = mock_cursor.execute.call_args.args[0]
    assert "UPDATE education_generation_jobs" in sql
    assert "jobs.status = 'preparing'" in sql
    assert "status = 'failed'" in sql
    assert "latest_attempt_id IS NOT DISTINCT FROM %s" in sql


@pytest.mark.asyncio
async def test_claim_generation_job_can_consume_pipeline_launch_preparing(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {
            "generation_job_id": "generation-1",
            "version_id": "version-1",
            "scope": "book_pipeline",
            "structure_id": None,
            "knowledge_point_id": None,
            "previous_attempt_id": None,
        },
        {
            "attempt_id": "attempt-2",
            "generation_job_id": "generation-1",
            "previous_attempt_id": None,
            "managed_workspace_id": "workspace-1",
            "managed_thread_id": "thread-1",
            "root_run_id": None,
        },
    ]

    attempt = await education_textbooks.claim_generation_job(
        generation_job_id="generation-1",
        managed_workspace_id="workspace-1",
        managed_thread_id="thread-1",
        expected_job_status="preparing",
    )

    assert attempt is not None
    assert attempt["attempt_id"] == "attempt-2"
    select_sql = mock_cursor.execute.call_args_list[0].args[0]
    assert "status = 'preparing'" in select_sql


@pytest.mark.asyncio
async def test_list_generation_progress_events_preserves_attempt_order_metadata(
    mock_connection, mock_cursor, monkeypatch
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchall.return_value = [
        {
            "generation_job_id": "generation-1",
            "attempt_id": "old-attempt",
            "attempt_started_at": "2026-09-22T01:00:00+00:00",
            "sequence": 41,
            "stage": "content_processing",
            "progress_truncated": True,
        }
    ]

    rows = await education_textbooks.list_generation_progress_events(
        generation_job_id="generation-1"
    )

    assert rows[0]["attempt_started_at"] == "2026-09-22T01:00:00+00:00"
    assert rows[0]["progress_truncated"] is True
    executed = mock_cursor.execute.call_args.args[0]
    assert "JOIN education_generation_attempts AS attempts" in executed
    assert "attempts.started_at AS attempt_started_at" in executed
    assert "ROW_NUMBER() OVER" in executed
    assert "GREATEST(total_event_count - %s, 0)" in executed
    assert "stage_counted_order" in executed
    assert "progress_truncated" in executed
    assert "ORDER BY attempts.started_at," in executed
