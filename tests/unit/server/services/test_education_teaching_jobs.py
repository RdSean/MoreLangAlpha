"""Product-level managed teaching job orchestration contracts."""

from importlib import import_module
from importlib.util import find_spec
from unittest.mock import AsyncMock, MagicMock, call
from uuid import UUID

import pytest


@pytest.mark.asyncio
async def test_cancel_stamps_education_job_before_requesting_root_run_cancel(
    monkeypatch,
):
    assert find_spec("src.server.services.education_teaching_jobs") is not None
    education_teaching_jobs = import_module(
        "src.server.services.education_teaching_jobs"
    )

    calls: list[str] = []

    async def mark(**_kwargs):
        calls.append("mark")
        return {"managed_thread_id": "thread-1", "root_run_id": "run-1"}

    async def cancel(**kwargs):
        calls.append("cancel")
        assert kwargs == {"thread_id": "thread-1", "run_id": "run-1"}

    monkeypatch.setattr(
        education_teaching_jobs, "mark_teaching_job_cancel_requested", mark
    )
    monkeypatch.setattr(education_teaching_jobs, "request_root_run_cancel", cancel)

    await education_teaching_jobs.cancel_teaching_job(
        parent_user_id="parent-1", job_id="job-1"
    )

    assert calls == ["mark", "cancel"]


@pytest.mark.asyncio
async def test_dispatch_persists_root_run_before_registering_managed_executor(
    monkeypatch,
):
    """Internal teaching dispatch uses the root-run lifecycle, never chat HTTP."""
    education_teaching_jobs = import_module(
        "src.server.services.education_teaching_jobs"
    )
    policy = import_module(
        "ptc_agent.agent.managed_execution"
    ).education_teaching_policy("8a77d086-0b23-4a1e-89d0-f163fa23d5d1")
    calls: list[str] = []
    run_id = "4ef3ea6b-33f3-4b12-91c9-1b31a168ad13"
    query_id = "1048d8c7-4696-44cd-837e-f92fbd68dbb7"

    class Coordinator:
        async def start_run(self, **kwargs):
            calls.append("start")
            assert kwargs["user_id"] is None
            assert kwargs["request_key"] == run_id
            assert UUID(kwargs["request_key"]).version == 4
            assert kwargs["query"].query_type == "system"
            assert (
                kwargs["query"].metadata["managed_execution"]["kind"]
                == "education_teaching"
            )
            assert (
                kwargs["run_metadata"]["managed_execution"]["kind"]
                == "education_teaching"
            )
            return type("Handle", (), {"turn_index": 3, "checkpointer": object()})()

    class Executor:
        async def start_run(self, **kwargs):
            calls.append("executor")
            assert kwargs["completion_callback"] is None
            assert kwargs["terminal_callback"] is not None
            return object()

    monkeypatch.setattr(
        education_teaching_jobs,
        "build_managed_teaching_graph",
        AsyncMock(return_value=(object(), {}, {})),
        raising=False,
    )
    monkeypatch.setattr(
        education_teaching_jobs,
        "RunCoordinator",
        type(
            "RunCoordinator", (), {"get_instance": staticmethod(lambda: Coordinator())}
        ),
        raising=False,
    )
    monkeypatch.setattr(
        education_teaching_jobs,
        "LocalRunExecutor",
        type(
            "LocalRunExecutor", (), {"get_instance": staticmethod(lambda: Executor())}
        ),
        raising=False,
    )
    monkeypatch.setattr(
        education_teaching_jobs, "RunSSEProducer", _FakeProducer, raising=False
    )
    _FakeProducer.last_kwargs = None
    monkeypatch.setattr(
        education_teaching_jobs,
        "get_education_teaching_workflow_timeout",
        lambda: 86_400,
        raising=False,
    )
    generated_ids = iter([run_id, query_id])
    monkeypatch.setattr(
        education_teaching_jobs, "uuid4", lambda: next(generated_ids), raising=False
    )
    monkeypatch.setattr(
        education_teaching_jobs,
        "settle_teaching_attempt",
        AsyncMock(return_value={"status": "running"}),
        raising=False,
    )

    dispatched = await education_teaching_jobs.dispatch_managed_root_run(
        job={
            "job_id": "8a77d086-0b23-4a1e-89d0-f163fa23d5d1",
            "chapters": [
                {"content_chapter_id": "4ef3ea6b-33f3-4b12-91c9-1b31a168ad13"}
            ],
        },
        attempt_id="attempt-1",
        session=object(),
        workspace_id="workspace-1",
        thread_id="thread-1",
        staged={
            "chapters": [
                {
                    "content_chapter_id": "4ef3ea6b-33f3-4b12-91c9-1b31a168ad13",
                    "position": 1,
                    "slug": "lesson-1",
                    "content_sha256": "a" * 64,
                }
            ]
        },
        policy=policy,
    )

    assert dispatched == {"root_run_id": run_id}
    assert calls == ["start", "executor"]
    assert _FakeProducer.last_kwargs == {
        "thread_id": "thread-1",
        "run_id": run_id,
        "workflow_timeout": 86_400,
    }
    graph_call = education_teaching_jobs.build_managed_teaching_graph.await_args
    assert callable(graph_call.kwargs["operation_callback"])
    education_teaching_jobs.settle_teaching_attempt.assert_awaited_once_with(
        attempt_id="attempt-1", root_run_id=run_id, status="running"
    )


class _FakeProducer:
    last_kwargs = None

    def __init__(self, **kwargs):
        type(self).last_kwargs = kwargs

    async def stream_workflow(self, **_kwargs):
        if False:
            yield ""


@pytest.mark.asyncio
async def test_managed_output_writes_append_each_safe_milestone_once(monkeypatch):
    """Fixed candidate paths give durable progress even when a model emits no text event."""
    education_teaching_jobs = import_module(
        "src.server.services.education_teaching_jobs"
    )
    recorded = AsyncMock()
    monkeypatch.setattr(education_teaching_jobs, "record_teaching_event", recorded)
    job_id = "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    chapter_id = "4ef3ea6b-33f3-4b12-91c9-1b31a168ad13"
    root = f"/managed/textbook-job/{job_id}"
    recorder = education_teaching_jobs.ManagedTeachingAssetProgress(
        attempt_id="attempt-1",
        filesystem_root=root,
        staged={
            "chapters": [
                {
                    "content_chapter_id": chapter_id,
                    "position": 1,
                    "slug": "lesson-1",
                    "content_sha256": "a" * 64,
                }
            ]
        },
    )

    recorder(
        {
            "operation": "write_file",
            "file_path": f"{root}/outputs/chapters/01-lesson-1-knowledge.json",
            "content": "untrusted",
        }
    )
    recorder(
        {
            "operation": "write_file",
            "file_path": f"{root}/outputs/chapters/01-lesson-1-knowledge.json",
            "content": "duplicate",
        }
    )
    recorder(
        {
            "operation": "write_file",
            "file_path": f"{root}/outputs/chapters/01-lesson-1-toolkit.md",
            "content": "untrusted",
        }
    )
    recorder(
        {
            "operation": "write_file",
            "file_path": f"{root}/outputs/knowledge/coverage-audit.json",
            "content": "untrusted",
        }
    )
    recorder(
        {
            "operation": "write_file",
            "file_path": f"{root}/outputs/other.json",
            "content": "ignored",
        }
    )
    await recorder.drain()

    assert recorded.await_args_list == [
        call(
            attempt_id="attempt-1",
            phase="concept_linking",
            chapter_id=chapter_id,
            asset_kind="knowledge",
            summary="Agent 已报告：第 1 章已完成概念关联",
        ),
        call(
            attempt_id="attempt-1",
            phase="teaching_build",
            chapter_id=chapter_id,
            asset_kind="toolkit",
            summary="Agent 已报告：第 1 章已完成教学材料生成",
        ),
        call(
            attempt_id="attempt-1",
            phase="coverage_audit",
            chapter_id=None,
            asset_kind=None,
            summary="Agent 已报告：已完成覆盖审计",
        ),
    ]


@pytest.mark.asyncio
async def test_managed_progress_projection_accepts_only_frozen_chapter_ids(monkeypatch):
    """A real SSE message advances only an approved phase for frozen input."""
    education_teaching_jobs = import_module(
        "src.server.services.education_teaching_jobs"
    )
    recorded = AsyncMock()
    monkeypatch.setattr(education_teaching_jobs, "record_teaching_event", recorded)
    chapter_id = "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    event = (
        'data: {"event":"message","content":"EDUCATION_PROGRESS '
        '{\\"phase\\":\\"practice_build\\",\\"content_chapter_id\\":\\"'
        f"{chapter_id}"
        '\\",\\"asset_kind\\":\\"practice\\"}"}\n\n'
    )

    await education_teaching_jobs._record_safe_progress(
        attempt_id="attempt-1",
        staged={"chapters": [{"content_chapter_id": chapter_id, "position": 2}]},
        event=event,
    )

    recorded.assert_awaited_once_with(
        attempt_id="attempt-1",
        phase="practice_build",
        chapter_id=chapter_id,
        asset_kind="practice",
        summary="Agent 已报告：第 2 章已完成练习构建",
    )


def test_managed_prompt_directs_one_root_to_read_staged_skills_without_forcing_order():
    education_teaching_jobs = import_module(
        "src.server.services.education_teaching_jobs"
    )

    prompt = education_teaching_jobs.managed_teaching_prompt(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    assert ".agents/skills/book-to-skill/SKILL.md" in prompt
    assert ".agents/skills/the-knowledge-guy/SKILL.md" in prompt
    assert (
        ".agents/skills/book-to-skill/reference/managed-textbook-contract.md" in prompt
    )
    assert (
        ".agents/skills/the-knowledge-guy/reference/managed-textbook-contract.md"
        in prompt
    )
    assert "## Managed textbook mode" not in prompt
    assert "严格先完成" not in prompt


@pytest.mark.asyncio
async def test_managed_workflow_refreshes_the_attempt_heartbeat(monkeypatch):
    education_teaching_jobs = import_module(
        "src.server.services.education_teaching_jobs"
    )
    heartbeat = AsyncMock(return_value=True)
    monkeypatch.setattr(education_teaching_jobs, "touch_teaching_attempt", heartbeat)

    async def workflow():
        yield 'data: {"event":"message","content":"working"}\n\n'

    events = [
        event
        async for event in education_teaching_jobs._managed_workflow_events(
            workflow(),
            attempt_id="attempt-1",
            root_run_id="run-1",
            staged={"chapters": []},
        )
    ]

    assert len(events) == 1
    heartbeat.assert_awaited_once_with(attempt_id="attempt-1", root_run_id="run-1")


@pytest.mark.asyncio
async def test_managed_workflow_refreshes_heartbeat_during_a_busy_event_stream(
    monkeypatch,
):
    """A continuous model stream must not hide a long-running root from parents."""
    education_teaching_jobs = import_module(
        "src.server.services.education_teaching_jobs"
    )
    heartbeat = AsyncMock(return_value=True)
    clock_values = iter([0.0, 3.0, 18.0])
    monkeypatch.setattr(education_teaching_jobs, "touch_teaching_attempt", heartbeat)
    monkeypatch.setattr(
        education_teaching_jobs,
        "monotonic",
        lambda: next(clock_values),
        raising=False,
    )

    async def workflow():
        yield 'data: {"event":"message","content":"first chunk"}\n\n'
        yield 'data: {"event":"message","content":"second chunk"}\n\n'

    events = [
        event
        async for event in education_teaching_jobs._managed_workflow_events(
            workflow(),
            attempt_id="attempt-1",
            root_run_id="run-1",
            staged={"chapters": []},
        )
    ]

    assert len(events) == 2
    assert heartbeat.await_count == 2
    heartbeat.assert_awaited_with(attempt_id="attempt-1", root_run_id="run-1")


@pytest.mark.asyncio
async def test_managed_graph_does_not_inject_interactive_skill_bodies(monkeypatch):
    """The compact service prompt carries only the managed modes."""
    education_teaching_jobs = import_module(
        "src.server.services.education_teaching_jobs"
    )
    setup = import_module("src.server.app.setup")
    policy = import_module(
        "ptc_agent.agent.managed_execution"
    ).education_teaching_policy("8a77d086-0b23-4a1e-89d0-f163fa23d5d1")
    agent_config = object()
    monkeypatch.setattr(setup, "agent_config", object())
    monkeypatch.setattr(education_teaching_jobs, "get_ptc_recursion_limit", lambda: 200)
    monkeypatch.setattr(
        education_teaching_jobs,
        "build_ptc_graph_with_session",
        AsyncMock(return_value=object()),
    )
    guard = object()
    handle = type(
        "Handle",
        (),
        {"run_id": "run-1", "turn_index": 1, "checkpointer": object(), "guard": guard},
    )()

    _graph, _state, config = await education_teaching_jobs.build_managed_teaching_graph(
        session=object(),
        thread_id="thread-1",
        run_handle=handle,
        policy=policy,
        agent_config=agent_config,
    )

    assert "skill_contexts" not in config["configurable"]
    assert "skill_dirs" not in config["configurable"]
    assert config["recursion_limit"] == 200
    graph_call = education_teaching_jobs.build_ptc_graph_with_session.await_args
    assert graph_call.kwargs["config"] is agent_config
    assert graph_call.kwargs["user_id"] is None
    assert graph_call.kwargs["disable_subagents"] is False
    assert graph_call.kwargs["subagent_names"] == ["textbook-chapter-worker"]
    assert graph_call.kwargs["namespace_owner"] is guard


@pytest.mark.asyncio
async def test_managed_graph_resolves_parent_credentials_before_sandbox_execution(
    monkeypatch,
):
    """Managed work uses the parent's model credentials without giving it parent identity."""
    education_teaching_jobs = import_module(
        "src.server.services.education_teaching_jobs"
    )
    setup = import_module("src.server.app.setup")
    base_config = object()
    resolved_config = MagicMock()
    resolve = AsyncMock(return_value=resolved_config)

    monkeypatch.setattr(setup, "agent_config", base_config)
    monkeypatch.setattr(
        "src.server.database.api_keys.is_byok_active", AsyncMock(return_value=True)
    )
    monkeypatch.setattr("src.server.services.llm.config.resolve_llm_config", resolve)

    result = await education_teaching_jobs.resolve_managed_teaching_agent_config(
        parent_user_id="parent-1"
    )

    assert result is resolved_config
    resolved_config.get_llm_client.assert_called_once_with()
    resolve.assert_awaited_once_with(
        base_config=base_config,
        user_id="parent-1",
        request_model=None,
        is_byok=True,
        mode="ptc",
        enabled_subagents=[],
    )
