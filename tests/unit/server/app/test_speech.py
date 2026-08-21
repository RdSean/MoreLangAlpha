"""Speech relay WebSocket route."""

from __future__ import annotations

import gzip
import json
import struct
from unittest.mock import AsyncMock

import pytest

from src.config.settings import VolcengineAsrConfig

CONFIG = VolcengineAsrConfig(
    app_id="test-app",
    access_token="test-token",
    access_secret="test-secret",
    cluster="test-cluster",
    ws_url="wss://asr.example.test/api/v2/asr",
)


def _server_response(text: str, *, definite: bool) -> bytes:
    body = {"code": 1000, "result": [{"utterances": [{"text": text, "definite": definite}]}]}
    payload = gzip.compress(json.dumps(body).encode())
    return bytes((0x11, 0x90, 0x11, 0)) + struct.pack("!I", len(payload)) + payload


class FakeWebSocket:
    def __init__(self, messages: list[dict[str, object]]) -> None:
        self.messages = messages
        self.accepted = False
        self.sent_json: list[dict[str, object]] = []
        self.close_code: int | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def receive(self) -> dict[str, object]:
        return self.messages.pop(0)

    async def send_json(self, event: dict[str, object]) -> None:
        self.sent_json.append(event)

    async def close(self, code: int = 1000) -> None:
        self.close_code = code


class FakeUpstream:
    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.responses = [_server_response("", definite=True), _server_response("你好", definite=False), _server_response("你好", definite=True)]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def send(self, frame: bytes) -> None:
        self.sent.append(frame)

    async def recv(self) -> bytes:
        return self.responses.pop(0)


@pytest.mark.asyncio
async def test_transcribe_stream_forwards_pcm_and_returns_live_events(monkeypatch) -> None:
    from src.server.app import speech

    browser = FakeWebSocket([
        {"type": "websocket.receive", "text": json.dumps({"type": "start"})},
        {"type": "websocket.receive", "bytes": b"pcm"},
        {"type": "websocket.receive", "text": json.dumps({"type": "stop"})},
    ])
    upstream = FakeUpstream()
    connect_kwargs: dict[str, object] = {}

    def connect(*_args, **kwargs):
        connect_kwargs.update(kwargs)
        return upstream

    monkeypatch.setattr(speech, "authenticate_websocket", AsyncMock(return_value="user-1"))
    monkeypatch.setattr(speech, "get_volcengine_asr_config", lambda: CONFIG)
    monkeypatch.setattr(speech.websockets, "connect", connect)

    await speech.transcribe_stream(browser)

    assert browser.accepted is True
    assert browser.sent_json == [
        {"type": "partial", "text": "你好", "definite": False},
        {"type": "final", "text": "你好", "definite": True},
        {"type": "done"},
    ]
    assert len(upstream.sent) == 3
    assert connect_kwargs["proxy"] is None


@pytest.mark.asyncio
async def test_transcribe_stream_reports_unconfigured_service(monkeypatch) -> None:
    from src.server.app import speech

    browser = FakeWebSocket([])
    monkeypatch.setattr(speech, "authenticate_websocket", AsyncMock(return_value="user-1"))
    monkeypatch.setattr(speech, "get_volcengine_asr_config", lambda: None)

    await speech.transcribe_stream(browser)

    assert browser.sent_json == [{"type": "error", "code": "service_unavailable"}]
    assert browser.close_code == 1013
