"""User-private document upload, organization, and exact-key deletion service."""

from __future__ import annotations

import hashlib
import logging
import os
import tempfile
from collections.abc import AsyncIterable, Callable
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from src.config.settings import get_document_parsing_config
from src.server.database import documents as document_repository
from src.server.database.documents import DocumentListFilter
from src.server.documents.contracts import (
    FileTooLargeError,
    UnsupportedMediaTypeError,
)
from src.server.documents.ids import new_public_id
from src.server.documents.storage import DocumentObjectStore


logger = logging.getLogger(__name__)


class DocumentRepository(Protocol):
    async def create_dataset(self, **kwargs: object) -> dict[str, Any]: ...

    async def list_datasets(
        self, **kwargs: object
    ) -> tuple[list[dict[str, Any]], int]: ...

    async def get_dataset(self, **kwargs: str) -> dict[str, Any] | None: ...

    async def update_dataset(self, **kwargs: object) -> dict[str, Any] | None: ...

    async def delete_dataset(self, **kwargs: str) -> dict[str, Any] | None: ...

    async def list_documents(
        self, **kwargs: object
    ) -> tuple[list[dict[str, Any]], int]: ...

    async def create_document(self, **kwargs: object) -> dict[str, Any]: ...

    async def get_document(self, **kwargs: str) -> dict[str, Any] | None: ...

    async def list_artifacts(self, **kwargs: str) -> list[dict[str, Any]]: ...

    async def delete_document(self, **kwargs: str) -> dict[str, Any] | None: ...

    async def update_document(self, **kwargs: object) -> dict[str, Any] | None: ...

    async def replace_dataset_memberships(self, **kwargs: object) -> None: ...

    async def replace_tag_assignments(self, **kwargs: object) -> None: ...

    async def create_tag(self, **kwargs: str) -> dict[str, Any]: ...

    async def list_tags(self, **kwargs: str) -> list[dict[str, Any]]: ...

    async def update_tag(self, **kwargs: str) -> dict[str, Any] | None: ...

    async def delete_tag(self, **kwargs: str) -> dict[str, Any] | None: ...


class DocumentLibraryService:
    """Own the source-object lifecycle outside parser-specific code."""

    def __init__(
        self,
        *,
        repository: DocumentRepository = document_repository,
        object_store: DocumentObjectStore,
        max_upload_bytes: int | None = None,
        id_factory: Callable[[str], str] = new_public_id,
    ) -> None:
        self._repository = repository
        self._object_store = object_store
        self._max_upload_bytes = (
            get_document_parsing_config().max_upload_bytes
            if max_upload_bytes is None
            else max_upload_bytes
        )
        self._id_factory = id_factory

    async def create_dataset(
        self,
        *,
        owner_user_id: str,
        name: str,
        description: str | None,
    ) -> dict[str, Any]:
        return await self._repository.create_dataset(
            owner_user_id=owner_user_id,
            dataset_id=self._id_factory("dataset"),
            name=name.strip(),
            description=description,
        )

    async def get_dataset(
        self, *, owner_user_id: str, dataset_id: str
    ) -> dict[str, Any] | None:
        return await self._repository.get_dataset(
            owner_user_id=owner_user_id, dataset_id=dataset_id
        )

    async def patch_dataset(
        self,
        *,
        owner_user_id: str,
        dataset_id: str,
        name: str,
        description: str | None,
    ) -> dict[str, Any] | None:
        return await self._repository.update_dataset(
            owner_user_id=owner_user_id,
            dataset_id=dataset_id,
            name=name.strip(),
            description=description,
        )

    async def delete_dataset(
        self, *, owner_user_id: str, dataset_id: str
    ) -> dict[str, Any] | None:
        return await self._repository.delete_dataset(
            owner_user_id=owner_user_id, dataset_id=dataset_id
        )

    async def list_datasets(
        self,
        *,
        owner_user_id: str,
        query: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        return await self._repository.list_datasets(
            owner_user_id=owner_user_id,
            query=query,
            limit=limit,
            offset=offset,
        )

    async def list_documents(
        self,
        *,
        owner_user_id: str,
        filters: DocumentListFilter,
    ) -> tuple[list[dict[str, Any]], int]:
        return await self._repository.list_documents(
            owner_user_id=owner_user_id,
            filters=filters,
        )

    async def get_document(
        self, *, owner_user_id: str, document_id: str
    ) -> dict[str, Any] | None:
        return await self._repository.get_document(
            owner_user_id=owner_user_id, document_id=document_id
        )

    async def create_tag(
        self,
        *,
        owner_user_id: str,
        name: str,
    ) -> dict[str, Any]:
        display_name, normalized_name = _normalize_tag_name(name)
        return await self._repository.create_tag(
            owner_user_id=owner_user_id,
            tag_id=self._id_factory("tag"),
            name=display_name,
            normalized_name=normalized_name,
        )

    async def list_tags(self, *, owner_user_id: str) -> list[dict[str, Any]]:
        return await self._repository.list_tags(owner_user_id=owner_user_id)

    async def update_tag(
        self,
        *,
        owner_user_id: str,
        tag_id: str,
        name: str,
    ) -> dict[str, Any] | None:
        display_name, normalized_name = _normalize_tag_name(name)
        return await self._repository.update_tag(
            owner_user_id=owner_user_id,
            tag_id=tag_id,
            name=display_name,
            normalized_name=normalized_name,
        )

    async def delete_tag(
        self,
        *,
        owner_user_id: str,
        tag_id: str,
    ) -> dict[str, Any] | None:
        return await self._repository.delete_tag(
            owner_user_id=owner_user_id,
            tag_id=tag_id,
        )

    async def patch_document(
        self,
        *,
        owner_user_id: str,
        document_id: str,
        original_filename: str,
        dataset_ids: tuple[str, ...] | None = None,
        tag_ids: tuple[str, ...] | None = None,
    ) -> dict[str, Any] | None:
        updated = await self._repository.update_document(
            owner_user_id=owner_user_id,
            document_id=document_id,
            original_filename=_normalize_pdf_filename(original_filename),
        )
        if updated is None:
            return None
        if dataset_ids is not None:
            await self._repository.replace_dataset_memberships(
                owner_user_id=owner_user_id,
                document_id=document_id,
                dataset_ids=dataset_ids,
            )
        if tag_ids is not None:
            await self._repository.replace_tag_assignments(
                owner_user_id=owner_user_id,
                document_id=document_id,
                tag_ids=tag_ids,
            )
        return updated

    async def upload_pdf(
        self,
        *,
        owner_user_id: str,
        original_filename: str,
        declared_media_type: str,
        chunks: AsyncIterable[bytes],
        declared_length: int | None = None,
        dataset_ids: tuple[str, ...] = (),
        tag_ids: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        filename = _normalize_pdf_filename(original_filename)
        if declared_media_type.strip().lower() != "application/pdf":
            raise UnsupportedMediaTypeError("Only PDF uploads are supported")
        if declared_length is not None and declared_length > self._max_upload_bytes:
            raise FileTooLargeError("The uploaded document exceeds the size limit")

        document_id = self._id_factory("document")
        storage_key = f"documents/{document_id}/source"
        file_descriptor, temp_name = tempfile.mkstemp(prefix="langalpha-document-")
        temp_path = Path(temp_name)
        source_size = 0
        source_hash = hashlib.sha256()
        signature = bytearray()

        try:
            with os.fdopen(file_descriptor, "wb") as temp_file:
                async for chunk in chunks:
                    if not isinstance(chunk, bytes):
                        raise TypeError("document upload chunks must be bytes")
                    if not chunk:
                        continue
                    source_size += len(chunk)
                    if source_size > self._max_upload_bytes:
                        raise FileTooLargeError(
                            "The uploaded document exceeds the size limit"
                        )
                    source_hash.update(chunk)
                    if len(signature) < 5:
                        signature.extend(chunk[: 5 - len(signature)])
                    temp_file.write(chunk)

            if bytes(signature) != b"%PDF-":
                raise UnsupportedMediaTypeError("The uploaded file is not a PDF")

            await self._object_store.put_file(
                storage_key,
                temp_path,
                content_type="application/pdf",
            )
            try:
                return await self._repository.create_document(
                    owner_user_id=owner_user_id,
                    document_id=document_id,
                    original_filename=filename,
                    media_type="application/pdf",
                    document_format="pdf",
                    source_storage_key=storage_key,
                    source_size_bytes=source_size,
                    source_sha256=source_hash.hexdigest(),
                    dataset_ids=dataset_ids,
                    tag_ids=tag_ids,
                )
            except Exception:
                try:
                    await self._object_store.delete(storage_key)
                except Exception:
                    logger.exception(
                        "Failed to compensate unpublished document object %s",
                        storage_key,
                    )
                raise
        finally:
            temp_path.unlink(missing_ok=True)

    async def delete_document(
        self,
        *,
        owner_user_id: str,
        document_id: str,
    ) -> dict[str, Any] | None:
        document = await self._repository.get_document(
            owner_user_id=owner_user_id,
            document_id=document_id,
        )
        if document is None:
            return None
        artifacts = await self._repository.list_artifacts(
            owner_user_id=owner_user_id,
            document_id=document_id,
        )

        keys = [artifact["storage_key"] for artifact in artifacts]
        keys.append(document["source_storage_key"])
        for key in dict.fromkeys(keys):
            await self._object_store.delete(str(key))

        return await self._repository.delete_document(
            owner_user_id=owner_user_id,
            document_id=document_id,
        )


def _normalize_pdf_filename(filename: str) -> str:
    normalized = PurePosixPath(filename.replace("\\", "/")).name.strip()
    if (
        not normalized
        or normalized in {".", ".."}
        or not normalized.lower().endswith(".pdf")
    ):
        raise UnsupportedMediaTypeError("Only PDF uploads are supported")
    return normalized


def _normalize_tag_name(name: str) -> tuple[str, str]:
    display_name = name.strip()
    if not display_name:
        raise ValueError("tag name must not be empty")
    return display_name, display_name.casefold()
