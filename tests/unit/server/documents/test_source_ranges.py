from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.server.documents.library import DocumentLibraryService
from src.server.documents.storage import S3CompatibleDocumentStore
from src.utils.storage.s3_compatible import ObjectMetadata


def library_fixture():
    key = 'documents/doc-A1b2C3d4E5f6/source.pdf'
    repository = SimpleNamespace(get_document=AsyncMock(return_value={
        'source_storage_key': key, 'original_filename': 'book.pdf', 'media_type': 'application/pdf',
    }))
    metadata = ObjectMetadata(100, '"v1"', datetime(2026, 10, 14, tzinfo=UTC))
    opened = SimpleNamespace(content_length=10, content_range='bytes 90-99/100', etag='"v1"', close=Mock())
    store = SimpleNamespace(get_metadata=AsyncMock(return_value=metadata), open_range=AsyncMock(return_value=opened), open_download=AsyncMock(return_value=opened))
    return DocumentLibraryService(repository=repository, object_store=store), repository, store, key, opened


@pytest.mark.asyncio
async def test_library_normalizes_suffix_and_pins_object_version():
    library, _, store, key, opened = library_fixture()
    download = await library.open_source_download(owner_user_id='parent', document_id='book', range_header='bytes=-10')
    assert download.object_download is opened
    assert download.total_length == 100
    assert (download.byte_range.start, download.byte_range.end) == (90, 99)
    store.open_range.assert_awaited_once()
    args = store.open_range.call_args
    assert args.args[0] == key
    assert args.kwargs['if_match'] == '"v1"'
    store.open_download.assert_not_awaited()


@pytest.mark.asyncio
async def test_library_does_not_head_full_download_or_inaccessible_document():
    library, repository, store, _, _ = library_fixture()
    await library.open_source_download(owner_user_id='parent', document_id='book')
    store.get_metadata.assert_not_awaited()
    repository.get_document.return_value = None
    assert await library.open_source_download(owner_user_id='parent', document_id='book', range_header='bytes=0-1') is None
    store.get_metadata.assert_not_awaited()
    store.open_range.assert_not_awaited()


@pytest.mark.asyncio
async def test_if_range_mismatch_ignores_even_unsatisfiable_range():
    library, _, store, _, _ = library_fixture()
    download = await library.open_source_download(owner_user_id='parent', document_id='book', range_header='bytes=1000-', if_range='"old"')
    assert download.byte_range is None
    store.open_range.assert_not_awaited()
    store.open_download.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['etag', 'content_range', 'content_length'])
async def test_library_rejects_inconsistent_storage_range_and_closes_it(mutation):
    library, _, _, _, opened = library_fixture()
    setattr(opened, mutation, {'etag': '"changed"', 'content_range': 'bytes 0-99/100', 'content_length': 100}[mutation])
    with pytest.raises(Exception, match='range|changed'):
        await library.open_source_download(owner_user_id='parent', document_id='book', range_header='bytes=-10')
    opened.close.assert_called_once()


@pytest.mark.asyncio
async def test_store_forwards_only_validated_keys_and_range():
    opened = object()
    open_stream = Mock(return_value=opened)
    metadata_reader = Mock(return_value=ObjectMetadata(100, '"v1"', None))
    store = S3CompatibleDocumentStore(open_download_stream=open_stream, get_object_metadata=metadata_reader)
    from src.server.documents.http_range import ByteRange
    key = 'documents/doc-A1b2C3d4E5f6/source.pdf'
    assert await store.get_metadata(key) == metadata_reader.return_value
    assert await store.open_range(key, ByteRange(0, 9), if_match='"v1"') is opened
    open_stream.assert_called_once_with(key, byte_range=(0, 9), if_match='"v1"')
    with pytest.raises(ValueError):
        await store.get_metadata('education/not-allowed/source.pdf')
    with pytest.raises(ValueError):
        await store.open_range('documents/../source.pdf', ByteRange(0, 9), if_match='"v1"')
