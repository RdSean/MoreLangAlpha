from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from src.server.channels.agent_adapters.langalpha_flash import LangAlphaFlashAdapter
from src.server.channels.contracts import (
    AgentSession,
    AgentTurn,
    OpenSessionRequest,
    ResolvedImage,
)


class FakeResponse:
    def __init__(self, status_code: int, *, json_data=None, lines=(), headers=None):
        self.status_code = status_code
        self._json_data = json_data
        self._lines = list(lines)
        self.headers = headers or {}

    def json(self):
        return self._json_data

    async def aread(self):
        return b""

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class FakeClient:
    def __init__(self, responses):
        self.responses = responses
        self.posts = []
        self.gets = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return self.responses.pop(0)

    @asynccontextmanager
    async def stream(self, method, url, **kwargs):
        self.gets.append((method, url, kwargs))
        yield self.responses.pop(0)


def session(ref="external-thread-1"):
    return AgentSession(ref=f"external:{ref}", opened_at=__import__("datetime").datetime.now(), actor_ref="user-1")


@pytest.mark.asyncio
async def test_flash_adapter_sends_image_context_and_collects_final_text(monkeypatch):
    fake = FakeClient(
        [
            FakeResponse(200, json_data={"status": "dispatched", "thread_id": "thread-1", "run_id": "run-1"}),
            FakeResponse(
                200,
                lines=[
                    'event: metadata',
                    'data: {"thread_id":"thread-1"}',
                    '',
                    'event: message_chunk',
                    'data: {"content_type":"text","content":"完整"}',
                    '',
                    'event: message_chunk',
                    'data: {"content_type":"text","content":"回复"}',
                    '',
                    'event: run_end',
                    'data: {"status":"completed"}',
                    '',
                ],
            ),
        ]
    )
    monkeypatch.setattr(
        "src.server.channels.agent_adapters.langalpha_flash.httpx.AsyncClient",
        lambda **kwargs: fake,
    )
    adapter = LangAlphaFlashAdapter(base_url="http://backend", service_token="svc")
    result = await adapter.run_turn(
        session(),
        AgentTurn(
            request_key="key-1",
            text="解释",
            received_at=__import__("datetime").datetime.now(),
            images=(ResolvedImage("data:image/png;base64,", "image/png", 3, 1, 1),),
        ),
    )
    body = fake.posts[0][1]["json"]
    assert body["agent_mode"] == "flash"
    assert body["platform"] == "wechat"
    assert body["external_thread_id"] == "external-thread-1"
    assert fake.posts[0][1]["headers"]["X-User-Id"] == "user-1"
    assert body["additional_context"][0]["type"] == "image"
    assert body["additional_context"][0]["data"] == "data:image/png;base64,"
    assert "完整回复" == "".join(part.text for part in result.parts)
    assert result.session_ref == "thread-1"


@pytest.mark.asyncio
async def test_duplicate_request_reconnects_to_existing_run(monkeypatch):
    fake = FakeClient(
        [
            FakeResponse(409, json_data={"detail": {"code": "duplicate_request", "thread_id": "thread-1", "run_id": "run-1"}}),
            FakeResponse(
                200,
                lines=[
                    'event: message_chunk',
                    'data: {"content_type":"text","content":"恢复"}',
                    '',
                    'event: run_end',
                    'data: {"status":"completed"}',
                    '',
                ],
            ),
        ]
    )
    monkeypatch.setattr(
        "src.server.channels.agent_adapters.langalpha_flash.httpx.AsyncClient",
        lambda **kwargs: fake,
    )
    adapter = LangAlphaFlashAdapter(base_url="http://backend", service_token="svc")
    result = await adapter.run_turn(
        session(),
        AgentTurn("same-key", "再次发送", __import__("datetime").datetime.now()),
    )
    assert "恢复" == "".join(part.text for part in result.parts)
    assert fake.gets[0][1].endswith("/api/v1/threads/thread-1/messages/stream?run_id=run-1")
