"""Execution-boundary contracts for managed textbook PTC runs."""

import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from importlib import import_module
from importlib.util import find_spec
from unittest.mock import AsyncMock

import pytest

from src.server.services import education_generation_progress
from src.server.services import education_teaching_storage


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_managed_textbook_policy_allows_only_staged_files_and_one_builtin_skill():
    assert find_spec("ptc_agent.agent.managed_execution") is not None
    education_teaching_policy = import_module(
        "ptc_agent.agent.managed_execution"
    ).education_teaching_policy
    policy = education_teaching_policy("8a77d086-0b23-4a1e-89d0-f163fa23d5d1")

    assert policy.allowed_skill_names == frozenset({"book-to-skill"})
    assert (
        policy.filesystem_root
        == "/managed/textbook-job/8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )
    assert policy.enable_mcp is False
    assert policy.enable_web is True
    assert policy.enable_vault is False
    assert policy.enable_code_execution is True
    assert policy.enable_bash is True
    assert policy.enable_preview is True
    assert policy.enable_widgets is True
    # The root can fan out only service-defined workers that inherit the same
    # sandbox boundary; user definitions are never registered for this mode.
    assert policy.allow_subagents is True


def test_managed_textbook_policy_rejects_non_uuid_job_ids():
    education_teaching_policy = import_module(
        "ptc_agent.agent.managed_execution"
    ).education_teaching_policy

    with pytest.raises(ValueError):
        education_teaching_policy("job-1")


def test_managed_textbook_directories_contract():
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    root = "/managed/textbook-job/8a77d086-0b23-4a1e-89d0-f163fa23d5d1"

    directories = managed_execution.managed_textbook_directories(root)

    assert directories == tuple(
        f"{root}/{relative}"
        for relative in (
            "work",
            "outputs",
            "outputs/book-skill",
            "outputs/book-skill/chapters",
            "outputs/content",
            "outputs/chapters",
            "outputs/knowledge",
            ".langalpha",
        )
    )
    assert f"{root}/inputs" not in directories
    assert f"{root}/.langalpha/progress.jsonl" not in directories


@pytest.mark.parametrize(
    "factory_name",
    (
        "education_structure_policy",
        "education_lesson_policy",
        "education_book_asset_policy",
        "education_book_pipeline_policy",
        "education_teaching_policy",
    ),
)
def test_full_ptc_capabilities_for_every_textbook_policy(factory_name):
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    factory = getattr(managed_execution, factory_name)

    policy = factory("8a77d086-0b23-4a1e-89d0-f163fa23d5d1")

    assert policy.enable_web is True
    assert policy.enable_code_execution is True
    assert policy.enable_bash is True
    assert policy.enable_preview is True
    assert policy.enable_widgets is True
    assert policy.enable_mcp is False
    assert policy.enable_vault is False


def test_managed_policy_tool_surface_uses_capability_flags(monkeypatch):
    agent_module = import_module("ptc_agent.agent.agent")
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_book_pipeline_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )
    created: list[tuple[str, tuple, dict]] = []

    def factory(name):
        def create(*args, **kwargs):
            created.append((name, args, kwargs))
            return SimpleNamespace(tool_name=name)

        return create

    for name in (
        "create_execute_code_tool",
        "create_execute_bash_tool",
        "create_bash_output_tool",
        "create_preview_url_tool",
        "create_show_widget_tool",
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

    assert [
        getattr(tool, "tool_name", getattr(tool, "name", None))
        for tool in tools
    ] == [
        "TodoWrite",
        "create_execute_code_tool",
        "create_execute_bash_tool",
        "create_bash_output_tool",
        "create_preview_url_tool",
        "create_show_widget_tool",
    ]
    assert execute_code_tool.tool_name == "create_execute_code_tool"
    assert bash_tool.tool_name == "create_execute_bash_tool"
    bash_call = next(call for call in created if call[0] == "create_execute_bash_tool")
    assert bash_call[2]["command_validator"] is None
    assert bash_call[2]["fixed_working_dir"] == policy.filesystem_root


def test_structure_policy_uses_zone_based_write_gate():
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_structure_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    assert policy.allowed_skill_names == frozenset({"book-to-skill"})
    assert policy.purpose == "structure"
    assert (
        managed_execution.validate_managed_textbook_write(
            f"{policy.filesystem_root}/outputs/structure.json",
            '{"format":"langalpha-managed-textbook-structure/v1","units":[]}',
            policy,
        )
        is None
    )
    assert (
        managed_execution.validate_managed_textbook_write(
            f"{policy.filesystem_root}/outputs/teaching-package.json",
            "{}",
            policy,
        )
        is None
    )
    assert (
        managed_execution.validate_managed_textbook_write(
            f"{policy.filesystem_root}/outputs/structure.json",
            "[]",
            policy,
        )
        is None
    )
    assert "valid JSON" in str(
        managed_execution.validate_managed_textbook_write(
            f"{policy.filesystem_root}/outputs/structure.json",
            "not json",
            policy,
        )
    )


def test_book_pipeline_policy_matches_managed_execution_boundaries():
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_book_pipeline_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    assert policy.allowed_skill_names == frozenset({"book-to-skill"})
    assert (
        policy.filesystem_root
        == "/managed/textbook-job/8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )
    assert policy.purpose == "book_pipeline"
    assert policy.enable_mcp is False
    assert policy.enable_web is True
    assert policy.enable_vault is False
    assert policy.enable_code_execution is True
    assert policy.enable_bash is True
    assert policy.enable_preview is True
    assert policy.enable_widgets is True
    assert policy.allow_subagents is True


def test_book_pipeline_policy_allows_package_skill_and_manifest_asset_paths():
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_book_pipeline_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )
    allowed = (
        ("outputs/book_package.json", "{}"),
        ("outputs/content_tree.json", "{}"),
        ("outputs/knowledge_points.json", "{}"),
        ("outputs/assets_manifest.json", "{}"),
        ("outputs/book-skill/SKILL.md", "# Textbook Skill"),
        ("outputs/book-skill/chapters/unit-1/reading-a.md", "# Reading A"),
        ("outputs/book-skill/glossary.md", "# Glossary"),
        ("outputs/book-skill/patterns.md", "# Patterns"),
        ("outputs/book-skill/cheatsheet.md", "# Cheatsheet"),
        ("outputs/content/unit-1/knowledge.md", "# Knowledge"),
        ("outputs/content/unit-1/practice.json", "{}"),
        ("outputs/content/unit-1/transcript.txt", "Transcript"),
        ("outputs/content/unit-1/figure.png", "image"),
        ("outputs/content/unit-1/photo.jpg", "image"),
        ("outputs/content/unit-1/photo.jpeg", "image"),
        ("outputs/content/unit-1/diagram.webp", "image"),
        ("outputs/content/unit-1/diagram.svg", "<svg/>"),
        ("outputs/content/unit-1/table.csv", "a,b\n1,2\n"),
    )

    for relative_path, content in allowed:
        assert (
            managed_execution.validate_managed_textbook_write(
                f"{policy.filesystem_root}/{relative_path}",
                content,
                policy,
            )
            is None
        )


def test_book_pipeline_zone_based_write_validation():
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_book_pipeline_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )
    accepted = (
        ("work/scratch/plan.txt", "scratch"),
        (
            "outputs/book-skill/chapters/unit-1/reading-a.md",
            "# Reading A",
        ),
        (
            "outputs/book-skill/chapters/unit-1/support.json",
            '{"support":true}',
        ),
        (
            "outputs/content/unit-1/knowledge.md",
            "# Knowledge",
        ),
        (
            "outputs/chapters/unit-1/transcript.txt",
            "Transcript",
        ),
        (
            "outputs/knowledge/unit-1/concepts.json",
            '["concept"]',
        ),
        ("outputs/temporary.json", '{"scratch":true}'),
        ("outputs/archive.bin", "binary"),
        ("outputs/book_package.json", "[]"),
    )
    rejected = (
        "../outside.txt",
        "inputs/source.md",
        ".agents/skills/book-to-skill/SKILL.md",
        ".langalpha/progress.jsonl",
        "work",
        "outputs",
        "/tmp/outside.txt",
    )

    for relative_path, content in accepted:
        assert (
            managed_execution.validate_managed_textbook_write(
                f"{policy.filesystem_root}/{relative_path}",
                content,
                policy,
            )
            is None
        )
    assert (
        managed_execution.validate_managed_textbook_write(
            "work/scratch/relative.txt",
            "scratch",
            policy,
        )
        is None
    )
    for relative_path in rejected:
        content = (
            '{"event_key":"chapter_analysis:completed:chapter","stage":"chapter_analysis",'
            '"status":"completed"}'
            if relative_path.endswith("progress.jsonl")
            else "content"
        )
        candidate = (
            relative_path
            if relative_path.startswith("/")
            else f"{policy.filesystem_root}/{relative_path}"
        )
        assert managed_execution.validate_managed_textbook_write(
            candidate,
            content,
            policy,
        )


def test_zone_based_write_keeps_defensive_size_bound(monkeypatch):
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_book_pipeline_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )
    monkeypatch.setattr(managed_execution, "_MAX_MANAGED_WRITE_BYTES", 4)

    error = managed_execution.validate_managed_textbook_write(
        f"{policy.filesystem_root}/work/scratch.txt",
        "12345",
        policy,
    )

    assert "too large" in str(error)


def test_managed_edit_uses_the_same_zone_gate():
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_book_pipeline_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    assert (
        managed_execution.validate_managed_textbook_edit(
            "outputs/book-skill/chapters/unit-1/support.json",
            policy,
        )
        is None
    )
    for path in (
        "inputs/source.md",
        ".agents/skills/book-to-skill/SKILL.md",
        ".langalpha/progress.jsonl",
        "outputs\n",
        "outputs",
        "/tmp/outside.txt",
    ):
        assert managed_execution.validate_managed_textbook_edit(path, policy)


@pytest.mark.parametrize(
    ("relative_path", "content", "expected"),
    (
        ("outputs/content_tree.json", "not json", "valid JSON"),
        (
            ".langalpha/progress.jsonl",
            '["not","an","object"]',
            "append-only",
        ),
        (
            ".langalpha/progress.jsonl",
            '{"event_key":"event-1","stage":"chapter_analysis","status":"running"}\n'
            "not json",
            "append-only",
        ),
    ),
)
def test_book_pipeline_policy_rejects_invalid_json_objects(
    relative_path, content, expected
):
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_book_pipeline_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    error = managed_execution.validate_managed_textbook_write(
        f"{policy.filesystem_root}/{relative_path}",
        content,
        policy,
    )

    assert expected in str(error)


@pytest.mark.parametrize(
    ("relative_path", "content"),
    (
        ("outputs/book_package.json", '{"value":NaN}'),
        ("outputs/book_package.json", '{"value":1e999}'),
        ("outputs/content_tree.json", '{"value":Infinity}'),
        ("outputs/content_tree.json", '{"value":-1e999}'),
        ("outputs/knowledge_points.json", '{"value":-Infinity}'),
        (
            "outputs/content/unit-1/practice.json",
            '{"question":"one","question":"two"}',
        ),
        (
            "outputs/book-skill/chapters/unit-1/payload.json",
            '{"nested":{"value":1,"value":2}}',
        ),
    ),
)
def test_book_pipeline_policy_rejects_nonstandard_or_duplicate_json(
    relative_path, content
):
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_book_pipeline_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    error = managed_execution.validate_managed_textbook_write(
        f"{policy.filesystem_root}/{relative_path}",
        content,
        policy,
    )

    assert "valid JSON" in str(error)


@pytest.mark.parametrize(
    "content",
    (
        '{"stage":"chapter_analysis","status":"running"}',
        '{"event_key":"event-1","stage":"unknown","status":"running"}',
        '{"event_key":"event-1","stage":"chapter_analysis","status":"unknown"}',
        (
            '{"event_key":"event-1","stage":"chapter_analysis",'
            '"status":"running","reasoning":"hidden"}'
        ),
        (
            '{"event_key":"event-1","stage":"chapter_analysis",'
            '"status":"running","metadata":{"tool_args":[]}}'
        ),
        (
            '{"event_key":"event-1","stage":"chapter_analysis",'
            '"status":"running","secret":"token"}'
        ),
        '{"event_key":"event-1","event_key":"event-2","stage":"chapter_analysis",'
        '"status":"running"}',
        '{"event_key":"event-1","stage":"chapter_analysis","status":"running",'
        '"current":NaN}',
        '{"event_key":"event-1","stage":"chapter_analysis","status":"running",'
        '"current":1e999}',
    ),
)
def test_book_pipeline_policy_rejects_unsafe_progress_events(content):
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_book_pipeline_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    assert managed_execution.validate_managed_textbook_write(
        f"{policy.filesystem_root}/.langalpha/progress.jsonl",
        content,
        policy,
    )


@pytest.mark.parametrize(
    "relative_path",
    (
        "../outside.json",
        "inputs/manifest.json",
        "outputs/book-skill/chapters/../../escape.md",
        ".langalpha/progress.jsonl.bak",
        "outputs/content/unit-1/bad\x00name.md",
        "outputs/content/unit-1/bad\rname.md",
        "outputs/content/unit-1/bad\nname.md",
        "outputs/content/unit-1/bad\tname.md",
        "\toutputs/content/unit-1/bad.md",
        "outputs/content/unit-1/bad.md\t",
    ),
)
def test_book_pipeline_policy_rejects_unmanaged_paths(relative_path):
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_book_pipeline_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    assert managed_execution.validate_managed_textbook_write(
        f"{policy.filesystem_root}/{relative_path}",
        "{}",
        policy,
    )


def test_book_pipeline_manifest_contract_separates_write_and_import_layers():
    plan = (
        REPO_ROOT / "docs/plans/2026-09-22-unified-book-processing-pipeline.md"
    ).read_text(encoding="utf-8")
    overlay = (
        REPO_ROOT
        / "plugins/langalpha_local/skills/book-to-skill/reference/langalpha-managed.md"
    ).read_text(encoding="utf-8")

    for contract in (plan, overlay):
        contract = " ".join(contract.split()).lower()
        assert "does not inspect manifest membership" in contract
        assert "downloads only asset paths explicitly listed" in contract
        assert "undeclared" in contract and "never" in contract


def test_progress_write_gate_defers_semantic_parsing_to_task_6():
    plan = (
        REPO_ROOT / "docs/plans/2026-09-22-unified-book-processing-pipeline.md"
    ).read_text(encoding="utf-8")

    assert "Task 6 progress parser is mandatory and authoritative" in plan


def test_lesson_policy_uses_zone_based_write_gate():
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_lesson_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    assert policy.allowed_skill_names == frozenset({"book-to-skill"})
    assert policy.purpose == "lesson"
    assert (
        managed_execution.validate_managed_textbook_write(
            f"{policy.filesystem_root}/outputs/lesson.md",
            "# Lesson",
            policy,
        )
        is None
    )
    assert (
        managed_execution.validate_managed_textbook_write(
            f"{policy.filesystem_root}/outputs/practice.json",
            '{"questions":[]}',
            policy,
        )
        is None
    )
    assert (
        managed_execution.validate_managed_textbook_write(
            f"{policy.filesystem_root}/outputs/lesson.json",
            "{}",
            policy,
        )
        is None
    )
    assert (
        managed_execution.validate_managed_textbook_write(
            f"{policy.filesystem_root}/work/notes.txt",
            "scratch",
            policy,
        )
        is None
    )
    assert "valid JSON" in str(
        managed_execution.validate_managed_textbook_write(
            f"{policy.filesystem_root}/outputs/practice.json",
            "not json",
            policy,
        )
    )


def test_book_asset_policy_uses_zone_based_write_gate():
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_book_asset_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    assert policy.allowed_skill_names == frozenset({"book-to-skill"})
    assert policy.purpose == "assets"
    for relative_path, content in (
        (
            "outputs/chapters_manifest.json",
            '{"format":"langalpha-managed-book-assets/v1","chapter_files":[]}',
        ),
        ("outputs/chapters/ch01-overview.md", "# Overview"),
        ("outputs/glossary.md", "# Glossary"),
    ):
        assert (
            managed_execution.validate_managed_textbook_write(
                f"{policy.filesystem_root}/{relative_path}",
                content,
                policy,
            )
            is None
        )
    assert (
        managed_execution.validate_managed_textbook_write(
            f"{policy.filesystem_root}/outputs/structure.json",
            "{}",
            policy,
        )
        is None
    )
    assert (
        managed_execution.validate_managed_textbook_write(
            f"{policy.filesystem_root}/work/scratch.json",
            '["scratch"]',
            policy,
        )
        is None
    )


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
async def test_managed_sandbox_initialization_precreates_writable_layout(monkeypatch):
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    PTCSandbox = import_module("ptc_agent.core.sandbox.ptc_sandbox").PTCSandbox
    policy = managed_execution.education_teaching_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    class Runtime:
        id = "sandbox-1"
        working_dir = policy.filesystem_root
        commands: list[str] = []
        directories: list[tuple[str, int]] = []
        uploads: list[tuple[bytes, str]] = []

        async def fetch_working_dir(self):
            return policy.filesystem_root

        async def exec(self, command, *_args, **_kwargs):
            self.commands.append(command)
            return SimpleNamespace(exit_code=0, stdout="", stderr="")

        async def ensure_directory(self, path, *, mode=0o755):
            self.directories.append((path, mode))

        async def upload_file(self, content, dest_path):
            self.uploads.append((content, dest_path))

    runtime = Runtime()
    sandbox = object.__new__(PTCSandbox)
    sandbox.config = managed_execution.managed_core_config(
        type(
            "Core",
            (),
            {
                "filesystem": type(
                    "Filesystem",
                    (),
                    {
                        "working_directory": "/home/workspace",
                        "allowed_directories": ["/home/workspace"],
                        "denied_directories": [],
                    },
                )(),
                "mcp": type("MCP", (), {"servers": []})(),
                "sandbox": type("Sandbox", (), {"platform_secrets": ()})(),
                "model_copy": lambda self, *, deep: self,
            },
        )(),
        policy,
    )
    sandbox.provider = AsyncMock()
    sandbox.provider.create.return_value = runtime

    async def runtime_call(func, *args, **kwargs):
        if getattr(func, "__name__", "") == "ensure_directories":
            kwargs.pop("retry_policy", None)
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
        retry_policy=pytest.importorskip(
            "ptc_agent.core.sandbox.retry"
        ).RetryPolicy.SAFE,
        allow_reconnect=False,
        managed_security=True,
    )
    assert sandbox.sandbox_id == "sandbox-1"
    assert sandbox._work_dir == policy.filesystem_root
    assert {path for path, _mode in runtime.directories} == set(
        managed_execution.managed_textbook_directories(policy.filesystem_root)
    ) | {f"{policy.filesystem_root}/inputs"}
    assert (
        dict(runtime.directories)[f"{policy.filesystem_root}/inputs"] == 0o555
    )
    assert runtime.uploads == [
        (b"", f"{policy.filesystem_root}/.langalpha/progress.jsonl")
    ]
    assert len(runtime.commands) == 1
    for directory in managed_execution.managed_textbook_directories(
        policy.filesystem_root
    ):
        assert f"test -w {directory}" in runtime.commands[0]
    assert f"test -w {policy.filesystem_root}/inputs" not in runtime.commands[0]


@pytest.mark.asyncio
async def test_managed_session_does_not_connect_mcp_or_hydrate_workspace(monkeypatch):
    """Managed sessions use the stripped config and the dedicated sandbox setup."""
    session_module = import_module("ptc_agent.core.session")
    policy = import_module(
        "ptc_agent.agent.managed_execution"
    ).education_teaching_policy("8a77d086-0b23-4a1e-89d0-f163fa23d5d1")
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
    policy = import_module(
        "ptc_agent.agent.managed_execution"
    ).education_teaching_policy("8a77d086-0b23-4a1e-89d0-f163fa23d5d1")
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
        config=type(
            "Config", (), {"subagents": type("Subagents", (), {"enabled": []})()}
        )(),
        user_id="parent-1",
        store=object(),
        on_signed_url=object(),
        managed_policy=policy,
    )

    assert captured["user_id"] is None
    assert captured["store"] is None
    assert captured["user_profile"] is None
    assert captured["on_signed_url"] is None


@pytest.mark.asyncio
async def test_managed_graph_keeps_the_root_guard_for_allowed_builtin_subagents(
    monkeypatch,
):
    """Service-owned work still needs the root fence for its fixed workers."""
    graph_module = import_module("ptc_agent.agent.graph")
    policy = import_module(
        "ptc_agent.agent.managed_execution"
    ).education_teaching_policy("8a77d086-0b23-4a1e-89d0-f163fa23d5d1")
    captured: dict[str, object] = {}

    class FakePTCAgent:
        def __init__(self, _config):
            pass

        def create_agent(self, **kwargs):
            captured.update(kwargs)
            return object()

    monkeypatch.setattr(graph_module, "PTCAgent", FakePTCAgent)
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
    guard = object()

    await graph_module.build_ptc_graph_with_session(
        session=session,
        config=type(
            "Config", (), {"subagents": type("Subagents", (), {"enabled": []})()}
        )(),
        namespace_owner=guard,
        managed_policy=policy,
    )

    assert captured["namespace_owner"] is guard
    assert captured["managed_policy"] is policy


def test_managed_agent_uses_a_rooted_backend_and_removes_ambient_tools(monkeypatch):
    agent_module = import_module("ptc_agent.agent.agent")
    policy = import_module(
        "ptc_agent.agent.managed_execution"
    ).education_teaching_policy("8a77d086-0b23-4a1e-89d0-f163fa23d5d1")

    captured: dict[str, object] = {}

    class FakeAgent:
        def with_config(self, _config):
            return self

    def fake_create_agent(_model, **kwargs):
        captured.update(kwargs)
        return FakeAgent()

    monkeypatch.setattr(agent_module, "create_agent", fake_create_agent)
    # Upstream renamed the registry entry point; the managed filter runs over
    # whatever this returns.
    monkeypatch.setattr(
        agent_module, "build_effective_skill_registry", lambda *_args, **_kwargs: {}
    )
    monkeypatch.setattr(agent_module, "resolve_compaction_client", lambda _config: None)
    compiled_subagents: list[dict[str, object]] = []

    def compile_subagents(**kwargs):
        compiled_subagents.append(
            {
                "enabled_names": kwargs["enabled_names"],
                "definition": kwargs["registry"].get("textbook-chapter-worker"),
            }
        )
        return [
            {
                "name": "textbook-chapter-worker",
                "description": "managed chapter worker",
                "system_prompt": "managed chapter worker prompt",
            }
        ]

    monkeypatch.setattr(agent_module, "create_subagents", compile_subagents)

    class Config:
        llm = None
        skills = type(
            "Skills",
            (),
            {
                "enabled": True,
                "sandbox_skills_base": "/home/workspace/.agents/skills",
                "local_skill_dirs_with_sandbox": staticmethod(lambda: []),
            },
        )()
        filesystem = type(
            "Filesystem",
            (),
            {
                "working_directory": policy.filesystem_root,
                "denied_directories": [],
            },
        )()
        mcp = type("MCP", (), {"servers": [], "tool_exposure_mode": "summary"})()
        compaction = type(
            "Compaction",
            (),
            {"model_dump": lambda self: {}, "profile": None},
        )()
        background_auto_wait = False
        search_api = "tavily"
        search_depth = "standard"
        input_modalities = None
        # Upstream's turn model reads the resolved prompt-guidance level.
        prompt_guidance = None
        # Upstream's skill registry reads the per-account disable set.
        disabled_skills = frozenset()
        user_skills = ()
        user_skill_dir = None
        workspace_skill_dir = None
        subagents = type("Subagents", (), {"enabled": [], "definitions": {}})()
        feature_enabled = staticmethod(lambda _key: False)

        def get_llm_client(self):
            # Upstream stamps call metadata onto the client, so the fake needs
            # a metadata slot rather than a bare object().
            return SimpleNamespace(metadata={})

        def client_for_role(self, *_args, **_kwargs):
            return None

    sandbox = AsyncMock()
    sandbox.config = Config()
    sandbox.sandbox_id = "sandbox-1"
    sandbox.skills_manifest = None
    ptc_agent = agent_module.PTCAgent(Config())
    guard = object()

    ptc_agent.create_agent(
        sandbox=sandbox,
        mcp_registry=object(),
        namespace_owner=guard,
        managed_policy=policy,
    )

    tool_names = {tool.name for tool in captured["tools"]}
    assert {
        "Bash",
        "BashOutput",
        "ExecuteCode",
        "GetPreviewUrl",
        "ShowWidget",
        "WebSearch",
        "Read",
        "Write",
        "Edit",
        "Glob",
        "Grep",
        "TodoWrite",
    } <= tool_names
    # A managed job still excludes interactive and household tools that reach
    # identity or data outside the service-owned textbook root.
    assert (
        not {
            "AskUserQuestion",
            "get_homework_schedule",
        }
        & tool_names
    )
    assert compiled_subagents[0]["enabled_names"] == ["textbook-chapter-worker"]
    assert compiled_subagents[0]["definition"] is not None
    background = next(
        middleware
        for middleware in captured["middleware"]
        if type(middleware).__name__ == "BackgroundSubagentMiddleware"
    )
    assert background.namespace_owner is guard


def test_managed_bash_rejects_shell_escapes_from_the_job_root():
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_teaching_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    assert (
        managed_execution.validate_managed_bash_command(
            "cat inputs/manifest.json", policy
        )
        is None
    )
    assert (
        managed_execution.validate_managed_bash_command(
            "sha256sum inputs/manifest.json", policy
        )
        is None
    )
    assert "outside the managed textbook job root" in str(
        managed_execution.validate_managed_bash_command("cat /etc/passwd", policy)
    )
    assert "outside the managed textbook job root" in str(
        managed_execution.validate_managed_bash_command("cd .. && ls", policy)
    )
    assert "not allowed" in str(
        managed_execution.validate_managed_bash_command(
            "curl https://example.com", policy
        )
    )


@pytest.mark.parametrize("interpreter", ["python", "python3"])
def test_managed_bash_allows_only_the_staged_progress_helper(interpreter):
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_book_pipeline_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )
    event = json.dumps(
        {
            "event_key": "chapter_analysis:running:chapter",
            "stage": "chapter_analysis",
            "status": "running",
        }
    )

    assert (
        managed_execution.validate_managed_bash_command(
            f"{interpreter} .langalpha/progress.py",
            policy,
        )
        is None
    )
    assert (
        managed_execution.validate_managed_bash_command(
            f"{interpreter} .langalpha/progress.py '{event}'",
            policy,
        )
        is None
    )
    for command in (
        f"{interpreter} .langalpha/progress.py '{event}' && cat inputs/manifest.json",
        f"{interpreter} .langalpha/progress.py \"$(cat inputs/manifest.json)\"",
        f"/usr/bin/{interpreter} .langalpha/progress.py '{event}'",
        f"{interpreter} {policy.filesystem_root}/.langalpha/progress.py '{event}'",
        f"{interpreter} .langalpha/progress.py '[]'",
    ):
        assert managed_execution.validate_managed_bash_command(command, policy)


@pytest.mark.parametrize(
    "policy_factory",
    [
        "education_structure_policy",
        "education_lesson_policy",
        "education_book_asset_policy",
        "education_book_pipeline_policy",
    ],
)
def test_all_managed_purposes_reject_direct_progress_stream_writes(
    policy_factory,
):
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = getattr(managed_execution, policy_factory)(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )
    progress_path = f"{policy.filesystem_root}/.langalpha/progress.jsonl"
    valid = (
        '{"event_key":"chapter_analysis:running:chapter","stage":"chapter_analysis",'
        '"status":"running"}\n'
    )

    for content in (
        valid,
        json.dumps(
            {
                "event_key": "chapter_analysis:running:chapter",
                "stage": "chapter_analysis",
                "status": "running",
                "label": "已完成 1 / 3",
            }
        ),
    ):
        error = managed_execution.validate_managed_textbook_write(
            progress_path,
            content,
            policy,
        )
        assert "append-only" in str(error)
        assert "progress.py" in str(error)
    for invalid_event in (
        {},
        {"event_key": "", "stage": "chapter_analysis", "status": "running"},
        {"event_key": "bad key", "stage": "chapter_analysis", "status": "running"},
        {
            "event_key": "x" * 256,
            "stage": "chapter_analysis",
            "status": "running",
        },
        {
            "event_key": "chapter_analysis:running:chapter",
            "stage": "unknown",
            "status": "running",
        },
        {
            "event_key": "chapter_analysis:running:chapter",
            "stage": "chapter_analysis",
            "status": "running",
            "label": "zero\u200bwidth",
        },
        {
            "event_key": "chapter_analysis:running:chapter",
            "stage": "chapter_analysis",
            "status": "running",
            "label": "/home/parent/book.md",
        },
        {
            "event_key": "chapter_analysis:running:chapter",
            "stage": "chapter_analysis",
            "status": "running",
            "label": "api_key=opaque-value",
        },
    ):
        assert managed_execution.validate_managed_textbook_write(
            progress_path,
            json.dumps(invalid_event),
            policy,
        )
    for relative_path in (
        ".langalpha/progress.py",
        ".langalpha/progress.jsonl.bak",
    ):
        assert managed_execution.validate_managed_textbook_write(
            f"{policy.filesystem_root}/{relative_path}",
            valid,
            policy,
        )


@pytest.mark.parametrize(
    ("event", "accepted"),
    [
        (
            {
                "event_key": "chapter_analysis:running:chapter",
                "stage": "chapter_analysis",
                "status": "running",
                "label": "已完成 1 / 3",
            },
            True,
        ),
        (
            {
                "event_key": "bad key",
                "stage": "chapter_analysis",
                "status": "running",
            },
            False,
        ),
        (
            {
                "event_key": "chapter_analysis:running:chapter",
                "stage": "chapter_analysis",
                "status": "running",
                "label": "zero\u200bwidth",
            },
            False,
        ),
        (
            {
                "event_key": "chapter_analysis:running:chapter",
                "stage": "chapter_analysis",
                "status": "running",
                "label": "/home/parent/book.md",
            },
            False,
        ),
        (
            {
                "event_key": "chapter_analysis:running:chapter",
                "stage": "chapter_analysis",
                "status": "running",
                "label": "api_key=opaque-value",
            },
            False,
        ),
    ],
)
def test_progress_validators_agree_on_the_same_input(
    event,
    accepted,
    tmp_path,
):
    managed_execution = import_module("ptc_agent.agent.managed_execution")
    policy = managed_execution.education_book_pipeline_policy(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )
    raw = json.dumps(event, ensure_ascii=False)

    try:
        education_generation_progress.parse_progress_json_line(raw)
    except education_generation_progress.ProgressEventValidationError:
        server_accepted = False
    else:
        server_accepted = True

    write_accepted = (
        managed_execution.validate_managed_textbook_write(
            f"{policy.filesystem_root}/.langalpha/progress.jsonl",
            raw,
            policy,
        )
        is None
    )

    helper = tmp_path / "progress.py"
    helper.write_bytes(education_teaching_storage.progress_helper_source())
    helper_result = subprocess.run(
        [sys.executable, str(helper)],
        input=raw,
        capture_output=True,
        text=True,
        check=False,
    )
    helper_accepted = helper_result.returncode == 0

    assert server_accepted == accepted
    assert write_accepted is False
    assert helper_accepted == accepted


def test_managed_teaching_write_defers_schema_and_cross_reference_checks():
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
            candidate,
            '{"chapters":[{"knowledge_points":["核心概念"],'
            '"questions":[{"knowledge_point":"扩展概念"}]}]}',
            policy,
        )
        is None
    )
    assert "valid JSON" in str(
        managed_execution.validate_managed_textbook_write(
            f"{policy.filesystem_root}/work/knowledge-skill/chapter.json",
            "not JSON",
            policy,
        )
    )
    assert (
        managed_execution.validate_managed_textbook_write(
            f"{policy.filesystem_root}/outputs/chapters/01-overview-toolkit.md",
            "# 工具包\n\n中文解释",
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
    assert (
        backend.aexecute_bash.await_args.kwargs["working_dir"] == policy.filesystem_root
    )
