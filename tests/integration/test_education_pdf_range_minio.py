"""Opt-in exact-key MinIO range reads; no real textbook objects are changed."""

import os
from pathlib import Path
from uuid import uuid4

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


def test_minio_returns_exact_head_middle_tail_and_validator(tmp_path: Path):
    if os.getenv('RUN_DOCUMENT_MINIO_TESTS') != '1':
        pytest.skip('set RUN_DOCUMENT_MINIO_TESTS=1 for configured development MinIO')
    from src.utils.storage import s3_compatible as storage
    from botocore.exceptions import ClientError

    key = f'education/tests/pdf-range/{uuid4().hex}/source.pdf'
    payload = Path('tests/fixtures/documents/mixed.pdf').read_bytes()
    source = tmp_path / 'source.pdf'
    source.write_bytes(payload)
    created = False
    try:
        assert storage.upload_file(key, str(source), 'application/pdf', max_bytes=2 * 1024 * 1024)
        created = True
        metadata = storage.get_object_metadata(key)
        assert metadata.content_length == len(payload)
        assert metadata.etag
        for start, end in [(0, 127), (len(payload)//2, len(payload)//2 + 127), (len(payload)-128, len(payload)-1)]:
            opened = storage.open_download_stream(key, byte_range=(start, end), if_match=metadata.etag)
            try:
                assert opened.content_range == f'bytes {start}-{end}/{len(payload)}'
                assert opened.content_length == 128
                assert opened.etag == metadata.etag
                assert b''.join(opened.chunks) == payload[start:end+1]
            finally:
                opened.close()
        with pytest.raises(ClientError) as error:
            storage.open_download_stream(key, byte_range=(0, 127), if_match='"wrong-version"')
        assert error.value.response['Error']['Code'] == 'PreconditionFailed'
    finally:
        if created:
            assert storage.delete_object(key)
