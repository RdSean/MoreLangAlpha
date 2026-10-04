"""Background source preparation without sandbox or PTC reservations."""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from src.server.database.education_book_deletion import book_item_storage_guard
from src.server.database.education_book_jobs import (
    assert_book_preparation_current,
    update_book_preparation_progress,
    record_candidate_object,
    renew_book_item_lease,
    fail_book_item,
)
from src.server.database.education_books import (
    commit_prepared_book_source,
    prepared_book_source_is_committed,
)
from src.server.services.education_textbook_source_snapshots import freeze_book_source
from src.server.services.education_book_activity import (
    publish_book_activity_hint,
    BookActivityObserver,
)
from src.server.services.education_book_timing import book_phase, measured_book_phase

logger = logging.getLogger(__name__)


async def prepare_book_item(
    *, item: dict[str, Any], worker_id: str, lease_seconds: int
) -> None:
    item_id = UUID(str(item["item_id"]))
    token = UUID(str(item["attempt_token"]))
    finished = asyncio.Event()
    owner = asyncio.current_task()
    observer = BookActivityObserver(
        job_id=item["job_id"],
        item_id=item_id,
        attempt_token=token,
        item_kind="structure",
    )

    async def current() -> None:
        await assert_book_preparation_current(item_id=item_id, attempt_token=token)

    async def before_write(key: str) -> None:
        await current()
        await record_candidate_object(
            item_id=item_id, attempt_token=token, content_key=key
        )

    async def verified(count: int, total: int) -> None:
        await update_book_preparation_progress(
            item_id=item_id,
            attempt_token=token,
            verified_resources=count,
            total_resources=total,
        )
        await observer.report_preparation_progress(count, total)

    async def heartbeat() -> None:
        while not finished.is_set():
            try:
                await asyncio.wait_for(finished.wait(), max(lease_seconds / 3, 0.01))
                return
            except TimeoutError:
                pass
            try:
                renewed = await renew_book_item_lease(
                    item_id=item_id,
                    attempt_token=token,
                    worker_id=worker_id,
                    lease_seconds=lease_seconds,
                )
                if not renewed:
                    if owner is not None:
                        owner.cancel()
                    return
            except Exception:
                logger.exception("Source preparation lease renewal failed")
                if owner is not None:
                    owner.cancel()
                return

    try:
        async with book_item_storage_guard(item_id=item_id, preparation=True):
            await current()
            lease_task = asyncio.create_task(heartbeat())
            try:
                descriptor = item["preparation_descriptor"]
                await verified(0, len(descriptor["artifacts"]))
                async with measured_book_phase(item, "source_freezing"):
                    with book_phase(item, "source_freezing"):
                        frozen = await freeze_book_source(
                            owner_user_id=item["requested_by_user_id"],
                            parse_job_id=item["selected_source"]["parse_job_id"],
                            primary_artifact_id=item["selected_source"][
                                "primary_artifact_id"
                            ],
                            household_id=str(item["household_id"]),
                            textbook_id=str(item["textbook_id"]),
                            pinned_bundle=descriptor,
                            attempt_token=token,
                            before_write=before_write,
                            on_verified=verified,
                            check_cancelled=current,
                        )
                        await commit_prepared_book_source(
                            item_id=item_id, attempt_token=token, source=frozen.source
                        )
            finally:
                finished.set()
                await lease_task
        await publish_book_activity_hint(item["job_id"], None)
    except asyncio.CancelledError:
        # Shutdown leaves the lease for another process; user cancel is already durable.
        raise
    except Exception:
        try:
            if await prepared_book_source_is_committed(
                textbook_id=UUID(str(item["textbook_id"])),
                household_id=UUID(str(item["household_id"])),
                attempt_token=token,
            ):
                return
            result = await fail_book_item(
                item_id=item_id,
                attempt_token=token,
                safe_error="教材来源准备失败，请重试",
                stop_remaining=True,
            )
            await publish_book_activity_hint(
                item["job_id"], result.get("high_water_seq")
            )
        except RuntimeError:
            pass
        except Exception:
            logger.exception("Source preparation settlement deferred to recovery")
