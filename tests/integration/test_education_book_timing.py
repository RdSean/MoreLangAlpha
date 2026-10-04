"""Reliable service intervals and attempt history against isolated PostgreSQL."""

from uuid import uuid4

import pytest

from tests.integration.test_education_book_jobs_db import (
    _seed_book,
    _seed_pending,
    _prepared_source,
)

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_phase_segments_are_idempotent_and_terminal_facts_stop_open_intervals(
    patched_get_db_connection, seed_user
):
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        fail_book_item,
        get_book_job_for_parent,
    )
    from src.server.database.education_book_timing import (
        begin_book_phase,
        end_book_phase,
    )

    book = await _seed_book(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    item = await claim_next_book_item(worker_id="timing", lease_seconds=30)
    start = await begin_book_phase(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        phase="sandbox_preparation",
    )
    await end_book_phase(segment_id=start, measured_ms=125, status="succeeded")
    await end_book_phase(segment_id=start, measured_ms=999, status="failed")
    executing = await begin_book_phase(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        phase="ptc_execution",
    )
    await fail_book_item(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        safe_error="Failed",
        stop_remaining=True,
    )
    job = await get_book_job_for_parent(
        job_id=book["job_id"], parent_user_id=seed_user["user_id"]
    )
    summary = job["items"][0]["timing_summary"]
    assert summary["total_ms"] is not None
    phases = {phase["phase"]: phase for phase in summary["phases"]}
    assert phases["sandbox_preparation"]["measured_ms"] == 125
    assert phases["ptc_execution"]["measured_ms"] is None
    assert phases["ptc_execution"]["ended_at"] is not None
    assert summary["status"] == "partial"
    await end_book_phase(segment_id=executing, measured_ms=375, status="failed")
    job = await get_book_job_for_parent(
        job_id=book["job_id"], parent_user_id=seed_user["user_id"]
    )
    assert job["items"][0]["timing_summary"]["status"] == "available"
    assert job["items"][0]["status"] == "failed"
    with pytest.raises(RuntimeError):
        await begin_book_phase(
            item_id=item["item_id"],
            attempt_token=item["attempt_token"],
            phase="finalization",
        )


async def test_ready_commit_closes_source_and_records_runtime_wait_atomically(
    patched_get_db_connection, seed_user
):
    from src.server.database.education_book_jobs import (
        claim_next_preparation_item,
        claim_next_book_item,
        get_book_job_for_parent,
    )
    from src.server.database.education_books import commit_prepared_book_source
    from src.server.database.education_book_timing import (
        begin_book_phase,
        end_book_phase,
    )

    book, original = await _seed_pending(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    item = await claim_next_preparation_item(worker_id="timing", lease_seconds=30)
    segment = await begin_book_phase(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        phase="source_freezing",
    )
    await commit_prepared_book_source(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        source=_prepared_source(book, original, item["attempt_token"]),
    )
    await end_book_phase(segment_id=segment, measured_ms=1200, status="succeeded")
    await claim_next_book_item(worker_id="runtime", lease_seconds=30)
    job = await get_book_job_for_parent(
        job_id=book["job_id"], parent_user_id=seed_user["user_id"]
    )
    phases = {p["phase"]: p for p in job["items"][0]["timing_summary"]["phases"]}
    assert phases["source_freezing"]["measured_ms"] == 1200
    assert phases["source_freezing"]["ended_at"] is not None
    assert phases["runtime_queue"]["measured_ms"] is not None
    assert phases["initial_queue"]["measured_ms"] is not None


async def test_statistics_acl_and_cursor_preserve_interrupted_attempts(
    patched_get_db_connection, seed_user
):
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        requeue_expired_book_preparation,
    )
    from src.server.services.education_book_timing import get_book_job_statistics
    from src.server.app.education.book_models import BookJobStatisticsResponse

    book = await _seed_book(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    first = await claim_next_book_item(worker_id="a", lease_seconds=30)
    async with patched_get_db_connection() as conn:
        await conn.execute(
            "UPDATE education_book_job_items SET lease_expires_at=NOW()-INTERVAL '1 second' WHERE item_id=%s",
            (first["item_id"],),
        )
    assert await requeue_expired_book_preparation(
        item_id=first["item_id"], attempt_token=first["attempt_token"]
    )
    await claim_next_book_item(worker_id="b", lease_seconds=30)
    page = BookJobStatisticsResponse.model_validate(
        await get_book_job_statistics(
            job_id=book["job_id"], parent_user_id=seed_user["user_id"], limit=1
        )
    )
    assert page.attempts[0].status == "interrupted"
    assert page.next_cursor is not None
    next_page = await get_book_job_statistics(
        job_id=book["job_id"],
        parent_user_id=seed_user["user_id"],
        cursor=page.next_cursor,
        limit=1,
    )
    assert next_page["attempts"][0]["timing"]["attempt"] == 2
    assert next_page["next_cursor"] is None
    assert (
        await get_book_job_statistics(
            job_id=book["job_id"], parent_user_id=str(uuid4())
        )
        is None
    )


async def test_retry_statistics_keep_prior_success_but_sample_only_current_round(
    patched_get_db_connection, seed_user
):
    from tests.integration.test_education_book_jobs_db import (
        _seed_claimed_material_job,
        IDENTITY,
    )
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        finalize_material,
        fail_book_item,
        retry_book_job,
        get_book_job_for_parent,
        record_candidate_object,
    )
    from src.server.services.education_book_timing import get_book_job_statistics

    book, job, first = await _seed_claimed_material_job(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
        include_supplementary=False,
        target_count=2,
    )

    async def commit(item):
        key = f"education/{book['household_id']}/textbooks/{book['textbook_id']}/materials/{item['knowledge_point_id']}/attempts/{item['attempt_token']}/lesson.md"
        await record_candidate_object(
            item_id=item["item_id"],
            attempt_token=item["attempt_token"],
            content_key=key,
        )
        await finalize_material(
            item_id=item["item_id"],
            attempt_token=item["attempt_token"],
            content_key=key,
            content_sha256="a" * 64,
            size_bytes=1,
            generation_params={},
        )

    await commit(first)
    second = await claim_next_book_item(worker_id="a", lease_seconds=30)
    await fail_book_item(
        item_id=second["item_id"],
        attempt_token=second["attempt_token"],
        safe_error="Invalid",
        stop_remaining=False,
    )
    retry = await retry_book_job(
        source_job_id=job["job_id"],
        requested_by_user_id=seed_user["user_id"],
        idempotency_key="retry-stats",
        identity=IDENTITY,
    )
    third = await claim_next_book_item(worker_id="b", lease_seconds=30)
    await commit(third)
    async with patched_get_db_connection() as conn:
        await conn.execute(
            "UPDATE education_book_job_attempts SET total_ms=CASE WHEN attempt_token=%s THEN 10000 ELSE 200 END WHERE attempt_token IN (%s,%s)",
            (first["attempt_token"], first["attempt_token"], third["attempt_token"]),
        )
    snapshot = await get_book_job_for_parent(
        job_id=retry["job_id"], parent_user_id=seed_user["user_id"]
    )
    assert snapshot["total_items"] == 1
    assert snapshot["material_progress"] == {"completed": 2, "total": 2}
    stats = await get_book_job_statistics(
        job_id=retry["job_id"], parent_user_id=seed_user["user_id"]
    )
    assert stats["material_sample_count"] == 1
    assert stats["material_median_ms"] == stats["material_longest_ms"] == 200
    assert len(stats["attempts"]) == 3
    assert {a["timing"]["request_round"] for a in stats["attempts"]} == {1, 2}


async def test_preparation_snapshot_survives_activity_budget_and_stale_callbacks(
    patched_get_db_connection, seed_user, monkeypatch
):
    from src.server.database import education_book_activity as activity
    from src.server.database.education_book_jobs import (
        claim_next_preparation_item,
        update_book_preparation_progress,
        get_book_job_for_parent,
    )
    from src.server.services.education_book_activity import BookActivityObserver
    from unittest.mock import AsyncMock

    book, _ = await _seed_pending(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    item = await claim_next_preparation_item(worker_id="prep", lease_seconds=30)
    monkeypatch.setattr(activity, "MAX_DETAIL_EVENTS", 0)
    observer = BookActivityObserver(
        job_id=item["job_id"],
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        item_kind="structure",
        publish=AsyncMock(),
    )
    await update_book_preparation_progress(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        verified_resources=1,
        total_resources=2,
    )
    await observer.report_preparation_progress(1, 2)
    await update_book_preparation_progress(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        verified_resources=2,
        total_resources=2,
    )
    await observer.report_preparation_progress(2, 2)
    with pytest.raises(RuntimeError):
        await update_book_preparation_progress(
            item_id=item["item_id"],
            attempt_token=uuid4(),
            verified_resources=0,
            total_resources=2,
        )
    snapshot = await get_book_job_for_parent(
        job_id=book["job_id"], parent_user_id=seed_user["user_id"]
    )
    assert snapshot["items"][0]["preparation_progress"] == {
        "total_resources": 2,
        "verified_resources": 2,
    }
    assert snapshot["items"][0]["execution_phase"] == "source_freezing"
    async with patched_get_db_connection() as conn:
        assert (
            await (
                await conn.execute(
                    "SELECT count(*) AS n FROM education_book_activity_events WHERE job_id=%s AND kind='resource'",
                    (item["job_id"],),
                )
            ).fetchone()
        )["n"] == 0


async def test_negative_wall_interval_is_unknown_without_changing_terminal_state(
    patched_get_db_connection, seed_user
):
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        fail_book_item,
        get_book_job_for_parent,
    )

    book = await _seed_book(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    item = await claim_next_book_item(worker_id="timing", lease_seconds=30)
    async with patched_get_db_connection() as conn:
        await conn.execute(
            "UPDATE education_book_job_items SET queued_at=NOW()+INTERVAL '1 hour' WHERE item_id=%s",
            (item["item_id"],),
        )
    await fail_book_item(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        safe_error="Failed",
        stop_remaining=True,
    )
    snapshot = await get_book_job_for_parent(
        job_id=book["job_id"], parent_user_id=seed_user["user_id"]
    )
    assert snapshot["items"][0]["timing_summary"]["total_ms"] is None
    assert snapshot["items"][0]["status"] == "failed"


async def test_service_clock_regression_keeps_phase_duration_unknown(
    patched_get_db_connection, seed_user
):
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        get_book_job_for_parent,
    )
    from src.server.database.education_book_timing import (
        begin_book_phase,
        end_book_phase,
    )

    book = await _seed_book(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    item = await claim_next_book_item(worker_id="timing", lease_seconds=30)
    segment = await begin_book_phase(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        phase="sandbox_preparation",
    )
    async with patched_get_db_connection() as conn:
        await conn.execute(
            "UPDATE education_book_job_phase_spans SET started_at=NOW()+INTERVAL '1 hour' WHERE segment_id=%s",
            (segment,),
        )
    await end_book_phase(segment_id=segment, measured_ms=200, status="succeeded")
    snapshot = await get_book_job_for_parent(
        job_id=book["job_id"], parent_user_id=seed_user["user_id"]
    )
    phase = next(
        p
        for p in snapshot["items"][0]["timing_summary"]["phases"]
        if p["phase"] == "sandbox_preparation"
    )
    assert phase["measured_ms"] is None
    assert phase["status"] == "partial"


async def test_new_process_finalization_interrupts_previous_open_intervals(
    patched_get_db_connection, seed_user
):
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        get_book_job_for_parent,
    )
    from src.server.database.education_book_timing import (
        begin_book_phase,
        end_book_phase,
    )

    book = await _seed_book(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    item = await claim_next_book_item(worker_id="timing", lease_seconds=30)
    execution = await begin_book_phase(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        phase="ptc_execution",
    )
    finalization = await begin_book_phase(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        phase="finalization",
    )
    next_finalization = await begin_book_phase(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        phase="finalization",
    )
    await end_book_phase(segment_id=execution, measured_ms=9999, status="succeeded")
    snapshot = await get_book_job_for_parent(
        job_id=book["job_id"], parent_user_id=seed_user["user_id"]
    )
    phases = {p["phase"]: p for p in snapshot["items"][0]["timing_summary"]["phases"]}
    assert phases["ptc_execution"]["ended_at"] is not None
    assert phases["ptc_execution"]["measured_ms"] is None
    assert phases["ptc_execution"]["status"] == "partial"
    assert phases["finalization"]["ended_at"] is None
    assert phases["finalization"]["segment_count"] == 2
    async with patched_get_db_connection() as conn:
        rows = await (
            await conn.execute(
                "SELECT segment_id,status FROM education_book_job_phase_spans WHERE attempt_id=%s AND ended_at IS NULL",
                (item["attempt_token"],),
            )
        ).fetchall()
    assert rows == [{"segment_id": next_finalization, "status": "running"}]
    assert finalization != next_finalization


async def test_ended_current_phase_is_partial_while_next_metric_start_is_unavailable(
    patched_get_db_connection, seed_user
):
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        get_book_job_for_parent,
    )
    from src.server.database.education_book_timing import (
        begin_book_phase,
        end_book_phase,
    )

    book = await _seed_book(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    item = await claim_next_book_item(worker_id="timing", lease_seconds=30)
    segment = await begin_book_phase(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        phase="input_staging",
    )
    await end_book_phase(segment_id=segment, measured_ms=120, status="succeeded")
    # A failed next metric transaction leaves the previous committed phase unchanged.
    snapshot = await get_book_job_for_parent(
        job_id=book["job_id"], parent_user_id=seed_user["user_id"]
    )
    assert snapshot["items"][0]["timing_summary"]["status"] == "partial"


async def test_missing_source_measurement_stays_partial_after_success(
    patched_get_db_connection, seed_user, monkeypatch
):
    from unittest.mock import AsyncMock

    from src.server.database.education_book_jobs import (
        claim_next_preparation_item,
        claim_next_book_item,
        get_book_job_for_parent,
    )
    from src.server.database.education_books import commit_prepared_book_source
    from src.server.database.education_book_timing import (
        begin_book_phase,
        end_book_phase,
    )
    from src.server.services import education_book_timing as timing

    book, original = await _seed_pending(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    item = await claim_next_preparation_item(worker_id="timing", lease_seconds=30)
    recorder = timing.BookPhaseRecorder(item, "source_freezing")
    with monkeypatch.context() as patch:
        patch.setattr(
            timing,
            "begin_book_phase",
            AsyncMock(side_effect=RuntimeError("metrics unavailable")),
        )
        await recorder.start()
    await commit_prepared_book_source(
        item_id=item["item_id"],
        attempt_token=item["attempt_token"],
        source=_prepared_source(book, original, item["attempt_token"]),
    )
    await recorder.finish("succeeded")
    await claim_next_book_item(worker_id="runtime", lease_seconds=30)
    for phase in (
        "sandbox_preparation",
        "input_staging",
        "ptc_execution",
        "finalization",
    ):
        segment = await begin_book_phase(
            item_id=item["item_id"], attempt_token=item["attempt_token"], phase=phase
        )
        await end_book_phase(segment_id=segment, measured_ms=100, status="succeeded")
    async with patched_get_db_connection() as conn:
        await conn.execute(
            "UPDATE education_book_job_items SET status='succeeded',finished_at=NOW() WHERE item_id=%s",
            (item["item_id"],),
        )
    snapshot = await get_book_job_for_parent(
        job_id=book["job_id"], parent_user_id=seed_user["user_id"]
    )
    assert snapshot["items"][0]["status"] == "succeeded"
    assert snapshot["items"][0]["timing_summary"]["status"] == "partial"
    statistics = await timing.get_book_job_statistics(
        job_id=book["job_id"], parent_user_id=seed_user["user_id"]
    )
    assert statistics["status"] == "partial"
