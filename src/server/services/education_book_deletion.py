"""Retryable storage cleanup limited to one deleted textbook's namespace."""

import asyncio
import logging
from pathlib import PurePosixPath
from uuid import UUID

from src.server.database.education_book_deletion import (
    claim_textbook_cleanup,
    finish_textbook_cleanup,
)
from src.utils.storage import delete_object, is_storage_enabled, list_object_keys

logger = logging.getLogger(__name__)


async def delete_textbook_objects(*, household_id: UUID, textbook_id: UUID) -> None:
    prefix = f"education/{UUID(str(household_id))}/textbooks/{UUID(str(textbook_id))}/"
    if not is_storage_enabled():
        raise RuntimeError("Textbook storage is unavailable")
    keys = await asyncio.to_thread(list_object_keys, prefix, strict=True)
    if any(
        not key.startswith(prefix) or ".." in PurePosixPath(key).parts for key in keys
    ):
        raise RuntimeError("Textbook cleanup returned an invalid object key")
    for key in keys:
        if not await asyncio.to_thread(delete_object, key):
            raise RuntimeError("Textbook object deletion failed")


async def cleanup_deleted_textbooks_once(*, limit: int = 5) -> int:
    cleaned = 0
    for _ in range(limit):
        row = await claim_textbook_cleanup()
        if row is None:
            break
        succeeded = False
        try:
            await delete_textbook_objects(
                household_id=row["household_id"], textbook_id=row["textbook_id"]
            )
            succeeded = True
            cleaned += 1
        except Exception:
            logger.exception(
                "Deleted textbook object cleanup will retry: %s", row["textbook_id"]
            )
        await finish_textbook_cleanup(
            textbook_id=row["textbook_id"],
            lease_token=row["lease_token"],
            succeeded=succeeded,
        )
    return cleaned
