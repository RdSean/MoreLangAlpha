from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.server.documents.contracts import FileTooLargeError, ParserUnavailableError
from src.server.documents.inspection import InspectionOutcome
from src.server.documents.providers.registry import build_default_provider_registry
from src.server.utils.api import get_current_user_id


DOC_ID = "doc-A1b2C3d4E5f6"
INS_ID = "ins-A1b2C3d4E5f6"
JOB_ID = "job-A1b2C3d4E5f6"
ART_ID = "art-A1b2C3d4E5f6"


def _document() -> dict[str, object]:
    return {
        "document_id": DOC_ID,
        "original_filename": "lesson.pdf",
        "media_type": "application/pdf",
        "document_format": "pdf",
        "source_size_bytes": 9,
        "source_sha256": "a" * 64,
        "dataset_ids": [],
        "tag_ids": [],
    }


def _inspection() -> dict[str, object]:
    return {
        "inspection_id": INS_ID,
        "document_id": DOC_ID,
        "inspector_id": "pdf-inspector",
        "inspector_name": "PDF Inspector",
        "inspector_version": "1.17.0",
        "status": "completed",
        "detected_format": "pdf",
        "classification": "text_based",
        "summary": {"page_count": 2, "page_size": "A4"},
        "details": {},
    }


def _job(status: str = "queued", version: int = 0) -> dict[str, object]:
    return {
        "job_id": JOB_ID,
        "document_id": DOC_ID,
        "inspection_id": INS_ID,
        "parser_id": "anydoc-local",
        "parser_name": "AnyDoc",
        "parser_version": "0.2.4",
        "parser_options": {},
        "request_mode": "async",
        "status": status,
        "stage": "completed" if status == "completed" else "queued",
        "percentage": 100 if status == "completed" else 0,
        "status_version": version,
        "attempt_count": 0,
    }


def _teaching_usage() -> dict[str, object]:
    return {
        "document_id": DOC_ID,
        "producer_job_id": JOB_ID,
        "primary_artifact_id": ART_ID,
        "textbook_id": "book-A1b2C3d4E5f6",
        "textbook_title": "Reading Explorer 3",
        "content_version_id": "ver-A1b2C3d4E5f6",
        "content_version_sequence": 2,
        "artifact_position": 1,
        "teaching_package_id": "pkg-A1b2C3d4E5f6",
        "teaching_package_sequence": 1,
        "status": "review",
        "has_asset_manifest": True,
        "created_at": "2026-09-16T12:00:00Z",
    }


class _Services:
    def __init__(self) -> None:
        self.library = AsyncMock()
        self.inspections = AsyncMock()
        self.jobs = AsyncMock()
        self.events = AsyncMock()
        self.teaching_usage = AsyncMock(return_value=[])
        self.library.upload_pdf.return_value = _document()
        self.library.list_documents.return_value = ([_document()], 1)
        self.library.list_datasets.return_value = ([], 0)
        self.library.list_tags.return_value = []
        self.inspections.inspect.return_value = InspectionOutcome(
            inspection=_inspection(),
            parser_options=build_default_provider_registry().parser_options(
                document_format="pdf", classification="text_based"
            ),
        )
        self.jobs.create_job.return_value = _job()
        self.events.wait_for_terminal_job.return_value = _job("completed", 3)


@pytest_asyncio.fixture
async def api(monkeypatch):
    from src.server.app import documents
    from src.server.app.documents import (
        get_document_event_service,
        get_document_inspection_service,
        get_document_job_service,
        get_document_library_service,
        router,
    )

    services = _Services()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user_id] = lambda: "owner-1"
    app.dependency_overrides[get_document_library_service] = lambda: services.library
    app.dependency_overrides[get_document_inspection_service] = (
        lambda: services.inspections
    )
    app.dependency_overrides[get_document_job_service] = lambda: services.jobs
    app.dependency_overrides[get_document_event_service] = lambda: services.events
    monkeypatch.setattr(
        documents,
        "list_document_teaching_usages",
        services.teaching_usage,
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, services


@pytest.mark.asyncio
async def test_upload_is_multipart_and_does_not_start_inspection(api) -> None:
    client, services = api
    captured: dict[str, object] = {}

    async def upload(**kwargs):
        captured.update(kwargs)
        captured["body"] = b"".join([chunk async for chunk in kwargs["chunks"]])
        return _document()

    services.library.upload_pdf.side_effect = upload
    response = await client.post(
        "/api/v1/documents",
        files={"file": ("lesson.pdf", b"%PDF-demo", "application/pdf")},
        data={
            "dataset_ids": ["dts-A1b2C3d4E5f6"],
            "tag_ids": ["tag-A1b2C3d4E5f6"],
        },
    )

    assert response.status_code == 201
    assert captured["owner_user_id"] == "owner-1"
    assert captured["dataset_ids"] == ("dts-A1b2C3d4E5f6",)
    assert captured["tag_ids"] == ("tag-A1b2C3d4E5f6",)
    assert captured["body"] == b"%PDF-demo"
    services.inspections.inspect.assert_not_awaited()
    services.jobs.create_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_upload_maps_size_failure_to_413(api) -> None:
    client, services = api
    services.library.upload_pdf.side_effect = FileTooLargeError("too large")

    response = await client.post(
        "/api/v1/documents",
        files={"file": ("large.pdf", b"%PDF-x", "application/pdf")},
    )

    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "file_too_large"


@pytest.mark.asyncio
async def test_document_list_passes_server_side_filters_and_pagination(api) -> None:
    client, services = api
    response = await client.get(
        "/api/v1/documents",
        params={
            "query": "lesson",
            "dataset_id": "dts-A1b2C3d4E5f6",
            "tag_ids": ["tag-A1b2C3d4E5f6", "tag-Z9y8X7w6V5u4"],
            "classification": "text_based",
            "parse_status": "completed",
            "limit": 20,
            "offset": 40,
        },
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1
    filters = services.library.list_documents.await_args.kwargs["filters"]
    assert filters.query == "lesson"
    assert filters.tag_ids == ("tag-A1b2C3d4E5f6", "tag-Z9y8X7w6V5u4")
    assert (filters.limit, filters.offset) == (20, 40)


@pytest.mark.asyncio
async def test_inspection_returns_summary_and_recommendations_without_job(api) -> None:
    client, services = api
    response = await client.post(f"/api/v1/documents/{DOC_ID}/inspections")

    assert response.status_code == 201
    assert response.json()["inspection"]["classification"] == "text_based"
    assert response.json()["parser_options"][0]["recommended"] is True
    services.jobs.create_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_parse_job_sync_and_async_status_codes(api) -> None:
    client, services = api
    payload = {"inspection_id": INS_ID, "parser_id": "anydoc-local"}

    async_response = await client.post(
        f"/api/v1/documents/{DOC_ID}/parse-jobs", json=payload
    )
    assert async_response.status_code == 202

    sync_response = await client.post(
        f"/api/v1/documents/{DOC_ID}/parse-jobs",
        json={**payload, "mode": "sync"},
    )
    assert sync_response.status_code == 200
    assert sync_response.json()["status"] == "completed"

    services.events.wait_for_terminal_job.return_value = _job("running", 2)
    pending_response = await client.post(
        f"/api/v1/documents/{DOC_ID}/parse-jobs",
        json={**payload, "mode": "sync"},
    )
    assert pending_response.status_code == 202


@pytest.mark.asyncio
async def test_unavailable_parser_maps_to_409(api) -> None:
    client, services = api
    services.jobs.create_job.side_effect = ParserUnavailableError("not available")

    response = await client.post(
        f"/api/v1/documents/{DOC_ID}/parse-jobs",
        json={"inspection_id": INS_ID, "parser_id": "ocr-document"},
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "parser_unavailable"


@pytest.mark.asyncio
async def test_job_events_emit_owned_database_snapshots_as_sse(api) -> None:
    client, services = api

    async def snapshots(**kwargs):
        yield _job("running", 2)
        yield _job("completed", 3)

    services.events.snapshots = snapshots
    response = await client.get(
        f"/api/v1/document-jobs/{JOB_ID}/events?after_status_version=1"
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    frames = [line for line in response.text.splitlines() if line.startswith("data: ")]
    assert json.loads(frames[-1][6:])["status"] == "completed"


@pytest.mark.asyncio
async def test_artifact_download_streams_through_the_authenticated_api(api) -> None:
    client, services = api
    close = Mock()
    services.jobs.open_artifact_download.return_value = SimpleNamespace(
        filename="教材.md",
        media_type="text/markdown",
        object_download=SimpleNamespace(
            chunks=iter([b"# Lesson\n"]),
            content_length=len(b"# Lesson\n"),
            close=close,
        ),
    )

    response = await client.get(
        f"/api/v1/document-artifacts/{ART_ID}/download",
        follow_redirects=False,
    )

    assert response.status_code == 200
    assert response.content == b"# Lesson\n"
    assert "location" not in response.headers
    assert response.headers["content-type"].startswith("text/markdown")
    assert response.headers["content-length"] == str(len(b"# Lesson\n"))
    assert "filename*=UTF-8''%E6%95%99%E6%9D%90.md" in response.headers[
        "content-disposition"
    ]
    assert close.called
    services.jobs.open_artifact_download.assert_awaited_once_with(
        owner_user_id="owner-1", artifact_id=ART_ID
    )


@pytest.mark.asyncio
async def test_teaching_usage_returns_owned_safe_rows(api) -> None:
    client, services = api
    services.library.get_document.return_value = _document()
    services.teaching_usage.return_value = [_teaching_usage()]

    response = await client.get(f"/api/v1/documents/{DOC_ID}/teaching-usage")

    assert response.status_code == 200
    assert response.json() == {"items": [_teaching_usage()]}
    services.library.get_document.assert_awaited_once_with(
        owner_user_id="owner-1",
        document_id=DOC_ID,
    )
    services.teaching_usage.assert_awaited_once_with(
        owner_user_id="owner-1",
        document_id=DOC_ID,
    )
    for unsafe in ("snapshot_prefix", "storage_key", "object_url", "sandbox_path"):
        assert unsafe not in response.text


@pytest.mark.asyncio
async def test_teaching_usage_returns_404_for_missing_or_foreign_document(api) -> None:
    client, services = api
    services.library.get_document.return_value = None

    response = await client.get(f"/api/v1/documents/{DOC_ID}/teaching-usage")

    assert response.status_code == 404
    services.teaching_usage.assert_not_awaited()


@pytest.mark.asyncio
async def test_student_guard_rejects_all_document_routes(monkeypatch) -> None:
    from src.server.app import documents

    guard = AsyncMock(
        side_effect=documents.HTTPException(status_code=403, detail="forbidden")
    )
    monkeypatch.setattr(documents, "require_nonstudent_agent_features", guard)
    app = FastAPI()
    app.include_router(documents.router)
    app.dependency_overrides[get_current_user_id] = lambda: "student-1"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        responses = [
            await client.get("/api/v1/documents"),
            await client.get(f"/api/v1/documents/{DOC_ID}/teaching-usage"),
        ]

    assert [response.status_code for response in responses] == [403, 403]


def test_router_exposes_complete_document_contract() -> None:
    from src.server.app.documents import router

    paths = {
        (route.path, method) for route in router.routes for method in route.methods
    }
    expected = {
        ("/api/v1/document-datasets", "POST"),
        ("/api/v1/document-datasets", "GET"),
        ("/api/v1/document-datasets/{dataset_id}", "GET"),
        ("/api/v1/document-datasets/{dataset_id}", "PATCH"),
        ("/api/v1/document-datasets/{dataset_id}", "DELETE"),
        ("/api/v1/document-tags", "GET"),
        ("/api/v1/document-tags", "POST"),
        ("/api/v1/document-tags/{tag_id}", "DELETE"),
        ("/api/v1/documents", "POST"),
        ("/api/v1/documents", "GET"),
        ("/api/v1/documents/{document_id}", "GET"),
        ("/api/v1/documents/{document_id}/teaching-usage", "GET"),
        ("/api/v1/documents/{document_id}/source", "GET"),
        ("/api/v1/documents/{document_id}", "PATCH"),
        ("/api/v1/documents/{document_id}", "DELETE"),
        ("/api/v1/documents/{document_id}/inspections", "POST"),
        ("/api/v1/documents/{document_id}/parse-options", "GET"),
        ("/api/v1/documents/{document_id}/parse-jobs", "POST"),
        ("/api/v1/documents/{document_id}/parse-jobs", "GET"),
        ("/api/v1/documents/{document_id}/artifacts", "GET"),
        ("/api/v1/document-jobs/{job_id}", "GET"),
        ("/api/v1/document-jobs/{job_id}/events", "GET"),
        ("/api/v1/document-jobs/{job_id}/cancel", "POST"),
        ("/api/v1/document-artifacts/{artifact_id}/download", "GET"),
    }
    assert expected <= paths


@pytest.mark.asyncio
async def test_source_download_streams_through_authenticated_api(api) -> None:
    client, services = api
    close = Mock()
    services.library.open_source_download.return_value = SimpleNamespace(
        filename="lesson.pdf",
        media_type="application/pdf",
        object_download=SimpleNamespace(
            chunks=iter([b"%PDF-demo"]),
            content_length=9,
            close=close,
        ),
    )

    response = await client.get(f"/api/v1/documents/{DOC_ID}/source")

    assert response.status_code == 200
    assert response.content == b"%PDF-demo"
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["content-length"] == "9"
    assert close.called
    services.library.open_source_download.assert_awaited_once_with(
        owner_user_id="owner-1", document_id=DOC_ID
    )
