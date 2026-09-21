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
    assert result["units"][0]["knowledge_points"][0]["lesson_revision_id"] == "revision-1"
    structure_sql = mock_cursor.execute.call_args_list[0].args[0]
    assert "education_textbook_structures" in structure_sql
    assert "memberships.role = 'parent'" in structure_sql
    knowledge_point_sql = mock_cursor.execute.call_args_list[2].args[0]
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
        "content_version_sequence": 1,
        "structure_sequence": 1,
        "slug": "textbook",
    }

    job = await education_textbooks.get_generation_job_for_parent(
        parent_user_id="parent-1",
        generation_job_id="generation-1",
    )

    assert job["structure_sequence"] == 1
    sql = mock_cursor.execute.call_args.args[0]
    assert "education_generation_jobs" in sql
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
