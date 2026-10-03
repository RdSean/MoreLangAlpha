"""Shared normal PTC graph assembly for managed textbook jobs."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from ptc_agent.agent.graph import build_ptc_graph_with_session
from ptc_agent.agent.managed_execution import ManagedExecutionPolicy
from src.config.settings import get_ptc_recursion_limit


async def build_managed_education_graph(
    *,
    session: Any,
    thread_id: str,
    run_handle: Any,
    policy: ManagedExecutionPolicy,
    agent_config: Any | None = None,
    operation_callback: Any | None = None,
    prompt: str,
    tags: tuple[str, ...],
    operation: str,
    textbook_id: str,
    job_id: str,
    item_id: str,
    execution_id: str,
    attempt_token: str,
    task_schema_version: str,
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Build a constrained managed graph from service-owned inputs."""
    from src.server.app import setup

    config = agent_config or setup.agent_config
    if config is None:
        raise RuntimeError("PTC Agent is not initialized")
    if operation not in {"structure", "material"}:
        raise ValueError("Unsupported education book operation")
    identity = {
        "kind": "education_book",
        "operation": operation,
        "textbook_id": str(UUID(textbook_id)),
        "job_id": str(UUID(job_id)),
        "item_id": str(UUID(item_id)),
        "execution_id": str(UUID(execution_id)),
        "attempt_token": str(UUID(attempt_token)),
    }
    if policy.filesystem_root.rsplit("/", 1)[-1] != identity["execution_id"]:
        raise ValueError("Managed policy root does not match execution_id")
    graph = await build_ptc_graph_with_session(
        session=session,
        operation_callback=operation_callback,
        config=config,
        subagent_names=[],
        disable_subagents=True,
        checkpointer=run_handle.checkpointer,
        background_registry=None,
        namespace_owner=None,
        user_id=None,
        plan_mode=False,
        thread_id=thread_id,
        store=None,
        on_signed_url=None,
        direct_mcp=None,
        managed_policy=policy,
    )
    graph_config: dict[str, Any] = {
        "configurable": {
            "thread_id": thread_id,
            "agent_mode": "ptc",
            "managed_execution": identity,
        },
        "recursion_limit": get_ptc_recursion_limit(),
        "tags": list(tags),
        "metadata": {
            "managed_execution": identity,
            "task_schema_version": task_schema_version,
            "run_id": run_handle.run_id,
            "turn_index": run_handle.turn_index,
        },
        "run_id": run_handle.run_id,
    }
    input_state = {
        "messages": [{"role": "user", "content": prompt}],
        "current_agent": "ptc",
    }
    return graph, input_state, graph_config


async def resolve_managed_education_agent_config(*, parent_user_id: str) -> Any:
    """Resolve model credentials without admitting parent runtime capabilities."""
    from src.server.app import setup
    from src.server.database.api_keys import is_byok_active
    from src.server.services.llm.config import resolve_llm_config

    if setup.agent_config is None:
        raise RuntimeError("PTC Agent is not initialized")
    config = await resolve_llm_config(
        base_config=setup.agent_config,
        user_id=parent_user_id,
        request_model=None,
        is_byok=await is_byok_active(parent_user_id),
        mode="ptc",
        enabled_subagents=[],
    )
    config.get_llm_client()
    return config
