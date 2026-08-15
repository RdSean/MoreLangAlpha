"""Managed teaching-job orchestration kept outside public chat routes."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Mapping
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
import re
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

from ptc_agent.agent.graph import build_ptc_graph_with_session
from ptc_agent.agent.managed_execution import (
    ManagedExecutionPolicy,
)
from src.config.settings import (
    get_education_teaching_workflow_timeout,
    get_ptc_recursion_limit,
)
from src.server.database.education_textbooks import (
    mark_teaching_job_cancel_requested,
    record_teaching_event,
    settle_teaching_attempt,
    touch_teaching_attempt,
)
from src.server.database.runs.lifecycle import QuerySpec
from src.server.services.runs.coordinator import RunCoordinator
from src.server.services.runs.executor import LocalRunExecutor
from src.server.services.runs.sse_producer import RunSSEProducer
from src.server.services.education_teaching_assets import expected_teaching_asset_paths


logger = logging.getLogger(__name__)

_MANAGED_KIND = "education_teaching"
_PROGRESS_PREFIX = "EDUCATION_PROGRESS "
_PROGRESS_PHASES = frozenset(
    {
        "planning",
        "chapter_mapping",
        "concept_linking",
        "coverage_audit",
        "practice_build",
        "teaching_build",
        "bundle_assembling",
        "validating_bundle",
        # Existing in-flight v1 attempts remain readable until they finish.
        "building_skill",
        "generating_teaching",
    }
)
_PROGRESS_ASSET_KINDS = frozenset({"knowledge", "toolkit", "practice", "teaching"})
_PROGRESS_LABELS = {
    "planning": "正在规划知识资产加工",
    "chapter_mapping": "已完成章节映射",
    "concept_linking": "已完成概念关联",
    "coverage_audit": "已完成覆盖审计",
    "practice_build": "已完成练习构建",
    "teaching_build": "已完成教学材料生成",
    "bundle_assembling": "正在汇总教材资产",
    "validating_bundle": "正在校验教材资产",
    "building_skill": "已完成知识整理",
    "generating_teaching": "已完成教学材料生成",
}
_PROGRESS_RE = re.compile(r"EDUCATION_PROGRESS\s+(\{[^\r\n]+\})")
_HEARTBEAT_INTERVAL_SECONDS = 15.0


@dataclass
class ManagedTeachingAssetProgress:
    """Turn successful fixed-path candidate writes into safe durable milestones.

    This observes the already-authorized Write tool boundary. It neither directs
    the PTC's order of work nor reads candidate contents; the path-to-milestone
    map comes solely from the frozen service manifest.
    """

    attempt_id: str
    filesystem_root: str
    staged: Mapping[str, Any]
    _events_by_path: dict[str, tuple[str, str | None, str | None]] = field(
        init=False, default_factory=dict
    )
    _emitted_paths: set[str] = field(init=False, default_factory=set)
    _pending: set[asyncio.Task[None]] = field(init=False, default_factory=set)

    def __post_init__(self) -> None:
        paths = expected_teaching_asset_paths(
            {"chapters": list(self.staged.get("chapters", []))}
        )
        self._events_by_path = {
            f"{self.filesystem_root}/{paths.concept_index}": (
                "concept_linking",
                None,
                "knowledge",
            ),
            f"{self.filesystem_root}/{paths.coverage_audit}": (
                "coverage_audit",
                None,
                None,
            ),
            f"{self.filesystem_root}/{paths.teaching_package}": (
                "bundle_assembling",
                None,
                None,
            ),
        }
        for chapter in self.staged.get("chapters", []):
            if not isinstance(chapter, Mapping):
                continue
            chapter_id = chapter.get("content_chapter_id")
            if not isinstance(chapter_id, str):
                continue
            chapter_paths = paths.for_chapter(chapter_id)
            self._events_by_path.update(
                {
                    f"{self.filesystem_root}/{chapter_paths.knowledge}": (
                        "concept_linking",
                        chapter_id,
                        "knowledge",
                    ),
                    f"{self.filesystem_root}/{chapter_paths.toolkit}": (
                        "teaching_build",
                        chapter_id,
                        "toolkit",
                    ),
                    f"{self.filesystem_root}/{chapter_paths.practice}": (
                        "practice_build",
                        chapter_id,
                        "practice",
                    ),
                }
            )

    def __call__(self, operation: Mapping[str, Any]) -> None:
        if operation.get("operation") != "write_file":
            return
        path = operation.get("file_path")
        if not isinstance(path, str) or path in self._emitted_paths:
            return
        event = self._events_by_path.get(path)
        if event is None:
            return
        self._emitted_paths.add(path)
        task = asyncio.create_task(self._record(*event))
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)

    async def _record(
        self, phase: str, chapter_id: str | None, asset_kind: str | None
    ) -> None:
        label = _PROGRESS_LABELS[phase]
        summary = (
            f"Agent 已报告：第 {self._position_for(chapter_id)} 章{label}"
            if chapter_id is not None
            else f"Agent 已报告：{label}"
        )
        try:
            await record_teaching_event(
                attempt_id=self.attempt_id,
                phase=phase,
                chapter_id=chapter_id,
                asset_kind=asset_kind,
                summary=summary,
            )
        except Exception:
            logger.warning(
                "Could not record managed teaching output milestone", exc_info=True
            )

    def _position_for(self, chapter_id: str) -> int:
        for chapter in self.staged.get("chapters", []):
            if (
                isinstance(chapter, Mapping)
                and chapter.get("content_chapter_id") == chapter_id
            ):
                return int(chapter["position"])
        raise ValueError("Managed teaching event chapter is not frozen")

    async def drain(self) -> None:
        while self._pending:
            await asyncio.gather(*tuple(self._pending), return_exceptions=True)


def managed_teaching_prompt(job_id: str) -> str:
    """Describe immutable service facts without deciding the Skill sequence."""
    root = f"/managed/textbook-job/{job_id}"
    return (
        "这是服务托管的家庭教材知识资产任务，不是与用户的对话。"
        f"任务编号为 {job_id}。冻结输入仅在 {root}/inputs/manifest.json 和 "
        f"{root}/inputs/chapters/。先按需读取 {root}/.agents/skills/book-to-skill/SKILL.md "
        f"和 {root}/.agents/skills/the-knowledge-guy/SKILL.md，并在需要具体输出合同时读取 "
        f"{root}/.agents/skills/book-to-skill/reference/managed-textbook-contract.md 与 "
        f"{root}/.agents/skills/the-knowledge-guy/reference/managed-textbook-contract.md。"
        "由你自主决定章节映射、概念关联、覆盖回查、练习构建和中文教学材料的顺序；"
        "不要询问用户、访问网络、MCP、Vault 或普通工作区，也不要发布或暴露任何资产。"
        "只写受管合同列出的 v2 固定输出；在真实工作单元完成后写安全的 EDUCATION_PROGRESS 里程碑。"
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
        asset_kind = progress.get("asset_kind")
        if phase not in _PROGRESS_PHASES:
            continue
        if asset_kind is not None and asset_kind not in _PROGRESS_ASSET_KINDS:
            continue
        position: int | None = None
        if chapter_id is not None:
            if not isinstance(chapter_id, str):
                continue
            try:
                UUID(chapter_id)
            except ValueError:
                continue
            position = chapter_positions.get(chapter_id)
            if position is None:
                continue
        label = _PROGRESS_LABELS[phase]
        summary = (
            f"Agent 已报告：第 {position} 章{label}"
            if position is not None
            else f"Agent 已报告：{label}"
        )
        try:
            await record_teaching_event(
                attempt_id=attempt_id,
                phase=phase,
                chapter_id=chapter_id,
                asset_kind=asset_kind,
                summary=summary,
            )
        except Exception:
            # Product-progress persistence is deliberately best effort. A
            # transient event-row failure must not interrupt a validated root
            # run; terminal projection still records the outcome.
            logger.warning("Could not record managed teaching progress", exc_info=True)


async def _managed_workflow_events(
    workflow: AsyncGenerator[str, None],
    *,
    attempt_id: str,
    root_run_id: str,
    staged: Mapping[str, Any],
) -> AsyncGenerator[str, None]:
    """Project progress while keeping a durable heartbeat during model waits."""

    async def touch() -> None:
        try:
            await touch_teaching_attempt(attempt_id=attempt_id, root_run_id=root_run_id)
        except Exception:
            # A heartbeat is observability only. A transient DB failure must not
            # interrupt an otherwise valid managed root run.
            logger.warning(
                "Could not refresh managed teaching heartbeat", exc_info=True
            )

    iterator = workflow.__aiter__()
    pending_event: asyncio.Task[str] | None = None
    last_heartbeat_at = monotonic()
    await touch()
    try:
        pending_event = asyncio.create_task(anext(iterator))
        while True:
            done, _pending = await asyncio.wait(
                {pending_event}, timeout=_HEARTBEAT_INTERVAL_SECONDS
            )
            if not done:
                await touch()
                last_heartbeat_at = monotonic()
                continue
            try:
                event = pending_event.result()
            except StopAsyncIteration:
                break
            await _record_safe_progress(
                attempt_id=attempt_id, staged=staged, event=event
            )
            now = monotonic()
            if now - last_heartbeat_at >= _HEARTBEAT_INTERVAL_SECONDS:
                await touch()
                last_heartbeat_at = now
            yield event
            pending_event = asyncio.create_task(anext(iterator))
    finally:
        if pending_event is not None and not pending_event.done():
            pending_event.cancel()
            with suppress(asyncio.CancelledError):
                await pending_event


async def build_managed_teaching_graph(
    *,
    session: Any,
    thread_id: str,
    run_handle: Any,
    policy: ManagedExecutionPolicy,
    agent_config: Any | None = None,
    operation_callback: Any | None = None,
) -> tuple[Any, dict[str, Any], dict[str, Any]]:
    """Build the constrained graph and its fixed input/configuration.

    This is intentionally separate from ``astream_ptc_workflow``: the latter
    accepts a public ``ChatRequest`` and owns user-facing admission semantics.
    The managed root already owns a durable run row and has no caller supplied
    prompt, identity, context or optional tools.
    """
    from src.server.app import setup

    config = agent_config or setup.agent_config
    if config is None:
        raise RuntimeError("PTC Agent is not initialized")
    job_id = str(UUID(policy.filesystem_root.rsplit("/", 1)[-1]))
    graph = await build_ptc_graph_with_session(
        session=session,
        operation_callback=operation_callback,
        config=config,
        subagent_names=["textbook-chapter-worker"] if policy.allow_subagents else [],
        disable_subagents=not policy.allow_subagents,
        checkpointer=run_handle.checkpointer,
        background_registry=None,
        # Built-in workers write to task:<id> through the same fenced saver as
        # the root run. This is a service-side write lease, not parent state.
        namespace_owner=run_handle.guard if policy.allow_subagents else None,
        user_id=None,
        plan_mode=False,
        thread_id=thread_id,
        store=None,
        on_signed_url=None,
        managed_policy=policy,
    )
    graph_config: dict[str, Any] = {
        "configurable": {
            "thread_id": thread_id,
            "agent_mode": "ptc",
            "managed_execution": {"kind": _MANAGED_KIND, "job_id": job_id},
        },
        # Teaching packages can span many chapters. Their durable root run
        # must use the configured operational limit rather than chat's former
        # short-turn cap, while cancellation and heartbeats remain shared.
        "recursion_limit": get_ptc_recursion_limit(),
        "tags": ["managed", "education", "teaching"],
        "metadata": {
            "managed_execution": {"kind": _MANAGED_KIND, "job_id": job_id},
            "run_id": run_handle.run_id,
            "turn_index": run_handle.turn_index,
        },
        "run_id": run_handle.run_id,
    }
    input_state = {
        "messages": [{"role": "user", "content": managed_teaching_prompt(job_id)}],
        "current_agent": "ptc",
    }
    return graph, input_state, graph_config


async def resolve_managed_teaching_agent_config(*, parent_user_id: str) -> Any:
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
    agent_config: Any | None = None,
    **_ignored: Any,
) -> dict[str, str]:
    """Persist and start one service-owned root run through the shared spine."""
    job_id = str(UUID(str(job["job_id"])))
    run_id = str(uuid4())
    run_handle = await RunCoordinator.get_instance().start_run(
        thread_id=thread_id,
        run_id=run_id,
        msg_type="ptc",
        request_key=run_id,
        workspace_id=workspace_id,
        user_id=None,
        query=QuerySpec(
            query_id=str(uuid4()),
            content=managed_teaching_prompt(job_id),
            query_type="system",
            metadata={"managed_execution": {"kind": _MANAGED_KIND, "job_id": job_id}},
            created_at=datetime.now(),
        ),
        run_metadata={
            "managed_execution": {"kind": _MANAGED_KIND, "job_id": job_id},
            "suppress_lifecycle_hooks": True,
        },
    )
    try:
        progress = ManagedTeachingAssetProgress(
            attempt_id=attempt_id,
            filesystem_root=policy.filesystem_root,
            staged=staged,
        )
        graph, input_state, graph_config = await build_managed_teaching_graph(
            session=session,
            thread_id=thread_id,
            run_handle=run_handle,
            policy=policy,
            agent_config=agent_config,
            operation_callback=progress,
        )
        attempt = await settle_teaching_attempt(
            attempt_id=attempt_id, root_run_id=run_id, status="running"
        )
        if attempt is None:
            raise RuntimeError("Managed teaching attempt could not enter running state")

        handler = RunSSEProducer(
            thread_id=thread_id,
            run_id=run_id,
            workflow_timeout=get_education_teaching_workflow_timeout(),
        )

        async def on_terminal(task_info: Any, status: str) -> None:
            from src.server.services.education_managed_ptc import (
                finalize_teaching_attempt,
            )

            await progress.drain()
            await finalize_teaching_attempt(
                job=job,
                attempt_id=attempt_id,
                root_run_id=run_id,
                sandbox=session.sandbox,
                terminal_status=status,
                terminal_error=getattr(task_info, "error", None),
            )

        workflow = _managed_workflow_events(
            handler.stream_workflow(
                graph=graph, input_state=input_state, config=graph_config
            ),
            attempt_id=attempt_id,
            root_run_id=run_id,
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
