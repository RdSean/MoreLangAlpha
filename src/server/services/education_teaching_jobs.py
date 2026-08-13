"""Managed teaching-job orchestration kept outside public chat routes."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping
from datetime import datetime
import json
import logging
from pathlib import Path
import re
from typing import Any
from uuid import UUID, uuid4

from ptc_agent.agent.graph import build_ptc_graph_with_session
from ptc_agent.agent.managed_execution import (
    ManagedExecutionPolicy,
)
from src.config.settings import get_ptc_recursion_limit
from src.server.database.education_textbooks import (
    mark_teaching_job_cancel_requested,
    record_teaching_event,
    settle_teaching_attempt,
)
from src.server.database.runs.lifecycle import QuerySpec
from src.server.services.runs.coordinator import RunCoordinator
from src.server.services.runs.executor import LocalRunExecutor
from src.server.services.runs.sse_producer import RunSSEProducer


logger = logging.getLogger(__name__)

_MANAGED_KIND = "education_teaching"
_PROGRESS_PREFIX = "EDUCATION_PROGRESS "
_PROGRESS_PHASES = frozenset({"building_skill", "generating_teaching"})
_PROGRESS_RE = re.compile(r"EDUCATION_PROGRESS\s+(\{[^\r\n]+\})")


def _managed_prompt(job_id: str) -> str:
    """Return the only instruction accepted by the service-owned root run."""
    return (
        "这是服务托管的家庭教材教学包任务，不是与用户的对话。"
        f"任务编号为 {job_id}。严格按以下顺序完成：\n"
        f"1. 执行 book-to-skill --managed-textbook {job_id}，只处理已冻结的 Markdown。\n"
        f"2. 在其成功后执行 the-knowledge-guy --managed-textbook {job_id}，"
        "为中国学生生成教学材料和可自动判定题集。\n"
        "不得提问、不得访问网络、不得调用其他技能或子代理、不得处理普通工作区文件。"
        "只可在已指定的受管任务目录工作；最终只写入 contract 指定的候选 JSON。"
    )


def _extract_progress_payloads(event: str) -> list[dict[str, Any]]:
    """Parse only explicit progress records from an SSE frame.

    The teaching database never stores raw model text or raw SSE payload. This
    helper accepts a progress record only when it occurs in a string field of a
    syntactically valid SSE JSON frame, and later callers whitelist its fields.
    """
    strings = [event]
    if event.startswith("data: "):
        try:
            payload = json.loads(event.split("data: ", 1)[1].split("\n", 1)[0])
        except json.JSONDecodeError:
            payload = None

        def collect(value: object) -> None:
            if isinstance(value, str):
                strings.append(value)
            elif isinstance(value, dict):
                for child in value.values():
                    collect(child)
            elif isinstance(value, list):
                for child in value:
                    collect(child)

        collect(payload)

    results: list[dict[str, Any]] = []
    for text in strings:
        for match in _PROGRESS_RE.finditer(text):
            try:
                decoded = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
            if isinstance(decoded, dict):
                results.append(decoded)
    return results


async def _record_safe_progress(
    *, attempt_id: str, staged: Mapping[str, Any], event: str
) -> None:
    """Persist a product projection of a valid managed progress record only."""
    chapter_positions = {
        str(chapter["content_chapter_id"]): int(chapter["position"])
        for chapter in staged.get("chapters", [])
        if isinstance(chapter, Mapping)
        and isinstance(chapter.get("position"), int)
        and chapter.get("content_chapter_id")
    }
    for progress in _extract_progress_payloads(event):
        phase = progress.get("phase")
        chapter_id = progress.get("content_chapter_id")
        if phase not in _PROGRESS_PHASES or not isinstance(chapter_id, str):
            continue
        try:
            UUID(chapter_id)
        except ValueError:
            continue
        position = chapter_positions.get(chapter_id)
        if position is None:
            continue
        summary = (
            f"已完成第 {position} 章知识整理"
            if phase == "building_skill"
            else f"已完成第 {position} 章教学材料生成"
        )
        try:
            await record_teaching_event(
                attempt_id=attempt_id,
                phase=phase,
                chapter_id=chapter_id,
                summary=summary,
            )
        except Exception:
            # Product-progress persistence is deliberately best effort. A
            # transient event-row failure must not interrupt a validated root
            # run; terminal projection still records the outcome.
            logger.warning("Could not record managed teaching progress", exc_info=True)


async def _managed_workflow_events(
    workflow: AsyncGenerator[str, None], *, attempt_id: str, staged: Mapping[str, Any]
) -> AsyncGenerator[str, None]:
    async for event in workflow:
        await _record_safe_progress(attempt_id=attempt_id, staged=staged, event=event)
        yield event


async def build_managed_teaching_graph(
    *,
    session: Any,
    thread_id: str,
    run_handle: Any,
    policy: ManagedExecutionPolicy,
    skill_contexts: list[dict[str, str]],
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Build the constrained graph and its fixed input/configuration.

    This is intentionally separate from ``astream_ptc_workflow``: the latter
    accepts a public ``ChatRequest`` and owns user-facing admission semantics.
    The managed root already owns a durable run row and has no caller supplied
    prompt, identity, context or optional tools.
    """
    from src.server.app import setup

    if setup.agent_config is None:
        raise RuntimeError("PTC Agent is not initialized")
    job_id = str(UUID(policy.filesystem_root.rsplit("/", 1)[-1]))
    graph = await build_ptc_graph_with_session(
        session=session,
        config=setup.agent_config,
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
        managed_policy=policy,
    )
    # Skill bodies are injected by ``SkillsMiddleware`` from the server process,
    # so this must be the checked-in built-in catalog rather than the sandbox
    # path. The staged sandbox copies remain the only files discoverable and
    # executable from within the managed job.
    managed_skill_source = str(Path(__file__).resolve().parents[3] / "skills")
    graph_config: dict[str, Any] = {
        "configurable": {
            "thread_id": thread_id,
            "agent_mode": "ptc",
            "managed_execution": {"kind": _MANAGED_KIND, "job_id": job_id},
            "skill_contexts": skill_contexts,
            "skill_dirs": [managed_skill_source],
        },
        "recursion_limit": min(get_ptc_recursion_limit(), 48),
        "tags": ["managed", "education", "teaching"],
        "metadata": {
            "managed_execution": {"kind": _MANAGED_KIND, "job_id": job_id},
            "run_id": run_handle.run_id,
            "turn_index": run_handle.turn_index,
        },
        "run_id": run_handle.run_id,
    }
    input_state = {
        "messages": [{"role": "user", "content": _managed_prompt(job_id)}],
        "current_agent": "ptc",
    }
    return graph, input_state, graph_config


async def request_root_run_cancel(*, thread_id: str, run_id: str) -> None:
    """Use the shared durable PTC cancellation mechanism for a root run."""
    from src.server.services.cancel_dispatch import cancel_workflow

    await cancel_workflow(thread_id, run_id)


async def cancel_teaching_job(*, parent_user_id: str, job_id: str) -> None:
    """Record the product-level stop intent before touching the PTC executor."""
    job = await mark_teaching_job_cancel_requested(
        parent_user_id=parent_user_id, job_id=job_id
    )
    if not job:
        raise LookupError("Teaching job not found or cannot be cancelled")
    thread_id = job.get("managed_thread_id")
    run_id = job.get("root_run_id")
    if thread_id and run_id:
        await request_root_run_cancel(thread_id=str(thread_id), run_id=str(run_id))


async def dispatch_managed_root_run(
    *,
    job: Mapping[str, Any],
    attempt_id: str,
    session: Any,
    workspace_id: str,
    thread_id: str,
    staged: Mapping[str, Any],
    policy: ManagedExecutionPolicy,
    skill_contexts: list[dict[str, str]],
    **_ignored: Any,
) -> dict[str, str]:
    """Persist and start one service-owned root run through the shared spine."""
    job_id = str(UUID(str(job["job_id"])))
    run_id = str(uuid4())
    run_handle = await RunCoordinator.get_instance().start_run(
        thread_id=thread_id,
        run_id=run_id,
        msg_type="ptc",
        request_key=f"education-teaching:{attempt_id}:{run_id}",
        workspace_id=workspace_id,
        user_id=None,
        query=QuerySpec(
            query_id=str(uuid4()),
            content=_managed_prompt(job_id),
            query_type="managed_education",
            metadata={"managed_execution": {"kind": _MANAGED_KIND, "job_id": job_id}},
            created_at=datetime.now(),
        ),
        run_metadata={
            "managed_execution": {"kind": _MANAGED_KIND, "job_id": job_id},
            "suppress_lifecycle_hooks": True,
        },
    )
    try:
        graph, input_state, graph_config = await build_managed_teaching_graph(
            session=session,
            thread_id=thread_id,
            run_handle=run_handle,
            policy=policy,
            skill_contexts=skill_contexts,
        )
        attempt = await settle_teaching_attempt(
            attempt_id=attempt_id, root_run_id=run_id, status="running"
        )
        if attempt is None:
            raise RuntimeError("Managed teaching attempt could not enter running state")

        handler = RunSSEProducer(
            thread_id=thread_id,
            run_id=run_id,
        )

        async def on_terminal(task_info: Any, status: str) -> None:
            from src.server.services.education_managed_ptc import finalize_teaching_attempt

            await finalize_teaching_attempt(
                job=job,
                attempt_id=attempt_id,
                root_run_id=run_id,
                sandbox=session.sandbox,
                terminal_status=status,
                terminal_error=getattr(task_info, "error", None),
            )

        workflow = _managed_workflow_events(
            handler.stream_workflow(graph=graph, input_state=input_state, config=graph_config),
            attempt_id=attempt_id,
            staged=staged,
        )
        await LocalRunExecutor.get_instance().start_run(
            thread_id=thread_id,
            run_id=run_id,
            workflow_generator=workflow,
            metadata={
                "workspace_id": workspace_id,
                "managed_execution": {"kind": _MANAGED_KIND, "job_id": job_id},
                "started_at": datetime.now().isoformat(),
                "msg_type": "ptc",
                "handler": handler,
                "run_handle": run_handle,
            },
            completion_callback=None,
            terminal_callback=on_terminal,
            graph=graph,
        )
    except BaseException as exc:
        # After START, every failure still needs the regular root-run terminal
        # transition. The product attempt receives a sanitized failure through
        # its own terminal projection when the executor starts; pre-executor
        # failures need the direct running attempt settlement below.
        await RunCoordinator.get_instance().fail_open_run(
            run_handle, str(exc), status="error"
        )
        await settle_teaching_attempt(
            attempt_id=attempt_id,
            root_run_id=run_id,
            status="failed",
            error_code="managed_start_failed",
            error_message="教材教学加工无法启动，请稍后重试。",
        )
        raise
    return {"root_run_id": run_id}
