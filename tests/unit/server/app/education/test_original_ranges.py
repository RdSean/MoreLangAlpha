from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.middleware.gzip import GZipMiddleware

from src.server.app.education import textbooks
from src.server.utils.api import get_current_user_id

BOOK = 'bc5734a8-8a30-459f-a1f3-8551feb4c169'


@pytest.mark.asyncio
@pytest.mark.parametrize('partial', [False, True])
async def test_pdf_stream_is_identity_with_correct_range_headers(monkeypatch, partial):
    from src.server.documents.http_range import ByteRange
    body = b'%PDF-' * 400
    close = Mock()
    opened = SimpleNamespace(chunks=iter([body]), content_length=len(body), close=close,
        etag='"v1"', last_modified=datetime(2026, 10, 14, tzinfo=UTC))
    download = SimpleNamespace(filename='book.pdf', media_type='application/pdf', object_download=opened,
        byte_range=ByteRange(0, len(body) - 1) if partial else None, total_length=10000 if partial else None)
    opener = AsyncMock(return_value=download)
    monkeypatch.setattr(textbooks, 'open_book_original', opener)
    app = FastAPI()
    app.include_router(textbooks.router)
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.dependency_overrides[get_current_user_id] = lambda: 'student'
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        headers = {'Accept-Encoding': 'gzip'}
        if partial:
            headers.update({'Range': f'bytes=0-{len(body)-1}', 'If-Range': '"v1"'})
        response = await client.get(f'/api/v1/education/textbooks/{BOOK}/original', headers=headers)
    assert response.status_code == (206 if partial else 200)
    assert response.content == body
    assert response.headers['content-encoding'] == 'identity'
    assert response.headers['accept-ranges'] == 'bytes'
    assert response.headers['content-length'] == str(len(body))
    assert response.headers['etag'] == '"v1"'
    assert response.headers['cache-control'] == 'private, no-store'
    if partial:
        assert response.headers['content-range'] == f'bytes 0-{len(body)-1}/10000'
        opener.assert_awaited_once_with(user_id='student', textbook_id=BOOK, range_header=f'bytes=0-{len(body)-1}', if_range='"v1"')
    close.assert_called_once()


@pytest.mark.asyncio
async def test_unsatisfiable_range_uses_authenticated_total_without_body(monkeypatch):
    from src.server.documents.http_range import RangeNotSatisfiable
    monkeypatch.setattr(textbooks, 'open_book_original', AsyncMock(side_effect=RangeNotSatisfiable(100)))
    app = FastAPI()
    app.include_router(textbooks.router)
    app.dependency_overrides[get_current_user_id] = lambda: 'student'
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get(f'/api/v1/education/textbooks/{BOOK}/original', headers={'Range': 'bytes=100-'})
    assert response.status_code == 416
    assert response.headers['content-range'] == 'bytes */100'
    assert response.headers['cache-control'] == 'private, no-store'


@pytest.mark.asyncio
async def test_member_gate_precedes_range_metadata(monkeypatch):
    from src.server.services import education_book_original as service
    from src.server.services.education_textbooks import TextbookNotFoundError
    monkeypatch.setattr(service, 'get_managed_source_for_user', AsyncMock(return_value=None))
    library = SimpleNamespace(open_source_download=AsyncMock())
    with pytest.raises(TextbookNotFoundError):
        await service.open_book_original(user_id='unassigned', textbook_id=BOOK, range_header='bytes=100-', library=library)
    library.open_source_download.assert_not_awaited()
