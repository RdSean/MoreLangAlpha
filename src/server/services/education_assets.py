"""Validation, private upload, and access-scoped download URLs for education assets."""

import asyncio
import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from src.config.env import (
    EDUCATION_ASSET_DOWNLOAD_TTL_SECONDS,
    EDUCATION_ASSET_MAX_BYTES,
)
from src.server.database.education_assets import (
    get_education_asset_for_user,
    get_staged_education_asset,
    insert_education_asset,
    list_education_assets_for_parent,
    delete_unreferenced_education_asset,
)
from src.server.database.education_members import get_membership_for_user
from src.utils.storage import delete_object, get_signed_url, upload_bytes


_CONTENT_TYPE_EXTENSIONS = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
_MAX_FILENAME_LENGTH = 255


class EducationAssetError(RuntimeError):
    """Base exception for education asset operations."""


class EducationAssetValidationError(EducationAssetError, ValueError):
    """The uploaded attachment is outside the accepted private-media contract."""


class EducationAssetAccessDeniedError(EducationAssetError, PermissionError):
    """The caller does not belong to an education household."""


class EducationAssetNotFoundError(EducationAssetError, LookupError):
    """The asset is absent or is outside the caller's household boundary."""


class EducationAssetStorageError(EducationAssetError):
    """The configured S3-compatible storage did not accept or sign an object."""


class EducationAssetPersistenceError(EducationAssetError):
    """Private metadata could not be persisted after a successful upload."""


@dataclass(frozen=True)
class ValidatedEducationUpload:
    """Safe upload input after MIME, signature, size, and filename checks."""

    filename: str
    content_type: str
    content: bytes


def _normalized_filename(filename: str | None) -> str:
    name = re.split(r"[\\/]", filename or "")[-1].strip()
    if not name or len(name) > _MAX_FILENAME_LENGTH:
        raise EducationAssetValidationError("A valid attachment filename is required")
    return name


def _content_matches_type(content_type: str, content: bytes) -> bool:
    if content_type == "application/pdf":
        return content.startswith(b"%PDF-")
    if content_type == "image/jpeg":
        return content.startswith(b"\xff\xd8\xff")
    if content_type == "image/png":
        return content.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/webp":
        return len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WEBP"
    return False


def validate_upload(
    *, filename: str | None, content_type: str | None, content: bytes
) -> ValidatedEducationUpload:
    """Validate the limited attachment formats allowed by the education product."""
    normalized_type = (content_type or "").strip().lower()
    if normalized_type not in _CONTENT_TYPE_EXTENSIONS:
        raise EducationAssetValidationError("Attachment content type is not allowed")
    if not content:
        raise EducationAssetValidationError("Attachment content cannot be empty")
    if len(content) > EDUCATION_ASSET_MAX_BYTES:
        raise EducationAssetValidationError("Attachment is too large")
    if not _content_matches_type(normalized_type, content):
        raise EducationAssetValidationError("Attachment content does not match its content type")
    return ValidatedEducationUpload(
        filename=_normalized_filename(filename),
        content_type=normalized_type,
        content=content,
    )


def build_storage_key(*, household_id: str, asset_id: str, content_type: str) -> str:
    """Build a private, non-user-controlled MinIO key under the education prefix."""
    household = str(UUID(str(household_id)))
    asset = str(UUID(str(asset_id)))
    extension = _CONTENT_TYPE_EXTENSIONS.get(content_type)
    if extension is None:
        raise EducationAssetValidationError("Attachment content type is not allowed")
    return f"education/{household}/{asset}{extension}"


def _normalized_staging_identity(
    *, staging_key: str | None, staging_slot: int | None,
) -> tuple[str | None, int | None]:
    if (staging_key is None) != (staging_slot is None):
        raise EducationAssetValidationError("Attachment staging key and slot must be provided together")
    if staging_key is None:
        return None, None
    if not 0 <= staging_slot <= 19:
        raise EducationAssetValidationError("Attachment staging slot is invalid")
    try:
        return str(UUID(str(staging_key))), staging_slot
    except (TypeError, ValueError) as exc:
        raise EducationAssetValidationError("Attachment staging key is invalid") from exc


async def create_education_asset(
    *, user_id: str, filename: str | None, content_type: str | None, content: bytes,
    staging_key: str | None = None, staging_slot: int | None = None,
) -> dict:
    """Upload private content, then persist metadata with compensating cleanup on failure."""
    upload = validate_upload(filename=filename, content_type=content_type, content=content)
    membership = await get_membership_for_user(user_id)
    if not membership:
        raise EducationAssetAccessDeniedError("Education household membership is required")

    normalized_staging_key, normalized_staging_slot = _normalized_staging_identity(
        staging_key=staging_key, staging_slot=staging_slot,
    )
    household_id = str(membership["household_id"])
    if normalized_staging_key is not None:
        existing_asset = await get_staged_education_asset(
            household_id=household_id,
            created_by_user_id=user_id,
            staging_key=normalized_staging_key,
            staging_slot=normalized_staging_slot,
        )
        if existing_asset:
            return existing_asset

    asset_id = str(uuid4())
    storage_key = build_storage_key(
        household_id=household_id,
        asset_id=asset_id,
        content_type=upload.content_type,
    )
    uploaded = await asyncio.to_thread(
        upload_bytes, storage_key, upload.content, upload.content_type
    )
    if not uploaded:
        raise EducationAssetStorageError("Attachment upload failed")

    try:
        asset = await insert_education_asset(
            asset_id=asset_id,
            household_id=household_id,
            created_by_user_id=user_id,
            storage_key=storage_key,
            original_filename=upload.filename,
            content_type=upload.content_type,
            size_bytes=len(upload.content),
            staging_key=normalized_staging_key,
            staging_slot=normalized_staging_slot,
        )
    except Exception as exc:
        await asyncio.to_thread(delete_object, storage_key)
        if normalized_staging_key is not None:
            existing_asset = await get_staged_education_asset(
                household_id=household_id,
                created_by_user_id=user_id,
                staging_key=normalized_staging_key,
                staging_slot=normalized_staging_slot,
            )
            if existing_asset:
                return existing_asset
        raise EducationAssetPersistenceError("Attachment metadata could not be saved") from exc

    if not asset:
        await asyncio.to_thread(delete_object, storage_key)
        raise EducationAssetAccessDeniedError("Education household membership is required")
    return asset


async def delete_education_asset(*, user_id: str, asset_id: str) -> None:
    """Remove an unreferenced creator-owned staged attachment and its private object."""
    asset = await delete_unreferenced_education_asset(
        asset_id=asset_id, created_by_user_id=user_id,
    )
    if not asset:
        return
    storage_key = asset["storage_key"]
    if not storage_key.startswith("education/"):
        raise EducationAssetPersistenceError("Education attachment key is invalid")
    deleted = await asyncio.to_thread(delete_object, storage_key)
    if not deleted:
        raise EducationAssetStorageError("Attachment cleanup is unavailable")


async def list_parent_education_assets(*, user_id: str) -> list[dict]:
    """Return reusable textbook-source metadata to a household parent only."""
    membership = await get_membership_for_user(user_id)
    if not membership or membership["role"] != "parent":
        raise EducationAssetAccessDeniedError(
            "Only a parent can list textbook source candidates"
        )
    return await list_education_assets_for_parent(parent_user_id=user_id)


async def get_education_asset_download_url(*, user_id: str, asset_id: str) -> str:
    """Generate a short-lived URL only after database-enforced household access."""
    asset = await get_education_asset_for_user(user_id=user_id, asset_id=asset_id)
    if not asset:
        raise EducationAssetNotFoundError("Attachment not found")
    url = await asyncio.to_thread(
        get_signed_url, asset["storage_key"], EDUCATION_ASSET_DOWNLOAD_TTL_SECONDS
    )
    if not url:
        raise EducationAssetStorageError("Attachment download is unavailable")
    return url
