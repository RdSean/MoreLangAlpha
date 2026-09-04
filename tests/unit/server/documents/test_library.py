from __future__ import annotations

from collections.abc import AsyncIterator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.server.documents.contracts import FileTooLargeError, UnsupportedMediaTypeError
from src.server.documents.library import DocumentLibraryService
from src.server.database.documents import DocumentListFilter


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


class _Repository:
    def __init__(self) -> None:
        self.created: dict[str, object] | None = None
        self.deleted: tuple[str, str] | None = None
        self.create_error: Exception | None = None
        self.document = {
            "document_id": "doc-A1b2C3d4E5f6",
            "owner_user_id": "owner-1",
            "source_storage_key": "documents/doc-A1b2C3d4E5f6/source",
        }
        self.artifacts = [
            {
                "storage_key": (
                    "documents/doc-A1b2C3d4E5f6/artifacts/"
                    "job-A1b2C3d4E5f6/document.md"
                ),
            },
            {
                "storage_key": (
                    "documents/doc-A1b2C3d4E5f6/artifacts/"
                    "job-A1b2C3d4E5f6/images/page-1.png"
                ),
            },
        ]

    async def create_document(self, **kwargs):
        self.created = kwargs
        if self.create_error:
            raise self.create_error
        return dict(kwargs)

    async def get_document(self, **kwargs):
        assert kwargs == {
            "owner_user_id": "owner-1",
            "document_id": "doc-A1b2C3d4E5f6",
        }
        return self.document

    async def list_artifacts(self, **kwargs):
        assert kwargs == {
            "owner_user_id": "owner-1",
            "document_id": "doc-A1b2C3d4E5f6",
        }
        return self.artifacts

    async def delete_document(self, **kwargs):
        self.deleted = (kwargs["owner_user_id"], kwargs["document_id"])
        return self.document


class _ObjectStore:
    def __init__(self) -> None:
        self.puts: list[tuple[str, bytes, str]] = []
        self.put_paths = []
        self.deletes: list[str] = []

    async def put_file(self, key, source, *, content_type):
        self.put_paths.append(source)
        self.puts.append((key, source.read_bytes(), content_type))

    async def delete(self, key):
        self.deletes.append(key)


def _service(repository=None, store=None, *, max_upload_bytes=1024):
    return DocumentLibraryService(
        repository=repository or _Repository(),
        object_store=store or _ObjectStore(),
        max_upload_bytes=max_upload_bytes,
        id_factory=lambda kind: {
            "document": "doc-A1b2C3d4E5f6",
            "dataset": "dts-A1b2C3d4E5f6",
            "tag": "tag-A1b2C3d4E5f6",
        }[kind],
    )


@pytest.mark.asyncio
async def test_upload_streams_to_temp_file_hashes_and_persists_pdf() -> None:
    repository = _Repository()
    store = _ObjectStore()
    service = _service(repository, store)

    result = await service.upload_pdf(
        owner_user_id="owner-1",
        original_filename="folder/source.pdf",
        declared_media_type="application/pdf",
        chunks=_chunks(b"%PD", b"F-1.4\ncontent"),
    )

    assert result["document_id"] == "doc-A1b2C3d4E5f6"
    assert repository.created is not None
    assert repository.created["original_filename"] == "source.pdf"
    assert repository.created["source_size_bytes"] == 16
    assert repository.created["source_sha256"] == (
        "4fbf22661c0285c55f8fa7518f954910e8b0c33750658fc6863f66aa6b94c7fd"
    )
    assert store.puts == [
        (
            "documents/doc-A1b2C3d4E5f6/source",
            b"%PDF-1.4\ncontent",
            "application/pdf",
        ),
    ]
    assert all(not path.exists() for path in store.put_paths)


@pytest.mark.asyncio
async def test_upload_rejects_declared_length_over_limit_before_reading() -> None:
    was_read = False

    async def stream():
        nonlocal was_read
        was_read = True
        yield b"%PDF-1.4"

    with pytest.raises(FileTooLargeError):
        await _service(max_upload_bytes=8).upload_pdf(
            owner_user_id="owner-1",
            original_filename="source.pdf",
            declared_media_type="application/pdf",
            declared_length=9,
            chunks=stream(),
        )

    assert not was_read


@pytest.mark.asyncio
async def test_upload_rejects_stream_that_crosses_limit() -> None:
    store = _ObjectStore()

    with pytest.raises(FileTooLargeError):
        await _service(store=store, max_upload_bytes=8).upload_pdf(
            owner_user_id="owner-1",
            original_filename="source.pdf",
            declared_media_type="application/pdf",
            chunks=_chunks(b"%PDF-", b"1234"),
        )

    assert store.puts == []


@pytest.mark.parametrize(
    ("filename", "media_type", "content"),
    [
        ("source.txt", "application/pdf", b"%PDF-1.4"),
        ("source.pdf", "text/plain", b"%PDF-1.4"),
        ("source.pdf", "application/pdf", b"not a pdf"),
    ],
)
@pytest.mark.asyncio
async def test_upload_rejects_non_pdf_signature_filename_or_media_type(
    filename,
    media_type,
    content,
) -> None:
    with pytest.raises(UnsupportedMediaTypeError):
        await _service().upload_pdf(
            owner_user_id="owner-1",
            original_filename=filename,
            declared_media_type=media_type,
            chunks=_chunks(content),
        )


@pytest.mark.asyncio
async def test_database_failure_deletes_only_the_new_source_key() -> None:
    repository = _Repository()
    repository.create_error = RuntimeError("database unavailable")
    store = _ObjectStore()

    with pytest.raises(RuntimeError, match="database unavailable"):
        await _service(repository, store).upload_pdf(
            owner_user_id="owner-1",
            original_filename="source.pdf",
            declared_media_type="application/pdf",
            chunks=_chunks(b"%PDF-1.4"),
        )

    assert store.deletes == ["documents/doc-A1b2C3d4E5f6/source"]
    assert all(not path.exists() for path in store.put_paths)


@pytest.mark.asyncio
async def test_dataset_and_tags_are_attached_after_owner_validation() -> None:
    repository = _Repository()

    await _service(repository=repository).upload_pdf(
        owner_user_id="owner-1",
        original_filename="source.pdf",
        declared_media_type="application/pdf",
        dataset_ids=("dts-A1b2C3d4E5f6",),
        tag_ids=("tag-A1b2C3d4E5f6", "tag-G7h8I9j0K1l2"),
        chunks=_chunks(b"%PDF-1.4"),
    )

    assert repository.created is not None
    assert repository.created["dataset_ids"] == ("dts-A1b2C3d4E5f6",)
    assert repository.created["tag_ids"] == (
        "tag-A1b2C3d4E5f6",
        "tag-G7h8I9j0K1l2",
    )


@pytest.mark.asyncio
async def test_delete_removes_only_keys_loaded_from_owned_rows() -> None:
    repository = _Repository()
    store = _ObjectStore()

    result = await _service(repository, store).delete_document(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
    )

    assert result == repository.document
    assert store.deletes == [
        "documents/doc-A1b2C3d4E5f6/artifacts/job-A1b2C3d4E5f6/document.md",
        "documents/doc-A1b2C3d4E5f6/artifacts/job-A1b2C3d4E5f6/images/page-1.png",
        "documents/doc-A1b2C3d4E5f6/source",
    ]
    assert repository.deleted == ("owner-1", "doc-A1b2C3d4E5f6")


@pytest.mark.asyncio
async def test_library_operations_keep_owner_and_sql_behind_service() -> None:
    repository = SimpleNamespace(
        create_dataset=AsyncMock(return_value={"dataset_id": "dts-A1b2C3d4E5f6"}),
        list_datasets=AsyncMock(return_value=([], 0)),
        list_documents=AsyncMock(return_value=([], 0)),
        create_tag=AsyncMock(return_value={"tag_id": "tag-A1b2C3d4E5f6"}),
        list_tags=AsyncMock(return_value=[]),
        update_tag=AsyncMock(return_value={"tag_id": "tag-A1b2C3d4E5f6"}),
        delete_tag=AsyncMock(return_value={"tag_id": "tag-A1b2C3d4E5f6"}),
        update_document=AsyncMock(return_value={"document_id": "doc-A1b2C3d4E5f6"}),
        replace_dataset_memberships=AsyncMock(return_value=None),
        replace_tag_assignments=AsyncMock(return_value=None),
    )
    service = _service(repository=repository)
    filters = DocumentListFilter(limit=25)

    await service.create_dataset(
        owner_user_id="owner-1",
        name="Mathematics",
        description=None,
    )
    await service.list_datasets(owner_user_id="owner-1", limit=25, offset=0)
    await service.list_documents(owner_user_id="owner-1", filters=filters)
    await service.create_tag(owner_user_id="owner-1", name=" Mathematics ")
    await service.list_tags(owner_user_id="owner-1")
    await service.update_tag(
        owner_user_id="owner-1",
        tag_id="tag-A1b2C3d4E5f6",
        name=" Algebra ",
    )
    await service.delete_tag(
        owner_user_id="owner-1",
        tag_id="tag-A1b2C3d4E5f6",
    )
    await service.patch_document(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
        original_filename="renamed.pdf",
        dataset_ids=("dts-A1b2C3d4E5f6",),
        tag_ids=("tag-A1b2C3d4E5f6",),
    )

    repository.create_dataset.assert_awaited_once_with(
        owner_user_id="owner-1",
        dataset_id="dts-A1b2C3d4E5f6",
        name="Mathematics",
        description=None,
    )
    repository.list_documents.assert_awaited_once_with(
        owner_user_id="owner-1",
        filters=filters,
    )
    repository.create_tag.assert_awaited_once_with(
        owner_user_id="owner-1",
        tag_id="tag-A1b2C3d4E5f6",
        name="Mathematics",
        normalized_name="mathematics",
    )
    repository.update_tag.assert_awaited_once_with(
        owner_user_id="owner-1",
        tag_id="tag-A1b2C3d4E5f6",
        name="Algebra",
        normalized_name="algebra",
    )
    repository.update_document.assert_awaited_once_with(
        owner_user_id="owner-1",
        document_id="doc-A1b2C3d4E5f6",
        original_filename="renamed.pdf",
    )
    repository.replace_dataset_memberships.assert_awaited_once()
    repository.replace_tag_assignments.assert_awaited_once()
