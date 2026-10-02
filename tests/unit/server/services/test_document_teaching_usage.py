"""Current textbook usage projections for owned library documents."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.server.database import education_books
from src.server.services import document_teaching_usage


UPDATED_AT = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)


def _usage_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "document_id": "doc-A1b2C3d4E5f6",
        "parse_job_id": "job-A1b2C3d4E5f6",
        "primary_artifact_id": "art-A1b2C3d4E5f6",
        "textbook_id": "book-A1b2C3d4E5f6",
        "textbook_title": "Reading Explorer 3",
        "source_filename": "lesson.pdf",
        "source_completed_at": UPDATED_AT,
        "structure_status": "ready",
        "materials": {"ready": 4, "total": 7},
        "updated_at": UPDATED_AT,
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_repository_reads_current_textbooks_without_legacy_joins(
    mock_connection, mock_cursor, monkeypatch
) -> None:
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_books, "get_db_connection", fake_connection)
    expected = [_usage_row()]
    mock_cursor.fetchall.return_value = expected

    rows = await education_books.list_document_teaching_usages(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert rows == expected
    sql, params = mock_cursor.execute.await_args.args
    normalized_sql = " ".join(sql.split())
    assert "JOIN education_textbooks AS textbooks" in normalized_sql
    assert "textbooks.source_document_id = documents.document_id" in normalized_sql
    assert "textbooks.source_parse_job_id AS parse_job_id" in normalized_sql
    assert (
        "textbooks.source_primary_artifact_id AS primary_artifact_id" in normalized_sql
    )
    assert "textbooks.current_structure_id IS NOT NULL THEN 'ready'" in normalized_sql
    assert "education_book_knowledge_points AS points" in normalized_sql
    assert "education_book_materials AS materials" in normalized_sql
    assert "JOIN education_memberships AS memberships" in normalized_sql
    assert "memberships.role = 'parent'" in normalized_sql
    for legacy in (
        "education_textbook_artifact_sources",
        "education_textbook_versions",
        "education_textbook_structures",
        "education_textbook_publications",
    ):
        assert legacy not in normalized_sql
    assert params == ("owner-1", "doc-A1b2C3d4E5f6", "owner-1")


@pytest.mark.asyncio
async def test_repository_access_uses_current_textbook_households(
    mock_connection, mock_cursor, monkeypatch
) -> None:
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_books, "get_db_connection", fake_connection)
    mock_cursor.fetchone.return_value = {"can_read": False}

    can_read = await education_books.get_document_teaching_usage_access(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert can_read is False
    sql, params = mock_cursor.execute.await_args.args
    normalized_sql = " ".join(sql.split())
    assert "WITH usage_candidates AS" in normalized_sql
    assert "JOIN education_textbooks AS textbooks" in normalized_sql
    assert "textbooks.source_document_id = documents.document_id" in normalized_sql
    assert "JOIN education_memberships AS memberships" in normalized_sql
    assert "memberships.role = 'parent'" in normalized_sql
    assert "education_textbook_versions" not in normalized_sql
    assert params == (
        "doc-A1b2C3d4E5f6",
        "owner-1",
        "owner-1",
        "doc-A1b2C3d4E5f6",
        "owner-1",
    )


@pytest.mark.asyncio
async def test_service_projects_only_the_current_public_contract(monkeypatch) -> None:
    textbook_id = uuid4()
    repository = AsyncMock(
        return_value=[
            {
                **_usage_row(textbook_id=textbook_id),
                "source_snapshot_prefix": "education/private/source/",
                "source_markdown_key": "education/private/source/document.md",
                "content_version_id": "legacy-version",
                "publication_id": "legacy-publication",
                "credentials": "secret-token",
            }
        ]
    )
    monkeypatch.setattr(
        document_teaching_usage.education_book_repository,
        "list_document_teaching_usages",
        repository,
    )

    [usage] = await document_teaching_usage.list_document_teaching_usages(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert usage == _usage_row(textbook_id=str(textbook_id))
    serialized = json.dumps(usage, default=str)
    for unsafe_or_legacy in (
        "source_snapshot_prefix",
        "source_markdown_key",
        "content_version_id",
        "publication_id",
        "credentials",
        "education/private",
        "secret-token",
    ):
        assert unsafe_or_legacy not in serialized
    repository.assert_awaited_once_with(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )


@pytest.mark.asyncio
async def test_service_preserves_all_current_structure_states(monkeypatch) -> None:
    rows = [
        _usage_row(structure_status=status, materials={"ready": 0, "total": 0})
        for status in ("queued", "running", "ready", "failed")
    ]
    monkeypatch.setattr(
        document_teaching_usage.education_book_repository,
        "list_document_teaching_usages",
        AsyncMock(return_value=rows),
    )

    usage = await document_teaching_usage.list_document_teaching_usages(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert [row["structure_status"] for row in usage] == [
        "queued",
        "running",
        "ready",
        "failed",
    ]


@pytest.mark.asyncio
async def test_service_delegates_current_membership_access(monkeypatch) -> None:
    repository = AsyncMock(return_value=False)
    monkeypatch.setattr(
        document_teaching_usage.education_book_repository,
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
async def test_service_returns_empty_for_a_foreign_owner(monkeypatch) -> None:
    repository = AsyncMock(return_value=[])
    monkeypatch.setattr(
        document_teaching_usage.education_book_repository,
        "list_document_teaching_usages",
        repository,
    )

    usage = await document_teaching_usage.list_document_teaching_usages(
        owner_user_id="foreign-owner",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert usage == []
