from __future__ import annotations

from pathlib import Path
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
async def test_signed_download_uses_short_ttl() -> None:
    calls: list[tuple[str, int, str]] = []

    def create_url(
        key: str,
        *,
        expires_seconds: int,
        download_name: str,
    ) -> str:
        calls.append((key, expires_seconds, download_name))
        return "https://storage.example/signed"

    store = S3CompatibleDocumentStore(
        create_presigned_download_url=create_url,
        signed_url_ttl_seconds=300,
    )
    key = "documents/doc-A1b2C3d4E5f6/artifacts/job-A1b2C3d4E5f6/document.md"

    result = await store.create_signed_download_url(key, download_name="教材.md")

    assert result == "https://storage.example/signed"
    assert calls == [(key, 300, "教材.md")]


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
