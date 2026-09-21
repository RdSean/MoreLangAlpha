"""Managed generation of one Markdown lesson per knowledge point."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
import hashlib
import json
import logging
from typing import Any
from uuid import UUID, uuid4

from ptc_agent.agent.managed_execution import education_lesson_policy
from src.config.settings import (
    get_education_teaching_workflow_timeout,
    get_ptc_recursion_limit,
)
from src.server.database.education_textbooks import (
    claim_generation_job,
    create_generation_job,
    create_kp_lesson_revision,
    get_generation_job_for_parent,
    get_knowledge_point_for_parent,
    get_teaching_input_for_parent,
    mark_generation_attempt_running,
    requeue_generation_job,
    settle_generation_job,
)
from src.server.database.runs.lifecycle import QuerySpec
from src.server.services.education_lesson_validation import (
    KnowledgePointLessonValidationError,
    validate_kp_lesson_outputs,
)
from src.server.services.education_source_refs import (
    resolve_quote_range,
    surrounding_section_range,
)
from src.server.services.education_processing_profiles import (
    processing_profile_prompt,
)
from src.server.services.education_structure_jobs import (
    create_generation_thread,
    create_generation_workspace,
    managed_generation_workflow_events,
)
from src.server.services.education_managed_runs import (
    build_managed_education_graph,
    resolve_managed_education_agent_config,
)
from src.server.services.education_teaching_storage import (
    download_kp_lesson_outputs,
    hydrate_source_asset_manifests,
    stage_kp_lesson_inputs,
    stage_managed_teaching_skills,
    write_kp_lesson_revision,
)
from src.server.services.runs.coordinator import RunCoordinator
from src.server.services.runs.executor import LocalRunExecutor
from src.server.services.runs.sse_producer import RunSSEProducer
from src.server.services.workspace_manager import WorkspaceManager
from src.server.utils.error_sanitization import sanitize_error_text


logger = logging.getLogger(__name__)

_LESSON_EXCERPT_MIN_CHARS = 3_000
_LESSON_EXCERPT_PADDING_CHARS = 1_200
_MANAGED_KIND = "education_lesson"
_PROFILE_VERSION = "kp-lesson-v1"
MAX_LESSON_GENERATION_ATTEMPTS = 3


def _processing_profile_sha256(*, auto_grading: bool) -> str:
    payload = {
        "profile": _PROFILE_VERSION,
        "skills": ["book-to-skill"],
        "auto_grading": auto_grading,
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def managed_lesson_prompt(job: Mapping[str, Any]) -> str:
    """Describe one lesson-only managed run."""
    job_id = str(job["generation_job_id"])
    root = f"/managed/textbook-job/{UUID(job_id)}"
    practice_instruction = (
        f"同时输出 {root}/outputs/practice.json，供自动判题使用。"
        if job.get("auto_grading")
        else f"不要输出 {root}/outputs/practice.json。"
    )
    return (
        "这是服务托管的单知识点课程生成任务，不是与用户的对话。"
        f"任务编号为 {job_id}。目标知识点是：{job.get('knowledge_point_title') or ''}；"
        f"所属单元是：{job.get('unit_title') or ''}。"
        f"只读取 {root}/inputs/manifest.json 和 {root}/inputs/lesson-context.md，"
        "不要读取整本书，也不要访问网络、MCP、Vault 或普通工作区。"
        f"读取 {root}/.agents/skills/book-to-skill/SKILL.md 及其 managed lesson contract。"
        "课程主体必须是一个 Mentrix 风格的完整知识点静态页面：使用 Markdown，"
        "自然包含学习目标、前置知识、分步讲解、例子、表格、词汇或公式、"
        "易错点、复习和普通练习；不要输出追问记录、笔记或个性化总结。"
        "不要为了统一格式生成 vocabulary.json 或 evidence.json。"
        f"{practice_instruction}"
        f"唯一允许的课程输出是 {root}/outputs/lesson.md。"
        + (
            "\n\n"
            + processing_profile_prompt(
                {
                    "subject": job.get("processing_profile_subject"),
                    "grade_band": job.get("processing_profile_grade_band"),
                    "language": job.get("processing_profile_language"),
                    "depth": job.get("processing_profile_depth"),
                    "question_types": job.get(
                        "processing_profile_question_types"
                    ),
                    "prompt_fragment": job.get(
                        "processing_profile_prompt_fragment"
                    ),
                    "allowed_skills": job.get(
                        "processing_profile_allowed_skills"
                    ),
                }
            )
            if job.get("processing_profile_id")
            else ""
        )
    )


def build_lesson_source_context(
    job: Mapping[str, Any],
    frozen_input: Mapping[str, Any],
) -> tuple[str, list[str]]:
    """Slice the target knowledge point's referenced sources.

    Returns the assembled excerpt plus warnings. A knowledge point whose
    source offsets could not be resolved must not fail the whole lesson job:
    the quote can still be located approximately, and as a last resort the
    source document's leading section is used with a warning.
    """
    raw_sources = frozen_input.get("sources")
    if not isinstance(raw_sources, list):
        raw_sources = frozen_input.get("chapters")
    source_by_id = {
        str(
            source.get("source_id")
            or source.get("content_chapter_id")
            or ""
        ): source
        for source in raw_sources or []
        if isinstance(source, Mapping)
    }
    source_refs = job.get("knowledge_point_source_refs")
    if not isinstance(source_refs, list) or not source_refs:
        raise ValueError("Knowledge-point lesson source refs are unavailable")
    excerpts: list[str] = []
    warnings: list[str] = []
    for reference in source_refs:
        if not isinstance(reference, Mapping):
            raise ValueError("Knowledge-point lesson source ref is invalid")
        source_id = str(reference.get("source_id") or "")
        source = source_by_id.get(source_id)
        if not source:
            raise ValueError("Knowledge-point lesson source is unavailable")
        markdown = source.get("markdown")
        start = reference.get("start")
        end = reference.get("end")
        if not isinstance(markdown, str) or not markdown.strip():
            raise ValueError("Knowledge-point lesson source range is invalid")
        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or end <= start
            or end > len(markdown)
        ):
            resolved = resolve_quote_range(
                markdown,
                str(reference.get("quote") or ""),
                source_id=source_id,
            )
            start = resolved["start"]
            end = resolved["end"]
            warnings.append(f"source_ref_{resolved['resolution_status']}")
        # Give the lesson writer the whole containing section, not just the
        # located sentence, so it has enough material to teach from.
        start, end = surrounding_section_range(
            markdown, start, end, max_chars=18_000
        )
        if end - start < _LESSON_EXCERPT_MIN_CHARS:
            padding = _LESSON_EXCERPT_PADDING_CHARS
            start = max(0, start - padding)
            end = min(len(markdown), end + padding)
        excerpts.append(
            f"## {source_id} [{start}:{end}]\n{markdown[start:end].strip()}"
        )
    return "\n\n".join(excerpts), warnings


async def queue_kp_lesson_generation_for_parent(
    *,
    parent_user_id: str,
    knowledge_point_id: str,
    auto_grading: bool = False,
) -> dict[str, Any]:
    """Create one lesson generation job for an accepted knowledge point."""
    knowledge_point = await get_knowledge_point_for_parent(
        parent_user_id=parent_user_id,
        knowledge_point_id=knowledge_point_id,
    )
    if not knowledge_point:
        raise LookupError("Accepted knowledge point not found")
    job = await create_generation_job(
        version_id=str(knowledge_point["version_id"]),
        scope="lesson",
        structure_id=None,
        knowledge_point_id=knowledge_point_id,
        processing_profile_sha256=_processing_profile_sha256(
            auto_grading=auto_grading
        ),
        auto_grading=auto_grading,
    )
    return {**knowledge_point, **job}


async def _fail_lesson_attempt(
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
            sanitize_error_text(error_message)
            if error_message is not None
            else None
        ),
    )


async def finalize_kp_lesson_generation(
    *,
    job: Mapping[str, Any],
    attempt_id: str,
    root_run_id: str,
    sandbox: Any,
    terminal_status: str,
    terminal_error: str | None,
    parent_user_id: str | None = None,
) -> dict[str, Any] | None:
    """Validate one lesson candidate and persist a new immutable revision."""
    del root_run_id, terminal_error
    if terminal_status != "completed":
        status = "cancelled" if terminal_status == "cancelled" else "failed"
        return await _fail_lesson_attempt(
            job=job,
            attempt_id=attempt_id,
            status=status,
            error_code=(
                "managed_lesson_cancelled"
                if status == "cancelled"
                else "managed_lesson_failed"
            ),
            error_message=(
                None
                if status == "cancelled"
                else "单知识点课程生成未能完成，请重新运行。"
            ),
        )
    try:
        markdown, practice = await download_kp_lesson_outputs(
            job_id=str(job["generation_job_id"]),
            sandbox=sandbox,
            auto_grading=bool(job.get("auto_grading")),
        )
        validated = validate_kp_lesson_outputs(
            markdown=markdown,
            practice=practice,
            auto_grading=bool(job.get("auto_grading")),
        )
        stored = await write_kp_lesson_revision(job, markdown)
        revision = await create_kp_lesson_revision(
            knowledge_point_id=str(job["knowledge_point_id"]),
            content_key=stored["content_key"],
            content_sha256=stored["content_sha256"],
            size_bytes=stored["size_bytes"],
            processing_profile_sha256=str(job["processing_profile_sha256"]),
            generation_job_id=str(job["generation_job_id"]),
        )
        if revision is None:
            raise RuntimeError("Knowledge-point lesson revision was not created")
        settled = await settle_generation_job(
            generation_job_id=str(job["generation_job_id"]),
            attempt_id=attempt_id,
            status="completed",
            error_code=None,
            error_message=None,
        )
        if settled is None:
            raise RuntimeError("Knowledge-point lesson job completion was lost")
        return {
            **revision,
            "markdown": validated["markdown"],
            "practice": validated["practice"],
            "job_status": settled["status"],
        }
    except KnowledgePointLessonValidationError:
        failed = await _fail_lesson_attempt(
            job=job,
            attempt_id=attempt_id,
            status="failed",
            error_code="managed_lesson_invalid",
            error_message="单知识点课程格式无效，请重新生成。",
        )
        attempt_count = int(job.get("attempt_count") or 0)
        if (
            parent_user_id
            and attempt_count < MAX_LESSON_GENERATION_ATTEMPTS
            and await requeue_generation_job(
                generation_job_id=str(job["generation_job_id"])
            )
        ):
            await launch_kp_lesson_generation(
                parent_user_id=parent_user_id,
                generation_job_id=str(job["generation_job_id"]),
            )
            return {"status": "retrying", "attempt_count": attempt_count + 1}
        return failed
    except Exception:
        logger.exception("Managed knowledge-point lesson finalization failed")
        return await _fail_lesson_attempt(
            job=job,
            attempt_id=attempt_id,
            status="failed",
            error_code="managed_lesson_archive_failed",
            error_message="单知识点课程归档失败，请稍后重试。",
        )


async def _dispatch_kp_lesson_root_run(
    *,
    job: Mapping[str, Any],
    source_context: str,
    attempt_id: str,
    session: Any,
    workspace_id: str,
    thread_id: str,
    agent_config: Any,
    parent_user_id: str,
) -> dict[str, str]:
    generation_job_id = str(job["generation_job_id"])
    run_id = str(uuid4())
    prompt = managed_lesson_prompt(job)
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
        await stage_kp_lesson_inputs(job, source_context, session.sandbox)
        graph, input_state, graph_config = await build_managed_education_graph(
            session=session,
            thread_id=thread_id,
            run_handle=run_handle,
            policy=education_lesson_policy(generation_job_id),
            agent_config=agent_config,
            prompt=prompt,
            tags=("managed", "education", "lesson"),
            managed_kind=_MANAGED_KIND,
        )
        graph_config["recursion_limit"] = get_ptc_recursion_limit()
        running = await mark_generation_attempt_running(
            generation_job_id=generation_job_id,
            attempt_id=attempt_id,
            root_run_id=run_id,
        )
        if running is None:
            raise RuntimeError("Lesson generation attempt could not enter running state")
        handler = RunSSEProducer(
            thread_id=thread_id,
            run_id=run_id,
            workflow_timeout=get_education_teaching_workflow_timeout(),
        )

        async def on_terminal(task_info: Any, status: str) -> None:
            await finalize_kp_lesson_generation(
                job=job,
                attempt_id=attempt_id,
                root_run_id=run_id,
                sandbox=session.sandbox,
                terminal_status=status,
                terminal_error=getattr(task_info, "error", None),
                parent_user_id=parent_user_id,
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
        logger.exception(
            "Managed knowledge-point lesson start failed",
            extra={"generation_job_id": generation_job_id},
        )
        await RunCoordinator.get_instance().fail_open_run(
            run_handle,
            str(exc),
            status="error",
        )
        await _fail_lesson_attempt(
            job=job,
            attempt_id=attempt_id,
            status="failed",
            error_code="managed_lesson_start_failed",
            error_message="单知识点课程生成无法启动，请稍后重试。",
        )
        raise
    return {"root_run_id": run_id}


async def launch_kp_lesson_generation(
    *, parent_user_id: str, generation_job_id: str
) -> dict[str, str]:
    """Launch one parent-owned lesson generation attempt."""
    job = await get_generation_job_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    if not job:
        raise LookupError("Knowledge-point lesson job not found")
    if job.get("scope") != "lesson" or job.get("status") != "queued":
        raise RuntimeError("Knowledge-point lesson job cannot start")
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
        raise RuntimeError("Knowledge-point lesson job was claimed")
    attempt_id = str(attempt["attempt_id"])
    try:
        agent_config = await resolve_managed_education_agent_config(
            parent_user_id=parent_user_id
        )
    except BaseException:
        # The user-visible error is intentionally generic, so keep the real
        # staging failure in the server log for diagnosis.
        logger.exception(
            "Knowledge-point lesson staging failed",
            extra={"generation_job_id": generation_job_id},
        )
        await _fail_lesson_attempt(
            job=job,
            attempt_id=attempt_id,
            status="failed",
            error_code="managed_model_unavailable",
            error_message="单知识点课程生成需要先配置模型服务，再继续运行。",
        )
        raise
    policy = education_lesson_policy(generation_job_id)
    try:
        session = await WorkspaceManager.get_instance().provision_managed_textbook_session(
            workspace_id=workspace_id,
            policy=policy,
        )
        await stage_managed_teaching_skills(
            generation_job_id,
            session.sandbox,
            skill_names=("book-to-skill",),
        )
        frozen_input = await get_teaching_input_for_parent(
            parent_user_id=parent_user_id,
            content_version_id=str(job["version_id"]),
        )
        if not frozen_input:
            raise LookupError("Knowledge-point lesson input is unavailable")
        frozen_input = await hydrate_source_asset_manifests(frozen_input)
        source_context, source_warnings = build_lesson_source_context(
            job, frozen_input
        )
        if source_warnings:
            logger.warning(
                "Knowledge-point lesson used fallback source ranges",
                extra={
                    "generation_job_id": generation_job_id,
                    "warnings": source_warnings,
                },
            )
        return await _dispatch_kp_lesson_root_run(
            job=job,
            source_context=source_context,
            attempt_id=attempt_id,
            session=session,
            workspace_id=workspace_id,
            thread_id=thread_id,
            agent_config=agent_config,
            parent_user_id=parent_user_id,
        )
    except BaseException:
        await _fail_lesson_attempt(
            job=job,
            attempt_id=attempt_id,
            status="failed",
            error_code="managed_lesson_staging_failed",
            error_message="单知识点课程准备失败，请重新运行。",
        )
        raise
