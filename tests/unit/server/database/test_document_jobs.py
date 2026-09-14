from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from src.server.database import document_jobs
from src.server.database.document_jobs import ArtifactPublication


def _patch_connection(monkeypatch, mock_connection) -> None:
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(document_jobs, "get_db_connection", fake_connection)


@pytest.mark.asyncio
async def test_create_job_always_inserts_for_same_document_and_parser(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {"job_id": "job-A1b2C3d4E5f6"}

    for job_id in ("job-A1b2C3d4E5f6", "job-G7h8I9j0K1l2"):
        await document_jobs.create_job(
            owner_user_id="owner-1",
            job_id=job_id,
            document_id="doc-A1b2C3d4E5f6",
            inspection_id="ins-A1b2C3d4E5f6",
            parser_id="anydoc-local",
            parser_name="AnyDoc Local",
            parser_version="0.2.4",
            parser_options={},
            request_mode="async",
        )

    for call in mock_cursor.execute.await_args_list:
        sql, params = call.args
        assert "INSERT INTO document_parse_jobs" in sql
        assert "document_inspections.status = 'completed'" in sql
        assert "documents.owner_user_id = %s" in sql
        assert "ON CONFLICT" not in sql
        assert "NOT EXISTS" not in sql
        assert params[-1] == "owner-1"


@pytest.mark.asyncio
async def test_claim_selects_queued_or_expired_job_with_skip_locked(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {
        "job_id": "job-A1b2C3d4E5f6",
        "claimed_by": "worker-1",
        "attempt_count": 2,
        "status_version": 4,
    }

    claimed = await document_jobs.claim_next_job(
        claimed_by="worker-1",
        lease_seconds=60,
    )

    assert claimed is not None
    sql, params = mock_cursor.execute.await_args.args
    assert "FOR UPDATE OF jobs SKIP LOCKED" in sql
    assert "status = 'queued'" in sql
    assert "status = 'running'" in sql
    assert "lease_expires_at <= clock_timestamp()" in sql
    assert "JOIN documents" in sql
    assert "JOIN document_inspections" in sql
    assert "candidate.source_storage_key" in sql
    assert "candidate.inspection_summary" in sql
    # The owner rides along so a provider's reported usage can be attributed
    # without the executor going back to the documents table.
    assert "documents.owner_user_id" in sql
    assert "attempt_count = attempt_count + 1" in sql
    assert "status_version = status_version + 1" in sql
    assert params == ("worker-1", 60)


@pytest.mark.asyncio
async def test_lease_and_progress_bind_claim_attempt_and_expected_version(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {"job_id": "job-A1b2C3d4E5f6"}

    await document_jobs.renew_lease(
        job_id="job-A1b2C3d4E5f6",
        claimed_by="worker-1",
        attempt_count=2,
        expected_status_version=4,
        lease_seconds=60,
    )
    await document_jobs.update_progress(
        job_id="job-A1b2C3d4E5f6",
        claimed_by="worker-1",
        attempt_count=2,
        expected_status_version=4,
        stage="parsing",
        percentage=40,
    )

    for call in mock_cursor.execute.await_args_list:
        sql, params = call.args
        assert "job_id = %s" in sql
        assert "claimed_by = %s" in sql
        assert "attempt_count = %s" in sql
        assert "status_version = %s" in sql
        assert "lease_expires_at > clock_timestamp()" in sql
        assert params[:4] == (
            "job-A1b2C3d4E5f6",
            "worker-1",
            2,
            4,
        ) or params[-4:] == (
            "job-A1b2C3d4E5f6",
            "worker-1",
            2,
            4,
        )


@pytest.mark.asyncio
async def test_wrong_claimant_cannot_update_or_complete(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = None

    updated = await document_jobs.update_progress(
        job_id="job-A1b2C3d4E5f6",
        claimed_by="wrong-worker",
        attempt_count=1,
        expected_status_version=2,
        stage="parsing",
        percentage=30,
    )
    completed = await document_jobs.publish_artifacts(
        job_id="job-A1b2C3d4E5f6",
        claimed_by="wrong-worker",
        attempt_count=1,
        expected_status_version=2,
        artifacts=(),
        primary_artifact_id=None,
    )

    assert updated is None
    assert completed is None
    assert mock_cursor.executemany.await_count == 0


@pytest.mark.asyncio
async def test_progress_guards_stage_percentage_and_version_monotonicity(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {"job_id": "job-A1b2C3d4E5f6"}

    await document_jobs.update_progress(
        job_id="job-A1b2C3d4E5f6",
        claimed_by="worker-1",
        attempt_count=1,
        expected_status_version=3,
        stage="storing",
        percentage=80,
    )

    sql = mock_cursor.execute.await_args.args[0]
    assert "percentage <= %s" in sql
    assert "CASE document_parse_jobs.stage" in sql
    assert "status_version = status_version + 1" in sql


@pytest.mark.asyncio
async def test_cancel_terminal_job_is_idempotent(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    terminal = {
        "job_id": "job-A1b2C3d4E5f6",
        "status": "completed",
        "status_version": 8,
    }
    mock_cursor.fetchone.return_value = terminal

    result = await document_jobs.request_cancel(
        owner_user_id="owner-1",
        job_id="job-A1b2C3d4E5f6",
    )

    assert result == terminal
    assert mock_cursor.execute.await_count == 1
    sql, params = mock_cursor.execute.await_args.args
    assert "FOR UPDATE" in sql
    assert "documents.owner_user_id = %s" in sql
    assert params == ("job-A1b2C3d4E5f6", "owner-1")


@pytest.mark.asyncio
async def test_cancel_running_job_is_terminal_and_releases_claim(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.side_effect = [
        {
            "job_id": "job-A1b2C3d4E5f6",
            "status": "running",
            "status_version": 4,
            "cancellation_requested_at": None,
        },
        {
            "job_id": "job-A1b2C3d4E5f6",
            "status": "cancelled",
            "status_version": 5,
        },
    ]

    result = await document_jobs.request_cancel(
        owner_user_id="owner-1",
        job_id="job-A1b2C3d4E5f6",
    )

    assert result is not None and result["status"] == "cancelled"
    update_sql = mock_cursor.execute.await_args_list[1].args[0]
    assert "status = 'cancelled'" in update_sql
    assert "stage = 'cancelled'" in update_sql
    assert "claimed_by = NULL" in update_sql
    assert "lease_expires_at = NULL" in update_sql


@pytest.mark.asyncio
async def test_publish_artifacts_and_completion_share_one_transaction(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.side_effect = [
        {"document_id": "doc-A1b2C3d4E5f6"},
        {"job_id": "job-A1b2C3d4E5f6", "status": "completed"},
    ]
    artifact = ArtifactPublication(
        artifact_id="art-A1b2C3d4E5f6",
        artifact_kind="primary_document",
        format="gfm",
        media_type="text/markdown",
        relative_path="document.md",
        storage_key=(
            "documents/doc-A1b2C3d4E5f6/artifacts/job-A1b2C3d4E5f6/document.md"
        ),
        metadata={"backend": "anydoc"},
    )

    result = await document_jobs.publish_artifacts(
        job_id="job-A1b2C3d4E5f6",
        claimed_by="worker-1",
        attempt_count=1,
        expected_status_version=3,
        artifacts=(artifact,),
        primary_artifact_id="art-A1b2C3d4E5f6",
    )

    assert result is not None
    fence_sql = mock_cursor.execute.await_args_list[0].args[0]
    complete_sql = mock_cursor.execute.await_args_list[1].args[0]
    assert "FOR UPDATE" in fence_sql
    assert "cancellation_requested_at IS NULL" in fence_sql
    assert mock_cursor.executemany.await_count == 1
    assert (
        "INSERT INTO document_artifacts" in mock_cursor.executemany.await_args.args[0]
    )
    assert "primary_artifact_id = %s" in complete_sql
    assert "status = 'completed'" in complete_sql
    assert "status_version = status_version + 1" in complete_sql


@pytest.mark.asyncio
async def test_fail_and_recover_expired_jobs_are_fenced(
    mock_connection,
    mock_cursor,
    monkeypatch,
) -> None:
    _patch_connection(monkeypatch, mock_connection)
    mock_cursor.fetchone.return_value = {"job_id": "job-A1b2C3d4E5f6"}
    mock_cursor.fetchall.return_value = [{"job_id": "job-G7h8I9j0K1l2"}]

    await document_jobs.fail_job(
        job_id="job-A1b2C3d4E5f6",
        claimed_by="worker-1",
        attempt_count=2,
        expected_status_version=4,
        error_code="parser_failed",
        error_message="Document parsing failed",
    )
    recovered = await document_jobs.recover_expired_jobs(limit=10)

    fail_sql = mock_cursor.execute.await_args_list[0].args[0]
    recover_sql = mock_cursor.execute.await_args_list[1].args[0]
    assert "claimed_by = %s" in fail_sql
    assert "attempt_count = %s" in fail_sql
    assert "status_version = %s" in fail_sql
    assert "FOR UPDATE SKIP LOCKED" in recover_sql
    assert "lease_expires_at <= clock_timestamp()" in recover_sql
    assert recovered == [{"job_id": "job-G7h8I9j0K1l2"}]
