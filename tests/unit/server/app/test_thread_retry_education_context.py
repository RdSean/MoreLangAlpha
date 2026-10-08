"""Retry preserves client scope for validation by the owned message path."""

from unittest.mock import AsyncMock

import pytest

from src.server.app.threads import messaging
from src.server.dependencies.usage_limits import ChatAuthResult
from src.server.models.workflow import RetryRequest


@pytest.mark.asyncio
async def test_retry_forwards_education_scope_and_keeps_route_owned_provenance(monkeypatch):
    from src.server.database.runs import lifecycle
    from src.server.handlers import checkpoint_handler

    monkeypatch.setattr(messaging.auth_api, "require_thread_owner", AsyncMock())
    monkeypatch.setattr(messaging, "_assert_stream_transport_ready", AsyncMock())
    monkeypatch.setattr(lifecycle, "get_latest_attempt", AsyncMock(return_value={
        "conversation_response_id": "failed-run", "status": "error",
    }))
    monkeypatch.setattr(checkpoint_handler, "get_retry_checkpoint", AsyncMock(return_value="checkpoint"))
    delegate = AsyncMock(return_value="stream")
    monkeypatch.setattr(messaging, "_handle_send_message", delegate)
    result = await messaging.retry_thread("thread", ChatAuthResult(user_id="student"), RetryRequest(
        workspace_id="ws", education_assignment_id="assignment", education_knowledge_point_id="kp",
    ))
    assert result == "stream"
    request = delegate.await_args.args[0]
    assert request.education_assignment_id == "assignment"
    assert request.education_knowledge_point_id == "kp"
    assert request.retry_of_run_id is None
    assert delegate.await_args.kwargs["retry_of_run_id"] == "failed-run"
