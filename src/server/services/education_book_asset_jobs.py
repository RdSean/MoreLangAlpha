"""Managed generation of optional book-to-skill chapter assets."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from ptc_agent.agent.managed_execution import education_book_policy
from src.config.settings import get_education_book_workflow_timeout
from src.server.database.conversation import create_thread
from src.server.database.education_textbooks import (
    claim_generation_job,
    complete_book_asset_generation,
    create_generation_job,
    get_generation_job_for_parent,
    get_teaching_input_for_parent,
    get_textbook_structure_for_parent,
    mark_generation_attempt_running,
    settle_generation_job,
)
from src.server.database.runs.lifecycle import QuerySpec
from src.server.database.workspace import create_workspace
from src.server.services.education_book_assets import BookAssetValidationError
from src.server.services.education_managed_runs import (
    build_managed_education_graph,
    resolve_managed_education_agent_config,
)
from src.server.services.education_structure_jobs import (
    managed_generation_workflow_events,
)
from src.server.services.education_teaching_storage import (
    download_book_asset_outputs,
    hydrate_source_asset_manifests,
    stage_reading_asset_inputs,
    stage_managed_teaching_skills,
    write_book_asset_bundle,
)
from src.server.services.runs.coordinator import RunCoordinator
from src.server.services.runs.executor import LocalRunExecutor
from src.server.services.runs.sse_producer import RunSSEProducer
from src.server.services.workspace_manager import WorkspaceManager
from src.server.utils.error_sanitization import sanitize_error_text


logger = logging.getLogger(__name__)
_MANAGED_KIND = "education_book"


def managed_book_assets_prompt(job_id: str) -> str:
    root = f"/managed/textbook-job/{UUID(job_id)}"
    return (
        "这是服务托管的教材知识包生成任务，不是与用户的对话或课程生成任务。"
        f"任务编号为 {job_id}。读取 {root}/inputs/readings_manifest.json、"
        f"{root}/inputs/readings/ 和 {root}/.agents/skills/book-to-skill/，"
        "使用 canonical book-to-skill 的 managed generate pass。"
        "manifest 中的每个 Reading 都必须独立处理：只读取它自己的 input_path，"
        "不得读取同书其他 Reading 的切片，也不得重新计算章节或行号边界。"
        "为每个 Reading 生成知识稿、词表和速查表三类内容。"
        "只写以下输出："
        f"{root}/outputs/readings_manifest.json；"
        f"{root}/outputs/readings/<unit-slug>/<slot>/knowledge.md；"
        f"{root}/outputs/readings/<unit-slug>/<slot>/glossary.md；"
        f"{root}/outputs/readings/<unit-slug>/<slot>/cheatsheet.md。"
        "输出 manifest 必须保持 langalpha-managed-reading-assets/v2，"
        "并逐项回填每个 Reading 的三条固定 outputs 路径，不能新增、改名或遗漏。"
        "不要生成 structure.json、lesson.md、practice.json、HTML 或任何其他文件。"
        "不要访问网络、MCP、Vault、普通工作区或发布资产。"
    )


def _profile_hash(structure_id: str) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "mode": "book-assets-v1",
                "skill": "book-to-skill",
                "structure_id": structure_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


async def queue_book_assets_for_parent(
    *,
    parent_user_id: str,
    structure_id: str,
) -> dict[str, Any]:
    """Create one optional asset job for an accepted structure."""
    structure = await get_textbook_structure_for_parent(
        parent_user_id=parent_user_id,
        structure_id=structure_id,
    )
    if not structure:
        raise LookupError("Textbook structure not found")
    if structure.get("status") not in {"accepted", "review"}:
        raise ValueError("Textbook structure is not ready for book assets")
    if not any(
        scope
        for unit in structure.get("units", [])
        if isinstance(unit, Mapping)
        for scope in unit.get("scopes", [])
        if isinstance(scope, Mapping) and scope.get("verified") is True
    ):
        raise ValueError("Textbook structure has no verified Reading scopes")
    job = await create_generation_job(
        version_id=str(structure["version_id"]),
        scope="assets",
        structure_id=structure_id,
        knowledge_point_id=None,
        processing_profile_sha256=_profile_hash(structure_id),
    )
    return {
        **structure,
        **job,
        "generation_job_id": job["generation_job_id"],
    }


async def _create_asset_workspace(
    *, parent_user_id: str, job_id: str
) -> dict[str, Any]:
    return await create_workspace(
        user_id=parent_user_id,
        name="家庭教材知识包",
        description="service-owned managed education book asset execution",
        config={
            "managed_execution": {
                "kind": _MANAGED_KIND,
                "job_id": job_id,
            }
        },
        status="creating",
    )


async def _create_asset_thread(*, job_id: str, workspace_id: str) -> dict[str, Any]:
    return await create_thread(
        conversation_thread_id=str(uuid4()),
        workspace_id=workspace_id,
        current_status="completed",
        msg_type="ptc",
        title="家庭教材知识包",
        platform="education",
        metadata={
            "managed_execution": {
                "kind": _MANAGED_KIND,
                "job_id": job_id,
            }
        },
    )


async def _fail_asset_attempt(
    *,
    job: Mapping[str, Any],
    attempt_id: str,
    status: str,
    error_code: str,
    error_message: str | None,
) -> dict[str, Any] | None:
    return await settle_generation_job(
        generation_job_id=str(job["generation_job_id"]),
        attempt_id=attempt_id,
        status=status,
        error_code=error_code,
        error_message=(
            sanitize_error_text(error_message) if error_message is not None else None
        ),
    )


async def finalize_book_asset_generation(
    *,
    job: Mapping[str, Any],
    attempt_id: str,
    root_run_id: str,
    sandbox: Any,
    terminal_status: str,
    terminal_error: str | None,
) -> dict[str, Any] | None:
    del root_run_id, terminal_error
    if terminal_status != "completed":
        status = "cancelled" if terminal_status == "cancelled" else "failed"
        return await _fail_asset_attempt(
            job=job,
            attempt_id=attempt_id,
            status=status,
            error_code=(
                "managed_book_assets_cancelled"
                if status == "cancelled"
                else "managed_book_assets_failed"
            ),
            error_message=(
                None
                if status == "cancelled"
                else "教材知识包生成未能完成，请重新运行。"
            ),
        )
    try:
        manifest, outputs = await download_book_asset_outputs(
            str(job["generation_job_id"]),
            sandbox,
        )
        prefix, stored_manifest = await write_book_asset_bundle(
            job,
            manifest,
            outputs,
        )
        completed = await complete_book_asset_generation(
            generation_job_id=str(job["generation_job_id"]),
            attempt_id=attempt_id,
            structure_id=str(job["structure_id"]),
            bundle_prefix=prefix,
            asset_manifest=stored_manifest,
        )
        if completed is None:
            raise RuntimeError("Book asset completion lost its active attempt")
        return completed
    except BookAssetValidationError:
        return await _fail_asset_attempt(
            job=job,
            attempt_id=attempt_id,
            status="failed",
            error_code="managed_book_assets_invalid",
            error_message="教材知识包格式无效，请重新运行。",
        )
    except Exception:
        logger.exception("Managed book asset finalization failed")
        return await _fail_asset_attempt(
            job=job,
            attempt_id=attempt_id,
            status="failed",
            error_code="managed_book_assets_archive_failed",
            error_message="教材知识包归档失败，请稍后重试。",
        )


async def launch_book_asset_generation(
    *,
    parent_user_id: str,
    generation_job_id: str,
) -> dict[str, str]:
    job = await get_generation_job_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    if not job:
        raise LookupError("Book asset generation job not found")
    if job.get("scope") != "assets" or job.get("status") != "queued":
        raise RuntimeError("Book asset generation job cannot start")
    generation_job_id = str(job["generation_job_id"])
    workspace = await _create_asset_workspace(
        parent_user_id=parent_user_id,
        job_id=generation_job_id,
    )
    workspace_id = str(workspace["workspace_id"])
    thread = await _create_asset_thread(
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
        raise RuntimeError("Book asset generation job was claimed")
    attempt_id = str(attempt["attempt_id"])
    policy = education_book_policy(generation_job_id)
    try:
        agent_config = await resolve_managed_education_agent_config(
            parent_user_id=parent_user_id
        )
        session = (
            await WorkspaceManager.get_instance().provision_managed_textbook_session(
                workspace_id=workspace_id,
                policy=policy,
            )
        )
        frozen_input = await get_teaching_input_for_parent(
            parent_user_id=parent_user_id,
            content_version_id=str(job["version_id"]),
        )
        if not frozen_input:
            raise LookupError("Book asset input is unavailable")
        frozen_input = await hydrate_source_asset_manifests(frozen_input)
        frozen_input = dict(frozen_input)
        frozen_input["job_id"] = generation_job_id
        structure = await get_textbook_structure_for_parent(
            parent_user_id=parent_user_id,
            structure_id=str(job["structure_id"]),
        )
        if not structure:
            raise LookupError("Textbook structure is unavailable")
        reading_scopes = [
            {**scope}
            for unit in structure.get("units", [])
            if isinstance(unit, Mapping)
            for scope in unit.get("scopes", [])
            if isinstance(scope, Mapping)
        ]
        if not reading_scopes:
            raise ValueError("Textbook structure has no verified Reading scopes")
        job = {**job, "units": structure.get("units", [])}
        await stage_managed_teaching_skills(
            generation_job_id,
            session.sandbox,
            skill_names=("book-to-skill",),
        )
        await stage_reading_asset_inputs(
            job,
            frozen_input,
            reading_scopes,
            session.sandbox,
        )
        run_id = str(uuid4())
        prompt = managed_book_assets_prompt(generation_job_id)
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
        graph, input_state, graph_config = await build_managed_education_graph(
            session=session,
            thread_id=thread_id,
            run_handle=run_handle,
            policy=policy,
            agent_config=agent_config,
            prompt=prompt,
            tags=("managed", "education", "book-assets"),
            operation="material",
            textbook_id=generation_job_id,
            job_id=generation_job_id,
            item_id=generation_job_id,
            execution_id=generation_job_id,
            attempt_token=attempt_id,
        )
        running = await mark_generation_attempt_running(
            generation_job_id=generation_job_id,
            attempt_id=attempt_id,
            root_run_id=run_id,
        )
        if running is None:
            raise RuntimeError("Book asset attempt could not enter running state")
        handler = RunSSEProducer(
            thread_id=thread_id,
            run_id=run_id,
            workflow_timeout=get_education_book_workflow_timeout(),
            replay_profile="education_compact",
        )

        async def on_terminal(task_info: Any, status: str) -> None:
            await finalize_book_asset_generation(
                job=job,
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
        await _fail_asset_attempt(
            job=job,
            attempt_id=attempt_id,
            status="failed",
            error_code="managed_book_assets_start_failed",
            error_message="教材知识包生成无法启动，请稍后重试。",
        )
        raise exc
    return {"root_run_id": run_id}
