"""Execution-boundary contracts for managed textbook PTC runs."""

from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


EXECUTION_ID = "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"


def test_education_book_policy_is_the_only_textbook_execution_policy():
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_book_policy(EXECUTION_ID)

    assert policy.allowed_skill_names == frozenset({"more-to-skills"})
    assert policy.filesystem_root == f"/managed/textbook-job/{EXECUTION_ID}"
    assert policy.enable_mcp is False
    assert policy.enable_web is True
    assert policy.enable_vault is False
    assert policy.enable_code_execution is True
    assert policy.enable_bash is True
    assert policy.enable_preview is True
    assert policy.enable_widgets is True
    assert policy.enable_progress_reporting is True
    assert policy.allow_subagents is False
    assert not hasattr(policy, "purpose")
    for old_factory in (
        "education_teaching_policy",
        "education_structure_policy",
        "education_lesson_policy",
        "education_book_asset_policy",
        "education_book_pipeline_policy",
    ):
        assert not hasattr(managed_execution, old_factory)


def test_education_book_policy_rejects_non_uuid_execution_ids():
    managed_execution = import_module("ptc_agent.agent.managed_execution")

    with pytest.raises(ValueError):
        managed_execution.education_book_policy("execution-1")


def test_managed_textbook_directories_keep_inputs_outside_the_write_zone():
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    root = f"/managed/textbook-job/{EXECUTION_ID}"

    directories = managed_execution.managed_textbook_directories(root)

    assert f"{root}/work" in directories
    assert f"{root}/outputs" in directories
    assert f"{root}/.system/code" in directories
    assert f"{root}/inputs" not in directories
    assert f"{root}/.agents/skills/more-to-skills" not in directories


@pytest.mark.asyncio
async def test_managed_graph_uses_explicit_education_book_execution_identity(
    monkeypatch,
):
    managed_runs = import_module("src.server.services.education_managed_runs")
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    build_graph = AsyncMock(return_value=object())
    monkeypatch.setattr(managed_runs, "build_ptc_graph_with_session", build_graph)
    identity = {
        "kind": "education_book",
        "operation": "material",
        "textbook_id": "2d08d9e6-73e4-40d3-aa6c-8111ae754fea",
        "job_id": "9998bb1a-687a-4d45-815d-5b1dd6ed2f17",
        "item_id": "86f03a73-7604-4097-905b-768e6ad0f644",
        "execution_id": EXECUTION_ID,
        "attempt_token": "d5c87e74-fb75-4624-bb25-a36ec73a89ce",
    }

    (
        _graph,
        _input_state,
        graph_config,
    ) = await managed_runs.build_managed_education_graph(
        session=object(),
        thread_id="1e0d57be-2b7e-4ed2-8daf-246c408d09ec",
        run_handle=SimpleNamespace(
            checkpointer=object(),
            run_id="e21b6198-85c6-41e2-b22b-2662851bc782",
            turn_index=1,
        ),
        policy=managed_execution.education_book_policy(EXECUTION_ID),
        agent_config=SimpleNamespace(),
        prompt="Generate one material.",
        tags=("managed", "education", "book"),
        operation="material",
        textbook_id=identity["textbook_id"],
        job_id=identity["job_id"],
        item_id=identity["item_id"],
        execution_id=identity["execution_id"],
        attempt_token=identity["attempt_token"],
        task_schema_version="langalpha-education-book-task/v2",
    )

    assert graph_config["configurable"]["managed_execution"] == identity
    assert graph_config["metadata"]["managed_execution"] == identity
    assert (
        graph_config["metadata"]["task_schema_version"]
        == "langalpha-education-book-task/v2"
    )
    assert build_graph.await_args.kwargs["subagent_names"] == []
    assert build_graph.await_args.kwargs["disable_subagents"] is True
    assert build_graph.await_args.kwargs["namespace_owner"] is None


@pytest.mark.asyncio
async def test_managed_graph_rejects_a_policy_for_another_execution():
    managed_runs = import_module("src.server.services.education_managed_runs")
    managed_execution = import_module("ptc_agent.agent.managed_execution")

    with pytest.raises(ValueError, match="execution_id"):
        await managed_runs.build_managed_education_graph(
            session=object(),
            thread_id="1e0d57be-2b7e-4ed2-8daf-246c408d09ec",
            run_handle=SimpleNamespace(
                checkpointer=None, run_id=EXECUTION_ID, turn_index=1
            ),
            policy=managed_execution.education_book_policy(EXECUTION_ID),
            agent_config=SimpleNamespace(),
            prompt="Analyze structure.",
            tags=("managed",),
            operation="structure",
            textbook_id="2d08d9e6-73e4-40d3-aa6c-8111ae754fea",
            job_id="9998bb1a-687a-4d45-815d-5b1dd6ed2f17",
            item_id="86f03a73-7604-4097-905b-768e6ad0f644",
            execution_id="e21b6198-85c6-41e2-b22b-2662851bc782",
            attempt_token="d5c87e74-fb75-4624-bb25-a36ec73a89ce",
            task_schema_version="langalpha-education-book-task/v2",
        )


def test_managed_policy_tool_surface_keeps_normal_bash_and_execute_code(monkeypatch):
    agent_module = import_module("ptc_agent.agent.agent")
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_book_policy(EXECUTION_ID)
    assert not hasattr(managed_execution, "validate_managed_bash_command")
    created: list[tuple[str, dict]] = []

    def factory(name):
        def create(*_args, **kwargs):
            created.append((name, kwargs))
            return SimpleNamespace(tool_name=name)

        return create

    for name in (
        "create_execute_code_tool",
        "create_execute_bash_tool",
        "create_bash_output_tool",
        "create_preview_url_tool",
        "create_show_widget_tool",
        "create_report_progress_tool",
    ):
        monkeypatch.setattr(agent_module, name, factory(name))

    tools, execute_code_tool, bash_tool = agent_module._build_managed_policy_tools(
        policy,
        backend=object(),
        mcp_registry=object(),
        thread_id="thread-1",
        workspace_id="workspace-1",
        on_signed_url=None,
    )

    assert execute_code_tool.tool_name == "create_execute_code_tool"
    assert bash_tool.tool_name == "create_execute_bash_tool"
    assert {tool.tool_name for tool in tools if hasattr(tool, "tool_name")} == {
        "create_execute_code_tool",
        "create_execute_bash_tool",
        "create_bash_output_tool",
        "create_preview_url_tool",
        "create_show_widget_tool",
        "create_report_progress_tool",
    }
    bash_call = next(
        kwargs for name, kwargs in created if name == "create_execute_bash_tool"
    )
    assert bash_call["command_validator"] is None
    assert bash_call["fixed_working_dir"] == policy.filesystem_root


def test_managed_policy_progress_tool_is_opt_in(monkeypatch):
    agent_module = import_module("ptc_agent.agent.agent")
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    created = []

    monkeypatch.setattr(
        agent_module,
        "create_report_progress_tool",
        lambda: created.append("report_progress")
        or SimpleNamespace(tool_name="report_progress"),
    )
    policy = managed_execution.ManagedExecutionPolicy(
        allowed_skill_names=frozenset(),
        filesystem_root=f"/managed/textbook-job/{EXECUTION_ID}",
        enable_bash=False,
    )

    tools, _execute_code_tool, _bash_tool = agent_module._build_managed_policy_tools(
        policy,
        backend=object(),
        mcp_registry=object(),
        thread_id="thread-1",
        workspace_id="workspace-1",
        on_signed_url=None,
    )

    assert created == []
    assert all(getattr(tool, "tool_name", None) != "report_progress" for tool in tools)


@pytest.mark.parametrize(
    ("path", "content", "allowed"),
    (
        ("work/scripts/build.py", "print('ok')", True),
        ("outputs/book/chapters/kp-1.md", "# Lesson", True),
        ("outputs/book/result.json", '{"ok":true}', True),
        ("outputs/book/result.json", '{"value":NaN}', False),
        ("inputs/source.md", "changed", False),
        (".agents/skills/more-to-skills/SKILL.md", "changed", False),
        ("../outside.txt", "changed", False),
    ),
)
def test_managed_write_gate_allows_work_outputs_and_protects_inputs(
    path, content, allowed
):
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_book_policy(EXECUTION_ID)

    error = managed_execution.validate_managed_textbook_write(path, content, policy)

    assert (error is None) is allowed


def test_managed_core_config_removes_mcp_secrets_and_other_roots():
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_book_policy(EXECUTION_ID)

    class Core:
        filesystem = SimpleNamespace(
            working_directory="/home/workspace",
            allowed_directories=["/home/workspace", "/tmp"],
            denied_directories=["/home/workspace/_internal"],
        )
        mcp = SimpleNamespace(servers=[object()])
        sandbox = SimpleNamespace(
            platform_secrets=(object(),),
            docker=SimpleNamespace(
                dev_mode=True,
                host_work_dir="/host/private",
                volumes=["/host/secret:/mounted:ro"],
            ),
        )

        def model_copy(self, *, deep):
            assert deep is True
            return Core()

    managed = managed_execution.managed_core_config(Core(), policy)

    assert managed.filesystem.working_directory == policy.filesystem_root
    assert managed.filesystem.allowed_directories == [policy.filesystem_root]
    assert managed.filesystem.denied_directories == []
    assert managed.mcp.servers == []
    assert managed.sandbox.platform_secrets == ()
    assert managed.sandbox.docker.dev_mode is False
    assert managed.sandbox.docker.host_work_dir is None
    assert managed.sandbox.docker.volumes == []


@pytest.mark.asyncio
async def test_managed_sandbox_precreates_write_zones_and_read_only_inputs(monkeypatch):
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    PTCSandbox = import_module("ptc_agent.core.sandbox.ptc_sandbox").PTCSandbox
    policy = managed_execution.education_book_policy(EXECUTION_ID)

    class Runtime:
        id = "sandbox-1"

        def __init__(self):
            self.directories = []
            self.uploads = []

        async def exec(self, *_args, **_kwargs):
            return SimpleNamespace(exit_code=0)

        async def ensure_directory(self, path, *, mode=0o755):
            self.directories.append((path, mode))

        async def upload_file(self, content, path):
            self.uploads.append((content, path))

    runtime = Runtime()
    sandbox = object.__new__(PTCSandbox)
    sandbox.config = SimpleNamespace(
        filesystem=SimpleNamespace(working_directory=policy.filesystem_root)
    )
    sandbox.provider = SimpleNamespace(create=object())
    sandbox.runtime = None
    sandbox.sandbox_id = None
    sandbox._work_dir = policy.filesystem_root
    monkeypatch.setattr(sandbox, "_runtime_call", AsyncMock(return_value=runtime))

    await sandbox.setup_managed_textbook_job(policy)

    assert (f"{policy.filesystem_root}/inputs", 0o555) in runtime.directories
    assert (f"{policy.filesystem_root}/work", 0o755) in runtime.directories
    assert (f"{policy.filesystem_root}/outputs", 0o755) in runtime.directories
    assert runtime.uploads == []


def test_managed_agent_has_no_fixed_textbook_subagent_registration():
    agent_module = import_module("ptc_agent.agent.agent")

    assert not hasattr(agent_module, "_MANAGED_TEXTBOOK_SUBAGENTS")


@pytest.mark.asyncio
async def test_managed_session_reconnect_skips_mcp_and_workspace_hydration(monkeypatch):
    session_module = import_module("ptc_agent.core.session")
    policy = import_module("ptc_agent.agent.managed_execution").education_book_policy(
        EXECUTION_ID
    )
    reconnect = AsyncMock()

    class Sandbox:
        sandbox_id = None
        working_dir = policy.filesystem_root

        def __init__(self, _config, mcp_registry):
            assert mcp_registry is not None

        async def reconnect(self, sandbox_id):
            self.sandbox_id = sandbox_id
            await reconnect(sandbox_id)

    monkeypatch.setattr(session_module, "PTCSandbox", Sandbox)
    monkeypatch.setattr(session_module, "MCPRegistry", lambda _config: object())
    session = object.__new__(session_module.Session)
    session.config = object()
    session.conversation_id = "workspace-1"
    session._initialized = False
    session.sandbox = None
    session.mcp_registry = None
    session._builtin_mcp_registry = None
    session._owns_mcp_registry = False

    await session.reconnect_managed_textbook(
        sandbox_id="sandbox-1",
        policy=policy,
    )

    reconnect.assert_awaited_once_with("sandbox-1")
    assert session._initialized is True
    assert session._owns_mcp_registry is True
