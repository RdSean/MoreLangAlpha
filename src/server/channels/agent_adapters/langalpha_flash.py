"""Bridge channel turns to LangAlpha's internal Flash chat API."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from typing import Any

import httpx

from src.server.channels.contracts import (
    AgentSession,
    AgentTurn,
    AgentTurnResult,
    OpenSessionRequest,
    TextPart,
)

logger = logging.getLogger(__name__)


class FlashAgentError(RuntimeError):
    """A retryable or terminal failure returned by the Flash API."""

    def __init__(self, message: str, *, code: str = "flash_error") -> None:
        super().__init__(message)
        self.code = code


class LangAlphaFlashAdapter:
    """Use the existing authenticated HTTP chat surface as an AgentAdapter."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        service_token: str | None = None,
        user_id: str | None = None,
        timeout: float = 90.0,
    ) -> None:
        self.base_url = (
            base_url or os.getenv("GINLIXFLOW_BASE_URL", "http://localhost:8000")
        ).rstrip("/")
        self.service_token = (
            service_token
            if service_token is not None
            else os.getenv("INTERNAL_SERVICE_TOKEN", "")
        )
        self.user_id = user_id
        self.timeout = timeout

    async def open_session(self, request: OpenSessionRequest) -> AgentSession:
        # Prefix prevents an opaque external thread key from being mistaken
        # for a real LangAlpha thread id on the first turn.
        return AgentSession(
            ref=f"external:{request.session_key}",
            opened_at=datetime.now(UTC),
            actor_ref=request.actor_ref,
        )

    def _headers(self, user_id: str | None = None) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream, application/json",
            "X-Service-Token": self.service_token,
            "X-Dispatch": "background",
        }
        if user_id or self.user_id:
            headers["X-User-Id"] = user_id or self.user_id or ""
        return headers

    @staticmethod
    def _image_contexts(turn: AgentTurn) -> list[dict[str, str]] | None:
        contexts: list[dict[str, str]] = []
        for image in turn.images:
            # The resolver hands us a validated data URL. Keep the adapter
            # provider-neutral: no filesystem or object-store access here.
            data = image.content_ref
            if not data.startswith("data:"):
                continue
            contexts.append({"type": "image", "data": data})
        return contexts or None

    @staticmethod
    def _json_response(response: httpx.Response) -> dict[str, Any]:
        try:
            value = response.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise FlashAgentError(
                "Flash API returned invalid JSON", code="invalid_response"
            ) from exc
        return value if isinstance(value, dict) else {}

    async def _consume_sse(
        self,
        response: Any,
        *,
        fallback_thread_id: str | None,
    ) -> AgentTurnResult:
        chunks: list[str] = []
        thread_id = fallback_thread_id
        event_name: str | None = None
        async for line in response.aiter_lines():
            if not line:
                event_name = None
                continue
            if line.startswith("event:"):
                event_name = line[6:].strip()
                continue
            if not line.startswith("data:"):
                continue
            try:
                payload = json.loads(line[5:].strip())
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            event = str(payload.get("event") or event_name or "")
            if event == "metadata" or payload.get("thread_id"):
                candidate = payload.get("thread_id") or (
                    payload.get("metadata") or {}
                ).get("thread_id")
                if candidate:
                    thread_id = str(candidate)
            if event in {"error", "run_error"}:
                detail = (
                    payload.get("error") or payload.get("message") or "Flash run failed"
                )
                raise FlashAgentError(
                    str(detail), code=str(payload.get("code") or "flash_run_error")
                )
            if event == "message_chunk" or payload.get("content_type") == "text":
                role = payload.get("role")
                if role and role not in {"assistant", "agent", "main"}:
                    continue
                content = payload.get("content")
                if isinstance(content, str) and content:
                    chunks.append(content)
            if event in {"run_end", "done", "finish", "complete"}:
                status = str(payload.get("status") or "").lower()
                if status in {"failed", "error", "cancelled"}:
                    raise FlashAgentError("Flash run did not complete", code=status)
        if not chunks:
            raise FlashAgentError("Flash run produced no text", code="empty_response")
        return AgentTurnResult(
            parts=(TextPart(text="".join(chunks)),),
            session_ref=thread_id,
        )

    async def run_turn(self, session: AgentSession, turn: AgentTurn) -> AgentTurnResult:
        thread_id = (
            session.ref
            if session.ref and not session.ref.startswith("wechat:")
            else None
        )
        if thread_id and thread_id.startswith("external:"):
            thread_id = None
        body: dict[str, Any] = {
            "agent_mode": "flash",
            "platform": turn.channel_type,
            "request_key": turn.request_key,
            "messages": [{"role": "user", "content": turn.text or ""}],
        }
        if not thread_id:
            body["external_thread_id"] = session.ref.removeprefix("external:")
        image_contexts = self._image_contexts(turn)
        if image_contexts:
            body["additional_context"] = image_contexts

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            path = (
                f"/api/v1/threads/{thread_id}/messages"
                if thread_id
                else "/api/v1/threads/messages"
            )
            try:
                response = await client.post(
                    f"{self.base_url}{path}",
                    headers=self._headers(session.actor_ref),
                    json=body,
                )
            except httpx.HTTPError as exc:
                raise FlashAgentError(
                    "Flash API transport failed", code="transport"
                ) from exc

            if response.status_code == 409:
                detail = self._json_response(response).get("detail")
                if (
                    isinstance(detail, dict)
                    and detail.get("code") == "duplicate_request"
                ):
                    thread_id = str(detail.get("thread_id") or thread_id or "") or None
                    run_id = str(detail.get("run_id") or "")
                    if thread_id and run_id:
                        path = f"/api/v1/threads/{thread_id}/messages/stream?run_id={run_id}"
                        async with client.stream(
                            "GET",
                            f"{self.base_url}{path}",
                            headers=self._headers(session.actor_ref),
                        ) as stream:
                            if stream.status_code >= 400:
                                raise FlashAgentError(
                                    "Unable to reconnect Flash run",
                                    code="reconnect_failed",
                                )
                            return await self._consume_sse(
                                stream, fallback_thread_id=thread_id
                            )
                raise FlashAgentError("Flash API rejected the request", code="conflict")
            if response.status_code >= 400:
                detail = self._json_response(response).get("detail")
                raise FlashAgentError(
                    str(detail or "Flash API request failed"),
                    code=f"http_{response.status_code}",
                )

            content_type = response.headers.get("content-type", "")
            if "text/event-stream" in content_type:
                return await self._consume_sse(response, fallback_thread_id=thread_id)

            data = self._json_response(response)
            if data.get("status") == "dispatched":
                thread_id = str(data.get("thread_id") or thread_id or "") or None
                run_id = str(data.get("run_id") or "")
                if not thread_id or not run_id:
                    raise FlashAgentError(
                        "Flash dispatch receipt is incomplete", code="invalid_receipt"
                    )
                path = f"/api/v1/threads/{thread_id}/messages/stream?run_id={run_id}"
                async with client.stream(
                    "GET",
                    f"{self.base_url}{path}",
                    headers=self._headers(session.actor_ref),
                ) as stream:
                    if stream.status_code >= 400:
                        raise FlashAgentError(
                            "Unable to read Flash stream", code="stream_failed"
                        )
                    return await self._consume_sse(stream, fallback_thread_id=thread_id)
            raise FlashAgentError(
                "Flash API returned an unexpected response", code="invalid_response"
            )
