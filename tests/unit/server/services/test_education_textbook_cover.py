from unittest.mock import AsyncMock, Mock

import pytest

from src.server.services import education_textbook_cover as service
from src.server.services.education_textbooks import TextbookNotFoundError, TextbookPermissionError


def _upload(content_type="image/png", content=b"\x89PNG\r\n\x1a\ncover"):
    return service.CoverUpload(
        filename="cover.png", content_type=content_type, content=content
    )


def test_validate_cover_accepts_supported_image_signatures():
    assert service.validate_cover_upload(_upload()).content_type == "image/png"
    assert service.validate_cover_upload(
        _upload("image/jpeg", b"\xff\xd8\xffcover")
    ).content_type == "image/jpeg"


@pytest.mark.parametrize(
    "content_type,content",
    [
        ("application/pdf", b"%PDF-1.7"),
        ("image/png", b"not-png"),
        ("image/svg+xml", b"<svg></svg>"),
    ],
)
def test_validate_cover_rejects_unsupported_or_mismatched_uploads(content_type, content):
    with pytest.raises(ValueError):
        service.validate_cover_upload(_upload(content_type, content))


@pytest.mark.asyncio
async def test_set_cover_is_parent_only_and_replaces_old_object(monkeypatch):
    monkeypatch.setattr(service, "get_household_context_for_parent", AsyncMock(return_value={"household_id": "6eebf7fb-9579-4c5d-825a-2e595b7f1b18"}))
    monkeypatch.setattr(
        service,
        "get_managed_textbook_for_parent",
        AsyncMock(
            return_value={
                "textbook_id": "bc5734a8-8a30-459f-a1f3-8551feb4c169",
                "household_id": "6eebf7fb-9579-4c5d-825a-2e595b7f1b18",
                "cover_storage_key": "education/6eebf7fb-9579-4c5d-825a-2e595b7f1b18/textbooks/bc5734a8-8a30-459f-a1f3-8551feb4c169/cover/old.png",
            }
        ),
    )
    update = AsyncMock(return_value={"cover_storage_key": "new", "cover_available": True, "cover_updated_at": "now"})
    monkeypatch.setattr(service, "update_managed_textbook_cover", update)
    upload = Mock(return_value=True)
    monkeypatch.setattr(service, "upload_bytes", upload)
    remove = Mock(return_value=True)
    monkeypatch.setattr(service, "delete_object", remove)

    result = await service.replace_textbook_cover(
        parent_user_id="parent-1", textbook_id="bc5734a8-8a30-459f-a1f3-8551feb4c169", upload=_upload()
    )

    assert result["cover_available"] is True
    upload.assert_called_once()
    remove.assert_called_once_with(
        "education/6eebf7fb-9579-4c5d-825a-2e595b7f1b18/textbooks/bc5734a8-8a30-459f-a1f3-8551feb4c169/cover/old.png"
    )
    update.assert_awaited_once()


@pytest.mark.asyncio
async def test_remove_cover_does_not_cross_parent_boundary(monkeypatch):
    monkeypatch.setattr(service, "get_household_context_for_parent", AsyncMock(return_value={"household_id": "household-1"}))
    monkeypatch.setattr(
        service,
        "get_managed_textbook_for_parent",
        AsyncMock(return_value=None),
    )
    with pytest.raises(TextbookNotFoundError):
        await service.remove_textbook_cover(parent_user_id="other", textbook_id="book-1")

