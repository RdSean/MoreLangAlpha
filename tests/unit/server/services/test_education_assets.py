"""Contract tests for household-scoped education attachments."""

from unittest.mock import AsyncMock

import pytest

from src.server.services import education_assets


HOUSEHOLD_ID = "6eebf7fb-9579-4c5d-825a-2e595b7f1b18"
ASSET_ID = "bc5734a8-8a30-459f-a1f3-8551feb4c169"
MEMBER = {"user_id": "student-1", "household_id": HOUSEHOLD_ID, "role": "student"}
ASSET = {
    "asset_id": ASSET_ID,
    "household_id": HOUSEHOLD_ID,
    "created_by_user_id": "student-1",
    "original_filename": "worksheet.pdf",
    "content_type": "application/pdf",
    "size_bytes": 12,
    "storage_key": f"education/{HOUSEHOLD_ID}/{ASSET_ID}.pdf",
}


@pytest.mark.asyncio
async def test_parent_lists_candidate_assets_from_only_their_household(monkeypatch):
    parent = {"user_id": "parent-1", "household_id": HOUSEHOLD_ID, "role": "parent"}
    listed = [{**ASSET, "created_at": None}]
    monkeypatch.setattr(
        education_assets, "get_membership_for_user", AsyncMock(return_value=parent)
    )
    candidates = AsyncMock(return_value=listed)
    monkeypatch.setattr(education_assets, "list_education_assets_for_parent", candidates)

    result = await education_assets.list_parent_education_assets(user_id="parent-1")

    assert result == listed
    candidates.assert_awaited_once_with(parent_user_id="parent-1")


@pytest.mark.asyncio
async def test_student_cannot_list_parent_candidate_assets(monkeypatch):
    monkeypatch.setattr(
        education_assets, "get_membership_for_user", AsyncMock(return_value=MEMBER)
    )

    with pytest.raises(education_assets.EducationAssetAccessDeniedError):
        await education_assets.list_parent_education_assets(user_id="student-1")


def test_validate_upload_rejects_disallowed_content_type():
    with pytest.raises(education_assets.EducationAssetValidationError, match="content type"):
        education_assets.validate_upload(
            filename="worksheet.exe",
            content_type="application/octet-stream",
            content=b"not an attachment",
        )


def test_validate_upload_rejects_content_larger_than_the_education_limit(monkeypatch):
    monkeypatch.setattr(education_assets, "EDUCATION_ASSET_MAX_BYTES", 3)

    with pytest.raises(education_assets.EducationAssetValidationError, match="too large"):
        education_assets.validate_upload(
            filename="worksheet.pdf",
            content_type="application/pdf",
            content=b"%PDF",
        )


def test_build_storage_key_is_scoped_to_the_household_and_uses_the_mime_extension():
    key = education_assets.build_storage_key(
        household_id=HOUSEHOLD_ID,
        asset_id=ASSET_ID,
        content_type="application/pdf",
    )

    assert key == f"education/{HOUSEHOLD_ID}/{ASSET_ID}.pdf"


@pytest.mark.asyncio
async def test_create_asset_uploads_private_bytes_and_records_metadata(monkeypatch):
    monkeypatch.setattr(education_assets, "get_membership_for_user", AsyncMock(return_value=MEMBER))
    monkeypatch.setattr(education_assets, "insert_education_asset", AsyncMock(return_value=ASSET))
    uploads: list[tuple[str, bytes, str]] = []

    def upload(key: str, content: bytes, content_type: str) -> bool:
        uploads.append((key, content, content_type))
        return True

    monkeypatch.setattr(education_assets, "upload_bytes", upload)
    monkeypatch.setattr(education_assets, "uuid4", lambda: ASSET_ID)

    result = await education_assets.create_education_asset(
        user_id="student-1",
        filename="worksheet.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.7...",
    )

    assert result == ASSET
    assert uploads == [
        (f"education/{HOUSEHOLD_ID}/{ASSET_ID}.pdf", b"%PDF-1.7...", "application/pdf")
    ]


@pytest.mark.asyncio
async def test_create_asset_reuses_a_staged_upload_without_reuploading_bytes(monkeypatch):
    monkeypatch.setattr(education_assets, "get_membership_for_user", AsyncMock(return_value=MEMBER))
    staged = {**ASSET, "staging_key": "ec4075f0-6e7a-4f3d-bf56-c04121bbb395", "staging_slot": 0}
    find_staged = AsyncMock(return_value=staged)
    uploads = AsyncMock()
    monkeypatch.setattr(education_assets, "get_staged_education_asset", find_staged)
    monkeypatch.setattr(education_assets, "upload_bytes", uploads)

    result = await education_assets.create_education_asset(
        user_id="student-1",
        filename="worksheet.pdf",
        content_type="application/pdf",
        content=b"%PDF-1.7...",
        staging_key="ec4075f0-6e7a-4f3d-bf56-c04121bbb395",
        staging_slot=0,
    )

    assert result == staged
    find_staged.assert_awaited_once_with(
        household_id=HOUSEHOLD_ID,
        created_by_user_id="student-1",
        staging_key="ec4075f0-6e7a-4f3d-bf56-c04121bbb395",
        staging_slot=0,
    )
    uploads.assert_not_awaited()


@pytest.mark.asyncio
async def test_creator_deletes_storage_before_removing_unreferenced_metadata(monkeypatch):
    find_record = AsyncMock(return_value=ASSET)
    remove_record = AsyncMock(return_value=ASSET)
    removed_keys: list[str] = []
    monkeypatch.setattr(education_assets, "get_unreferenced_education_asset", find_record)
    monkeypatch.setattr(education_assets, "delete_unreferenced_education_asset", remove_record)
    monkeypatch.setattr(education_assets, "delete_object", lambda key: removed_keys.append(key) or True)

    await education_assets.delete_education_asset(user_id="student-1", asset_id=ASSET_ID)

    find_record.assert_awaited_once_with(asset_id=ASSET_ID, created_by_user_id="student-1")
    assert removed_keys == [ASSET["storage_key"]]
    remove_record.assert_awaited_once_with(asset_id=ASSET_ID, created_by_user_id="student-1")


@pytest.mark.asyncio
async def test_failed_storage_cleanup_preserves_metadata_for_a_retry(monkeypatch):
    find_record = AsyncMock(return_value=ASSET)
    remove_record = AsyncMock()
    monkeypatch.setattr(education_assets, "get_unreferenced_education_asset", find_record)
    monkeypatch.setattr(education_assets, "delete_unreferenced_education_asset", remove_record)
    monkeypatch.setattr(education_assets, "delete_object", lambda *_args: False)

    with pytest.raises(education_assets.EducationAssetStorageError, match="cleanup"):
        await education_assets.delete_education_asset(user_id="student-1", asset_id=ASSET_ID)

    remove_record.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_asset_removes_just_uploaded_object_when_metadata_write_fails(monkeypatch):
    monkeypatch.setattr(education_assets, "get_membership_for_user", AsyncMock(return_value=MEMBER))
    monkeypatch.setattr(
        education_assets,
        "insert_education_asset",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
    )
    monkeypatch.setattr(education_assets, "upload_bytes", lambda *_args: True)
    removed: list[str] = []
    monkeypatch.setattr(education_assets, "delete_object", lambda key: removed.append(key) or True)
    monkeypatch.setattr(education_assets, "uuid4", lambda: ASSET_ID)

    with pytest.raises(education_assets.EducationAssetPersistenceError):
        await education_assets.create_education_asset(
            user_id="student-1",
            filename="worksheet.pdf",
            content_type="application/pdf",
            content=b"%PDF-1.7...",
        )

    assert removed == [f"education/{HOUSEHOLD_ID}/{ASSET_ID}.pdf"]


@pytest.mark.asyncio
async def test_download_refuses_cross_household_access_without_signing_a_url(monkeypatch):
    monkeypatch.setattr(
        education_assets,
        "get_education_asset_for_user",
        AsyncMock(return_value=None),
    )
    signed = AsyncMock(return_value="https://storage.test/private-url")
    monkeypatch.setattr(education_assets, "get_signed_url", signed)

    with pytest.raises(education_assets.EducationAssetNotFoundError):
        await education_assets.get_education_asset_download_url(
            user_id="member-of-another-household",
            asset_id=ASSET_ID,
        )

    signed.assert_not_called()


@pytest.mark.asyncio
async def test_download_returns_a_short_lived_signed_url_for_household_member(monkeypatch):
    monkeypatch.setattr(
        education_assets,
        "get_education_asset_for_user",
        AsyncMock(return_value=ASSET),
    )
    monkeypatch.setattr(
        education_assets,
        "get_signed_url",
        lambda key, expires_in: f"https://storage.test/{key}?expires={expires_in}",
    )

    url = await education_assets.get_education_asset_download_url(
        user_id="student-1",
        asset_id=ASSET_ID,
    )

    assert url == f"https://storage.test/{ASSET['storage_key']}?expires=300"
