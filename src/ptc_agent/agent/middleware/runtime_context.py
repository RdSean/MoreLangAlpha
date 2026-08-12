"""Middleware for injecting runtime context (time, user profile) into system prompt.

Appends dynamic per-request context as the last content block of the system
message.  Positioned after WorkspaceContextMiddleware in the middleware stack
so this block appears after agent.md and outside the prompt cache breakpoint.

This keeps the base system prompt + skills manifest fully static and cacheable
across users and requests — only this block varies per request.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware, ModelRequest, ModelResponse

from ptc_agent.agent.middleware._utils import append_to_system_message
from ptc_agent.agent.prompts import get_loader


class RuntimeContextMiddleware(AgentMiddleware):
    """Injects current_time and user_profile into the system prompt.

    These dynamic fields are placed after the cache breakpoint so the static
    system prompt prefix remains cacheable across users and requests.

    Args:
        current_time: Pre-formatted current time string.
        user_profile: Optional user profile dict with name, timezone, locale, etc.
        sandbox_enabled: Whether the agent has a sandbox/filesystem. Gates
            filesystem-dependent steering in the shared user_profile component
            (e.g. HTML-report output) — true for PTC, false for Flash.
    """

    def __init__(
        self,
        *,
        current_time: str,
        user_profile: dict[str, Any] | None = None,
        sandbox_enabled: bool = False,
    ) -> None:
        self._context_block = self._build_context_block(
            current_time, user_profile, sandbox_enabled
        )

    @staticmethod
    def _build_context_block(
        current_time: str,
        user_profile: dict[str, Any] | None,
        sandbox_enabled: bool = False,
    ) -> str:
        loader = get_loader()
        parts: list[str] = []

        time_content = loader.render(
            "components/time_awareness.md.j2",
            current_time=current_time,
        )
        parts.append(f"<time_awareness>\n{time_content}\n</time_awareness>")

        if user_profile:
            profile_content = loader.render(
                "components/user_profile.md.j2",
                user_profile=user_profile or {},
                sandbox_enabled=sandbox_enabled,
            )
            parts.append(f"<user_profile>\n{profile_content}\n</user_profile>")

        return "\n".join(parts)

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        # Sync fallback — the async agent won't call this but the protocol requires it.
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        """Inject runtime context into system message before each model call."""
        new_system_message = append_to_system_message(
            request.system_message, self._context_block
        )
        modified_request = request.override(system_message=new_system_message)
        return await handler(modified_request)
