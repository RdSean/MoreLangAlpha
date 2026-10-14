import asyncio
import socket
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
import uvicorn
from fastapi import FastAPI

from src.server.app.education import textbooks
from src.server.utils.api import get_current_user_id

pytestmark = [pytest.mark.integration, pytest.mark.enable_socket]


@pytest.mark.asyncio
async def test_client_disconnect_closes_private_pdf_object(monkeypatch):
    closed = threading.Event()
    def chunks():
        try:
            for _ in range(100):
                yield b'x' * 65536
                time.sleep(0.02)
        finally:
            closed.set()
    opened = SimpleNamespace(chunks=chunks(), content_length=100 * 65536, close=closed.set)
    monkeypatch.setattr(textbooks, 'open_book_original', AsyncMock(return_value=SimpleNamespace(filename='source.pdf', media_type='application/pdf', object_download=opened)))
    app = FastAPI()
    app.include_router(textbooks.router)
    app.dependency_overrides[get_current_user_id] = lambda: 'parent'
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, lifespan='off', log_level='error'))
    task = asyncio.create_task(server.serve(sockets=[sock]))
    try:
        while not server.started:
            await asyncio.sleep(0.01)
        async with httpx.AsyncClient() as client:
            async with client.stream('GET', f'http://127.0.0.1:{port}/api/v1/education/textbooks/bc5734a8-8a30-459f-a1f3-8551feb4c169/original') as response:
                assert response.status_code == 200
                async for chunk in response.aiter_bytes():
                    assert chunk
                    break
        assert await asyncio.to_thread(closed.wait, 2)
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 5)
        sock.close()
