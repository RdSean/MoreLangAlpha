"""Repeatable inspection orchestration for owned document sources."""

from __future__ import annotations

import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from src.server.database import documents as document_repository
from src.server.documents.contracts import InspectionResult, ParserDescriptor
from src.server.documents.ids import new_public_id
from src.server.documents.providers.registry import (
    DocumentProviderRegistry,
    build_default_provider_registry,
)
from src.server.documents.storage import DocumentObjectStore


class InspectionRepository(Protocol):
    async def get_document(self, **kwargs: str) -> dict[str, Any] | None: ...

    async def create_inspection(
        self, **kwargs: object
    ) -> dict[str, Any] | None: ...

    async def finish_inspection(
        self, **kwargs: object
    ) -> dict[str, Any] | None: ...

    async def get_inspection(self, **kwargs: str) -> dict[str, Any] | None: ...

    async def get_latest_successful_inspection(
        self, **kwargs: str
    ) -> dict[str, Any] | None: ...


@dataclass(frozen=True, slots=True)
class InspectionOutcome:
    inspection: dict[str, Any]
    parser_options: tuple[ParserDescriptor, ...]


class DocumentInspectionService:
    """Download, inspect, persist, and recommend without starting a parse job."""

    def __init__(
        self,
        *,
        repository: InspectionRepository = document_repository,
        object_store: DocumentObjectStore,
        provider_registry: DocumentProviderRegistry | None = None,
        id_factory: Callable[[str], str] = new_public_id,
    ) -> None:
        self._repository = repository
        self._object_store = object_store
        self._provider_registry = (
            provider_registry or build_default_provider_registry()
        )
        self._id_factory = id_factory

    async def inspect(
        self,
        *,
        owner_user_id: str,
        document_id: str,
    ) -> InspectionOutcome | None:
        document = await self._repository.get_document(
            owner_user_id=owner_user_id,
            document_id=document_id,
        )
        if document is None:
            return None

        document_format = str(document["document_format"])
        inspector = self._provider_registry.inspector_for_format(document_format)
        descriptor = inspector.descriptor
        inspection_id = self._id_factory("inspection")
        pending = await self._repository.create_inspection(
            owner_user_id=owner_user_id,
            inspection_id=inspection_id,
            document_id=document_id,
            inspector_id=descriptor.inspector_id,
            inspector_name=descriptor.display_name,
            inspector_version=descriptor.version,
            status="pending",
            detected_format=None,
            classification=None,
            summary={},
            details={},
            error_code=None,
            error_message=None,
        )
        if pending is None:
            return None

        result: InspectionResult
        with tempfile.TemporaryDirectory(prefix="langalpha-inspection-") as temp_name:
            source_path = Path(temp_name) / f"source.{document_format}"
            try:
                await self._object_store.get_file(
                    str(document["source_storage_key"]),
                    source_path,
                    max_bytes=int(document["source_size_bytes"]),
                )
                result = await inspector.inspect(source_path)
                if result.status not in {"completed", "failed"}:
                    raise ValueError("Inspector returned a non-terminal result")
            except Exception:
                result = _failed_result(
                    inspector_id=descriptor.inspector_id,
                    inspector_name=descriptor.display_name,
                    inspector_version=descriptor.version,
                    detected_format=document_format,
                )

        saved = await self._repository.finish_inspection(
            owner_user_id=owner_user_id,
            document_id=document_id,
            inspection_id=inspection_id,
            status=result.status,
            detected_format=result.detected_format,
            classification=result.classification,
            summary=result.summary,
            details=result.details,
            error_code=result.error_code,
            error_message=result.error_message,
        )
        if saved is None:
            raise RuntimeError("Pending inspection could not be finalized")

        options: tuple[ParserDescriptor, ...] = ()
        if result.status == "completed":
            options = self._provider_registry.parser_options(
                document_format=result.detected_format,
                classification=result.classification,
            )
        return InspectionOutcome(inspection=saved, parser_options=options)

    async def get_parser_options(
        self,
        *,
        owner_user_id: str,
        document_id: str,
        inspection_id: str | None = None,
    ) -> tuple[ParserDescriptor, ...] | None:
        if inspection_id is None:
            inspection = (
                await self._repository.get_latest_successful_inspection(
                    owner_user_id=owner_user_id,
                    document_id=document_id,
                )
            )
        else:
            inspection = await self._repository.get_inspection(
                owner_user_id=owner_user_id,
                inspection_id=inspection_id,
            )

        if (
            inspection is None
            or inspection.get("document_id") != document_id
            or inspection.get("status") != "completed"
        ):
            return None
        detected_format = inspection.get("detected_format")
        classification = inspection.get("classification")
        if not isinstance(detected_format, str) or not isinstance(
            classification, str
        ):
            return None
        return self._provider_registry.parser_options(
            document_format=detected_format,
            classification=classification,
        )


def _failed_result(
    *,
    inspector_id: str,
    inspector_name: str,
    inspector_version: str | None,
    detected_format: str,
) -> InspectionResult:
    return InspectionResult(
        inspector_id=inspector_id,
        inspector_name=inspector_name,
        inspector_version=inspector_version,
        status="failed",
        detected_format=detected_format,
        classification="unknown",
        error_code="inspection_failed",
        error_message="Document inspection failed",
    )
