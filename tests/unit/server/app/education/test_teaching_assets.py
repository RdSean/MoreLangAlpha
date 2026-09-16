"""HTTP boundary tests for private managed teaching assets."""

from hashlib import sha256
from unittest.mock import AsyncMock, Mock, call, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.server.app.education.textbooks import router
from src.server.services import (
    education_managed_ptc,
    education_teaching_jobs,
    education_textbooks,
)
from src.server.services.education_textbooks import TextbookPermissionError
from src.server.utils.api import get_current_user_id


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as session:
        yield session


@pytest.mark.asyncio
async def test_parent_reads_safe_managed_asset_summary_without_storage_fields(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    package_id, chapter_id = uuid4(), uuid4()
    summary = {
        "teaching_package_id": package_id,
        "format": "langalpha-family-teaching-assets/v2",
        "concept_index": {"size_bytes": 12, "concept_count": 2},
        "coverage_audit": {"size_bytes": 20, "status": "complete"},
        "chapters": [
            {
                "chapter_id": chapter_id,
                "position": 1,
                "title": "导读",
                "coverage_status": "complete",
                "concept_count": 2,
                "assets": [{"kind": "toolkit", "size_bytes": 18}],
            }
        ],
        "bundle_prefix": "education/private/package",
        "storage_key": "education/private/package/manifest.json",
        "managed_path": "/managed/textbook-job/private",
    }
    with patch(
        "src.server.app.education.textbooks.get_teaching_asset_summary",
        new=AsyncMock(return_value=summary),
        create=True,
    ) as get_summary:
        response = await client.get(
            f"/api/v1/education/teaching-packages/{package_id}/assets"
        )

    assert response.status_code == 200
    assert response.json()["chapters"][0]["chapter_id"] == str(chapter_id)
    assert "education/" not in response.text
    assert "storage_key" not in response.text
    assert "/managed/" not in response.text
    get_summary.assert_awaited_once_with(
        parent_user_id="parent-1", teaching_package_id=str(package_id)
    )


@pytest.mark.asyncio
async def test_formal_asset_reads_use_only_db_and_object_storage_when_runtime_unavailable(
    client, monkeypatch
):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    package_id, chapter_id = uuid4(), uuid4()
    toolkit = "# 导读工具包\n\n核心概念".encode()
    review = {
        "teaching_package_id": str(package_id),
        "bundle_prefix": "education/household-1/english-2/v1/teaching/v2",
        "asset_manifest": {
            "format": "langalpha-family-teaching-assets/v2",
            "concept_index": {"size_bytes": 2, "concept_count": 1},
            "coverage_audit": {"size_bytes": 2, "status": "complete"},
            "chapters": [
                {
                    "content_chapter_id": str(chapter_id),
                    "content_sha256": "a" * 64,
                    "coverage_status": "complete",
                    "concept_count": 1,
                    "assets": [
                        {"kind": "knowledge", "size_bytes": 0, "sha256": "b" * 64},
                        {
                            "kind": "toolkit",
                            "size_bytes": len(toolkit),
                            "sha256": sha256(toolkit).hexdigest(),
                        },
                        {"kind": "practice", "size_bytes": 0, "sha256": "c" * 64},
                    ],
                }
            ],
        },
        "chapters": [
            {
                "content_chapter_id": str(chapter_id),
                "position": 1,
                "slug": "overview",
                "title": "导读",
            }
        ],
    }
    get_review = AsyncMock(return_value=review)
    get_object = Mock(return_value=toolkit)
    runtime_unavailable = AsyncMock(
        side_effect=AssertionError("sandbox runtime must not be used")
    )
    monkeypatch.setattr(
        education_textbooks, "get_teaching_asset_review_for_parent", get_review
    )
    monkeypatch.setattr(education_textbooks, "get_bytes", get_object)
    monkeypatch.setattr(
        education_managed_ptc, "launch_teaching_attempt", runtime_unavailable
    )
    monkeypatch.setattr(
        education_managed_ptc, "resume_teaching_job", runtime_unavailable
    )
    monkeypatch.setattr(
        education_teaching_jobs, "cancel_teaching_job", runtime_unavailable
    )

    summary = await client.get(
        f"/api/v1/education/teaching-packages/{package_id}/assets"
    )
    chapter = await client.get(
        f"/api/v1/education/teaching-packages/{package_id}/chapters/{chapter_id}/assets/toolkit"
    )

    assert summary.status_code == 200
    assert summary.json()["teaching_package_id"] == str(package_id)
    assert summary.json()["chapters"][0]["chapter_id"] == str(chapter_id)
    assert chapter.status_code == 200
    assert chapter.json() == {
        "teaching_package_id": str(package_id),
        "chapter_id": str(chapter_id),
        "kind": "toolkit",
        "content": toolkit.decode(),
    }
    assert get_review.await_args_list == [
        call(parent_user_id="parent-1", teaching_package_id=str(package_id)),
        call(parent_user_id="parent-1", teaching_package_id=str(package_id)),
    ]
    get_object.assert_called_once_with(
        "education/household-1/english-2/v1/teaching/v2/chapters/01-overview-toolkit.md"
    )
    runtime_unavailable.assert_not_awaited()


@pytest.mark.asyncio
async def test_parent_reads_one_safe_chapter_asset(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-1"
    package_id, chapter_id = uuid4(), uuid4()
    asset = {
        "teaching_package_id": package_id,
        "chapter_id": chapter_id,
        "kind": "toolkit",
        "content": "# 导读工具包",
        "storage_key": "education/private/toolkit.md",
    }
    with patch(
        "src.server.app.education.textbooks.get_teaching_chapter_asset",
        new=AsyncMock(return_value=asset),
        create=True,
    ) as get_asset:
        response = await client.get(
            f"/api/v1/education/teaching-packages/{package_id}/chapters/{chapter_id}/assets/toolkit"
        )

    assert response.status_code == 200
    assert response.json()["content"] == "# 导读工具包"
    assert "storage_key" not in response.text
    get_asset.assert_awaited_once_with(
        parent_user_id="parent-1",
        teaching_package_id=str(package_id),
        chapter_id=str(chapter_id),
        kind="toolkit",
    )


@pytest.mark.asyncio
async def test_student_and_unknown_kind_cannot_read_parent_teaching_assets(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"
    package_id, chapter_id = uuid4(), uuid4()
    with patch(
        "src.server.app.education.textbooks.get_teaching_asset_summary",
        new=AsyncMock(
            side_effect=TextbookPermissionError(
                "Only a parent can review teaching assets"
            )
        ),
        create=True,
    ):
        denied = await client.get(
            f"/api/v1/education/teaching-packages/{package_id}/assets"
        )
    unknown_kind = await client.get(
        f"/api/v1/education/teaching-packages/{package_id}/chapters/{chapter_id}/assets/raw-model-output"
    )

    assert denied.status_code == 403
    assert unknown_kind.status_code == 422
