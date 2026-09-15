"""Full document-library HTTP workflow against PostgreSQL and real PDF providers."""

from __future__ import annotations

import asyncio
import hashlib
import os
import shutil
import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.server.database import document_jobs, documents, education_members
from src.server.documents.executor import DocumentJobExecutor
from src.server.documents.inspection import DocumentInspectionService
from src.server.documents.jobs import DocumentParseJobService
from src.server.documents.library import DocumentLibraryService
from src.server.documents.providers.pdf_inspector import PdfInspectorDetector
from src.server.services.document_job_worker import DocumentJobWorker
from src.server.utils.api import get_current_user_id


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "documents"
OWNER_ID = "document-api-owner"
OTHER_ID = "document-api-other"
STUDENT_ID = "document-api-student"


class _LocalObjectStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _path(self, key: str) -> Path:
        path = PurePosixPath(key)
        if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
            raise ValueError("invalid test object key")
        destination = self.root.joinpath(*path.parts).resolve()
        if not destination.is_relative_to(self.root):
            raise ValueError("test object key escaped its root")
        return destination

    async def put_file(self, key: str, source: Path, *, content_type: str) -> None:
        del content_type
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, source, destination)

    async def get_file(self, key: str, destination: Path, *, max_bytes: int) -> int:
        source = self._path(key)
        size = source.stat().st_size
        if size > max_bytes:
            raise ValueError("test object exceeds requested bound")
        destination.parent.mkdir(parents=True, exist_ok=True)
        await asyncio.to_thread(shutil.copyfile, source, destination)
        return size

    async def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    async def open_download(self, key: str):
        payload = self._path(key).read_bytes()
        return SimpleNamespace(
            chunks=iter([payload]),
            content_length=len(payload),
            close=lambda: None,
        )

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()


class _TestEventService:
    def __init__(self, worker: DocumentJobWorker, jobs: DocumentParseJobService) -> None:
        self.worker = worker
        self.jobs = jobs

    async def run_next(self) -> None:
        assert await self.worker.run_once()
        await self.worker.wait_until_idle()

    async def wait_for_terminal_job(self, *, owner_user_id: str, job_id: str):
        await self.run_next()
        return await self.jobs.get_job(owner_user_id=owner_user_id, job_id=job_id)

    async def snapshots(
        self,
        *,
        owner_user_id: str,
        job_id: str,
        after_status_version: int,
    ) -> AsyncIterator[dict[str, object]]:
        snapshot = await self.jobs.get_job(owner_user_id=owner_user_id, job_id=job_id)
        if snapshot is not None and int(snapshot["status_version"]) > after_status_version:
            yield snapshot


@pytest_asyncio.fixture
async def document_api(
    cleanup_tables,
    test_db_pool,
    monkeypatch,
    tmp_path: Path,
):
    @asynccontextmanager
    async def test_connection():
        async with test_db_pool.connection() as connection:
            yield connection

    monkeypatch.setattr(documents, "get_db_connection", test_connection)
    monkeypatch.setattr(document_jobs, "get_db_connection", test_connection)
    monkeypatch.setattr(education_members, "get_db_connection", test_connection)

    household_id = uuid4()
    async with test_db_pool.connection() as connection:
        async with connection.transaction():
            async with connection.cursor() as cursor:
                await cursor.executemany(
                    "INSERT INTO users (user_id, name) VALUES (%s, %s)",
                    [
                        (OWNER_ID, "Document owner"),
                        (OTHER_ID, "Other user"),
                        (STUDENT_ID, "Student user"),
                    ],
                )
                await cursor.execute(
                    """
                    INSERT INTO education_households (
                        household_id, name, timezone, model_owner_user_id
                    ) VALUES (%s, %s, 'UTC', %s)
                    """,
                    (household_id, "Document test household", OWNER_ID),
                )
                await cursor.executemany(
                    """
                    INSERT INTO education_memberships (
                        household_id, user_id, role, display_name
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    [
                        (household_id, OWNER_ID, "parent", "Owner"),
                        (household_id, STUDENT_ID, "student", "Student"),
                    ],
                )

    store = _LocalObjectStore(tmp_path / "objects")
    library = DocumentLibraryService(object_store=store)
    inspections = DocumentInspectionService(object_store=store)
    jobs = DocumentParseJobService(object_store=store)
    executor = DocumentJobExecutor(object_store=store)
    worker = DocumentJobWorker(
        executor=executor,
        claimant_id="document-api-test-worker",
        lease_seconds=30,
        renew_interval_seconds=10,
        poll_interval_seconds=0.01,
        concurrency=1,
    )
    events = _TestEventService(worker, jobs)
    active_user = {"user_id": OWNER_ID}

    from src.server.app.documents import (
        get_document_event_service,
        get_document_inspection_service,
        get_document_job_service,
        get_document_library_service,
        router,
    )

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user_id] = lambda: active_user["user_id"]
    app.dependency_overrides[get_document_library_service] = lambda: library
    app.dependency_overrides[get_document_inspection_service] = lambda: inspections
    app.dependency_overrides[get_document_job_service] = lambda: jobs
    app.dependency_overrides[get_document_event_service] = lambda: events

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
    ) as client:
        yield client, active_user, events, store, test_db_pool

    await worker.shutdown()


async def _upload(
    client: AsyncClient,
    filename: str,
    *,
    dataset_id: str | None = None,
    tag_ids: tuple[str, ...] = (),
) -> dict[str, object]:
    form: list[tuple[str, tuple[str | None, bytes | str, str | None]]] = [
        (
            "file",
            (filename, (FIXTURES / filename).read_bytes(), "application/pdf"),
        )
    ]
    if dataset_id:
        form.append(("dataset_ids", (None, dataset_id, None)))
    form.extend(("tag_ids", (None, tag_id, None)) for tag_id in tag_ids)
    response = await client.post("/api/v1/documents", files=form)
    assert response.status_code == 201, response.text
    return response.json()


async def _inspect(client: AsyncClient, document_id: str) -> dict[str, object]:
    response = await client.post(f"/api/v1/documents/{document_id}/inspections")
    assert response.status_code == 201, response.text
    return response.json()


async def test_full_document_library_api_workflow(document_api) -> None:
    client, active_user, events, store, pool = document_api
    dataset_response = await client.post(
        "/api/v1/document-datasets",
        json={"name": "Mathematics", "description": "Reusable source material"},
    )
    assert dataset_response.status_code == 201
    dataset_id = dataset_response.json()["dataset_id"]
    tag_ids = []
    for name in ("algebra", "textbook"):
        response = await client.post("/api/v1/document-tags", json={"name": name})
        assert response.status_code == 201
        tag_ids.append(response.json()["tag_id"])

    source = await _upload(
        client,
        "text.pdf",
        dataset_id=dataset_id,
        tag_ids=tuple(tag_ids),
    )
    document_id = str(source["document_id"])
    assert source["source_sha256"] == hashlib.sha256((FIXTURES / "text.pdf").read_bytes()).hexdigest()

    jobs_before_choice = await client.get(f"/api/v1/documents/{document_id}/parse-jobs")
    assert jobs_before_choice.status_code == 200
    assert jobs_before_choice.json()["items"] == []

    inspected = await _inspect(client, document_id)
    inspection = inspected["inspection"]
    assert inspection["classification"] == "text_based"
    assert inspection["summary"]["page_count"] == 1
    assert inspection["summary"]["page_dimensions"][0] == {
        "page": 1,
        "width_points": 612.0,
        "height_points": 792.0,
    }
    assert inspected["parser_options"][0]["parser_id"] == "anydoc-local"
    assert inspected["parser_options"][0]["recommended"] is True

    async_response = await client.post(
        f"/api/v1/documents/{document_id}/parse-jobs",
        json={
            "inspection_id": inspection["inspection_id"],
            "parser_id": "anydoc-local",
            "mode": "async",
        },
    )
    assert async_response.status_code == 202
    async_job_id = async_response.json()["job_id"]
    await events.run_next()

    stream = await client.get(f"/api/v1/document-jobs/{async_job_id}/events")
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert "event: snapshot" in stream.text
    assert '"status":"completed"' in stream.text

    artifacts = await client.get(
        f"/api/v1/documents/{document_id}/artifacts",
        params={"producer_job_id": async_job_id},
    )
    assert artifacts.status_code == 200
    async_artifacts = artifacts.json()["items"]
    assert [(item["artifact_kind"], item["media_type"]) for item in async_artifacts] == [
        ("primary_document", "text/markdown")
    ]
    async with pool.connection() as connection:
        async with connection.cursor() as cursor:
            await cursor.execute(
                "SELECT storage_key FROM document_artifacts WHERE artifact_id = %s",
                (async_artifacts[0]["artifact_id"],),
            )
            artifact_key = (await cursor.fetchone())["storage_key"]
    assert b"Digital Algebra Notes" in store.read(artifact_key)

    sync_response = await client.post(
        f"/api/v1/documents/{document_id}/parse-jobs",
        json={
            "inspection_id": inspection["inspection_id"],
            "parser_id": "anydoc-local",
            "mode": "sync",
        },
    )
    assert sync_response.status_code in {200, 202}
    assert sync_response.json()["status"] == "completed"

    legacy_job_ids = []
    for _ in range(2):
        response = await client.post(
            f"/api/v1/documents/{document_id}/parse-jobs",
            json={
                "inspection_id": inspection["inspection_id"],
                "parser_id": "legacy-pdf-text",
                "mode": "sync",
            },
        )
        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        legacy_job_ids.append(response.json()["job_id"])
    assert legacy_job_ids[0] != legacy_job_ids[1]

    history = await client.get(f"/api/v1/documents/{document_id}/parse-jobs")
    assert history.status_code == 200
    assert len(history.json()["items"]) == 4
    assert len({item["job_id"] for item in history.json()["items"]}) == 4

    dataset_page = await client.get(
        "/api/v1/documents",
        params={"dataset_id": dataset_id, "tag_ids": tag_ids, "limit": 1, "offset": 0},
    )
    assert dataset_page.status_code == 200
    assert dataset_page.json()["total"] == 1
    assert dataset_page.json()["items"][0]["document_id"] == document_id
    assert {item["tag_id"] for item in dataset_page.json()["items"][0]["tags"]} == set(tag_ids)
    assert dataset_page.json()["items"][0]["parse_status"] == "completed"

    for filename, expected_classification in (
        ("mixed.pdf", "mixed"),
        ("scanned.pdf", "scanned"),
        ("image-based.pdf", "image_based"),
    ):
        candidate = await _upload(client, filename)
        outcome = await _inspect(client, str(candidate["document_id"]))
        assert outcome["inspection"]["classification"] == expected_classification
        options = {item["parser_id"]: item for item in outcome["parser_options"]}
        assert options["legacy-pdf-text"]["recommended"] is True
        assert options["legacy-pdf-text"]["warning"]
        assert options["ocr-document"]["available"] is False

    paginated = await client.get("/api/v1/documents", params={"limit": 2, "offset": 2})
    assert paginated.status_code == 200
    assert paginated.json()["total"] == 4
    assert len(paginated.json()["items"]) == 2

    artifact_id = async_artifacts[0]["artifact_id"]
    download = await client.get(
        f"/api/v1/document-artifacts/{artifact_id}/download",
        follow_redirects=False,
    )
    assert download.status_code == 200
    assert download.content == store.read(artifact_key)
    assert "location" not in download.headers
    assert download.headers["content-type"].startswith("text/markdown")

    active_user["user_id"] = OTHER_ID
    assert (await client.get(f"/api/v1/documents/{document_id}")).status_code == 404
    assert (await client.get(f"/api/v1/document-jobs/{async_job_id}")).status_code == 404
    assert (await client.get(f"/api/v1/document-artifacts/{artifact_id}/download")).status_code == 404

    active_user["user_id"] = STUDENT_ID
    assert (await client.get(f"/api/v1/documents/{document_id}")).status_code == 403
    assert (await client.get(f"/api/v1/document-jobs/{async_job_id}")).status_code == 403
    assert (await client.get(f"/api/v1/document-artifacts/{artifact_id}/download")).status_code == 403


@pytest.mark.parametrize(
    ("url", "expected_sha256", "classification"),
    [
        (
            "https://raw.githubusercontent.com/firecrawl/anydoc/main/tests/fixtures/pdf/text.pdf",
            "7d1fd0932634cffa80bf9fb1bd73a6871f82a2cb29b4d7bcfb689927bc5d84e7",
            "mixed",
        ),
        (
            "https://raw.githubusercontent.com/firecrawl/pdf-inspector/main/tests/fixtures/broken_startxref_pointer.pdf",
            "e1434ed34da5861c423f65807c5c480532d8eb4ae4b196c652cded390ba65974",
            "text_based",
        ),
    ],
)
async def test_pinned_upstream_pdf_compatibility(
    tmp_path: Path,
    url: str,
    expected_sha256: str,
    classification: str,
) -> None:
    if os.getenv("RUN_UPSTREAM_DOCUMENT_FIXTURES") != "1":
        pytest.skip("set RUN_UPSTREAM_DOCUMENT_FIXTURES=1 to download pinned Firecrawl PDFs")

    request = Request(url, headers={"User-Agent": "LangAlpha document compatibility test"})
    tls_context = ssl.create_default_context()
    # Some development transparent proxies terminate Python's TLS 1.3 handshake.
    tls_context.maximum_version = ssl.TLSVersion.TLSv1_2
    direct_opener = build_opener(ProxyHandler({}), HTTPSHandler(context=tls_context))
    with direct_opener.open(request, timeout=20) as response:
        content = response.read(2 * 1024 * 1024)
    assert hashlib.sha256(content).hexdigest() == expected_sha256
    source = tmp_path / "upstream.pdf"
    source.write_bytes(content)

    inspected = await PdfInspectorDetector(timeout_seconds=15).inspect(source)
    assert inspected.status == "completed"
    assert inspected.classification == classification
    if "firecrawl/anydoc" in url:
        import anydoc

        markdown = anydoc.to_markdown(source, ocr="reject")
        assert len(markdown.strip()) >= 100


async def test_smoke_client_stops_after_inspection_without_explicit_parser(
    tmp_path: Path,
) -> None:
    import httpx

    from scripts.smoke_document_library import SmokeConfig, run_smoke

    fixture = tmp_path / "source.pdf"
    fixture.write_bytes(b"%PDF-1.7\nfixture\n%%EOF\n")
    requests: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append((request.method, request.url.path))
        if request.url.path == "/api/v1/documents":
            return httpx.Response(201, json={"document_id": "doc-A1b2C3d4E5f6"})
        if request.url.path.endswith("/inspections"):
            return httpx.Response(
                201,
                json={
                    "inspection": {
                        "inspection_id": "ins-A1b2C3d4E5f6",
                        "classification": "text_based",
                    },
                    "parser_options": [
                        {
                            "parser_id": "anydoc-local",
                            "available": True,
                            "recommended": True,
                        }
                    ],
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    output: list[str] = []
    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://test",
    ) as client:
        result = run_smoke(
            SmokeConfig(
                base_url="http://test",
                fixture=fixture,
                session_cookie="opaque-session",
            ),
            client=client,
            output=output.append,
        )

    assert result.document_id == "doc-A1b2C3d4E5f6"
    assert result.classification == "text_based"
    assert result.job_id is None
    assert all(not path.endswith("/parse-jobs") for _, path in requests)
    assert "opaque-session" not in "\n".join(output)


async def test_smoke_client_runs_only_the_explicit_parser_to_artifacts(
    tmp_path: Path,
) -> None:
    import httpx

    from scripts.smoke_document_library import SmokeConfig, run_smoke

    fixture = tmp_path / "source.pdf"
    fixture.write_bytes(b"%PDF-1.7\nfixture\n%%EOF\n")
    job_reads = iter(("running", "completed"))

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v1/documents":
            return httpx.Response(201, json={"document_id": "doc-A1b2C3d4E5f6"})
        if path.endswith("/inspections"):
            return httpx.Response(
                201,
                json={
                    "inspection": {
                        "inspection_id": "ins-A1b2C3d4E5f6",
                        "classification": "text_based",
                    },
                    "parser_options": [
                        {
                            "parser_id": "anydoc-local",
                            "available": True,
                            "recommended": True,
                        }
                    ],
                },
            )
        if path.endswith("/parse-jobs"):
            return httpx.Response(
                202,
                json={"job_id": "job-A1b2C3d4E5f6", "status": "queued"},
            )
        if path == "/api/v1/document-jobs/job-A1b2C3d4E5f6":
            status = next(job_reads)
            return httpx.Response(
                200,
                json={"job_id": "job-A1b2C3d4E5f6", "status": status},
            )
        if path.endswith("/artifacts"):
            return httpx.Response(
                200,
                json={"items": [{"relative_path": "document.md"}]},
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    output: list[str] = []
    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://test",
    ) as client:
        result = run_smoke(
            SmokeConfig(
                base_url="http://test",
                fixture=fixture,
                session_cookie="opaque-session",
                parser_id="anydoc-local",
                poll_interval_seconds=0,
            ),
            client=client,
            output=output.append,
        )

    assert result.job_id == "job-A1b2C3d4E5f6"
    assert result.status == "completed"
    assert result.artifact_names == ("document.md",)
    assert any(line.startswith("parser_id=anydoc-local ") for line in output)
