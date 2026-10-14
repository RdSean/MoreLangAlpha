from datetime import UTC, datetime
from io import BytesIO
from unittest.mock import Mock

import pytest

from src.utils.storage import s3_compatible as storage


def test_metadata_reads_only_head(monkeypatch):
    modified = datetime(2026, 10, 14, tzinfo=UTC)
    client = Mock()
    client.head_object.return_value = {'ContentLength': 100, 'ETag': '"v1"', 'LastModified': modified}
    monkeypatch.setattr(storage, '_get_client', lambda: client)
    metadata = storage.get_object_metadata('education/tests/source.pdf')
    assert (metadata.content_length, metadata.etag, metadata.last_modified) == (100, '"v1"', modified)
    client.get_object.assert_not_called()


def test_range_is_forwarded_to_s3_and_response_metadata_preserved(monkeypatch):
    body = BytesIO(b'0123')
    client = Mock()
    client.get_object.return_value = {'Body': body, 'ContentLength': 4, 'ContentRange': 'bytes 10-13/100', 'ETag': '"v1"'}
    monkeypatch.setattr(storage, '_get_client', lambda: client)
    opened = storage.open_download_stream('education/tests/source.pdf', byte_range=(10, 13), if_match='"v1"')
    assert b''.join(opened.chunks) == b'0123'
    assert opened.content_length == 4
    assert opened.content_range == 'bytes 10-13/100'
    assert opened.etag == '"v1"'
    assert body.closed
    opened.close()
    client.get_object.assert_called_once_with(Bucket=storage.StorageConfig.BUCKET_NAME, Key='education/tests/source.pdf', Range='bytes=10-13', IfMatch='"v1"')


def test_full_stream_keeps_existing_call_shape(monkeypatch):
    client = Mock()
    client.get_object.return_value = {'Body': BytesIO(b'pdf'), 'ContentLength': 3}
    monkeypatch.setattr(storage, '_get_client', lambda: client)
    opened = storage.open_download_stream('education/tests/source.pdf')
    assert b''.join(opened.chunks) == b'pdf'
    client.get_object.assert_called_once_with(Bucket=storage.StorageConfig.BUCKET_NAME, Key='education/tests/source.pdf')


def test_early_close_and_failed_reads_release_body(monkeypatch):
    body = Mock()
    body.read.side_effect = OSError('read failed')
    client = Mock()
    client.get_object.return_value = {'Body': body, 'ContentLength': 4}
    monkeypatch.setattr(storage, '_get_client', lambda: client)
    opened = storage.open_download_stream('education/tests/source.pdf')
    with pytest.raises(OSError):
        next(opened.chunks)
    opened.close()
    body.close.assert_called_once()
