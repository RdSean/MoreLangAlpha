"""Private upload and temporary-download routes for education attachments."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from src.config.env import EDUCATION_ASSET_MAX_BYTES
from src.server.services.education_assets import (
    EducationAssetAccessDeniedError,
    EducationAssetNotFoundError,
    EducationAssetPersistenceError,
    EducationAssetStorageError,
    EducationAssetValidationError,
    create_education_asset,
    get_education_asset_download_url,
    list_parent_education_assets,
)
from src.server.utils.api import CurrentUserId


router = APIRouter(prefix="/api/v1/education/assets", tags=["Education assets"])


class EducationAssetResponse(BaseModel):
    """Client-safe metadata; the storage key never leaves the API."""

    asset_id: UUID
    household_id: UUID
    created_by_user_id: str
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime | None = None


class EducationAssetDownloadResponse(BaseModel):
    url: str


@router.get("", response_model=list[EducationAssetResponse])
async def list_education_assets(user_id: CurrentUserId):
    try:
        return await list_parent_education_assets(user_id=user_id)
    except EducationAssetAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.post(
    "",
    response_model=EducationAssetResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_201_CREATED,
)
async def upload_education_asset(
    user_id: CurrentUserId,
    file: UploadFile = File(...),
):
    """Proxy an attachment upload and return metadata without a durable URL."""
    content = await file.read(EDUCATION_ASSET_MAX_BYTES + 1)
    try:
        return await create_education_asset(
            user_id=user_id,
            filename=file.filename,
            content_type=file.content_type,
            content=content,
        )
    except EducationAssetValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EducationAssetAccessDeniedError as exc:
        raise HTTPException(status_code=403, detail="Education household membership is required") from exc
    except EducationAssetStorageError as exc:
        raise HTTPException(status_code=503, detail="Attachment storage is unavailable") from exc
    except EducationAssetPersistenceError as exc:
        raise HTTPException(status_code=500, detail="Attachment metadata could not be saved") from exc


@router.get("/{asset_id}/download", response_model=EducationAssetDownloadResponse)
async def get_education_asset_download(
    asset_id: UUID,
    user_id: CurrentUserId,
):
    """Return a short-lived download URL only to a member of the owning household."""
    try:
        url = await get_education_asset_download_url(user_id=user_id, asset_id=str(asset_id))
    except EducationAssetNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Attachment not found") from exc
    except EducationAssetStorageError as exc:
        raise HTTPException(status_code=503, detail="Attachment download is unavailable") from exc
    return EducationAssetDownloadResponse(url=url)
