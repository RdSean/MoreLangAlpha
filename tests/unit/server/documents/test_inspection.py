from __future__ import annotations

import asyncio
import stat
from pathlib import Path

import pytest

from src.server.documents.contracts import (
    ArtifactBundle,
    InspectionResult,
    ParseRequest,
    ParserDescriptor,
)
from src.server.documents.inspection import DocumentInspectionService
from src.server.documents.providers.base import InspectorDescriptor
from src.server.documents.providers.registry import DocumentProviderRegistry


class _Repository:
    def __init__(self) -> None:
        self.document = {
            "document_id": "doc-A1b2C3d4E5f6",
            "owner_user_id": "owner-1",
            "original_filename": "source.pdf",
            "media_type": "application/pdf",
            "document_format": "pdf",
            "source_storage_key": "documents/doc-A1b2C3d4E5f6/source",
            "source_size_bytes": 16,
        }
        self.inspections: dict[str, dict[str, object]] = {}
        self.created: list[dict[str, object]] = []
        self.finished: list[dict[str, object]] = []
        self.requested_inspection_id: str | None = None
        self.latest_requested = False

    async def get_document(self, **kwargs):
        assert kwargs == {
            "owner_user_id": "owner-1",
            "document_id": "doc-A1b2C3d4E5f6",
        }
        return dict(self.document)

    async def create_inspection(self, **kwargs):
        self.created.append(kwargs)
        row = dict(kwargs)
        self.inspections[str(kwargs["inspection_id"])] = row
        return row

    async def finish_inspection(self, **kwargs):
        self.finished.append(kwargs)
        row = self.inspections[str(kwargs["inspection_id"])]
        row.update(kwargs)
        return dict(row)

    async def get_inspection(self, **kwargs):
        self.requested_inspection_id = kwargs["inspection_id"]
        row = self.inspections.get(kwargs["inspection_id"])
        return dict(row) if row else None

    async def get_latest_successful_inspection(self, **kwargs):
        self.latest_requested = True
        completed = [
            row
            for row in self.inspections.values()
            if row.get("document_id") == kwargs["document_id"]
            and row.get("status") == "completed"
        ]
        return dict(completed[-1]) if completed else None


class _ObjectStore:
    def __init__(self, content: bytes = b"%PDF-1.4 source") -> None:
        self.content = content
        self.destinations: list[Path] = []
        self.max_bytes: list[int] = []

    async def get_file(self, key, destination, *, max_bytes):
        assert key == "documents/doc-A1b2C3d4E5f6/source"
        self.destinations.append(destination)
        self.max_bytes.append(max_bytes)
        destination.write_bytes(self.content)
        return len(self.content)


class _Inspector:
    descriptor = InspectorDescriptor(
        inspector_id="pdf-inspector",
        display_name="PDF Inspector",
        version="1.17.0",
        supported_formats=frozenset({"pdf"}),
        available=True,
        reason="Detects PDF types.",
    )

    def __init__(self, result: InspectionResult | Exception) -> None:
        self.result = result
        self.paths: list[Path] = []

    async def inspect(self, source_path: Path) -> InspectionResult:
        self.paths.append(source_path)
        assert source_path.read_bytes() == b"%PDF-1.4 source"
        assert stat.S_IMODE(source_path.parent.stat().st_mode) == 0o700
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class _Parser:
    def __init__(self, descriptor: ParserDescriptor) -> None:
        self.descriptor = descriptor

    def parse(self, request: ParseRequest) -> ArtifactBundle:
        raise AssertionError("inspection must not execute a parser")


def _completed_result(classification: str = "text_based") -> InspectionResult:
    return InspectionResult(
        inspector_id="pdf-inspector",
        inspector_name="PDF Inspector",
        inspector_version="1.17.0",
        status="completed",
        detected_format="pdf",
        classification=classification,  # type: ignore[arg-type]
        summary={"page_count": 3, "page_dimensions": []},
        details={"pages_needing_ocr": []},
    )


def _registry(inspector: _Inspector) -> DocumentProviderRegistry:
    anydoc = _Parser(
        ParserDescriptor(
            parser_id="anydoc-local",
            display_name="AnyDoc Local",
            version="0.1",
            supported_formats=frozenset({"pdf"}),
            supported_classifications=frozenset({"text_based"}),
            available=True,
            reason="Best for digital PDFs.",
        )
    )
    legacy = _Parser(
        ParserDescriptor(
            parser_id="legacy-pdf-text",
            display_name="Legacy PDF Text",
            version=None,
            supported_formats=frozenset({"pdf"}),
            supported_classifications=frozenset(
                {"text_based", "mixed", "scanned", "image_based", "unknown"}
            ),
            available=True,
            reason="Extracts the available text layer.",
        )
    )
    return DocumentProviderRegistry(
        inspectors=(inspector,),
        parsers=(anydoc, legacy),
    )


def _service(
    repository: _Repository,
    store: _ObjectStore,
    inspector: _Inspector,
    ids: tuple[str, ...] = ("ins-A1b2C3d4E5f6",),
) -> DocumentInspectionService:
    inspection_ids = iter(ids)
    return DocumentInspectionService(
        repository=repository,
        object_store=store,
        provider_registry=_registry(inspector),
        id_factory=lambda kind: next(inspection_ids),
    )


@pytest.mark.asyncio
async def test_inspection_downloads_owned_source_to_private_temp_dir() -> None:
    repository = _Repository()
    store = _ObjectStore()
    inspector = _Inspector(_completed_result())

    outcome = await _service(repository, store, inspector).inspect(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert outcome is not None
    assert store.max_bytes == [16]
    assert inspector.paths == store.destinations
    assert all(not path.exists() for path in store.destinations)


@pytest.mark.asyncio
async def test_every_retry_creates_a_new_inspection_row() -> None:
    repository = _Repository()
    store = _ObjectStore()
    inspector = _Inspector(_completed_result())
    service = _service(
        repository,
        store,
        inspector,
        ids=("ins-A1b2C3d4E5f6", "ins-G7h8I9j0K1l2"),
    )

    await service.inspect(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )
    await service.inspect(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert [row["inspection_id"] for row in repository.created] == [
        "ins-A1b2C3d4E5f6",
        "ins-G7h8I9j0K1l2",
    ]


@pytest.mark.asyncio
async def test_success_persists_generic_result_and_returns_parser_options() -> None:
    repository = _Repository()
    store = _ObjectStore()
    inspector = _Inspector(_completed_result())

    outcome = await _service(repository, store, inspector).inspect(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert outcome is not None
    assert repository.created[0]["status"] == "pending"
    assert repository.finished[0]["status"] == "completed"
    assert repository.finished[0]["summary"] == {
        "page_count": 3,
        "page_dimensions": [],
    }
    assert repository.finished[0]["details"] == {"pages_needing_ocr": []}
    assert outcome.inspection["classification"] == "text_based"
    assert [option.parser_id for option in outcome.parser_options] == [
        "anydoc-local",
        "legacy-pdf-text",
    ]


@pytest.mark.parametrize(
    "provider_error",
    [RuntimeError("secret path: /tmp/source.pdf"), asyncio.TimeoutError()],
)
@pytest.mark.asyncio
async def test_failure_records_safe_error_and_cleans_temp_file(
    provider_error: Exception,
) -> None:
    repository = _Repository()
    store = _ObjectStore()
    inspector = _Inspector(provider_error)

    outcome = await _service(repository, store, inspector).inspect(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert outcome is not None
    assert repository.finished[0]["status"] == "failed"
    assert repository.finished[0]["error_code"] == "inspection_failed"
    assert repository.finished[0]["error_message"] == "Document inspection failed"
    assert outcome.parser_options == ()
    assert repository.document["document_id"] == "doc-A1b2C3d4E5f6"
    assert all(not path.exists() for path in store.destinations)


@pytest.mark.asyncio
async def test_parse_options_use_selected_inspection_or_latest_when_omitted() -> None:
    repository = _Repository()
    selected = {
        "inspection_id": "ins-A1b2C3d4E5f6",
        "document_id": "doc-A1b2C3d4E5f6",
        "status": "completed",
        "detected_format": "pdf",
        "classification": "mixed",
    }
    latest = {
        "inspection_id": "ins-G7h8I9j0K1l2",
        "document_id": "doc-A1b2C3d4E5f6",
        "status": "completed",
        "detected_format": "pdf",
        "classification": "text_based",
    }
    repository.inspections = {
        str(selected["inspection_id"]): selected,
        str(latest["inspection_id"]): latest,
    }
    inspector = _Inspector(_completed_result())
    service = _service(repository, _ObjectStore(), inspector)

    selected_options = await service.get_parser_options(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
        inspection_id="ins-A1b2C3d4E5f6",
    )
    latest_options = await service.get_parser_options(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert [option.parser_id for option in selected_options or ()] == [
        "legacy-pdf-text"
    ]
    assert [option.parser_id for option in latest_options or ()] == [
        "anydoc-local",
        "legacy-pdf-text",
    ]
    assert repository.requested_inspection_id == "ins-A1b2C3d4E5f6"
    assert repository.latest_requested
