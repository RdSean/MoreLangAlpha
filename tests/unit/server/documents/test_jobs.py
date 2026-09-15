from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.server.documents.contracts import (
    ParserIncompatibleError,
    ParserUnavailableError,
)
from src.server.documents.jobs import DocumentParseJobService
from src.server.documents.providers.registry import build_default_provider_registry


def _inspection(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "inspection_id": "ins-A1b2C3d4E5f6",
        "document_id": "doc-A1b2C3d4E5f6",
        "status": "completed",
        "detected_format": "pdf",
        "classification": "text_based",
    }
    row.update(overrides)
    return row


@pytest.mark.asyncio
async def test_create_job_persists_selected_parser_snapshot() -> None:
    repository = AsyncMock()
    repository.get_inspection.return_value = _inspection()
    repository.create_job.return_value = {"job_id": "job-A1b2C3d4E5f6"}
    service = DocumentParseJobService(
        document_repository=repository,
        job_repository=repository,
        provider_registry=build_default_provider_registry(),
        id_factory=lambda kind: "job-A1b2C3d4E5f6",
    )

    result = await service.create_job(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
        inspection_id="ins-A1b2C3d4E5f6",
        parser_id="anydoc-local",
        parser_options={"include_images": True},
        request_mode="async",
    )

    assert result == {"job_id": "job-A1b2C3d4E5f6"}
    call = repository.create_job.await_args.kwargs
    assert call["owner_user_id"] == "owner-1"
    assert call["parser_id"] == "anydoc-local"
    assert call["parser_name"] == "AnyDoc Local"
    assert call["parser_options"] == {"include_images": True}


@pytest.mark.asyncio
async def test_create_job_does_not_cross_document_or_owner_boundary() -> None:
    repository = AsyncMock()
    repository.get_inspection.return_value = _inspection(document_id="doc-other")
    service = DocumentParseJobService(
        document_repository=repository, job_repository=repository
    )

    result = await service.create_job(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
        inspection_id="ins-A1b2C3d4E5f6",
        parser_id="anydoc-local",
        parser_options={},
        request_mode="async",
    )

    assert result is None
    repository.create_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_job_rejects_unavailable_or_incompatible_parser() -> None:
    repository = AsyncMock()
    repository.get_inspection.return_value = _inspection(classification="scanned")
    service = DocumentParseJobService(
        document_repository=repository, job_repository=repository
    )

    with pytest.raises(ParserUnavailableError):
        await service.create_job(
            owner_user_id="owner-1",
            document_id="doc-A1b2C3d4E5f6",
            inspection_id="ins-A1b2C3d4E5f6",
            parser_id="ocr-document",
            parser_options={},
            request_mode="async",
        )

    with pytest.raises(ParserIncompatibleError):
        await service.create_job(
            owner_user_id="owner-1",
            document_id="doc-A1b2C3d4E5f6",
            inspection_id="ins-A1b2C3d4E5f6",
            parser_id="anydoc-local",
            parser_options={},
            request_mode="async",
        )


@pytest.mark.asyncio
async def test_open_artifact_download_is_owner_scoped_and_keeps_metadata() -> None:
    repository = AsyncMock()
    repository.get_artifact.return_value = {
        "storage_key": (
            "documents/doc-A1b2C3d4E5f6/artifacts/"
            "job-A1b2C3d4E5f6/教材.md"
        ),
        "relative_path": "教材.md",
        "media_type": "text/markdown",
    }
    opened = SimpleNamespace(
        chunks=iter([b"# Lesson\n"]),
        content_length=9,
        close=Mock(),
    )
    object_store = AsyncMock()
    object_store.open_download.return_value = opened
    service = DocumentParseJobService(
        document_repository=repository,
        job_repository=repository,
        object_store=object_store,
    )

    result = await service.open_artifact_download(
        owner_user_id="owner-1",
        artifact_id="art-A1b2C3d4E5f6",
    )

    assert result is not None
    assert result.filename == "教材.md"
    assert result.media_type == "text/markdown"
    assert result.object_download is opened
    repository.get_artifact.assert_awaited_once_with(
        owner_user_id="owner-1", artifact_id="art-A1b2C3d4E5f6"
    )
    object_store.open_download.assert_awaited_once_with(
        "documents/doc-A1b2C3d4E5f6/artifacts/"
        "job-A1b2C3d4E5f6/教材.md"
    )
