"""Managed prompts follow service capabilities without the normal chat workflow."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from ptc_agent.agent.agent import PTCAgent
from ptc_agent.agent.managed_execution import (
    ManagedExecutionPolicy,
    education_book_policy,
)
from ptc_agent.agent.middleware.runtime_context import RuntimeContextMiddleware


def _agent():
    agent = PTCAgent.__new__(PTCAgent)
    agent.config = SimpleNamespace(
        filesystem=SimpleNamespace(working_directory="/home/workspace"),
        feature_enabled=lambda _name: True,
    )
    return agent


@pytest.mark.parametrize("guidance", ["lean", "detailed"])
def test_managed_prompt_preserves_security_and_enabled_execution(guidance):
    policy = education_book_policy("8a77d086-0b23-4a1e-89d0-f163fa23d5d1")
    prompt = _agent()._build_system_prompt("", "", guidance, managed_policy=policy)

    assert "service-owned" in prompt
    assert "read-only" in prompt
    assert "outputs/" in prompt
    assert "ExecuteCode" in prompt
    assert "Bash" in prompt
    assert "report_progress" in prompt
    assert "image" in prompt
    assert "NEVER" in prompt and "API key" in prompt
    for absent in (
        "investment research",
        "agent.md",
        "TodoWrite",
        "User Vault",
        "tools.<server_name>",
    ):
        assert absent not in prompt
    assert policy.filesystem_root not in prompt


def test_managed_prompt_only_advertises_enabled_capabilities():
    policy = ManagedExecutionPolicy(
        allowed_skill_names=frozenset(),
        filesystem_root="/managed/job",
        enable_bash=False,
    )
    prompt = _agent()._build_system_prompt("", "", "detailed", managed_policy=policy)
    for absent in (
        "Bash",
        "ExecuteCode",
        "report_progress",
        "WebSearch",
        "PreviewURL",
        "ShowWidget",
    ):
        assert absent not in prompt
    assert "Read" in prompt and "Write" in prompt


def test_normal_prompt_keeps_existing_workflow():
    prompt = _agent()._build_system_prompt("", "", "detailed")
    assert "investment research" in prompt
    assert "Update agent.md" in prompt


def test_managed_static_prefix_is_identical_across_execution_roots():
    agent = _agent()
    prompts = [
        agent._build_system_prompt(
            "", "", "lean", managed_policy=education_book_policy(execution)
        )
        for execution in (
            "8a77d086-0b23-4a1e-89d0-f163fa23d5d1",
            "e21b6198-85c6-41e2-b22b-2662851bc782",
        )
    ]
    assert prompts[0] == prompts[1]


def test_managed_runtime_directory_is_dynamic_context():
    root = "/managed/textbook-job/8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    middleware = RuntimeContextMiddleware(current_time="now", working_directory=root)
    assert root in middleware._context_block
    assert "<execution_directory>" in middleware._context_block


def test_managed_lean_prompt_is_a_subset_of_detailed():
    policy = education_book_policy("8a77d086-0b23-4a1e-89d0-f163fa23d5d1")
    agent = _agent()
    lean = agent._build_system_prompt("", "", "lean", managed_policy=policy)
    detailed = agent._build_system_prompt("", "", "detailed", managed_policy=policy)
    assert set(lean.splitlines()) <= set(detailed.splitlines())


@pytest.mark.asyncio
async def test_actual_managed_assembly_omits_workspace_and_market_context(monkeypatch):
    from langchain.agents.middleware.types import ModelRequest
    from langchain_core.messages import SystemMessage
    from ptc_agent.agent import agent as agent_module
    from ptc_agent.config import AgentConfig
    from ptc_agent.config.core import (
        FilesystemConfig,
        LoggingConfig,
        MCPConfig,
        SandboxConfig,
        SecurityConfig,
    )

    config = AgentConfig(
        security=SecurityConfig(),
        logging=LoggingConfig(),
        sandbox=SandboxConfig(provider="docker"),
        mcp=MCPConfig(),
        filesystem=FilesystemConfig(),
        features={"market_watch": True},
    )
    agent = PTCAgent.__new__(PTCAgent)
    agent.config = config
    agent.llm = MagicMock()
    sandbox = MagicMock(config=config, skills_manifest={})
    factory = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(agent_module, "create_agent", factory)
    monkeypatch.setattr(
        agent_module,
        "turn_model",
        lambda *_args, **_kwargs: SimpleNamespace(client=agent.llm, guidance="lean"),
    )
    monkeypatch.setattr(
        agent_module, "build_model_resilience_middleware", lambda *_args: MagicMock()
    )
    monkeypatch.setattr(
        agent_module.CompactionMiddleware, "from_config", lambda **_kwargs: MagicMock()
    )
    policy = education_book_policy("8a77d086-0b23-4a1e-89d0-f163fa23d5d1")
    session = MagicMock()
    agent.create_agent(
        sandbox,
        MagicMock(),
        session=session,
        managed_policy=policy,
        user_profile={"name": "private parent"},
        user_data_counts={"portfolio": 99},
    )
    assembled = factory.call_args.kwargs
    names = {type(m).__name__ for m in assembled["middleware"]}
    assert "WorkspaceContextMiddleware" not in names
    assert "MarketWatchMiddleware" not in names
    assert "OpenAIPromptCachingMiddleware" in names
    assert "MultimodalMiddleware" in names
    assert "service-owned" in assembled["system_prompt"]
    runtime = next(
        m for m in assembled["middleware"] if isinstance(m, RuntimeContextMiddleware)
    )
    request = ModelRequest(
        model=agent.llm,
        messages=[],
        system_message=SystemMessage(assembled["system_prompt"]),
    )
    captured = []

    async def handler(value):
        captured.append(value.system_message.content)
        return MagicMock()

    await runtime.awrap_model_call(request, handler)
    assert policy.filesystem_root in str(captured)
    assert "private parent" not in str(captured)
    assert "agent.md" not in str(captured)
    session.get_agent_md.assert_not_called()
