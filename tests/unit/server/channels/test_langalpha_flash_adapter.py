from __future__ import annotations

from contextlib import asynccontextmanager

import pytest

from src.server.channels.agent_adapters.langalpha_flash import (
    FlashAgentError,
    LangAlphaFlashAdapter,
)
from src.server.channels.contracts import (
    AgentSession,
    AgentTurn,
    ResolvedImage,
)
from src.server.channels.events import (
    Commentary,
    MessageChunk,
    MessageStop,
    ToolCallChunk,
    ToolCallFinished,
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
    return AgentSession(
        ref=f"external:{ref}",
        opened_at=__import__("datetime").datetime.now(),
        actor_ref="user-1",
    )


@pytest.mark.asyncio
async def test_flash_adapter_sends_image_context_and_collects_final_text(monkeypatch):
    fake = FakeClient(
        [
            FakeResponse(
                200,
                json_data={
                    "status": "dispatched",
                    "thread_id": "thread-1",
                    "run_id": "run-1",
                },
            ),
            FakeResponse(
                200,
                lines=[
                    "event: metadata",
                    'data: {"thread_id":"thread-1"}',
                    "",
                    "event: message_chunk",
                    'data: {"content_type":"text","content":"完整"}',
                    "",
                    "event: message_chunk",
                    'data: {"content_type":"text","content":"回复"}',
                    "",
                    "event: run_end",
                    'data: {"status":"completed"}',
                    "",
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
            channel_type="telegram",
            images=(ResolvedImage("data:image/png;base64,", "image/png", 3, 1, 1),),
        ),
    )
    body = fake.posts[0][1]["json"]
    assert body["agent_mode"] == "flash"
    assert body["platform"] == "telegram"
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
            FakeResponse(
                409,
                json_data={
                    "detail": {
                        "code": "duplicate_request",
                        "thread_id": "thread-1",
                        "run_id": "run-1",
                    }
                },
            ),
            FakeResponse(
                200,
                lines=[
                    "event: message_chunk",
                    'data: {"content_type":"text","content":"恢复"}',
                    "",
                    "event: run_end",
                    'data: {"status":"completed"}',
                    "",
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
    assert fake.gets[0][1].endswith(
        "/api/v1/threads/thread-1/messages/stream?run_id=run-1"
    )


@pytest.mark.asyncio
async def test_flash_adapter_only_collects_main_text_from_sse(monkeypatch):
    fake = FakeClient(
        [
            FakeResponse(
                200,
                json_data={
                    "status": "dispatched",
                    "thread_id": "thread-1",
                    "run_id": "run-1",
                },
            ),
            FakeResponse(
                200,
                lines=[
                    "event: message_chunk",
                    'data: {"agent":"main","content_type":"reasoning","content":"内部思考"}',
                    "",
                    "event: message_chunk",
                    'data: {"agent":"task:skill-1","content_type":"text","content":"技能调用过程"}',
                    "",
                    "event: commentary",
                    'data: {"content":"工具执行中"}',
                    "",
                    "event: tool_call_result",
                    'data: {"content":"工具返回值"}',
                    "",
                    "event: message_chunk",
                    'data: {"agent":"main","content_type":"text","content":"最终结果"}',
                    "",
                    "event: run_end",
                    'data: {"status":"completed"}',
                    "",
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
        AgentTurn("key-1", "你好", __import__("datetime").datetime.now()),
    )

    assert "最终结果" == "".join(part.text for part in result.parts)


@pytest.mark.asyncio
async def test_flash_adapter_collects_model_namespace_as_main_text(monkeypatch):
    """The main Flash lane uses a ``model:<id>`` namespace on the wire."""
    fake = FakeClient(
        [
            FakeResponse(
                200,
                json_data={
                    "status": "dispatched",
                    "thread_id": "thread-1",
                    "run_id": "run-1",
                },
            ),
            FakeResponse(
                200,
                lines=[
                    "event: message_chunk",
                    'data: {"agent":"model:1569fd6c-4502-4823-d4b7-418bebd4a88b","role":"assistant","content_type":"text","content":"你好"}',
                    "",
                    "event: message_chunk",
                    'data: {"agent":"model:1569fd6c-4502-4823-d4b7-418bebd4a88b","role":"assistant","content_type":"text","content":"，世界"}',
                    "",
                    "event: run_end",
                    'data: {"status":"completed"}',
                    "",
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
        AgentTurn("key-1", "你好", __import__("datetime").datetime.now()),
    )

    assert "你好，世界" == "".join(part.text for part in result.parts)


@pytest.mark.asyncio
async def test_flash_adapter_emits_structured_events_without_channel_filtering(monkeypatch):
    fake = FakeClient(
        [
            FakeResponse(
                200,
                json_data={
                    "status": "dispatched",
                    "thread_id": "thread-1",
                    "run_id": "run-1",
                },
            ),
            FakeResponse(
                200,
                lines=[
                    "event: message_chunk",
                    'data: {"agent":"main","role":"assistant","content_type":"reasoning","content":"思考"}',
                    "",
                    "event: commentary",
                    'data: {"agent":"main","content":"先检查"}',
                    "",
                    "event: tool_call_chunks",
                    'data: {"tool_call_chunks":[{"name":"search","index":2,"args":{"q":"x"},"preview":"x"}]}',
                    "",
                    "event: tool_call_result",
                    'data: {"tool_call_id":"call-1","duration":0.2,"ok":true}',
                    "",
                    "event: message_chunk",
                    'data: {"agent":"task:one","role":"assistant","content_type":"text","content":"子任务"}',
                    "",
                    "event: message_chunk",
                    'data: {"agent":"main","role":"assistant","content_type":"text","content":"答案"}',
                    "",
                    "event: run_end",
                    'data: {"status":"completed"}',
                    "",
                ],
            ),
        ]
    )
    monkeypatch.setattr(
        "src.server.channels.agent_adapters.langalpha_flash.httpx.AsyncClient",
        lambda **kwargs: fake,
    )
    events = []
    adapter = LangAlphaFlashAdapter(base_url="http://backend", service_token="svc")

    result = await adapter.run_turn(
        session(),
        AgentTurn("key-1", "你好", __import__("datetime").datetime.now()),
        on_event=events.append,
    )

    assert isinstance(events[0], MessageChunk)
    assert events[0].content_type == "reasoning"
    assert any(isinstance(event, Commentary) for event in events)
    assert any(isinstance(event, ToolCallChunk) for event in events)
    assert any(isinstance(event, ToolCallFinished) for event in events)
    assert next(event for event in events if isinstance(event, ToolCallChunk)).index == 2
    assert next(event for event in events if isinstance(event, ToolCallFinished)).tool_call_id == "call-1"
    assert isinstance(events[-1], MessageStop)
    assert "答案" == "".join(part.text for part in result.parts)


@pytest.mark.asyncio
async def test_flash_adapter_preserves_failed_run_status(monkeypatch):
    fake = FakeClient(
        [
            FakeResponse(
                200,
                json_data={
                    "status": "dispatched",
                    "thread_id": "thread-1",
                    "run_id": "run-1",
                },
            ),
            FakeResponse(
                200,
                lines=[
                    "event: run_end",
                    'data: {"status":"failed"}',
                    "",
                ],
            ),
        ]
    )
    monkeypatch.setattr(
        "src.server.channels.agent_adapters.langalpha_flash.httpx.AsyncClient",
        lambda **kwargs: fake,
    )
    adapter = LangAlphaFlashAdapter(base_url="http://backend", service_token="svc")

    with pytest.raises(FlashAgentError) as error:
        await adapter.run_turn(
            session(),
            AgentTurn("key-1", "你好", __import__("datetime").datetime.now()),
        )

    assert getattr(error.value, "code", None) == "failed"
