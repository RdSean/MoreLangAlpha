"""Household-owned textbook cover uploads and reads."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from src.server.database.education_books import (
    get_managed_textbook_cover_for_user,
    update_managed_textbook_cover,
)
from src.server.database.education_tasks import get_household_context_for_parent
from src.server.services.education_textbooks import (
    TextbookNotFoundError,
    TextbookPermissionError,
)
from src.server.database.education_books import get_managed_textbook_for_parent
from src.utils.storage import delete_object, get_bytes, upload_bytes


logger = logging.getLogger(__name__)

MAX_COVER_BYTES = 10 * 1024 * 1024
_FILENAME_RE = re.compile(r"[^\w.()@+\- ]", re.UNICODE)
_TYPES = {
    "image/png": (".png", b"\x89PNG\r\n\x1a\n"),
    "image/jpeg": (".jpg", b"\xff\xd8\xff"),
    "image/webp": (".webp", None),
}


class TextbookCoverError(RuntimeError):
    """Base error for cover operations."""


class TextbookCoverValidationError(TextbookCoverError, ValueError):
    """The uploaded cover is not a supported image."""


class TextbookCoverStorageError(TextbookCoverError):
    """Cover bytes could not be stored or read."""


@dataclass(frozen=True)
class CoverUpload:
    filename: str
    content_type: str
    content: bytes


def _safe_filename(filename: str | None) -> str:
    name = re.split(r"[\\/]", filename or "")[-1].strip()
    name = _FILENAME_RE.sub("_", name)
    if not name or len(name) > 255:
        raise TextbookCoverValidationError("封面文件名无效")
    return name


def validate_cover_upload(upload: CoverUpload) -> CoverUpload:
    content_type = upload.content_type.split(";", 1)[0].strip().lower()
    descriptor = _TYPES.get(content_type)
    if descriptor is None:
        raise TextbookCoverValidationError("封面仅支持 PNG、JPEG 或 WebP 图片")
    if not upload.content or len(upload.content) > MAX_COVER_BYTES:
        raise TextbookCoverValidationError("封面图片不能为空且不能超过 10 MB")
    magic = descriptor[1]
    valid = upload.content.startswith(magic) if magic else (
        len(upload.content) >= 12
        and upload.content.startswith(b"RIFF")
        and upload.content[8:12] == b"WEBP"
    )
    if not valid:
        raise TextbookCoverValidationError("封面内容与文件类型不匹配")
    return CoverUpload(
        filename=_safe_filename(upload.filename),
        content_type=content_type,
        content=upload.content,
    )


def _cover_result(row: dict) -> dict:
    return {
        "cover_available": bool(row.get("cover_storage_key")),
        "cover_filename": row.get("cover_filename"),
        "cover_content_type": row.get("cover_content_type"),
        "cover_size_bytes": row.get("cover_size_bytes"),
        "cover_sha256": row.get("cover_sha256"),
        "cover_updated_at": row.get("cover_updated_at"),
    }


async def replace_textbook_cover(
    *, parent_user_id: str, textbook_id: str | UUID, upload: CoverUpload
) -> dict:
    context = await get_household_context_for_parent(parent_user_id)
    if context is None:
        raise TextbookPermissionError("只有家长可以设置教材封面")
    book = await get_managed_textbook_for_parent(
        parent_user_id=parent_user_id, textbook_id=textbook_id
    )
    if book is None:
        raise TextbookNotFoundError("教材不存在")
    validated = validate_cover_upload(upload)
    extension = _TYPES[validated.content_type][0]
    key = (
        f"education/{UUID(str(context['household_id']))}/textbooks/"
        f"{UUID(str(textbook_id))}/cover/{uuid4()}{extension}"
    )
    uploaded = await asyncio.to_thread(
        upload_bytes, key, validated.content, validated.content_type, MAX_COVER_BYTES
    )
    if not uploaded:
        raise TextbookCoverStorageError("封面上传失败，请稍后重试")
    digest = hashlib.sha256(validated.content).hexdigest()
    try:
        updated = await update_managed_textbook_cover(
            textbook_id=textbook_id,
            storage_key=key,
            filename=validated.filename,
            content_type=validated.content_type,
            size_bytes=len(validated.content),
            sha256=digest,
        )
    except Exception:
        await asyncio.to_thread(delete_object, key)
        raise
    if updated is None:
        await asyncio.to_thread(delete_object, key)
        raise TextbookNotFoundError("教材不存在")
    old_key = book.get("cover_storage_key")
    if old_key and old_key != key:
        if not await asyncio.to_thread(delete_object, old_key):
            logger.warning("Could not delete replaced textbook cover %s", old_key)
    return _cover_result(updated)


async def remove_textbook_cover(
    *, parent_user_id: str, textbook_id: str | UUID
) -> dict:
    context = await get_household_context_for_parent(parent_user_id)
    if context is None:
        raise TextbookPermissionError("只有家长可以移除教材封面")
    book = await get_managed_textbook_for_parent(
        parent_user_id=parent_user_id, textbook_id=textbook_id
    )
    if book is None:
        raise TextbookNotFoundError("教材不存在")
    updated = await update_managed_textbook_cover(
        textbook_id=textbook_id, storage_key=None, filename=None,
        content_type=None, size_bytes=None, sha256=None,
    )
    if updated is None:
        raise TextbookNotFoundError("教材不存在")
    old_key = book.get("cover_storage_key")
    if old_key and not await asyncio.to_thread(delete_object, old_key):
        logger.warning("Could not delete textbook cover %s", old_key)
    return _cover_result(updated)


async def open_textbook_cover(*, user_id: str, textbook_id: str | UUID) -> dict:
    row = await get_managed_textbook_cover_for_user(
        user_id=user_id, textbook_id=textbook_id
    )
    if row is None:
        raise TextbookNotFoundError("教材不存在")
    key = row.get("cover_storage_key")
    if not key:
        raise TextbookNotFoundError("教材尚未设置封面")
    content = await asyncio.to_thread(get_bytes, key)
    if content is None:
        raise TextbookCoverStorageError("教材封面暂不可用")
    return {"content": content, "media_type": row["cover_content_type"], "sha256": row["cover_sha256"]}
