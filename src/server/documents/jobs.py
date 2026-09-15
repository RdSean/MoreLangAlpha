"""Owner-scoped parse-job selection, history, cancellation, and downloads."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from src.server.database import document_jobs as default_job_repository
from src.server.database import documents as default_document_repository
from src.server.documents.contracts import JsonValue
from src.server.documents.ids import new_public_id
from src.server.documents.providers.registry import (
    DocumentProviderRegistry,
    build_default_provider_registry,
)
from src.server.documents.storage import DocumentObjectStore, OpenedDocumentObject


@dataclass(frozen=True, slots=True)
class ArtifactDownload:
    filename: str
    media_type: str
    object_download: OpenedDocumentObject


class DocumentMetadataRepository(Protocol):
    async def get_inspection(self, **kwargs: str) -> dict[str, Any] | None: ...

    async def list_parse_jobs(self, **kwargs: object) -> list[dict[str, Any]]: ...

    async def list_artifacts(self, **kwargs: object) -> list[dict[str, Any]]: ...

    async def get_artifact(self, **kwargs: str) -> dict[str, Any] | None: ...


class ParseJobRepository(Protocol):
    async def create_job(self, **kwargs: object) -> dict[str, Any] | None: ...

    async def get_owned_job(self, **kwargs: str) -> dict[str, Any] | None: ...

    async def request_cancel(self, **kwargs: str) -> dict[str, Any] | None: ...


JobNotifier = Callable[[str, int], Awaitable[None]]


class DocumentParseJobService:
    """Validate explicit parser choices before creating durable work."""

    def __init__(
        self,
        *,
        document_repository: DocumentMetadataRepository = default_document_repository,
        job_repository: ParseJobRepository = default_job_repository,
        object_store: DocumentObjectStore | None = None,
        provider_registry: DocumentProviderRegistry | None = None,
        notifier: JobNotifier | None = None,
        id_factory: Callable[[str], str] = new_public_id,
    ) -> None:
        self._document_repository = document_repository
        self._job_repository = job_repository
        self._object_store = object_store
        self._provider_registry = provider_registry or build_default_provider_registry()
        self._notifier = notifier
        self._id_factory = id_factory

    async def create_job(
        self,
        *,
        owner_user_id: str,
        document_id: str,
        inspection_id: str,
        parser_id: str,
        parser_options: dict[str, JsonValue],
        request_mode: str,
    ) -> dict[str, Any] | None:
        inspection = await self._document_repository.get_inspection(
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
        if not isinstance(detected_format, str) or not isinstance(classification, str):
            return None

        parser = self._provider_registry.parser_for_selection(
            parser_id=parser_id,
            document_format=detected_format,
            classification=classification,
        )
        descriptor = parser.descriptor
        job = await self._job_repository.create_job(
            owner_user_id=owner_user_id,
            job_id=self._id_factory("job"),
            document_id=document_id,
            inspection_id=inspection_id,
            parser_id=descriptor.parser_id,
            parser_name=descriptor.display_name,
            parser_version=descriptor.version,
            parser_options=parser_options,
            request_mode=request_mode,
        )
        await self._notify(job)
        return job

    async def get_job(
        self, *, owner_user_id: str, job_id: str
    ) -> dict[str, Any] | None:
        return await self._job_repository.get_owned_job(
            owner_user_id=owner_user_id, job_id=job_id
        )

    async def list_jobs(
        self,
        *,
        owner_user_id: str,
        document_id: str,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        return await self._document_repository.list_parse_jobs(
            owner_user_id=owner_user_id,
            document_id=document_id,
            limit=limit,
            offset=offset,
        )

    async def cancel_job(
        self, *, owner_user_id: str, job_id: str
    ) -> dict[str, Any] | None:
        job = await self._job_repository.request_cancel(
            owner_user_id=owner_user_id, job_id=job_id
        )
        await self._notify(job)
        return job

    async def list_artifacts(
        self,
        *,
        owner_user_id: str,
        document_id: str,
        producer_job_id: str | None = None,
    ) -> list[dict[str, Any]]:
        return await self._document_repository.list_artifacts(
            owner_user_id=owner_user_id,
            document_id=document_id,
            producer_job_id=producer_job_id,
        )

    async def open_artifact_download(
        self, *, owner_user_id: str, artifact_id: str
    ) -> ArtifactDownload | None:
        artifact = await self._document_repository.get_artifact(
            owner_user_id=owner_user_id, artifact_id=artifact_id
        )
        if artifact is None:
            return None
        if self._object_store is None:
            raise RuntimeError("Document object store is unavailable")
        opened = await self._object_store.open_download(str(artifact["storage_key"]))
        return ArtifactDownload(
            filename=str(artifact["relative_path"]).rsplit("/", 1)[-1],
            media_type=str(artifact["media_type"]),
            object_download=opened,
        )

    async def _notify(self, job: dict[str, Any] | None) -> None:
        if job is None or self._notifier is None:
            return
        await self._notifier(str(job["job_id"]), int(job["status_version"]))
