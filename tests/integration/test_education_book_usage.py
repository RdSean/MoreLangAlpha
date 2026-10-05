"""Usage survives finalization and rejects stale attempts in isolated PG."""

from uuid import uuid4

import pytest

from tests.integration.test_education_book_jobs_db import _seed_book

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

USAGE = {
    "status": "available",
    "input_tokens": 20,
    "output_tokens": 7,
    "total_tokens": 27,
    "recorded_calls": 1,
}


async def test_usage_is_idempotent_and_survives_terminal_commit(
    patched_get_db_connection, seed_user
):
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        fail_book_item,
        get_book_job_for_parent,
    )
    from src.server.database.education_book_usage import record_book_usage

    book = await _seed_book(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    item = await claim_next_book_item(worker_id="usage", lease_seconds=30)
    args = {"item_id": item["item_id"], "attempt_token": item["attempt_token"]}
    assert await record_book_usage(**args, usage=USAGE)
    assert not await record_book_usage(**args, usage={**USAGE, "total_tokens": 999})
    assert not await record_book_usage(
        item_id=item["item_id"], attempt_token=uuid4(), usage=USAGE
    )
    await fail_book_item(**args, safe_error="test", stop_remaining=True)
    job = await get_book_job_for_parent(
        job_id=book["job_id"], parent_user_id=seed_user["user_id"]
    )
    assert job["token_usage"] == USAGE


async def test_recovery_rejects_late_old_usage_and_marks_missing_attempt_partial(
    patched_get_db_connection, seed_user
):
    from src.server.database.education_book_jobs import (
        claim_next_book_item,
        requeue_expired_book_preparation,
        get_book_job_for_parent,
    )
    from src.server.database.education_book_usage import record_book_usage

    book = await _seed_book(
        patched_get_db_connection, parent_user_id=seed_user["user_id"]
    )
    first = await claim_next_book_item(worker_id="usage-a", lease_seconds=30)
    async with patched_get_db_connection() as conn:
        await conn.execute(
            "UPDATE education_book_job_items SET lease_expires_at=NOW()-INTERVAL '1 second' WHERE item_id=%s",
            (first["item_id"],),
        )
    assert await requeue_expired_book_preparation(
        item_id=first["item_id"], attempt_token=first["attempt_token"]
    )
    second = await claim_next_book_item(worker_id="usage-b", lease_seconds=30)
    assert not await record_book_usage(
        item_id=first["item_id"], attempt_token=first["attempt_token"], usage=USAGE
    )
    assert await record_book_usage(
        item_id=second["item_id"], attempt_token=second["attempt_token"], usage=USAGE
    )
    job = await get_book_job_for_parent(
        job_id=book["job_id"], parent_user_id=seed_user["user_id"]
    )
    assert job["token_usage"] == {**USAGE, "status": "partial"}
