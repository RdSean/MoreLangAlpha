"""Bounded object-store boundary for private document sources and artifacts."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Protocol

from src.config.settings import get_document_parsing_config
from src.server.documents.contracts import DocumentStorageError
from src.utils.storage import s3_compatible


_DOCUMENT_ID_RE = re.compile(r"^doc-[0-9A-Za-z]{12}$")
PutFile = Callable[..., bool]
DownloadToFile = Callable[..., int]
DeleteObject = Callable[[str], bool]


class OpenedDocumentObject(Protocol):
    """Object content and lifecycle returned by a document storage backend."""

    chunks: Iterator[bytes]
    content_length: int | None
    close: Callable[[], None]


OpenDownloadStream = Callable[[str], OpenedDocumentObject]


class DocumentObjectStore(Protocol):
    """Storage operations used by document services."""

    async def put_file(
        self,
        key: str,
        source: Path,
        *,
        content_type: str,
    ) -> None: ...

    async def get_file(
        self,
        key: str,
        destination: Path,
        *,
        max_bytes: int,
    ) -> int: ...

    async def delete(self, key: str) -> None: ...

    async def open_download(self, key: str) -> OpenedDocumentObject: ...


class S3CompatibleDocumentStore:
    """Async document adapter over the repository's synchronous boto3 helpers."""

    def __init__(
        self,
        *,
        put_file: PutFile | None = None,
        download_to_file: DownloadToFile | None = None,
        delete_object: DeleteObject | None = None,
        open_download_stream: OpenDownloadStream | None = None,
        max_upload_bytes: int | None = None,
    ) -> None:
        self._put_file = put_file or s3_compatible.upload_file
        self._download_to_file = (
            download_to_file or s3_compatible.download_to_file
        )
        self._delete_object = delete_object or s3_compatible.delete_object
        self._open_download_stream = (
            open_download_stream or s3_compatible.open_download_stream
        )
        self._max_upload_bytes = (
            get_document_parsing_config().max_upload_bytes
            if max_upload_bytes is None
            else max_upload_bytes
        )

    async def put_file(
        self,
        key: str,
        source: Path,
        *,
        content_type: str,
    ) -> None:
        _validate_document_key(key)
        try:
            uploaded = await asyncio.to_thread(
                self._put_file,
                key,
                str(source),
                content_type,
                max_bytes=self._max_upload_bytes,
            )
        except Exception as exc:
            raise DocumentStorageError("Document upload failed") from exc
        if not uploaded:
            raise DocumentStorageError("Document upload failed")

    async def get_file(
        self,
        key: str,
        destination: Path,
        *,
        max_bytes: int,
    ) -> int:
        _validate_document_key(key)
        try:
            return await asyncio.to_thread(
                self._download_to_file,
                key,
                destination,
                max_bytes=max_bytes,
            )
        except Exception as exc:
            raise DocumentStorageError("Document download failed") from exc

    async def delete(self, key: str) -> None:
        _validate_document_key(key)
        try:
            deleted = await asyncio.to_thread(self._delete_object, key)
        except Exception as exc:
            raise DocumentStorageError("Document deletion failed") from exc
        if not deleted:
            raise DocumentStorageError("Document deletion failed")

    async def open_download(self, key: str) -> OpenedDocumentObject:
        _validate_document_key(key)
        try:
            return await asyncio.to_thread(self._open_download_stream, key)
        except Exception as exc:
            raise DocumentStorageError("Document download failed") from exc


def _validate_document_key(key: str) -> None:
    raw_parts = key.split("/")
    if (
        "\\" in key
        or len(raw_parts) < 3
        or any(part in {"", ".", ".."} for part in raw_parts)
        or raw_parts[0] != "documents"
        or _DOCUMENT_ID_RE.fullmatch(raw_parts[1]) is None
    ):
        raise ValueError("invalid document storage key")
