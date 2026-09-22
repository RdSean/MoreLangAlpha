"""Service contract for the unified managed book-processing job."""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Mapping
from datetime import datetime
import logging
from typing import Any
from uuid import uuid4

from ptc_agent.agent.managed_execution import education_book_pipeline_policy
from src.config.settings import (
    get_education_teaching_workflow_timeout,
    get_ptc_recursion_limit,
)
from src.server.database.conversation import create_thread
from src.server.database.education_textbooks import (
    claim_book_pipeline_launch,
    claim_generation_job,
    complete_book_pipeline_import,
    fail_claimed_book_pipeline_launch,
    get_generation_job_for_parent,
    get_teaching_input_for_parent,
    mark_generation_attempt_running,
    pause_book_pipeline_for_chapter_review,
    queue_book_pipeline_job,
    resume_book_pipeline_job,
    settle_generation_job,
)
from src.server.database.runs.lifecycle import QuerySpec
from src.server.database.workspace import create_workspace
from src.server.services.education_managed_runs import (
    build_managed_education_graph,
    resolve_managed_education_agent_config,
)
from src.server.services.education_progress_collector import (
    ManagedProgressCollector,
)
from src.server.services.education_structure_jobs import (
    managed_book_pipeline_prompt,
    managed_book_pipeline_continuation_prompt,
    managed_generation_workflow_events,
)
from src.server.services.education_teaching_storage import (
    TeachingPackageStorageError,
    download_book_package_outputs,
    hydrate_source_asset_manifests,
    stage_managed_teaching_skills,
    stage_book_pipeline_checkpoint_bundle,
    stage_teaching_inputs,
    validate_book_pipeline_checkpoint_prefix,
    write_book_package_bundle,
    write_book_pipeline_checkpoint_bundle,
)
from src.server.services.runs.coordinator import RunCoordinator
from src.server.services.runs.executor import LocalRunExecutor
from src.server.services.runs.sse_producer import RunSSEProducer
from src.server.services.workspace_manager import WorkspaceManager
from src.server.services.education_textbooks import (
    TextbookNotFoundError,
    TextbookPermissionError,
    TextbookTransitionError,
    get_household_context_for_parent,
)
from src.server.utils.error_sanitization import sanitize_error_text


logger = logging.getLogger(__name__)

_MANAGED_KIND = "education_book_pipeline"


def _processing_profile_sha256(processing_brief: str) -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "mode": "book-pipeline-v1",
                "skill": "book-to-skill",
                "processing_brief": processing_brief.strip(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _job_projection(job: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: job.get(key)
        for key in (
            "generation_job_id",
            "version_id",
            "scope",
            "structure_id",
            "knowledge_point_id",
            "status",
            "attempt_count",
            "pause_after_chapter_analysis",
            "checkpoint_bundle_prefix",
            "error_code",
            "error_message",
            "created_at",
            "updated_at",
            "root_run_id",
            "started_at",
            "heartbeat_at",
        )
    } | {"reused_existing_job": bool(job.get("reused_existing_job"))}


def _frozen_source_documents(
    frozen_input: Mapping[str, Any],
) -> tuple[dict[str, str], str | None]:
    sources = frozen_input.get("sources")
    if not isinstance(sources, list) or not sources:
        sources = frozen_input.get("chapters")
    if not isinstance(sources, list) or not sources:
        raise TeachingPackageStorageError(
            "Managed book package requires at least one frozen source"
        )
    documents: dict[str, str] = {}
    primary_source_id: str | None = None
    for source in sources:
        if not isinstance(source, Mapping):
            raise TeachingPackageStorageError("Managed frozen source is invalid")
        markdown = source.get("markdown")
        if not isinstance(markdown, str) or not markdown:
            raise TeachingPackageStorageError("Managed frozen Markdown is unavailable")
        source_id = str(
            source.get("source_id") or source.get("content_chapter_id") or ""
        ).strip()
        if not source_id:
            raise TeachingPackageStorageError(
                "Managed frozen source identity is unavailable"
            )
        if primary_source_id is None:
            primary_source_id = source_id
        aliases = {
            source_id,
            str(source.get("content_chapter_id") or "").strip(),
        }
        for alias in aliases - {""}:
            existing = documents.get(alias)
            if existing is not None and existing != markdown:
                raise TeachingPackageStorageError(
                    "Managed frozen source identities are ambiguous"
                )
            documents[alias] = markdown
    return documents, primary_source_id if len(sources) == 1 else None


async def import_book_package(
    job: Mapping[str, Any],
    sandbox: Any,
    *,
    frozen_input: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate, archive, and persist one managed book package for review."""
    source = frozen_input or job.get("frozen_input")
    if not isinstance(source, Mapping):
        raise TeachingPackageStorageError("Managed frozen input is unavailable")
    markdown_by_source, default_source_id = _frozen_source_documents(source)
    downloaded = await download_book_package_outputs(
        str(job["generation_job_id"]),
        sandbox,
        markdown_by_source=markdown_by_source,
        default_source_id=default_source_id,
    )
    package = dict(downloaded["package"])
    package["knowledge_points"] = [
        {
            **dict(point),
            "origin": "generated",
            "candidate_status": "pending",
        }
        for point in package.get("knowledge_points", [])
    ]
    bundle = await write_book_package_bundle(
        job,
        {
            **downloaded,
            "package": package,
        },
    )
    attempt_id = str(job.get("attempt_id") or "")
    if not attempt_id:
        raise TeachingPackageStorageError(
            "Managed book pipeline attempt is unavailable"
        )
    result = await complete_book_pipeline_import(
        parent_user_id=str(job["parent_user_id"]),
        generation_job_id=str(job["generation_job_id"]),
        attempt_id=attempt_id,
        package=package,
        bundle_prefix=str(bundle["prefix"]),
        bundle_manifest=dict(bundle["manifest"]),
        asset_content_keys=dict(bundle["asset_content_keys"]),
        warnings=list(downloaded.get("warnings") or []),
    )
    if result is None:
        raise TeachingPackageStorageError("Managed book pipeline completion was lost")
    return result


async def _fail_book_pipeline_attempt(
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


async def finalize_book_pipeline_generation(
    *,
    job: Mapping[str, Any],
    frozen_input: Mapping[str, Any],
    attempt_id: str,
    root_run_id: str,
    sandbox: Any,
    terminal_status: str,
    terminal_error: str | None,
    checkpoint_stop_event: asyncio.Event | None = None,
) -> dict[str, Any] | None:
    """Import one completed package or settle its failed attempt."""
    del root_run_id
    if checkpoint_stop_event is not None and checkpoint_stop_event.is_set():
        return {
            "status": "awaiting_review",
            "job_status": "awaiting_review",
        }
    if terminal_status != "completed":
        status = "cancelled" if terminal_status == "cancelled" else "failed"
        return await _fail_book_pipeline_attempt(
            job=job,
            attempt_id=attempt_id,
            status=status,
            error_code=(
                "managed_book_pipeline_cancelled"
                if status == "cancelled"
                else "managed_book_pipeline_failed"
            ),
            error_message=(
                None if status == "cancelled" else "教材智能处理未能完成，请重新运行。"
            ),
        )
    try:
        imported = await import_book_package(
            {**dict(job), "attempt_id": attempt_id},
            sandbox,
            frozen_input=frozen_input,
        )
        return {
            **imported,
            "status": imported.get("status") or "review",
            "job_status": "completed",
        }
    except TeachingPackageStorageError:
        return await _fail_book_pipeline_attempt(
            job=job,
            attempt_id=attempt_id,
            status="failed",
            error_code="managed_book_pipeline_invalid",
            error_message="教材智能处理结果不完整、格式无效或资产校验失败，请重新运行。",
        )
    except Exception:
        logger.exception("Managed book package import failed")
        return await _fail_book_pipeline_attempt(
            job=job,
            attempt_id=attempt_id,
            status="failed",
            error_code="managed_book_pipeline_archive_failed",
            error_message="教材智能处理资产归档失败，请稍后重新运行。",
        )


async def pause_book_pipeline_after_chapter_analysis(
    *,
    job: Mapping[str, Any],
    attempt_id: str,
    checkpoint_bundle_prefix: str,
) -> dict[str, Any]:
    """Pause a checkpointed run after the collector reports chapter analysis.

    Task 7 calls this hook from the live progress collector. Keeping the
    transition here makes the durable state change identical to the public
    resume API and avoids inferring chapter completion from tool events.
    """
    parent_user_id = str(job.get("parent_user_id") or "")
    if not parent_user_id:
        raise TextbookTransitionError("Book pipeline parent is unavailable")
    return await pause_book_pipeline_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=str(job["generation_job_id"]),
        attempt_id=attempt_id,
        checkpoint_bundle_prefix=checkpoint_bundle_prefix,
    )


async def _create_book_pipeline_workspace(
    *, parent_user_id: str, job_id: str
) -> dict[str, Any]:
    return await create_workspace(
        user_id=parent_user_id,
        name="家庭教材智能处理",
        description="service-owned unified book-to-skill execution",
        config={
            "managed_execution": {
                "kind": _MANAGED_KIND,
                "job_id": job_id,
            }
        },
        status="creating",
    )


async def _create_book_pipeline_thread(
    *, job_id: str, workspace_id: str
) -> dict[str, Any]:
    return await create_thread(
        conversation_thread_id=str(uuid4()),
        workspace_id=workspace_id,
        current_status="completed",
        msg_type="ptc",
        title="家庭教材智能处理",
        platform="education",
        metadata={
            "managed_execution": {
                "kind": _MANAGED_KIND,
                "job_id": job_id,
            }
        },
    )


async def _dispatch_book_pipeline_root_run(
    *,
    job: Mapping[str, Any],
    frozen_input: Mapping[str, Any],
    attempt_id: str,
    session: Any,
    workspace_id: str,
    thread_id: str,
    agent_config: Any,
) -> dict[str, str]:
    del frozen_input
    generation_job_id = str(job["generation_job_id"])
    run_id = str(uuid4())
    continuation = bool(job.get("checkpoint_bundle_prefix"))
    prompt = (
        managed_book_pipeline_continuation_prompt(
            generation_job_id,
            processing_brief=str(job.get("processing_brief") or ""),
        )
        if continuation
        else managed_book_pipeline_prompt(
            generation_job_id,
            processing_brief=str(job.get("processing_brief") or ""),
        )
    )
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
            policy=education_book_pipeline_policy(generation_job_id),
            agent_config=agent_config,
            prompt=prompt,
            tags=("managed", "education", "book-pipeline"),
            managed_kind=_MANAGED_KIND,
        )
        graph_config["recursion_limit"] = get_ptc_recursion_limit()
        running = await mark_generation_attempt_running(
            generation_job_id=generation_job_id,
            attempt_id=attempt_id,
            root_run_id=run_id,
        )
        if running is None:
            raise RuntimeError("Book pipeline attempt could not enter running state")
        handler = RunSSEProducer(
            thread_id=thread_id,
            run_id=run_id,
            workflow_timeout=get_education_teaching_workflow_timeout(),
        )
        checkpoint_stop_event = asyncio.Event()

        async def persist_checkpoint() -> None:
            bundle = await write_book_pipeline_checkpoint_bundle(
                job,
                attempt_id,
                session.sandbox,
            )
            await pause_book_pipeline_after_chapter_analysis(
                job=job,
                attempt_id=attempt_id,
                checkpoint_bundle_prefix=str(bundle["prefix"]),
            )

        collector = ManagedProgressCollector(
            sandbox=session.sandbox,
            generation_job_id=generation_job_id,
            attempt_id=attempt_id,
            run_id=run_id,
            checkpoint_stop_event=(
                checkpoint_stop_event
                if bool(job.get("pause_after_chapter_analysis"))
                else None
            ),
        )

        async def on_terminal(task_info: Any, status: str) -> None:
            await finalize_book_pipeline_generation(
                job=job,
                frozen_input=job.get("frozen_input") or {},
                attempt_id=attempt_id,
                root_run_id=run_id,
                sandbox=session.sandbox,
                terminal_status=status,
                terminal_error=getattr(task_info, "error", None),
                checkpoint_stop_event=checkpoint_stop_event,
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
            progress_collector=collector,
            checkpoint_stop_event=checkpoint_stop_event,
            on_checkpoint_stop=(
                persist_checkpoint
                if bool(job.get("pause_after_chapter_analysis"))
                else None
            ),
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
        await _fail_book_pipeline_attempt(
            job=job,
            attempt_id=attempt_id,
            status="failed",
            error_code="managed_book_pipeline_start_failed",
            error_message="教材智能处理无法启动，请稍后重试。",
        )
        raise
    return {"root_run_id": run_id}


async def _stage_continuation_checkpoint_bundle(
    job: Mapping[str, Any],
    sandbox: Any,
) -> None:
    try:
        await stage_book_pipeline_checkpoint_bundle(job, sandbox)
    except TeachingPackageStorageError as exc:
        raise TextbookTransitionError(
            "Textbook processing continuation checkpoint is corrupt"
        ) from exc


async def launch_book_pipeline_generation(
    *, parent_user_id: str, generation_job_id: str
) -> dict[str, Any]:
    """Launch one queued full-pipeline attempt through the shared executor."""
    job = await get_generation_job_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    if not job:
        raise TextbookNotFoundError("Textbook processing job not found")
    if job.get("scope") != "book_pipeline":
        raise TextbookTransitionError("Textbook processing job cannot start")
    continuation_required = bool(
        int(job.get("attempt_count") or 0) > 0
        or job.get("checkpoint_bundle_prefix") is not None
    )
    checkpoint_bundle_prefix: str | None = None
    if continuation_required:
        try:
            checkpoint_bundle_prefix = validate_book_pipeline_checkpoint_prefix(
                job.get("checkpoint_bundle_prefix")
            )
        except TeachingPackageStorageError as exc:
            raise TextbookTransitionError(
                "Textbook processing continuation checkpoint bundle is invalid"
            ) from exc
    if job.get("status") == "preparing":
        return {"launch_claimed": False}
    if job.get("status") != "queued":
        raise TextbookTransitionError("Textbook processing job cannot start")
    generation_job_id = str(job["generation_job_id"])
    launch_claim = await claim_book_pipeline_launch(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    if launch_claim is None:
        return {"launch_claimed": False}
    job = {**dict(job), **launch_claim}
    expected_previous_attempt_id = job.get("latest_attempt_id")
    attempt_id: str | None = None
    try:
        workspace = await _create_book_pipeline_workspace(
            parent_user_id=parent_user_id,
            job_id=generation_job_id,
        )
        workspace_id = str(workspace["workspace_id"])
        thread = await _create_book_pipeline_thread(
            job_id=generation_job_id,
            workspace_id=workspace_id,
        )
        thread_id = str(thread["conversation_thread_id"])
        attempt = await claim_generation_job(
            generation_job_id=generation_job_id,
            managed_workspace_id=workspace_id,
            managed_thread_id=thread_id,
            expected_job_status="preparing",
        )
        if not attempt:
            raise TextbookTransitionError("Textbook processing job was already claimed")
        attempt_id = str(attempt["attempt_id"])
        agent_config = await resolve_managed_education_agent_config(
            parent_user_id=parent_user_id
        )
        policy = education_book_pipeline_policy(generation_job_id)
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
            raise TextbookNotFoundError("Textbook processing input is unavailable")
        frozen_input = await hydrate_source_asset_manifests(frozen_input)
        frozen_input = dict(frozen_input)
        frozen_input["job_id"] = generation_job_id
        job = {**dict(job), "frozen_input": frozen_input}
        await stage_managed_teaching_skills(
            generation_job_id,
            session.sandbox,
            skill_names=("book-to-skill",),
        )
        await stage_teaching_inputs(frozen_input, session.sandbox)
        if checkpoint_bundle_prefix is not None:
            job = {
                **dict(job),
                "checkpoint_bundle_prefix": checkpoint_bundle_prefix,
            }
            await _stage_continuation_checkpoint_bundle(job, session.sandbox)
        return await _dispatch_book_pipeline_root_run(
            job=job,
            frozen_input=frozen_input,
            attempt_id=attempt_id,
            session=session,
            workspace_id=workspace_id,
            thread_id=thread_id,
            agent_config=agent_config,
        )
    except BaseException as exc:
        if attempt_id is not None:
            logger.exception(
                "Managed book pipeline preparing failed",
                extra={"generation_job_id": generation_job_id},
            )
            await _fail_book_pipeline_attempt(
                job=job,
                attempt_id=attempt_id,
                status="failed",
                error_code="managed_book_pipeline_staging_failed",
                error_message="教材智能处理准备失败，请重新运行。",
            )
        else:
            sanitized_message = sanitize_error_text(
                "教材智能处理无法启动，请稍后重试。"
            )
            await fail_claimed_book_pipeline_launch(
                generation_job_id=generation_job_id,
                expected_latest_attempt_id=expected_previous_attempt_id,
                error_code="managed_book_pipeline_start_failed",
                error_message=sanitized_message,
            )
            logger.warning(
                "Managed book pipeline launch claim failed before attempt",
                extra={"generation_job_id": generation_job_id},
                exc_info=exc,
            )
        raise


async def queue_and_launch_book_pipeline_for_parent(
    *,
    parent_user_id: str,
    content_version_id: str,
    processing_brief: str = "",
    request_id: str | None = None,
    pause_after_chapter_analysis: bool = False,
) -> dict[str, Any]:
    """Atomically queue/reuse a job, then start it through the shared executor."""
    queued = await queue_book_pipeline_for_parent(
        parent_user_id=parent_user_id,
        content_version_id=content_version_id,
        processing_brief=processing_brief,
        request_id=request_id,
        pause_after_chapter_analysis=pause_after_chapter_analysis,
    )
    generation_job_id = str(queued["generation_job_id"])
    if queued.get("status") != "queued":
        return queued
    try:
        await launch_book_pipeline_generation(
            parent_user_id=parent_user_id,
            generation_job_id=generation_job_id,
        )
    except Exception:
        projection = await get_book_pipeline_job_for_parent(
            parent_user_id=parent_user_id,
            generation_job_id=generation_job_id,
        )
        if projection.get("status") in {"failed", "cancelled"}:
            return projection
        raise
    projected = await get_book_pipeline_job_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    return {
        **(projected or queued),
        "reused_existing_job": bool(queued.get("reused_existing_job")),
    }


async def queue_book_pipeline_for_parent(
    *,
    parent_user_id: str,
    content_version_id: str,
    processing_brief: str = "",
    request_id: str | None = None,
    pause_after_chapter_analysis: bool = False,
) -> dict[str, Any]:
    """Create or reuse one parent-owned unified processing job."""
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError(
            "Only a parent can create textbook processing jobs"
        )
    normalized_brief = processing_brief.strip()
    job = await queue_book_pipeline_job(
        parent_user_id=parent_user_id,
        content_version_id=content_version_id,
        processing_profile_sha256=_processing_profile_sha256(normalized_brief),
        processing_brief=normalized_brief,
        request_id=request_id,
        pause_after_chapter_analysis=pause_after_chapter_analysis,
    )
    if not job:
        raise TextbookNotFoundError("Reviewable textbook content version not found")
    return _job_projection(job)


async def get_book_pipeline_job_for_parent(
    *,
    parent_user_id: str,
    generation_job_id: str,
) -> dict[str, Any]:
    """Return one parent-owned unified processing job."""
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can read textbook processing jobs")
    job = await get_generation_job_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    if not job or job.get("scope") != "book_pipeline":
        raise TextbookNotFoundError("Textbook processing job not found")
    return _job_projection(job)


async def pause_book_pipeline_for_parent(
    *,
    parent_user_id: str,
    generation_job_id: str,
    attempt_id: str,
    checkpoint_bundle_prefix: str,
) -> dict[str, Any]:
    """Finish the current attempt at the chapter-analysis review checkpoint."""
    try:
        checkpoint_bundle_prefix = validate_book_pipeline_checkpoint_prefix(
            checkpoint_bundle_prefix
        )
    except TeachingPackageStorageError as exc:
        raise TextbookTransitionError(
            "Textbook processing checkpoint bundle is invalid"
        ) from exc
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError(
            "Only a parent can update textbook processing jobs"
        )
    job = await pause_book_pipeline_for_chapter_review(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
        attempt_id=attempt_id,
        checkpoint_bundle_prefix=checkpoint_bundle_prefix,
    )
    if not job:
        raise TextbookTransitionError("Textbook processing job cannot pause for review")
    return _job_projection(job)


async def resume_book_pipeline_for_parent(
    *,
    parent_user_id: str,
    generation_job_id: str,
) -> dict[str, Any]:
    """Requeue one unified job waiting at the chapter-analysis checkpoint."""
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError(
            "Only a parent can resume textbook processing jobs"
        )
    job = await get_generation_job_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    if not job or job.get("scope") != "book_pipeline":
        raise TextbookNotFoundError("Textbook processing job not found")
    if job.get("status") != "awaiting_review":
        raise TextbookTransitionError(
            "Only a chapter-analysis checkpoint can be resumed"
        )
    try:
        checkpoint_bundle_prefix = validate_book_pipeline_checkpoint_prefix(
            job.get("checkpoint_bundle_prefix")
        )
    except TeachingPackageStorageError as exc:
        raise TextbookTransitionError(
            "Textbook processing continuation checkpoint bundle is invalid"
        ) from exc
    resumed = await resume_book_pipeline_job(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    if not resumed:
        raise TextbookTransitionError("Textbook processing job cannot be resumed")
    if str(resumed.get("checkpoint_bundle_prefix") or "") != checkpoint_bundle_prefix:
        raise TextbookTransitionError(
            "Textbook processing continuation checkpoint changed during resume"
        )
    await launch_book_pipeline_generation(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    projected = await get_book_pipeline_job_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    return projected
