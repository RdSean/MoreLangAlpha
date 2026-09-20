"""Managed generation of reviewable textbook structures."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Mapping
from contextlib import suppress
from datetime import datetime
import logging
from time import monotonic
from typing import Any
from uuid import UUID, uuid4

from ptc_agent.agent.managed_execution import education_structure_policy
from src.config.settings import (
    get_education_teaching_workflow_timeout,
    get_ptc_recursion_limit,
)
from src.server.database.conversation import create_thread
from src.server.database.education_textbooks import (
    claim_generation_job,
    complete_structure_generation,
    fail_structure_generation,
    get_generation_job_for_parent,
    get_teaching_input_for_parent,
    mark_generation_attempt_running,
    queue_textbook_structure,
    replace_structure_contents,
    touch_generation_attempt,
)
from src.server.database.runs.lifecycle import QuerySpec
from src.server.database.workspace import create_workspace
from src.server.services.education_structure_validation import (
    TextbookStructureValidationError,
    validate_textbook_structure,
)
from src.server.services.education_processing_profiles import (
    processing_profile_prompt,
    resolve_processing_profile,
)
from src.server.services.education_managed_runs import (
    build_managed_education_graph,
    resolve_managed_education_agent_config,
)
from src.server.services.education_teaching_storage import (
    build_staged_teaching_input,
    download_structure_output,
    hydrate_source_asset_manifests,
    stage_managed_teaching_skills,
    stage_teaching_inputs,
    structure_bundle_prefix,
    write_structure_bundle,
)
from src.server.services.runs.coordinator import RunCoordinator
from src.server.services.runs.executor import LocalRunExecutor
from src.server.services.runs.sse_producer import RunSSEProducer
from src.server.services.workspace_manager import WorkspaceManager
from src.server.utils.error_sanitization import sanitize_error_text


logger = logging.getLogger(__name__)

_MANAGED_KIND = "education_structure"
_HEARTBEAT_INTERVAL_SECONDS = 15.0
def managed_structure_prompt(
    job_id: str, profile: Mapping[str, Any] | None = None
) -> str:
    """Describe a non-interactive structure-only managed run."""
    root = f"/managed/textbook-job/{UUID(job_id)}"
    return (
        "这是服务托管的教材结构分析任务，不是与用户的对话或课程生成任务。"
        f"任务编号为 {job_id}。冻结输入位于 {root}/inputs/manifest.json 与 "
        f"{root}/inputs/sources/；被 Markdown 引用的图片位于 "
        f"{root}/inputs/assets/。解析器不保证标准 Unit/TOC 边界。"
        f"先读取 {root}/.agents/skills/book-to-skill/SKILL.md，再按需读取 "
        f"{root}/.agents/skills/book-to-skill/reference/managed-textbook-contract.md 中的结构模式。"
        "识别教学 Unit、前言/目录/附录等非教学单元，并为每个 Unit 和知识点尽量写出来源 quote。"
        "不要计算 position、slug、行号、字符偏移、PDF 页码或坐标；这些由服务端生成。"
        "非教学单元可以没有知识点；教学单元在真实内容不足时也可以暂时为空。"
        "不得为了满足数量、格式或进度而编造知识点。"
        f"只写 {root}/outputs/structure.json，输出格式必须是 "
        "langalpha-managed-textbook-structure/v1。不要生成课程、练习或教学包。"
        "不要访问网络、MCP、Vault、普通工作区或发布任何资产。"
        + (
            "\n\n" + processing_profile_prompt(profile)
            if profile
            else ""
        )
    )


async def queue_structure_generation_for_parent(
    *,
    parent_user_id: str,
    content_version_id: str,
    profile_input: Mapping[str, Any] | None = None,
    profile_id: str | None = None,
) -> dict[str, Any]:
    """Freeze one content version and create its structure generation job."""
    generation_job_id = str(uuid4())
    frozen_input = await get_teaching_input_for_parent(
        parent_user_id=parent_user_id,
        content_version_id=content_version_id,
    )
    if not frozen_input:
        raise LookupError("Reviewable textbook content version not found")
    frozen_input = await hydrate_source_asset_manifests(frozen_input)
    profile = await resolve_processing_profile(
        parent_user_id=parent_user_id,
        version_id=content_version_id,
        profile_input=profile_input,
        profile_id=profile_id,
    )
    frozen_input = dict(frozen_input)
    frozen_input["job_id"] = generation_job_id
    staged = build_staged_teaching_input(frozen_input)
    queued = await queue_textbook_structure(
        parent_user_id=parent_user_id,
        content_version_id=content_version_id,
        processing_profile_id=str(profile["profile_id"]),
        processing_profile_sha256=str(profile["profile_sha256"]),
        input_manifest_sha256=staged["manifest_sha256"],
        source_revision=staged["manifest_sha256"],
        generation_job_id=generation_job_id,
    )
    if queued is None:
        raise LookupError("Reviewable textbook content version not found")
    return queued


async def create_generation_workspace(
    *, parent_user_id: str, job_id: str
) -> dict[str, Any]:
    return await create_workspace(
        user_id=parent_user_id,
        name="家庭教材结构分析",
        description="service-owned managed education structure execution",
        config={
            "managed_execution": {
                "kind": _MANAGED_KIND,
                "job_id": job_id,
            }
        },
        status="creating",
    )


async def create_generation_thread(
    *, job_id: str, workspace_id: str
) -> dict[str, Any]:
    return await create_thread(
        conversation_thread_id=str(uuid4()),
        workspace_id=workspace_id,
        current_status="completed",
        msg_type="ptc",
        title="家庭教材结构分析",
        platform="education",
        metadata={
            "managed_execution": {
                "kind": _MANAGED_KIND,
                "job_id": job_id,
            }
        },
    )


async def managed_generation_workflow_events(
    workflow: AsyncGenerator[str, None],
    *,
    generation_job_id: str,
    attempt_id: str,
    root_run_id: str,
) -> AsyncGenerator[str, None]:
    async def touch() -> None:
        try:
            await touch_generation_attempt(
                generation_job_id=generation_job_id,
                attempt_id=attempt_id,
                root_run_id=root_run_id,
            )
        except Exception:
            logger.warning(
                "Could not refresh managed structure heartbeat",
                exc_info=True,
            )

    iterator = workflow.__aiter__()
    pending_event: asyncio.Task[str] | None = None
    last_heartbeat_at = monotonic()
    await touch()
    try:
        pending_event = asyncio.create_task(anext(iterator))
        while True:
            done, _pending = await asyncio.wait(
                {pending_event},
                timeout=_HEARTBEAT_INTERVAL_SECONDS,
            )
            if not done:
                await touch()
                last_heartbeat_at = monotonic()
                continue
            try:
                event = pending_event.result()
            except StopAsyncIteration:
                break
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


async def _fail_structure_attempt(
    *,
    job: Mapping[str, Any],
    attempt_id: str,
    status: str,
    error_code: str,
    error_message: str | None,
) -> dict[str, Any] | None:
    return await fail_structure_generation(
        generation_job_id=str(job["generation_job_id"]),
        attempt_id=attempt_id,
        structure_id=str(job["structure_id"]),
        status=status,
        error_code=error_code,
        error_message=(
            sanitize_error_text(error_message)
            if error_message is not None
            else None
        ),
    )


async def finalize_structure_generation(
    *,
    job: Mapping[str, Any],
    frozen_input: Mapping[str, Any],
    attempt_id: str,
    root_run_id: str,
    sandbox: Any,
    terminal_status: str,
    terminal_error: str | None,
) -> dict[str, Any] | None:
    """Validate and persist one completed structure candidate."""
    del root_run_id
    if terminal_status != "completed":
        status = "cancelled" if terminal_status == "cancelled" else "failed"
        return await _fail_structure_attempt(
            job=job,
            attempt_id=attempt_id,
            status=status,
            error_code=(
                "managed_structure_cancelled"
                if status == "cancelled"
                else "managed_structure_failed"
            ),
            error_message=(
                None
                if status == "cancelled"
                else "教材结构分析未能完成，请重新运行。"
            ),
        )
    try:
        candidate = await download_structure_output(
            str(job["generation_job_id"]),
            sandbox,
        )
        validated = validate_textbook_structure(candidate, frozen_input)
        await replace_structure_contents(
            structure_id=str(job["structure_id"]),
            units=validated["units"],
            warnings=list(validated.get("warnings", [])),
        )
        bundle_prefix = await write_structure_bundle(job, validated)
        completed = await complete_structure_generation(
            generation_job_id=str(job["generation_job_id"]),
            attempt_id=attempt_id,
            structure_id=str(job["structure_id"]),
            bundle_prefix=bundle_prefix,
        )
        if completed is None:
            raise RuntimeError("Structure completion lost its active attempt")
        return completed
    except TextbookStructureValidationError:
        return await _fail_structure_attempt(
            job=job,
            attempt_id=attempt_id,
            status="failed",
            error_code="managed_structure_invalid",
            error_message="教材结构分析结果不完整或格式无效，请重新运行。",
        )
    except Exception:
        logger.exception("Managed textbook structure finalization failed")
        return await _fail_structure_attempt(
            job=job,
            attempt_id=attempt_id,
            status="failed",
            error_code="managed_structure_archive_failed",
            error_message="教材结构资产归档失败，请稍后重新运行。",
        )


async def _dispatch_structure_root_run(
    *,
    parent_user_id: str,
    job: Mapping[str, Any],
    frozen_input: Mapping[str, Any],
    attempt_id: str,
    session: Any,
    workspace_id: str,
    thread_id: str,
    agent_config: Any,
) -> dict[str, str]:
    del parent_user_id
    generation_job_id = str(job["generation_job_id"])
    run_id = str(uuid4())
    profile = (
        {
            "profile_id": job.get("processing_profile_id"),
            "subject": job.get("processing_profile_subject"),
            "grade_band": job.get("processing_profile_grade_band"),
            "language": job.get("processing_profile_language"),
            "depth": job.get("processing_profile_depth"),
            "question_types": job.get("processing_profile_question_types"),
            "prompt_fragment": job.get("processing_profile_prompt_fragment"),
            "allowed_skills": job.get("processing_profile_allowed_skills"),
        }
        if job.get("processing_profile_id")
        else None
    )
    prompt = managed_structure_prompt(generation_job_id, profile)
    run_handle = await RunCoordinator.get_instance().start_run(
        thread_id=thread_id,
        run_id=run_id,
        msg_type="ptc",
        request_key=run_id,
        workspace_id=workspace_id,
        user_id=None,
        query=QuerySpec(
            query_id=str(uuid4()),
            content=prompt,
            query_type="system",
            metadata={
                "managed_execution": {
                    "kind": _MANAGED_KIND,
                    "job_id": generation_job_id,
                }
            },
            created_at=datetime.now(),
        ),
        run_metadata={
            "managed_execution": {
                "kind": _MANAGED_KIND,
                "job_id": generation_job_id,
            },
            "suppress_lifecycle_hooks": True,
        },
    )
    try:
        graph, input_state, graph_config = await build_managed_education_graph(
            session=session,
            thread_id=thread_id,
            run_handle=run_handle,
            policy=education_structure_policy(generation_job_id),
            agent_config=agent_config,
            prompt=prompt,
            tags=("managed", "education", "structure"),
            managed_kind=_MANAGED_KIND,
        )
        graph_config["recursion_limit"] = get_ptc_recursion_limit()
        running = await mark_generation_attempt_running(
            generation_job_id=generation_job_id,
            attempt_id=attempt_id,
            root_run_id=run_id,
        )
        if running is None:
            raise RuntimeError("Generation attempt could not enter running state")

        handler = RunSSEProducer(
            thread_id=thread_id,
            run_id=run_id,
            workflow_timeout=get_education_teaching_workflow_timeout(),
        )

        async def on_terminal(task_info: Any, status: str) -> None:
            await finalize_structure_generation(
                job=job,
                frozen_input=frozen_input,
                attempt_id=attempt_id,
                root_run_id=run_id,
                sandbox=session.sandbox,
                terminal_status=status,
                terminal_error=getattr(task_info, "error", None),
            )

        workflow = managed_generation_workflow_events(
            handler.stream_workflow(
                graph=graph,
                input_state=input_state,
                config=graph_config,
            ),
            generation_job_id=generation_job_id,
            attempt_id=attempt_id,
            root_run_id=run_id,
        )
        await LocalRunExecutor.get_instance().start_run(
            thread_id=thread_id,
            run_id=run_id,
            workflow_generator=workflow,
            metadata={
                "workspace_id": workspace_id,
                "managed_execution": {
                    "kind": _MANAGED_KIND,
                    "job_id": generation_job_id,
                },
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
        await RunCoordinator.get_instance().fail_open_run(
            run_handle,
            str(exc),
            status="error",
        )
        await _fail_structure_attempt(
            job=job,
            attempt_id=attempt_id,
            status="failed",
            error_code="managed_structure_start_failed",
            error_message="教材结构分析无法启动，请稍后重试。",
        )
        raise
    return {"root_run_id": run_id}


async def launch_structure_generation(
    *, parent_user_id: str, generation_job_id: str
) -> dict[str, str]:
    """Launch one parent-owned, recoverable structure generation attempt."""
    job = await get_generation_job_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    if not job:
        raise LookupError("Textbook structure generation job not found")
    if job.get("scope") != "structure" or job.get("status") != "queued":
        raise RuntimeError("Textbook structure generation job cannot start")
    generation_job_id = str(job["generation_job_id"])
    workspace = await create_generation_workspace(
        parent_user_id=parent_user_id,
        job_id=generation_job_id,
    )
    workspace_id = str(workspace["workspace_id"])
    thread = await create_generation_thread(
        job_id=generation_job_id,
        workspace_id=workspace_id,
    )
    thread_id = str(thread["conversation_thread_id"])
    attempt = await claim_generation_job(
        generation_job_id=generation_job_id,
        managed_workspace_id=workspace_id,
        managed_thread_id=thread_id,
    )
    if not attempt:
        raise RuntimeError("Textbook structure generation job was claimed")
    attempt_id = str(attempt["attempt_id"])
    try:
        agent_config = await resolve_managed_education_agent_config(
            parent_user_id=parent_user_id
        )
    except BaseException:
        await _fail_structure_attempt(
            job=job,
            attempt_id=attempt_id,
            status="failed",
            error_code="managed_model_unavailable",
            error_message="教材结构分析需要先配置模型服务，再继续运行。",
        )
        raise

    policy = education_structure_policy(generation_job_id)
    try:
        session = await WorkspaceManager.get_instance().provision_managed_textbook_session(
            workspace_id=workspace_id,
            policy=policy,
        )
    except BaseException:
        await _fail_structure_attempt(
            job=job,
            attempt_id=attempt_id,
            status="failed",
            error_code="managed_sandbox_unavailable",
            error_message="教材结构分析环境无法启动，请重新运行。",
        )
        raise

    frozen_input = await get_teaching_input_for_parent(
        parent_user_id=parent_user_id,
        content_version_id=str(job["version_id"]),
    )
    if not frozen_input:
        await _fail_structure_attempt(
            job=job,
            attempt_id=attempt_id,
            status="failed",
            error_code="managed_structure_input_unavailable",
            error_message="教材结构分析输入已不可用，请重新开始。",
        )
        raise LookupError("Textbook structure input is unavailable")
    frozen_input = await hydrate_source_asset_manifests(frozen_input)
    frozen_input = dict(frozen_input)
    frozen_input["job_id"] = generation_job_id
    try:
        await stage_managed_teaching_skills(
            generation_job_id,
            session.sandbox,
            skill_names=("book-to-skill",),
        )
        await stage_teaching_inputs(frozen_input, session.sandbox)
        return await _dispatch_structure_root_run(
            parent_user_id=parent_user_id,
            job=job,
            frozen_input=frozen_input,
            attempt_id=attempt_id,
            session=session,
            workspace_id=workspace_id,
            thread_id=thread_id,
            agent_config=agent_config,
        )
    except BaseException:
        await _fail_structure_attempt(
            job=job,
            attempt_id=attempt_id,
            status="failed",
            error_code="managed_structure_staging_failed",
            error_message="教材结构分析准备失败，请重新运行。",
        )
        raise


async def get_structure_generation_job_for_parent(
    *, parent_user_id: str, generation_job_id: str
) -> dict[str, Any] | None:
    """Return the safe internal projection used by structure APIs."""
    job = await get_generation_job_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    if not job:
        return None
    return {
        key: job.get(key)
        for key in (
            "generation_job_id",
            "version_id",
            "scope",
            "structure_id",
            "status",
            "attempt_count",
            "error_code",
            "error_message",
            "created_at",
            "updated_at",
            "structure_sequence",
            "structure_status",
            "structure_bundle_prefix",
        )
    }


def expected_structure_bundle_prefix(job: Mapping[str, Any]) -> str:
    """Expose the deterministic archive prefix for tests and diagnostics."""
    return structure_bundle_prefix(job)
