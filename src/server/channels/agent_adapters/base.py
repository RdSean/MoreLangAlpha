"""Interface between the generic channel gateway and an internal agent."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.server.channels.contracts import (
    AgentSession,
    AgentTurn,
    AgentTurnResult,
    OpenSessionRequest,
)


@runtime_checkable
class AgentAdapter(Protocol):
    """Open and use opaque agent sessions for normalized channel turns."""

    async def open_session(self, request: OpenSessionRequest) -> AgentSession: ...

    async def run_turn(
        self,
        session: AgentSession,
        turn: AgentTurn,
    ) -> AgentTurnResult: ...
