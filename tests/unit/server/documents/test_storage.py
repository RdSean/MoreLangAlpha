from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from src.server.documents.contracts import DocumentStorageError
from src.server.documents.storage import S3CompatibleDocumentStore


@pytest.mark.asyncio
async def test_document_store_rejects_keys_outside_documents_prefix(tmp_path) -> None:
    put_file = Mock(return_value=True)
    store = S3CompatibleDocumentStore(put_file=put_file)

    with pytest.raises(ValueError, match="document storage key"):
        await store.put_file(
            "education/doc-A1b2C3d4E5f6/source",
            tmp_path / "source.pdf",
            content_type="application/pdf",
        )

    put_file.assert_not_called()


@pytest.mark.parametrize(
    "key",
    [
        "documents/not-a-document/source",
        "documents/doc-A1b2C3d4E5f6",
        "documents/doc-A1b2C3d4E5f6/../source",
        "documents/doc-A1b2C3d4E5f6\\source",
    ],
)
@pytest.mark.asyncio
async def test_document_store_rejects_malformed_or_escaping_keys(key) -> None:
    store = S3CompatibleDocumentStore()

    with pytest.raises(ValueError, match="document storage key"):
        await store.delete(key)


@pytest.mark.asyncio
async def test_document_store_uses_document_upload_cap(tmp_path) -> None:
    calls: list[tuple[str, str, str | None, int | None]] = []

    def put_file(
        key: str,
        file_path: str,
        content_type: str | None,
        *,
        max_bytes: int | None,
    ) -> bool:
        calls.append((key, file_path, content_type, max_bytes))
        return True

    store = S3CompatibleDocumentStore(put_file=put_file, max_upload_bytes=52_428_800)
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4")

    await store.put_file(
        "documents/doc-A1b2C3d4E5f6/source",
        source,
        content_type="application/pdf",
    )

    assert calls == [
        (
            "documents/doc-A1b2C3d4E5f6/source",
            str(source),
            "application/pdf",
            52_428_800,
        )
    ]


@pytest.mark.asyncio
async def test_document_store_downloads_to_explicit_file_with_cap(tmp_path) -> None:
    calls: list[tuple[str, Path, int]] = []

    def download_to_file(key: str, destination: Path, *, max_bytes: int) -> int:
        calls.append((key, destination, max_bytes))
        return 123

    store = S3CompatibleDocumentStore(download_to_file=download_to_file)
    destination = tmp_path / "source.pdf"

    result = await store.get_file(
        "documents/doc-A1b2C3d4E5f6/source",
        destination,
        max_bytes=456,
    )

    assert result == 123
    assert calls == [
        ("documents/doc-A1b2C3d4E5f6/source", destination, 456),
    ]


@pytest.mark.asyncio
async def test_document_store_deletes_only_the_exact_supplied_key() -> None:
    deleted: list[str] = []

    def delete_object(key: str) -> bool:
        deleted.append(key)
        return True

    store = S3CompatibleDocumentStore(delete_object=delete_object)
    key = "documents/doc-A1b2C3d4E5f6/artifacts/job-A1b2C3d4E5f6/document.md"

    await store.delete(key)

    assert deleted == [key]


@pytest.mark.asyncio
async def test_document_store_opens_download_stream() -> None:
    calls: list[str] = []
    opened = SimpleNamespace(
        chunks=iter([b"# Lesson\n"]),
        content_length=9,
        close=Mock(),
    )

    def open_stream(key: str):
        calls.append(key)
        return opened

    store = S3CompatibleDocumentStore(open_download_stream=open_stream)
    key = "documents/doc-A1b2C3d4E5f6/artifacts/job-A1b2C3d4E5f6/document.md"

    result = await store.open_download(key)

    assert result is opened
    assert calls == [key]


@pytest.mark.asyncio
async def test_document_store_rejects_invalid_key_before_opening_download() -> None:
    open_stream = Mock()
    store = S3CompatibleDocumentStore(open_download_stream=open_stream)

    with pytest.raises(ValueError, match="document storage key"):
        await store.open_download("education/doc-A1b2C3d4E5f6/document.md")

    open_stream.assert_not_called()


@pytest.mark.asyncio
async def test_document_store_maps_download_open_failure_to_safe_error() -> None:
    open_stream = Mock(side_effect=OSError("backend details"))
    store = S3CompatibleDocumentStore(open_download_stream=open_stream)

    with pytest.raises(DocumentStorageError) as exc_info:
        await store.open_download(
            "documents/doc-A1b2C3d4E5f6/artifacts/"
            "job-A1b2C3d4E5f6/document.md"
        )

    assert exc_info.value.code == "storage_failed"
    assert "backend details" not in exc_info.value.safe_message


@pytest.mark.asyncio
async def test_document_store_maps_backend_failure_to_safe_domain_error(
    tmp_path,
) -> None:
    store = S3CompatibleDocumentStore(put_file=Mock(return_value=False))

    with pytest.raises(DocumentStorageError) as exc_info:
        await store.put_file(
            "documents/doc-A1b2C3d4E5f6/source",
            tmp_path / "source.pdf",
            content_type="application/pdf",
        )

    assert exc_info.value.code == "storage_failed"
    assert "document" in exc_info.value.safe_message.lower()
