"""WebSocket authentication helper for first-party opaque session cookies."""

import logging

from fastapi import WebSocket, WebSocketException, status

from src.server.auth.local_sessions import (
    SESSION_COOKIE_NAME,
    get_user_id_for_session_token,
)

logger = logging.getLogger(__name__)


async def authenticate_websocket(websocket: WebSocket) -> str:
    """Resolve the handshake's HttpOnly local-auth cookie before accepting."""
    token = websocket.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing auth token")
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION, reason="Missing auth token")

    user_id = await get_user_id_for_session_token(token)
    if user_id:
        return user_id
    logger.warning("WS auth failed: invalid or expired local session")
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token")
    raise WebSocketException(
        code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token"
    )
