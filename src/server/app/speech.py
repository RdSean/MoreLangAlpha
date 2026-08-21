"""Cookie-authenticated relay for browser speech input."""

from __future__ import annotations

import json
import logging
from uuid import uuid4

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.config.settings import get_volcengine_asr_config
from src.server.auth.ws_auth import authenticate_websocket
from src.server.services.volcengine_asr import (
    build_audio_request,
    build_authorization_header,
    build_full_request,
    decode_server_frame,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ws/v1", tags=["Speech"])


async def _receive_start(websocket: WebSocket) -> bool:
    message = await websocket.receive()
    if message.get("type") != "websocket.receive" or not isinstance(message.get("text"), str):
        return False
    try:
        return json.loads(message["text"]) == {"type": "start"}
    except json.JSONDecodeError:
        return False


async def _send_upstream_event(websocket: WebSocket, frame: bytes) -> bool:
    try:
        event = decode_server_frame(frame)
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError, OSError):
        await websocket.send_json({"type": "error", "code": "protocol_error"})
        return False
    if event.get("type") == "error" or event.get("text"):
        await websocket.send_json(event)
    return event.get("type") != "error"


@router.websocket("/speech/transcribe")
async def transcribe_stream(websocket: WebSocket) -> None:
    """Forward raw PCM sent by the browser to Volcengine and return text events."""
    user_id = await authenticate_websocket(websocket)
    config = get_volcengine_asr_config()
    await websocket.accept()
    if config is None:
        await websocket.send_json({"type": "error", "code": "service_unavailable"})
        await websocket.close(code=1013)
        return

    try:
        if not await _receive_start(websocket):
            await websocket.send_json({"type": "error", "code": "protocol_error"})
            await websocket.close(code=1003)
            return

        headers = {"Authorization": build_authorization_header(config)}
        async with websockets.connect(
            config.ws_url,
            additional_headers=headers,
            user_agent_header=None,
            proxy=None,
        ) as upstream:
            await upstream.send(build_full_request(config, request_id=str(uuid4()), user_id=user_id))
            if not await _send_upstream_event(websocket, await upstream.recv()):
                return

            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    return
                audio = message.get("bytes")
                if isinstance(audio, bytes):
                    await upstream.send(build_audio_request(audio))
                    if not await _send_upstream_event(websocket, await upstream.recv()):
                        return
                    continue
                if message.get("type") == "websocket.receive" and isinstance(message.get("text"), str):
                    try:
                        is_stop = json.loads(message["text"]) == {"type": "stop"}
                    except json.JSONDecodeError:
                        is_stop = False
                    if is_stop:
                        await upstream.send(build_audio_request(b"", is_last=True))
                        if await _send_upstream_event(websocket, await upstream.recv()):
                            await websocket.send_json({"type": "done"})
                        return
                await websocket.send_json({"type": "error", "code": "protocol_error"})
                await websocket.close(code=1003)
                return
    except WebSocketDisconnect:
        return
    except Exception:
        logger.warning("Volcengine ASR relay failed")
        try:
            await websocket.send_json({"type": "error", "code": "service_unavailable"})
        except Exception:
            pass
