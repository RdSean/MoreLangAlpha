"""Safe, artifact-backed textbook usage read-model contracts."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.server.database import education_textbooks
from src.server.services import document_teaching_usage


CREATED_AT = datetime(2026, 9, 16, 12, 0, tzinfo=UTC)


def _usage_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "document_id": "doc-A1b2C3d4E5f6",
        "producer_job_id": "job-A1b2C3d4E5f6",
        "primary_artifact_id": "art-A1b2C3d4E5f6",
        "textbook_id": "book-A1b2C3d4E5f6",
        "textbook_title": "Reading Explorer 3",
        "content_version_id": "ver-A1b2C3d4E5f6",
        "content_version_sequence": 2,
        "artifact_position": 1,
        "teaching_package_id": "pkg-A1b2C3d4E5f6",
        "teaching_package_sequence": 1,
        "status": "review",
        "publication_id": None,
        "is_published": False,
        "has_asset_manifest": True,
        "created_at": CREATED_AT,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_repository_reads_only_artifact_backed_usage_for_the_owner(
    mock_connection, mock_cursor, monkeypatch
) -> None:
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    expected = [_usage_row()]
    mock_cursor.fetchall.return_value = expected

    rows = await education_textbooks.list_document_teaching_usages(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert rows == expected
    sql, params = mock_cursor.execute.await_args.args
    normalized_sql = " ".join(sql.split())
    assert "JOIN education_textbook_artifact_sources AS sources" in normalized_sql
    assert "JOIN education_textbook_versions AS versions" in normalized_sql
    assert "JOIN education_textbooks AS textbooks" in normalized_sql
    assert (
        "JOIN education_memberships AS memberships "
        "ON memberships.household_id = textbooks.household_id "
        "AND memberships.user_id = documents.owner_user_id "
        "AND memberships.role = 'parent'" in normalized_sql
    )
    assert "LEFT JOIN education_teaching_packages AS packages" in normalized_sql
    assert "LEFT JOIN education_teaching_jobs AS jobs" in normalized_sql
    assert (
        "LEFT JOIN education_textbook_publications AS publications "
        "ON publications.version_id = versions.version_id "
        "AND publications.teaching_package_id = packages.teaching_package_id"
        in normalized_sql
    )
    assert "documents.owner_user_id = %s" in normalized_sql
    assert "sources.position AS artifact_position" in normalized_sql
    assert "COALESCE(" in normalized_sql
    assert "packages.asset_manifest <> '{}'::jsonb" in normalized_sql
    assert "FALSE" in normalized_sql
    assert "AS has_asset_manifest" in normalized_sql
    assert "publications.publication_id" in normalized_sql
    assert (
        "publications.publication_id IS NOT NULL AS is_published"
        in normalized_sql
    )
    assert "education_textbook_sources" not in normalized_sql
    assert "education_assets" not in normalized_sql
    assert "snapshot_prefix" not in normalized_sql
    assert "bundle_prefix" not in normalized_sql
    assert "storage_key" not in normalized_sql
    assert params == ("doc-A1b2C3d4E5f6", "owner-1")


@pytest.mark.asyncio
async def test_service_normalizes_database_uuid_columns_for_the_api(
    monkeypatch,
) -> None:
    textbook_id = uuid4()
    content_version_id = uuid4()
    teaching_package_id = uuid4()
    publication_id = uuid4()
    row = _usage_row(
        textbook_id=textbook_id,
        content_version_id=content_version_id,
        teaching_package_id=teaching_package_id,
        publication_id=publication_id,
    )
    monkeypatch.setattr(
        document_teaching_usage.education_textbook_repository,
        "list_document_teaching_usages",
        AsyncMock(return_value=[row]),
    )

    [usage] = await document_teaching_usage.list_document_teaching_usages(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert usage["textbook_id"] == str(textbook_id)
    assert usage["content_version_id"] == str(content_version_id)
    assert usage["teaching_package_id"] == str(teaching_package_id)
    assert usage["publication_id"] == str(publication_id)


@pytest.mark.asyncio
async def test_repository_access_requires_current_parent_membership(
    mock_connection, mock_cursor, monkeypatch
) -> None:
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = {"can_read": False}

    can_read = await education_textbooks.get_document_teaching_usage_access(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert can_read is False
    sql, params = mock_cursor.execute.await_args.args
    normalized_sql = " ".join(sql.split())
    assert "WITH usage_candidates AS" in normalized_sql
    assert "JOIN education_memberships AS memberships" in normalized_sql
    assert (
        "memberships.household_id = usage_candidates.household_id"
        in normalized_sql
    )
    assert "memberships.user_id = %s" in normalized_sql
    assert "memberships.role = 'parent'" in normalized_sql
    assert "documents.owner_user_id = %s" in normalized_sql
    assert params == (
        "doc-A1b2C3d4E5f6",
        "owner-1",
        "owner-1",
        "doc-A1b2C3d4E5f6",
        "owner-1",
    )


@pytest.mark.asyncio
async def test_service_denies_usage_without_current_parent_membership(
    monkeypatch,
) -> None:
    repository = AsyncMock(return_value=False)
    monkeypatch.setattr(
        document_teaching_usage.education_textbook_repository,
        "get_document_teaching_usage_access",
        repository,
    )

    can_read = await document_teaching_usage.can_read_document_teaching_usage(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert can_read is False
    repository.assert_awaited_once_with(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )


@pytest.mark.asyncio
async def test_service_keeps_review_failed_cancelled_and_unpackaged_usage(
    monkeypatch,
) -> None:
    rows = [
        _usage_row(),
        _usage_row(
            teaching_package_id="pkg-failed",
            teaching_package_sequence=2,
            status="failed",
            has_asset_manifest=False,
        ),
        _usage_row(
            teaching_package_id="pkg-cancelled",
            teaching_package_sequence=3,
            status="cancelled",
            has_asset_manifest=False,
        ),
        _usage_row(
            teaching_package_id=None,
            teaching_package_sequence=None,
            status=None,
            has_asset_manifest=False,
        ),
    ]
    repository = AsyncMock(return_value=rows)
    monkeypatch.setattr(
        document_teaching_usage.education_textbook_repository,
        "list_document_teaching_usages",
        repository,
    )

    usage = await document_teaching_usage.list_document_teaching_usages(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert [row["status"] for row in usage] == [
        "review",
        "failed",
        "cancelled",
        None,
    ]
    assert usage[1]["has_asset_manifest"] is False
    assert usage[2]["has_asset_manifest"] is False
    assert usage[3]["teaching_package_id"] is None
    assert usage[3]["teaching_package_sequence"] is None
    repository.assert_awaited_once_with(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )


@pytest.mark.asyncio
async def test_service_marks_review_package_published_by_publication(
    monkeypatch,
) -> None:
    published = _usage_row(
        publication_id="publication-A1b2C3d4E5f6",
        is_published=True,
    )
    repository = AsyncMock(return_value=[published])
    monkeypatch.setattr(
        document_teaching_usage.education_textbook_repository,
        "list_document_teaching_usages",
        repository,
    )

    usage = await document_teaching_usage.list_document_teaching_usages(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert usage[0]["status"] == "review"
    assert usage[0]["publication_id"] == "publication-A1b2C3d4E5f6"
    assert usage[0]["is_published"] is True


@pytest.mark.asyncio
async def test_service_returns_empty_for_a_foreign_owner(monkeypatch) -> None:
    repository = AsyncMock(return_value=[])
    monkeypatch.setattr(
        document_teaching_usage.education_textbook_repository,
        "list_document_teaching_usages",
        repository,
    )

    usage = await document_teaching_usage.list_document_teaching_usages(
        owner_user_id="foreign-owner",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert usage == []
    repository.assert_awaited_once_with(
        owner_user_id="foreign-owner",
        document_id="doc-A1b2C3d4E5f6",
    )


@pytest.mark.asyncio
async def test_service_projects_only_safe_public_fields(monkeypatch) -> None:
    repository = AsyncMock(
        return_value=[
            {
                **_usage_row(),
                "snapshot_prefix": "education/household/book/source-bundles/secret/",
                "storage_key": "education/private/source.pdf",
                "object_url": "https://objects.invalid/private?token=secret",
                "sandbox_path": "/workspace/private/source.md",
                "raw_model_output": "private model output",
                "credentials": "secret-token",
            }
        ]
    )
    monkeypatch.setattr(
        document_teaching_usage.education_textbook_repository,
        "list_document_teaching_usages",
        repository,
    )

    usage = await document_teaching_usage.list_document_teaching_usages(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert usage == [_usage_row()]
    serialized = json.dumps(usage, default=str)
    for unsafe in (
        "snapshot_prefix",
        "storage_key",
        "object_url",
        "sandbox_path",
        "raw_model_output",
        "credentials",
        "education/",
        "objects.invalid",
        "secret-token",
    ):
        assert unsafe not in serialized
