"""Managed PTC workspace and thread ownership contracts."""

from importlib import import_module
from importlib.util import find_spec
from hashlib import sha256
from unittest.mock import AsyncMock, MagicMock

import pytest


JOB_ID = "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"


@pytest.mark.asyncio
async def test_managed_workspace_provision_skips_normal_workspace_sync(monkeypatch):
    workspace_manager_module = import_module("src.server.services.workspace_manager")
    policy = import_module("ptc_agent.agent.managed_execution").education_teaching_policy(
        JOB_ID
    )
    manager = object.__new__(workspace_manager_module.WorkspaceManager)
    class Core:
        def __init__(self):
            self.filesystem = type("Filesystem", (), {})()
            self.mcp = type("MCP", (), {})()
            self.sandbox = type("Sandbox", (), {})()

        def model_copy(self, *, deep):
            assert deep is True
            return Core()

    manager.config = type("Config", (), {"to_core_config": lambda self: Core()})()
    manager._sessions = {}
    manager._provision_sandbox_session = AsyncMock()
    manager._sync_sandbox_assets = AsyncMock()

    session = type(
        "Session",
        (),
        {
            "sandbox": type("Sandbox", (), {"sandbox_id": "sandbox-1"})(),
            "initialize_managed_textbook": AsyncMock(),
        },
    )()
    monkeypatch.setattr(
        workspace_manager_module.SessionManager,
        "get_session",
        lambda *_args: session,
    )
    monkeypatch.setattr(
        workspace_manager_module,
        "update_workspace_status",
        AsyncMock(return_value={"workspace_id": "workspace-1", "status": "running"}),
    )

    provisioned = await manager.provision_managed_textbook_session(
        workspace_id="workspace-1", policy=policy
    )

    assert provisioned is session
    session.initialize_managed_textbook.assert_awaited_once_with(policy)
    manager._provision_sandbox_session.assert_not_awaited()
    manager._sync_sandbox_assets.assert_not_awaited()


@pytest.mark.asyncio
async def test_launcher_creates_hidden_workspace_thread_then_stages_before_dispatch(
    monkeypatch,
):
    assert find_spec("src.server.services.education_managed_ptc") is not None
    education_managed_ptc = import_module(
        "src.server.services.education_managed_ptc"
    )

    calls: list[str] = []
    workspace = AsyncMock(return_value={"workspace_id": "workspace-1"})
    thread = AsyncMock(return_value={"conversation_thread_id": "thread-1"})

    async def stage(*_args, **_kwargs):
        calls.append("stage")
        return {"manifest": {"job_id": "job-1"}}

    async def dispatch(**kwargs):
        calls.append("dispatch")
        assert kwargs["agent_config"] is agent_config
        assert kwargs["skill_contexts"] == [
            {
                "name": "book-to-skill",
                "instruction": f"--managed-textbook {JOB_ID}",
            },
            {
                "name": "the-knowledge-guy",
                "instruction": f"--managed-textbook {JOB_ID}",
            },
        ]
        policy = kwargs["policy"]
        assert policy.filesystem_root == f"/managed/textbook-job/{JOB_ID}"
        assert policy.enable_mcp is False
        assert policy.enable_web is False
        assert policy.enable_vault is False
        return {"root_run_id": "run-1"}

    agent_config = MagicMock()
    monkeypatch.setattr(education_managed_ptc, "create_managed_workspace", workspace)
    monkeypatch.setattr(education_managed_ptc, "create_managed_thread", thread)
    monkeypatch.setattr(education_managed_ptc, "stage_managed_teaching_skills", AsyncMock())
    monkeypatch.setattr(education_managed_ptc, "stage_teaching_inputs", stage)
    monkeypatch.setattr(education_managed_ptc, "dispatch_managed_root_run", dispatch)

    launched = await education_managed_ptc.prepare_and_dispatch_teaching_attempt(
        parent_user_id="parent-1",
        job={"job_id": JOB_ID, "chapters": [{"content_chapter_id": "chapter-1"}]},
        sandbox=object(),
        agent_config=agent_config,
    )

    assert launched == {
        "managed_workspace_id": "workspace-1",
        "managed_thread_id": "thread-1",
        "root_run_id": "run-1",
    }
    assert calls == ["stage", "dispatch"]
    workspace.assert_awaited_once_with(parent_user_id="parent-1", job_id=JOB_ID)
    thread.assert_awaited_once_with(
        parent_user_id="parent-1", job_id=JOB_ID, workspace_id="workspace-1"
    )


@pytest.mark.asyncio
async def test_launches_authorized_job_with_managed_session_before_staging(monkeypatch):
    education_managed_ptc = import_module("src.server.services.education_managed_ptc")
    calls: list[str] = []
    job = {
        "job_id": JOB_ID,
        "job_status": "queued",
        "chapters": [{"content_chapter_id": "chapter-1"}],
    }

    class Manager:
        async def provision_managed_textbook_session(self, **kwargs):
            calls.append("provision")
            assert kwargs["policy"].filesystem_root.endswith(JOB_ID)
            return type("Session", (), {"sandbox": object()})()

    async def create_attempt(**kwargs):
        calls.append("attempt")
        assert kwargs["job_id"] == JOB_ID
        return {"attempt_id": "attempt-1"}

    async def prepare(**kwargs):
        calls.append("stage-and-dispatch")
        assert kwargs["attempt_id"] == "attempt-1"
        assert kwargs["session"].sandbox is not None
        assert kwargs["agent_config"] is agent_config
        return {"root_run_id": "run-1"}

    agent_config = object()
    monkeypatch.setattr(education_managed_ptc, "get_teaching_job_for_parent", AsyncMock(return_value=job), raising=False)
    monkeypatch.setattr(education_managed_ptc, "create_managed_workspace", AsyncMock(return_value={"workspace_id": "workspace-1"}))
    monkeypatch.setattr(education_managed_ptc, "create_managed_thread", AsyncMock(return_value={"conversation_thread_id": "thread-1"}))
    monkeypatch.setattr(education_managed_ptc, "create_teaching_attempt", create_attempt, raising=False)
    monkeypatch.setattr(education_managed_ptc, "prepare_and_dispatch_teaching_attempt", prepare, raising=False)
    monkeypatch.setattr(
        education_managed_ptc,
        "resolve_managed_teaching_agent_config",
        AsyncMock(return_value=agent_config),
        raising=False,
    )
    monkeypatch.setattr(
        education_managed_ptc,
        "WorkspaceManager",
        type("WorkspaceManager", (), {"get_instance": staticmethod(lambda: Manager())}),
        raising=False,
    )

    launched = await education_managed_ptc.launch_teaching_attempt(
        parent_user_id="parent-1", job_id=JOB_ID
    )

    assert launched["root_run_id"] == "run-1"
    assert calls == ["attempt", "provision", "stage-and-dispatch"]


@pytest.mark.asyncio
async def test_launch_records_model_configuration_guidance_before_sandbox_provisioning(
    monkeypatch,
):
    education_managed_ptc = import_module("src.server.services.education_managed_ptc")
    job = {
        "job_id": JOB_ID,
        "job_status": "queued",
        "chapters": [{"content_chapter_id": "chapter-1"}],
    }
    failed = AsyncMock(return_value={"attempt_id": "attempt-1", "status": "failed"})
    provision = AsyncMock()

    monkeypatch.setattr(
        education_managed_ptc,
        "get_teaching_job_for_parent",
        AsyncMock(return_value=job),
    )
    monkeypatch.setattr(
        education_managed_ptc,
        "create_managed_workspace",
        AsyncMock(return_value={"workspace_id": "workspace-1"}),
    )
    monkeypatch.setattr(
        education_managed_ptc,
        "create_managed_thread",
        AsyncMock(return_value={"conversation_thread_id": "thread-1"}),
    )
    monkeypatch.setattr(
        education_managed_ptc,
        "create_teaching_attempt",
        AsyncMock(return_value={"attempt_id": "attempt-1"}),
    )
    monkeypatch.setattr(
        education_managed_ptc,
        "fail_preparing_teaching_attempt",
        failed,
        raising=False,
    )
    monkeypatch.setattr(
        education_managed_ptc,
        "resolve_managed_teaching_agent_config",
        AsyncMock(side_effect=ValueError("provider secret must not reach the parent API")),
    )
    monkeypatch.setattr(
        education_managed_ptc,
        "WorkspaceManager",
        type(
            "WorkspaceManager",
            (),
            {
                "get_instance": staticmethod(
                    lambda: type(
                        "Manager",
                        (), {"provision_managed_textbook_session": provision},
                    )()
                )
            },
        ),
    )

    with pytest.raises(ValueError, match="provider secret"):
        await education_managed_ptc.launch_teaching_attempt(
            parent_user_id="parent-1", job_id=JOB_ID
        )

    provision.assert_not_awaited()
    failed.assert_awaited_once_with(
        attempt_id="attempt-1",
        error_code="managed_model_unavailable",
        error_message="教材教学加工需要先配置模型服务，再继续运行。",
    )


@pytest.mark.asyncio
async def test_launch_marks_reserved_attempt_failed_when_sandbox_provisioning_fails(monkeypatch):
    education_managed_ptc = import_module("src.server.services.education_managed_ptc")
    job = {"job_id": JOB_ID, "job_status": "queued", "chapters": [{"content_chapter_id": "chapter-1"}]}
    failed = AsyncMock(return_value={"attempt_id": "attempt-1", "status": "failed"})

    class Manager:
        async def provision_managed_textbook_session(self, **_kwargs):
            raise RuntimeError("sandbox unavailable")

    monkeypatch.setattr(education_managed_ptc, "get_teaching_job_for_parent", AsyncMock(return_value=job))
    monkeypatch.setattr(education_managed_ptc, "create_managed_workspace", AsyncMock(return_value={"workspace_id": "workspace-1"}))
    monkeypatch.setattr(education_managed_ptc, "create_managed_thread", AsyncMock(return_value={"conversation_thread_id": "thread-1"}))
    monkeypatch.setattr(education_managed_ptc, "create_teaching_attempt", AsyncMock(return_value={"attempt_id": "attempt-1"}))
    monkeypatch.setattr(education_managed_ptc, "fail_preparing_teaching_attempt", failed, raising=False)
    monkeypatch.setattr(
        education_managed_ptc,
        "resolve_managed_teaching_agent_config",
        AsyncMock(return_value=MagicMock()),
    )
    monkeypatch.setattr(education_managed_ptc, "WorkspaceManager", type("WorkspaceManager", (), {"get_instance": staticmethod(lambda: Manager())}))

    with pytest.raises(RuntimeError, match="sandbox unavailable"):
        await education_managed_ptc.launch_teaching_attempt(parent_user_id="parent-1", job_id=JOB_ID)

    failed.assert_awaited_once_with(
        attempt_id="attempt-1",
        error_code="managed_sandbox_unavailable",
        error_message="教材教学加工环境无法启动，请重新运行。",
    )


@pytest.mark.asyncio
async def test_resume_requeues_failed_job_then_creates_a_new_root_attempt(monkeypatch):
    education_managed_ptc = import_module("src.server.services.education_managed_ptc")
    calls: list[str] = []

    async def requeue(**kwargs):
        calls.append("requeue")
        assert kwargs == {"parent_user_id": "parent-1", "job_id": JOB_ID}
        return {"job_id": JOB_ID, "status": "queued"}

    async def launch(**kwargs):
        calls.append("launch")
        assert kwargs == {"parent_user_id": "parent-1", "job_id": JOB_ID}
        return {"root_run_id": "run-2"}

    monkeypatch.setattr(education_managed_ptc, "requeue_teaching_job", requeue, raising=False)
    monkeypatch.setattr(education_managed_ptc, "launch_teaching_attempt", launch)

    resumed = await education_managed_ptc.resume_teaching_job(parent_user_id="parent-1", job_id=JOB_ID)

    assert resumed == {"root_run_id": "run-2"}
    assert calls == ["requeue", "launch"]


@pytest.mark.asyncio
async def test_completed_root_archives_validated_candidate_before_review_projection(monkeypatch):
    education_managed_ptc = import_module("src.server.services.education_managed_ptc")
    calls: list[str] = []
    markdown = "# 导读\n\n冻结教材正文"

    async def download(*_args, **_kwargs):
        calls.append("download")
        return {"format": "candidate"}

    async def validating(**_kwargs):
        calls.append("validating")
        return {"status": "validating"}

    def validate(candidate, frozen):
        calls.append("validate")
        assert candidate == {"format": "candidate"}
        assert frozen["chapters"][0]["content_sha256"] == sha256(
            markdown.encode("utf-8")
        ).hexdigest()
        return {"chapters": [{"content_chapter_id": "chapter-1"}]}

    async def archive(*_args, **_kwargs):
        calls.append("archive")
        return "education/household/book/v1/teaching/v1"

    async def complete(**kwargs):
        calls.append("complete")
        assert kwargs["bundle_prefix"].startswith("education/")
        return {"status": "completed"}

    monkeypatch.setattr(education_managed_ptc, "download_teaching_output", download, raising=False)
    monkeypatch.setattr(education_managed_ptc, "begin_teaching_validation", validating, raising=False)
    monkeypatch.setattr(education_managed_ptc, "validate_teaching_package", validate, raising=False)
    monkeypatch.setattr(education_managed_ptc, "write_teaching_package_bundle", archive, raising=False)
    monkeypatch.setattr(education_managed_ptc, "complete_teaching_attempt", complete, raising=False)
    monkeypatch.setattr(education_managed_ptc, "settle_teaching_attempt", AsyncMock(), raising=False)

    result = await education_managed_ptc.finalize_teaching_attempt(
        job={
            "job_id": JOB_ID,
            "chapters": [
                {
                    "content_chapter_id": "f5761267-11d1-4977-8107-e2671c99a2f0",
                    "position": 1,
                    "slug": "01-overview",
                    "title": "导读",
                    "markdown": markdown,
                }
            ],
        },
        attempt_id="attempt-1",
        root_run_id="run-1",
        sandbox=object(),
        terminal_status="completed",
        terminal_error=None,
    )

    assert result == {"status": "completed"}
    assert calls == ["validating", "download", "validate", "archive", "complete"]


@pytest.mark.asyncio
async def test_invalid_completed_root_never_creates_review_projection(monkeypatch):
    education_managed_ptc = import_module("src.server.services.education_managed_ptc")
    settle = AsyncMock(return_value={"status": "failed"})
    complete = AsyncMock()
    monkeypatch.setattr(
        education_managed_ptc,
        "download_teaching_output",
        AsyncMock(return_value={"format": "candidate"}),
        raising=False,
    )
    monkeypatch.setattr(
        education_managed_ptc,
        "validate_teaching_package",
        MagicMock(side_effect=ValueError("invalid candidate")),
        raising=False,
    )
    monkeypatch.setattr(education_managed_ptc, "complete_teaching_attempt", complete, raising=False)
    monkeypatch.setattr(education_managed_ptc, "settle_teaching_attempt", settle, raising=False)

    result = await education_managed_ptc.finalize_teaching_attempt(
        job={"job_id": JOB_ID, "chapters": [{"content_chapter_id": "chapter-1"}]},
        attempt_id="attempt-1",
        root_run_id="run-1",
        sandbox=object(),
        terminal_status="completed",
        terminal_error=None,
    )

    assert result == {"status": "failed"}
    complete.assert_not_awaited()
    settle.assert_awaited_once()
    assert settle.await_args.kwargs["status"] == "failed"
