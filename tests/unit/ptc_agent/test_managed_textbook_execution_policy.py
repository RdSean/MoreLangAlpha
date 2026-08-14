"""Execution-boundary contracts for managed textbook PTC runs."""

from importlib import import_module
from importlib.util import find_spec
from unittest.mock import AsyncMock

import pytest


def test_managed_textbook_policy_allows_only_staged_files_and_two_builtin_skills():
    assert find_spec("ptc_agent.agent.managed_execution") is not None
    education_teaching_policy = import_module(
        "ptc_agent.agent.managed_execution"
    ).education_teaching_policy
    policy = education_teaching_policy("8a77d086-0b23-4a1e-89d0-f163fa23d5d1")

    assert policy.allowed_skill_names == frozenset(
        {"book-to-skill", "the-knowledge-guy"}
    )
    assert policy.filesystem_root == "/managed/textbook-job/8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    assert policy.enable_mcp is False
    assert policy.enable_web is False
    assert policy.enable_vault is False
    assert policy.enable_preview is False
    # A managed teaching run is one service-owned root execution. Letting it
    # create arbitrary subagents would reintroduce a second execution surface
    # outside the fixed staged-input boundary.
    assert policy.allow_subagents is False


def test_managed_textbook_policy_rejects_non_uuid_job_ids():
    education_teaching_policy = import_module(
        "ptc_agent.agent.managed_execution"
    ).education_teaching_policy

    with pytest.raises(ValueError):
        education_teaching_policy("job-1")


def test_managed_core_config_removes_mcp_secrets_and_other_filesystem_roots():
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_teaching_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    class Filesystem:
        working_directory = "/home/workspace"
        allowed_directories = ["/home/workspace", "/tmp"]
        denied_directories = ["/home/workspace/_internal"]

    class MCP:
        servers = [object()]

    class Sandbox:
        platform_secrets = (object(),)

    class Core:
        filesystem = Filesystem()
        mcp = MCP()
        sandbox = Sandbox()

        def model_copy(self, *, deep):
            assert deep is True
            return Core()

    managed = managed_execution.managed_core_config(Core(), policy)

    assert managed.filesystem.working_directory == policy.filesystem_root
    assert managed.filesystem.allowed_directories == [policy.filesystem_root]
    assert managed.filesystem.denied_directories == []
    assert managed.mcp.servers == []
    assert managed.sandbox.platform_secrets == ()


@pytest.mark.asyncio
async def test_managed_sandbox_initialization_creates_only_the_job_root(monkeypatch):
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    PTCSandbox = import_module("ptc_agent.core.sandbox.ptc_sandbox").PTCSandbox
    policy = managed_execution.education_teaching_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    class Runtime:
        id = "sandbox-1"
        working_dir = policy.filesystem_root

        async def fetch_working_dir(self):
            return policy.filesystem_root

        async def exec(self, *_args, **_kwargs):
            return None

    runtime = Runtime()
    sandbox = object.__new__(PTCSandbox)
    sandbox.config = managed_execution.managed_core_config(
        type("Core", (), {
            "filesystem": type("Filesystem", (), {
                "working_directory": "/home/workspace",
                "allowed_directories": ["/home/workspace"],
                "denied_directories": [],
            })(),
            "mcp": type("MCP", (), {"servers": []})(),
            "sandbox": type("Sandbox", (), {"platform_secrets": ()})(),
            "model_copy": lambda self, *, deep: self,
        })(),
        policy,
    )
    sandbox.provider = AsyncMock()
    sandbox.provider.create.return_value = runtime
    async def runtime_call(func, *args, **kwargs):
        return await func(*args, **kwargs)

    sandbox._runtime_call = AsyncMock(side_effect=runtime_call)
    sandbox._work_dir = policy.filesystem_root
    sandbox.runtime = None
    sandbox.sandbox_id = None

    await sandbox.setup_managed_textbook_job(policy)

    sandbox.provider.create.assert_awaited_once_with(
        env_vars=None,
        platform_secret_bindings=None,
        mcp_packages=[],
        retry_policy=pytest.importorskip("ptc_agent.core.sandbox.retry").RetryPolicy.SAFE,
        allow_reconnect=False,
    )
    assert sandbox.sandbox_id == "sandbox-1"
    assert sandbox._work_dir == policy.filesystem_root
    assert sandbox._runtime_call.await_args.args[1] == f"mkdir -p {policy.filesystem_root}"


@pytest.mark.asyncio
async def test_managed_session_does_not_connect_mcp_or_hydrate_workspace(monkeypatch):
    """Managed sessions use the stripped config and the dedicated sandbox setup."""
    session_module = import_module("ptc_agent.core.session")
    policy = import_module("ptc_agent.agent.managed_execution").education_teaching_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )
    created: list[object] = []

    class Registry:
        def __init__(self, config):
            self.config = config
            self.connect_all = AsyncMock()
            created.append(self)

    class Sandbox:
        def __init__(self, config, mcp_registry):
            self.config = config
            self.mcp_registry = mcp_registry
            self.sandbox_id = "sandbox-1"
            self.setup_managed_textbook_job = AsyncMock()

    monkeypatch.setattr(session_module, "MCPRegistry", Registry)
    monkeypatch.setattr(session_module, "PTCSandbox", Sandbox)
    monkeypatch.setattr(session_module, "get_global_registry", lambda: object())

    core = type("Core", (), {"mcp": type("MCP", (), {"servers": []})()})()
    session = session_module.Session("workspace-1", core)
    await session.initialize_managed_textbook(policy)

    assert session._initialized is True
    assert len(created) == 1
    created[0].connect_all.assert_not_awaited()
    session.sandbox.setup_managed_textbook_job.assert_awaited_once_with(policy)


@pytest.mark.asyncio
async def test_managed_graph_discards_caller_identity_and_store(monkeypatch):
    """A service-owned run must not inherit parent memory or signed-url hooks."""
    graph_module = import_module("ptc_agent.agent.graph")
    policy = import_module("ptc_agent.agent.managed_execution").education_teaching_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )
    captured: dict[str, object] = {}

    class FakePTCAgent:
        def __init__(self, _config):
            pass

        def create_agent(self, **kwargs):
            captured.update(kwargs)
            return object()

    monkeypatch.setattr(graph_module, "PTCAgent", FakePTCAgent)
    monkeypatch.setattr(
        graph_module,
        "get_user_profile_for_prompt",
        AsyncMock(return_value={"name": "Parent"}),
    )

    session = type(
        "Session",
        (),
        {
            "conversation_id": "workspace-1",
            "sandbox": object(),
            "mcp_registry": object(),
            "mcp_tool_summary": None,
            "invalidate_agent_md": lambda self: None,
        },
    )()

    await graph_module.build_ptc_graph_with_session(
        session=session,
        config=type("Config", (), {"subagents": type("Subagents", (), {"enabled": []})()})(),
        user_id="parent-1",
        store=object(),
        on_signed_url=object(),
        managed_policy=policy,
    )

    assert captured["user_id"] is None
    assert captured["store"] is None
    assert captured["user_profile"] is None
    assert captured["on_signed_url"] is None


def test_managed_agent_uses_a_rooted_backend_and_removes_ambient_tools(monkeypatch):
    agent_module = import_module("ptc_agent.agent.agent")
    policy = import_module("ptc_agent.agent.managed_execution").education_teaching_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    captured: dict[str, object] = {}

    class FakeAgent:
        def with_config(self, _config):
            return self

    def fake_create_agent(_model, **kwargs):
        captured.update(kwargs)
        return FakeAgent()

    monkeypatch.setattr(agent_module, "create_agent", fake_create_agent)
    monkeypatch.setattr(agent_module, "get_skill_registry", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(agent_module.PTCAgent, "_build_model_resilience_middleware", lambda _self: [])
    monkeypatch.setattr(agent_module, "resolve_compaction_client", lambda _config: None)

    class Config:
        llm = None
        skills = type("Skills", (), {"enabled": True, "sandbox_skills_base": "/home/workspace/.agents/skills"})()
        filesystem = type("Filesystem", (), {
            "working_directory": policy.filesystem_root,
            "denied_directories": [],
        })()
        mcp = type("MCP", (), {"servers": [], "tool_exposure_mode": "summary"})()
        compaction = type("Compaction", (), {"model_dump": lambda self: {}})()
        background_auto_wait = False
        search_api = "tavily"
        search_depth = "standard"
        input_modalities = None
        subagents = type("Subagents", (), {"enabled": [], "definitions": {}})()
        feature_enabled = staticmethod(lambda _key: False)

        def get_llm_client(self):
            return object()

        def client_for_role(self, *_args, **_kwargs):
            return None

    sandbox = AsyncMock()
    sandbox.config = Config()
    sandbox.sandbox_id = "sandbox-1"
    sandbox.skills_manifest = None
    ptc_agent = agent_module.PTCAgent(Config())

    ptc_agent.create_agent(
        sandbox=sandbox,
        mcp_registry=object(),
        managed_policy=policy,
    )

    tool_names = {tool.name for tool in captured["tools"]}
    assert {"Bash", "Read", "Write", "Edit", "Glob", "Grep", "TodoWrite"} <= tool_names
    assert not {"ExecuteCode", "BashOutput", "PreviewURL", "ShowWidget", "WebSearch", "AskUserQuestion", "Task"} & tool_names


def test_managed_bash_rejects_shell_escapes_from_the_job_root():
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_teaching_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    assert managed_execution.validate_managed_bash_command(
        "cat inputs/manifest.json", policy
    ) is None
    assert managed_execution.validate_managed_bash_command(
        "sha256sum inputs/manifest.json", policy
    ) is None
    assert "outside the managed textbook job root" in str(
        managed_execution.validate_managed_bash_command("cat /etc/passwd", policy)
    )
    assert "outside the managed textbook job root" in str(
        managed_execution.validate_managed_bash_command("cd .. && ls", policy)
    )
    assert "not allowed" in str(
        managed_execution.validate_managed_bash_command("curl https://example.com", policy)
    )


def test_managed_candidate_write_requires_strict_json_before_saving():
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_teaching_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )
    candidate = f"{policy.filesystem_root}/outputs/teaching-package.json"

    assert "valid JSON" in str(
        managed_execution.validate_managed_textbook_write(
            candidate, '{"teaching_material":"未转义的"引号"}', policy
        )
    )
    assert (
        managed_execution.validate_managed_textbook_write(
            candidate,
            '{"format":"langalpha-managed-teaching-package/v1","chapters":[]}',
            policy,
        )
        is None
    )
    assert (
        managed_execution.validate_managed_textbook_write(
            f"{policy.filesystem_root}/work/knowledge-skill/chapter.json",
            "not JSON",
            policy,
        )
        is None
    )


@pytest.mark.asyncio
async def test_managed_bash_tool_enforces_the_policy_before_execution():
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    create_execute_bash_tool = import_module(
        "ptc_agent.agent.tools"
    ).create_execute_bash_tool
    policy = managed_execution.education_teaching_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    backend = AsyncMock()
    backend.filesystem_config.working_directory = policy.filesystem_root
    backend.aexecute_bash.return_value = {"success": True, "stdout": "ok"}
    tool = create_execute_bash_tool(
        backend,
        command_validator=lambda command: managed_execution.validate_managed_bash_command(
            command, policy
        ),
        fixed_working_dir=policy.filesystem_root,
    )

    rejected = await tool.ainvoke({"command": "cat /etc/passwd"})
    accepted = await tool.ainvoke(
        {"command": "cat inputs/manifest.json", "working_dir": "/tmp"}
    )

    assert "outside the managed textbook job root" in rejected
    assert accepted == "ok"
    backend.aexecute_bash.assert_awaited_once()
    assert backend.aexecute_bash.await_args.kwargs["working_dir"] == policy.filesystem_root
