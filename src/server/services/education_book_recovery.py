"""PostgreSQL/runtime-ledger recovery for managed textbook items."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from ptc_agent.agent.managed_execution import education_book_policy
from src.server.database.education_book_jobs import (
    fail_book_item,
    list_book_jobs_pending_cancellation,
    list_book_items_for_recovery,
    mark_book_job_cancelled,
    renew_book_item_lease,
)
from src.server.database.education_book_activity import BookActivityWriteError
from src.server.database.runs.lifecycle import get_run, request_run_cancel
from src.server.services.education_book_jobs import (
    _is_book_infrastructure_error,
    _is_book_item_content_runtime_failure,
    _read_storage_object,
    build_execution_task,
    finalize_book_item,
)
from src.server.services.education_book_activity import publish_book_activity_hint
from src.server.services.runs.cancel import publish_cancel_nudge
from src.server.services.runs.executor import LocalRunExecutor
from src.server.services.workspace_manager import WorkspaceManager


async def recover_completed_book_item(item: Mapping[str, Any]) -> dict[str, Any]:
    """Reconnect the persisted managed sandbox and replay the idempotent commit."""

    workspace_id = item.get("managed_workspace_id")
    if workspace_id is None:
        raise RuntimeError("Managed textbook attempt has no workspace")
    execution_id = str(UUID(str(item["execution_id"])))
    session = await WorkspaceManager.get_instance().recover_managed_textbook_session(
        workspace_id=str(workspace_id),
        policy=education_book_policy(execution_id),
    )
    recovered_item = dict(item)
    if recovered_item.get("operation") == "structure":
        source = await _read_storage_object(str(recovered_item["source_markdown_key"]))
        if source is None:
            raise RuntimeError("Frozen textbook Markdown is unavailable")
        try:
            recovered_item["source_total_lines"] = len(
                source.decode("utf-8").splitlines()
            )
        except UnicodeDecodeError as exc:
            raise RuntimeError("Frozen textbook Markdown is not UTF-8") from exc
    return await finalize_book_item(
        item=recovered_item,
        task=build_execution_task(recovered_item),
        sandbox=session.sandbox,
    )


async def _signal_cancelled_book_runtime(
    context: Mapping[str, Any],
    *,
    signalled: set[tuple[str, str]],
) -> None:
    thread_id = context.get("thread_id")
    run_id = context.get("run_id")
    if thread_id is None or run_id is None:
        return
    identity = str(thread_id), str(run_id)
    if identity in signalled:
        return
    await request_run_cancel(identity[1], thread_id=identity[0])
    await LocalRunExecutor.get_instance().signal_cancel(*identity)
    await publish_cancel_nudge(*identity)
    signalled.add(identity)


async def reconcile_book_jobs_once(
    *,
    worker_id: str,
    lease_seconds: int,
    limit: int = 100,
) -> int:
    """Reconcile expired attempts using only PG rows and the runtime ledger."""

    reconciled = 0
    for job in await list_book_jobs_pending_cancellation(limit=limit):
        try:
            signalled: set[tuple[str, str]] = set()
            await _signal_cancelled_book_runtime(job, signalled=signalled)
            cancelled_job = await mark_book_job_cancelled(
                job_id=job["job_id"],
                item_id=job.get("item_id"),
                attempt_token=job.get("attempt_token"),
            )
            for runtime_context in cancelled_job.get("runtime_contexts", []):
                await _signal_cancelled_book_runtime(
                    runtime_context,
                    signalled=signalled,
                )
            await publish_book_activity_hint(
                job["job_id"], cancelled_job.get("high_water_seq")
            )
            reconciled += 1
        except (BookActivityWriteError, RuntimeError):
            continue
    for item in await list_book_items_for_recovery(limit=limit):
        run_id = item.get("run_id")
        run = await get_run(str(run_id)) if run_id is not None else None
        status = run.get("status") if run is not None else None
        if status == "in_progress":
            await renew_book_item_lease(
                item_id=item["item_id"],
                attempt_token=item["attempt_token"],
                worker_id=worker_id,
                lease_seconds=lease_seconds,
            )
            continue
        if status == "completed":
            try:
                result = await recover_completed_book_item(item)
                await publish_book_activity_hint(
                    item["job_id"],
                    result.get("high_water_seq")
                    if isinstance(result, Mapping)
                    else None,
                )
                reconciled += 1
                continue
            except BookActivityWriteError:
                continue
            except Exception as exc:
                finalization_error = exc
        else:
            finalization_error = None
        if status == "cancelled":
            try:
                cancelled_job = await mark_book_job_cancelled(
                    job_id=item["job_id"],
                    item_id=item["item_id"],
                    attempt_token=item["attempt_token"],
                )
                await publish_book_activity_hint(
                    item["job_id"], cancelled_job.get("high_water_seq")
                )
                reconciled += 1
            except RuntimeError:
                # The business callback or a newer attempt already won.
                pass
            continue
        try:
            failed_job = await fail_book_item(
                item_id=item["item_id"],
                attempt_token=item["attempt_token"],
                safe_error="Managed textbook runtime ended before business commit",
                stop_remaining=(
                    _is_book_infrastructure_error(finalization_error)
                    if finalization_error is not None
                    else not (
                        status == "error"
                        and run is not None
                        and _is_book_item_content_runtime_failure(run)
                    )
                ),
            )
            await publish_book_activity_hint(
                item["job_id"], failed_job.get("high_water_seq")
            )
            reconciled += 1
        except RuntimeError:
            # Cancel or a newer attempt won the item fence.
            continue
    return reconciled
