"""Internal-only setup and dispatch helpers for managed textbook generation."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib
import logging
from typing import Any
from uuid import uuid4

from ptc_agent.agent.managed_execution import education_teaching_policy
from src.server.database.conversation import create_thread
from src.server.database.education_textbooks import (
    begin_teaching_validation,
    claim_teaching_archive_stage_for_parent,
    complete_teaching_attempt,
    create_teaching_attempt,
    delete_teaching_archive_stage,
    fail_preparing_teaching_attempt,
    get_teaching_job_for_parent,
    requeue_teaching_job,
    reconcile_terminal_teaching_root_runs as _reconcile_terminal_teaching_root_runs,
    settle_recovered_teaching_root_run as _settle_recovered_teaching_root_run,
    settle_teaching_attempt,
    store_teaching_archive_stage,
)
from src.server.database.workspace import create_workspace
from src.server.services.workspace_manager import WorkspaceManager
from src.server.services.education_teaching_storage import (
    decode_teaching_archive_stage,
    download_teaching_asset_outputs,
    encode_teaching_archive_stage,
    freeze_teaching_input,
    stage_managed_teaching_skills,
    stage_teaching_inputs,
    write_teaching_asset_bundle,
)
from src.server.services.education_teaching_jobs import (
    resolve_managed_teaching_agent_config,
)
from src.server.services.education_teaching_assets import validate_teaching_assets
from src.server.utils.error_sanitization import sanitize_error_text


_MANAGED_MARKER = "managed_execution"
logger = logging.getLogger(__name__)


async def create_managed_workspace(*, parent_user_id: str, job_id: str) -> dict[str, Any]:
    """Create the hidden row the root-run ledger needs; no public route uses it."""
    return await create_workspace(
        user_id=parent_user_id,
        name="家庭教材加工",
        description="service-owned managed education execution",
        config={_MANAGED_MARKER: {"kind": "education_teaching", "job_id": job_id}},
        status="creating",
    )


async def create_managed_thread(
    *, parent_user_id: str, job_id: str, workspace_id: str
) -> dict[str, Any]:
    """Create a hidden PTC thread for one managed job attempt."""
    del parent_user_id  # Ownership is fixed by the newly-created workspace.
    return await create_thread(
        conversation_thread_id=str(uuid4()),
        workspace_id=workspace_id,
        current_status="completed",
        msg_type="ptc",
        title="家庭教材加工",
        platform="education",
        metadata={_MANAGED_MARKER: {"kind": "education_teaching", "job_id": job_id}},
    )


async def dispatch_managed_root_run(**kwargs: Any) -> dict[str, Any]:
    """Dispatch one managed run through the shared run-ledger implementation.

    The concrete dispatcher is intentionally imported late to avoid circular
    startup imports. Its public shape remains internal: callers never control
    prompt, thread id, skills, or execution policy through HTTP.
    """
    from src.server.services.education_teaching_jobs import dispatch_managed_root_run

    return await dispatch_managed_root_run(**kwargs)


async def prepare_and_dispatch_teaching_attempt(
    *,
    parent_user_id: str,
    job: Mapping[str, Any],
    sandbox: Any | None = None,
    session: Any | None = None,
    attempt_id: str | None = None,
    workspace_id: str | None = None,
    thread_id: str | None = None,
    agent_config: Any | None = None,
) -> dict[str, str]:
    """Create hidden ownership rows, stage frozen inputs, then start the root run."""
    job_id = str(job["job_id"])
    if workspace_id is None:
        workspace = await create_managed_workspace(parent_user_id=parent_user_id, job_id=job_id)
        workspace_id = str(workspace["workspace_id"])
    if thread_id is None:
        thread = await create_managed_thread(
            parent_user_id=parent_user_id, job_id=job_id, workspace_id=workspace_id
        )
        thread_id = str(thread["conversation_thread_id"])
    staged_sandbox = sandbox or getattr(session, "sandbox", None)
    if staged_sandbox is None:
        raise RuntimeError("Managed teaching sandbox is unavailable")

    await stage_managed_teaching_skills(job_id, staged_sandbox)
    staged = await stage_teaching_inputs(job, staged_sandbox)
    policy = education_teaching_policy(job_id)
    dispatched = await dispatch_managed_root_run(
        parent_user_id=parent_user_id,
        job=job,
        sandbox=staged_sandbox,
        session=session,
        attempt_id=attempt_id,
        workspace_id=workspace_id,
        thread_id=thread_id,
        staged=staged,
        policy=policy,
        agent_config=agent_config,
    )
    return {
        "managed_workspace_id": workspace_id,
        "managed_thread_id": thread_id,
        "root_run_id": str(dispatched["root_run_id"]),
    }


async def launch_teaching_attempt(
    *, parent_user_id: str, job_id: str
) -> dict[str, str]:
    """Authorize and launch one hidden, recoverable teaching attempt.

    Hidden ownership rows and the attempt reservation are created before any
    sandbox write. The frozen job read is parent-scoped and staging then occurs
    before the root executor starts, so a later upload cannot enter this run.
    """
    job = await get_teaching_job_for_parent(parent_user_id=parent_user_id, job_id=job_id)
    if not job:
        raise LookupError("Teaching job not found")
    if job.get("job_status") != "queued":
        raise RuntimeError("Teaching job cannot start from its current status")
    normalized_job_id = str(job["job_id"])
    workspace = await create_managed_workspace(
        parent_user_id=parent_user_id, job_id=normalized_job_id
    )
    workspace_id = str(workspace["workspace_id"])
    thread = await create_managed_thread(
        parent_user_id=parent_user_id,
        job_id=normalized_job_id,
        workspace_id=workspace_id,
    )
    thread_id = str(thread["conversation_thread_id"])
    policy = education_teaching_policy(normalized_job_id)
    attempt = await create_teaching_attempt(
        job_id=normalized_job_id,
        managed_workspace_id=workspace_id,
        managed_thread_id=thread_id,
    )
    if not attempt:
        raise RuntimeError("Teaching job was claimed before its managed attempt started")
    attempt_id = str(attempt["attempt_id"])
    try:
        agent_config = await resolve_managed_teaching_agent_config(
            parent_user_id=parent_user_id
        )
    except BaseException:
        await fail_preparing_teaching_attempt(
            attempt_id=attempt_id,
            error_code="managed_model_unavailable",
            error_message="教材教学加工需要先配置模型服务，再继续运行。",
        )
        raise

    try:
        session = await WorkspaceManager.get_instance().provision_managed_textbook_session(
            workspace_id=workspace_id, policy=policy
        )
        return await prepare_and_dispatch_teaching_attempt(
            parent_user_id=parent_user_id,
            job=job,
            session=session,
            attempt_id=attempt_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            agent_config=agent_config,
        )
    except BaseException:
        await fail_preparing_teaching_attempt(
            attempt_id=attempt_id,
            error_code="managed_sandbox_unavailable",
            error_message="教材教学加工环境无法启动，请重新运行。",
        )
        raise


async def resume_teaching_job(*, parent_user_id: str, job_id: str) -> dict[str, str]:
    """Retry private archive first, otherwise create a new managed root attempt."""
    archived = await retry_staged_teaching_archive(
        parent_user_id=parent_user_id, job_id=job_id
    )
    if archived is not None:
        return archived
    resumed = await requeue_teaching_job(parent_user_id=parent_user_id, job_id=job_id)
    if not resumed:
        raise LookupError("Teaching job cannot be resumed")
    return await launch_teaching_attempt(parent_user_id=parent_user_id, job_id=job_id)


async def _archive_validated_teaching_candidate(
    *,
    job: Mapping[str, Any],
    attempt_id: str,
    root_run_id: str,
    outputs: Mapping[str, bytes],
    validated: Mapping[str, Any],
) -> dict[str, Any]:
    prefix = await write_teaching_asset_bundle(job, validated, outputs)
    asset_manifest = {
        key: value for key, value in validated.items() if key != "teaching_package"
    }
    completed = await complete_teaching_attempt(
        job_id=str(job["job_id"]),
        attempt_id=attempt_id,
        root_run_id=root_run_id,
        bundle_prefix=prefix,
        asset_manifest=asset_manifest,
        package=dict(validated["teaching_package"]),
    )
    if completed is None:
        raise RuntimeError("Managed teaching completion lost its active attempt")
    await delete_teaching_archive_stage(
        attempt_id=attempt_id, job_id=str(job["job_id"]), root_run_id=root_run_id
    )
    return completed


async def retry_staged_teaching_archive(
    *, parent_user_id: str, job_id: str
) -> dict[str, Any] | None:
    """Resume only the private archive of a previously validated candidate."""
    stage = await claim_teaching_archive_stage_for_parent(
        parent_user_id=parent_user_id, job_id=job_id
    )
    if stage is None:
        return None
    attempt_id = str(stage["attempt_id"])
    root_run_id = str(stage["root_run_id"])
    try:
        job = await get_teaching_job_for_parent(parent_user_id=parent_user_id, job_id=job_id)
        if job is None or str(job["job_id"]) != job_id:
            raise LookupError("Teaching archive stage job is unavailable")
        output_bundle = bytes(stage["output_bundle"])
        if hashlib.sha256(output_bundle).hexdigest() != stage["output_bundle_sha256"]:
            raise RuntimeError("Teaching archive stage digest is invalid")
        frozen = freeze_teaching_input(job)
        outputs = decode_teaching_archive_stage(frozen, output_bundle)
        validated = validate_teaching_assets(outputs, frozen)
        return await _archive_validated_teaching_candidate(
            job=job,
            attempt_id=attempt_id,
            root_run_id=root_run_id,
            outputs=outputs,
            validated=validated,
        )
    except Exception:
        logger.exception("Managed teaching archive retry failed")
        return await settle_teaching_attempt(
            attempt_id=attempt_id,
            root_run_id=root_run_id,
            status="failed",
            error_code="managed_archive_pending",
            error_message=sanitize_error_text(
                "教材教学资产已校验，正在等待私有存储连接，请继续运行。"
            ),
        )


async def settle_recovered_teaching_root_run(
    *, root_run_id: str, status: str, error_code: str, error_message: str
) -> dict[str, Any] | None:
    """Internal recovery projection for a scanner-finalized managed root run."""
    return await _settle_recovered_teaching_root_run(
        root_run_id=root_run_id,
        status=status,
        error_code=error_code,
        error_message=error_message,
    )


async def reconcile_terminal_teaching_root_runs() -> int:
    """Internal idle-scan repair for terminal managed roots missing a callback."""
    return await _reconcile_terminal_teaching_root_runs()


async def finalize_teaching_attempt(
    *,
    job: Mapping[str, Any],
    attempt_id: str,
    root_run_id: str,
    sandbox: Any,
    terminal_status: str,
    terminal_error: str | None,
) -> dict[str, Any] | None:
    """Project one root-run terminal status into the teaching product model.

    A completed PTC run is merely a candidate. It becomes reviewable only after
    the service retrieves the one fixed output, validates it against the frozen
    input and archives it under the generated ``education/`` path. All other
    terminal paths are deliberately fail-closed and do not create review rows.
    """
    job_id = str(job["job_id"])
    if terminal_status != "completed":
        mapped_status = "cancelled" if terminal_status == "cancelled" else "failed"
        return await settle_teaching_attempt(
            attempt_id=attempt_id,
            root_run_id=root_run_id,
            status=mapped_status,
            error_code=("managed_cancelled" if mapped_status == "cancelled" else "managed_run_failed"),
            error_message=(
                None
                if mapped_status == "cancelled"
                else "教材教学加工未能完成，请重新运行。"
            ),
        )

    archive_staged = False
    try:
        validation = await begin_teaching_validation(
            attempt_id=attempt_id, root_run_id=root_run_id
        )
        if validation is None:
            logger.info(
                "Managed teaching terminal callback lost active attempt before validation",
                extra={"attempt_id": attempt_id, "root_run_id": root_run_id},
            )
            return None
        frozen = freeze_teaching_input(job)
        outputs = await download_teaching_asset_outputs(job_id, frozen, sandbox)
        validated = validate_teaching_assets(outputs, frozen)
        output_bundle = encode_teaching_archive_stage(frozen, outputs)
        stored = await store_teaching_archive_stage(
            attempt_id=attempt_id,
            job_id=job_id,
            root_run_id=root_run_id,
            validated_assets=dict(validated),
            output_bundle=output_bundle,
            output_bundle_sha256=hashlib.sha256(output_bundle).hexdigest(),
        )
        if not stored:
            raise RuntimeError("Managed teaching archive stage was not retained")
        archive_staged = True
        return await _archive_validated_teaching_candidate(
            job=job,
            attempt_id=attempt_id,
            root_run_id=root_run_id,
            outputs=outputs,
            validated=validated,
        )
    except Exception as exc:
        # Keep raw PTC/provider/sandbox diagnostics out of the product API.
        # The detailed exception remains in server logs, while the persisted
        # message stays useful without leaking credentials, paths or endpoints.
        logger.exception(
            "Managed teaching candidate finalization failed",
            extra={
                "relative_output_path": getattr(exc, "relative_path", None),
            },
        )
        return await settle_teaching_attempt(
            attempt_id=attempt_id,
            root_run_id=root_run_id,
            status="failed",
            error_code=("managed_archive_pending" if archive_staged else "managed_output_invalid"),
            error_message=sanitize_error_text(
                (
                    "教材教学资产已校验，正在等待私有存储连接，请继续运行。"
                    if archive_staged
                    else "教材教学包校验或归档失败，请重新运行。"
                )
            ),
        )
