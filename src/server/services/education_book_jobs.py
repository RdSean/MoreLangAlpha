"""Managed PTC orchestration contracts for textbook job items."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID, uuid4

import psycopg
from ptc_agent.agent.managed_execution import education_book_policy
from ptc_agent.core.sandbox.runtime import SandboxGoneError, SandboxTransientError
from src.server.database.education_book_jobs import (
    bind_book_item_runtime,
    claim_next_book_item,
    fail_book_item,
    list_book_items_for_terminal_cleanup,
    mark_book_job_cancelled,
    request_book_job_cancel,
    renew_book_item_lease,
)
from src.server.database.education_book_activity import BookActivityWriteError
from src.server.database.conversation import create_thread, update_thread_fields
from src.server.database.runs.lifecycle import QuerySpec
from src.server.database.education_books import commit_book_structure
from src.server.database.runs.lifecycle import request_run_cancel
from src.server.database.workspace import create_workspace
from src.config.settings import get_education_book_workflow_timeout
from src.server.services.education_book_storage import (
    BookStorageError,
    cleanup_book_item_candidates,
    store_material,
    store_supplementary,
)
from src.server.services.education_book_activity import (
    BookActivityObserver,
    publish_book_activity_hint,
)
from src.server.services.education_book_progress import progress_contract
from src.server.services.education_book_timing import book_phase
from src.server.services.education_book_structure import (
    MoreToSkillsIdentity,
    TrustedBookSource,
    get_more_to_skills_identity,
    get_projected_current_structure,
    load_more_to_skills_files,
    parse_book_structure,
)
from src.server.services.education_managed_runs import (
    build_managed_education_graph,
    resolve_managed_education_agent_config,
)
from src.server.services.runs.coordinator import RunCoordinator
from src.server.services.runs.cancel import publish_cancel_nudge
from src.server.services.runs.executor import LocalRunExecutor
from src.server.services.runs.sse_producer import RunSSEProducer
from src.server.services.workspace_manager import WorkspaceManager
from src.utils.storage import get_bytes


logger = logging.getLogger(__name__)
_ITEM_CONTENT_TERMINAL_ERROR_TYPES = frozenset({"langgraph.errors.GraphRecursionError"})


async def cleanup_managed_book_runtime(
    *, workspace_id: str, thread_id: str | None
) -> None:
    """Archive the audit thread and delete its service-owned workspace sandbox."""

    if thread_id is not None:
        try:
            await update_thread_fields(thread_id, archived=True)
        except Exception:
            logger.exception("Could not archive managed textbook thread %s", thread_id)
    try:
        await WorkspaceManager.get_instance().delete_workspace(
            workspace_id,
            backup_files=False,
        )
    except Exception:
        logger.exception("Could not delete managed textbook workspace %s", workspace_id)


async def _settle_failed_book_launch(
    *,
    item: Mapping[str, Any],
    identity: Mapping[str, str],
    workspace_id: str,
    thread_id: str | None,
    run_handle: Any | None,
    error: BaseException,
) -> None:
    if run_handle is not None:
        try:
            await RunCoordinator.get_instance().fail_open_run(
                run_handle,
                str(error),
                status="error",
            )
        except Exception:
            logger.exception("Could not fail the managed textbook runtime ledger")
    try:
        failed_job = await fail_book_item(
            item_id=item["item_id"],
            attempt_token=UUID(identity["attempt_token"]),
            safe_error="Managed textbook execution could not start",
            stop_remaining=True,
        )
        await publish_book_activity_hint(
            item["job_id"], failed_job.get("high_water_seq")
        )
    except Exception:
        logger.exception("Could not fail the managed textbook business item")
    await cleanup_book_item_candidates(
        item_id=UUID(str(item["item_id"])),
        attempt_token=UUID(identity["attempt_token"]),
    )
    await cleanup_managed_book_runtime(
        workspace_id=workspace_id,
        thread_id=thread_id,
    )


async def cleanup_settled_book_items_once(*, limit: int = 100) -> int:
    """Retry exact-key and service-owned runtime cleanup after process exits."""

    cleaned = 0
    for item in await list_book_items_for_terminal_cleanup(limit=limit):
        await cleanup_book_item_candidates(
            item_id=UUID(str(item["item_id"])),
            attempt_token=UUID(str(item["attempt_token"])),
        )
        workspace_id = item.get("managed_workspace_id")
        thread_id = item.get("managed_thread_id")
        if workspace_id is not None and thread_id is not None:
            await cleanup_managed_book_runtime(
                workspace_id=str(workspace_id),
                thread_id=str(thread_id),
            )
        cleaned += 1
    return cleaned


def _is_book_infrastructure_error(exc: Exception) -> bool:
    """Return whether one item failure invalidates the remaining queue runtime."""

    return isinstance(
        exc,
        (
            BookStorageError,
            SandboxGoneError,
            SandboxTransientError,
            psycopg.Error,
        ),
    )


def _is_book_item_content_runtime_failure(runtime: object) -> bool:
    """Return whether a failed graph run is isolated to one generated item."""

    metadata = (
        runtime.get("metadata")
        if isinstance(runtime, Mapping)
        else getattr(runtime, "metadata", None)
    )
    return isinstance(metadata, Mapping) and (
        metadata.get("terminal_error_type") in _ITEM_CONTENT_TERMINAL_ERROR_TYPES
    )


def _validate_book_execution_identity(item: Mapping[str, Any]) -> None:
    """Refuse to execute a queued job with changed shipped instructions."""

    actual = get_more_to_skills_identity()
    expected = MoreToSkillsIdentity(
        version=str(item.get("more_to_skills_version") or ""),
        skill_sha256=str(item.get("skill_sha256") or ""),
        schema_sha256=str(item.get("schema_sha256") or ""),
    )
    if actual != expected:
        raise RuntimeError("Managed textbook skill identity changed after queueing")


def _uuid(value: object, field: str) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a UUID") from exc


def build_execution_task(item: Mapping[str, Any]) -> dict[str, Any]:
    """Build the immutable task.json staged for one item execution."""

    operation = str(item.get("operation") or "")
    if operation not in {"structure", "material"}:
        raise ValueError("Unsupported education book operation")
    slug = str(item.get("slug") or "").strip()
    if not slug or "/" in slug or ".." in slug:
        raise ValueError("Textbook slug is invalid")
    task: dict[str, Any] = {
        "schema_version": "langalpha-education-book-task/v2",
        "mode": (
            "structure_only" if operation == "structure" else "reading_material_only"
        ),
        "textbook_id": _uuid(item.get("textbook_id"), "textbook_id"),
        "job_id": _uuid(item.get("job_id"), "job_id"),
        "item_id": _uuid(item.get("item_id"), "item_id"),
        "execution_id": _uuid(item.get("execution_id"), "execution_id"),
        "attempt_token": _uuid(item.get("attempt_token"), "attempt_token"),
        "attempt": int(item.get("attempt") or 0),
        "source": {
            "markdown": "inputs/source/document.md",
            "blocks": (
                "inputs/source/blocks.json" if item.get("source_blocks_key") else None
            ),
            "report": (
                "inputs/source/report.json" if item.get("source_report_key") else None
            ),
            "content_sha256": str(item.get("source_content_sha256") or ""),
        },
        "more_to_skills": {
            "version": str(item.get("more_to_skills_version") or ""),
            "skill_sha256": str(item.get("skill_sha256") or ""),
            "schema_sha256": str(item.get("schema_sha256") or ""),
        },
        "progress": progress_contract(item),
        "delivery": {
            "structure_owner": "agent" if operation == "structure" else "host",
            "content_file_owner": "host",
            "completion_owner": "host",
        },
        "output": {
            "root": f"outputs/{slug}",
        },
    }
    if operation == "structure":
        task["output"]["structure"] = f"outputs/{slug}/book-structure.json"
    if operation == "material" and item.get("kind") == "supplementary":
        task.update(
            {
                "supplementary": True,
                "requirements": item.get("requirements"),
                "context": {
                    "structure": "inputs/book-structure.json",
                    "materials_root": "inputs/materials",
                },
            }
        )
        task["output"]["supplementary"] = [
            f"outputs/{slug}/{filename}"
            for filename in ("glossary.md", "patterns.md", "cheatsheet.md")
        ]
    elif operation == "material":
        skill_kp_id = str(item.get("skill_kp_id") or "").strip()
        if not skill_kp_id or "/" in skill_kp_id or ".." in skill_kp_id:
            raise ValueError("Material item skill_kp_id is invalid")
        point = item.get("knowledge_point_json")
        if not isinstance(point, Mapping):
            raise ValueError("Material item has no frozen knowledge point")
        task.update(
            {
                "requires_previous_material": False,
                "context": {"manifest": "inputs/material-context.json"},
                "knowledge_point": {
                    "knowledge_point_id": _uuid(
                        item.get("knowledge_point_id"), "knowledge_point_id"
                    ),
                    "skill_kp_id": skill_kp_id,
                    "value": dict(point),
                },
                "depth": item.get("depth"),
                "requirements": item.get("requirements"),
            }
        )
        task["output"]["material"] = f"outputs/{slug}/chapters/{skill_kp_id}.md"
    return task


def _source_excerpt(
    source_lines: list[str], *, start_line: object, end_line: object, limit: int = 20
) -> str:
    start = max(1, int(start_line or 1))
    end = min(len(source_lines), int(end_line or 0))
    if end < start:
        return ""
    return "\n".join(source_lines[start - 1 : end][-limit:])


async def _stage_material_context(
    *,
    item: Mapping[str, Any],
    source_text: str,
    root: str,
) -> tuple[dict[str, Any], list[tuple[str, bytes]]]:
    projected = await get_projected_current_structure(
        textbook_id=_uuid(item.get("textbook_id"), "textbook_id")
    )
    if projected is None:
        raise RuntimeError("Current textbook structure is unavailable")
    points = projected.get("knowledge_points")
    structure = projected.get("structure_json")
    if not isinstance(points, list) or not isinstance(structure, Mapping):
        raise RuntimeError("Current textbook structure is invalid")

    target_id = _uuid(item.get("knowledge_point_id"), "knowledge_point_id")
    try:
        target_index = next(
            index
            for index, point in enumerate(points)
            if str(point.get("knowledge_point_id")) == target_id
        )
    except StopIteration as exc:
        raise RuntimeError(
            "Material target is not in the current textbook structure"
        ) from exc
    target = points[target_index]
    previous = points[target_index - 1] if target_index > 0 else None
    following = points[target_index + 1] if target_index + 1 < len(points) else None
    unit_id = target.get("unit_skill_node_id")
    unit_points = [
        point for point in points if point.get("unit_skill_node_id") == unit_id
    ]
    context: dict[str, Any] = {
        "target": {
            "skill_kp_id": str(target["skill_kp_id"]),
            "title": str(target["title"]),
            "start_line": int(target["start_line"]),
            "end_line": int(target["end_line"]),
        },
        "previous": None,
        "next": (
            {
                "skill_kp_id": str(following["skill_kp_id"]),
                "title": str(following["title"]),
            }
            if following is not None
            else None
        ),
        "unit_skill_node_id": str(unit_id) if unit_id is not None else None,
        "unit_titles": [str(point["title"]) for point in unit_points],
    }
    extra_files: list[tuple[str, bytes]] = []
    if previous is not None:
        previous_context: dict[str, Any] = {
            "skill_kp_id": str(previous["skill_kp_id"]),
            "title": str(previous["title"]),
        }
        content_key = previous.get("content_key")
        previous_material = None
        if content_key is not None:
            content_key = str(content_key)
            if not content_key.startswith("education/") or ".." in content_key:
                raise RuntimeError("Previous textbook material key is invalid")
            previous_material = await _read_storage_object(content_key)
        if previous_material:
            material_path = "inputs/context/previous-material.md"
            previous_context.update(
                {"source": "material", "material_path": material_path}
            )
            extra_files.append((f"{root}/{material_path}", previous_material))
        else:
            previous_context.update(
                {
                    "source": "source_excerpt",
                    "start_line": int(previous["start_line"]),
                    "end_line": int(previous["end_line"]),
                    "source_excerpt": _source_excerpt(
                        source_text.splitlines(),
                        start_line=previous["start_line"],
                        end_line=previous["end_line"],
                    ),
                }
            )
        context["previous"] = previous_context
    return dict(structure), [
        *extra_files,
        (
            f"{root}/inputs/material-context.json",
            json.dumps(
                context,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
        ),
    ]


async def _stage_supplementary_context(
    *, item: Mapping[str, Any], root: str
) -> list[tuple[str, bytes]]:
    projected = await get_projected_current_structure(
        textbook_id=_uuid(item.get("textbook_id"), "textbook_id")
    )
    if projected is None:
        raise RuntimeError("Current textbook structure is unavailable")
    points = projected.get("knowledge_points")
    structure = projected.get("structure_json")
    if not isinstance(points, list) or not isinstance(structure, Mapping):
        raise RuntimeError("Current textbook structure is invalid")
    files = [
        (
            f"{root}/inputs/book-structure.json",
            json.dumps(
                structure,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
        )
    ]
    for point in points:
        content_key = point.get("content_key")
        if content_key is None:
            continue
        content_key = str(content_key)
        if not content_key.startswith("education/") or ".." in content_key:
            raise RuntimeError("Current textbook material key is invalid")
        material = await _read_storage_object(content_key)
        if not material:
            raise RuntimeError("A current textbook material is unavailable")
        knowledge_point_id = _uuid(
            point.get("knowledge_point_id"), "knowledge_point_id"
        )
        files.append((f"{root}/inputs/materials/{knowledge_point_id}.md", material))
    return files


def managed_item_prompt(item: Mapping[str, Any]) -> str:
    """Return a prompt whose only business identifier is the execution id."""

    execution_id = _uuid(item.get("execution_id"), "execution_id")
    operation = str(item.get("operation") or "")
    mode = (
        "Structure Only"
        if operation == "structure"
        else "Reading Material Only"
        if operation == "material"
        else None
    )
    if mode is None:
        raise ValueError("Unsupported education book operation")
    root = f"/managed/textbook-job/{execution_id}"
    return (
        f"Managed textbook execution {execution_id}. Run more-to-skills in "
        f"{mode} mode. Read {root}/inputs/task.json and the frozen "
        f"{root}/.agents/skills/more-to-skills/SKILL.md contract. Use normal "
        "Read, image reading, Bash, and ExecuteCode as needed. Follow the "
        "task.json progress contract: call report_progress only with a listed "
        "progress.allowed_stages value when entering a real stage, optionally selecting "
        "an allowed action matching its stages and when condition. Follow the Skill's "
        "optional host progress guidance; the catalog is not a required checklist. Progress is "
        "optional and does not replace outputs or the final response. When the progress tool "
        "is available, prefer reporting a real major stage before beginning lengthy work: "
        "use a separate short tool-only turn before composing long scripts or lecture content, "
        "then generate that content in the next turn. Do not bundle that report with long "
        "Write/Edit/Bash arguments. Do not retrospectively report completed stages as ongoing. "
        "Missing or unavailable reporting must not interrupt content work. Write only the "
        "single task's declared outputs; output.root is a directory, not an additional "
        "deliverable. Follow task.json delivery ownership: the host commits results, "
        "updates content_file pointers and confirms completion. For Reading Material "
        "Only, read the input structure as context. Do not copy or update an output "
        "structure or validate the presence of other knowledge points' materials. "
        "Check the target content and sources, write the final deliverable directly "
        "without creating a second full draft, and keep the final response brief. "
        "Do not infer business identifiers from paths."
    )


async def _read_storage_object(key: str) -> bytes | None:
    return await asyncio.to_thread(get_bytes, key)


def _safe_snapshot_relative_path(value: object) -> str:
    path = PurePosixPath(str(value or ""))
    if path.is_absolute() or not path.parts or ".." in path.parts:
        raise ValueError("Textbook source asset path is invalid")
    return path.as_posix()


async def stage_book_skill(
    execution_id: str,
    sandbox: Any,
    *,
    expected_skill_sha256: str,
    expected_schema_sha256: str,
) -> None:
    """Stage only the fixed repository skill, then make its catalog read-only."""
    files = load_more_to_skills_files(
        expected_skill_sha256=expected_skill_sha256,
        expected_schema_sha256=expected_schema_sha256,
    )
    root = f"/managed/textbook-job/{UUID(execution_id)}/.agents/skills/more-to-skills"
    for relative, content in files.items():
        if not await sandbox.aupload_file_bytes(f"{root}/{relative}", content):
            raise RuntimeError("Could not stage the managed textbook skill")
    await sandbox.seal_directory_read_only(root)


async def stage_book_execution(
    *,
    item: Mapping[str, Any],
    task: Mapping[str, Any],
    sandbox: Any,
) -> dict[str, Any]:
    """Stage one exact source snapshot and seal it read-only."""

    execution_id = _uuid(item.get("execution_id"), "execution_id")
    root = f"/managed/textbook-job/{execution_id}"
    prefix = str(item.get("source_snapshot_prefix") or "")
    if not prefix.startswith("education/") or ".." in prefix:
        raise ValueError("Textbook source snapshot prefix is invalid")
    await stage_book_skill(
        execution_id,
        sandbox,
        expected_skill_sha256=str(item.get("skill_sha256") or ""),
        expected_schema_sha256=str(item.get("schema_sha256") or ""),
    )
    files: list[tuple[str, bytes]] = []
    source: bytes | None = None
    for field, destination in (
        ("source_markdown_key", "document.md"),
        ("source_blocks_key", "blocks.json"),
        ("source_report_key", "report.json"),
    ):
        key = item.get(field)
        if key is None:
            continue
        key = str(key)
        if not key.startswith(prefix) or ".." in key:
            raise ValueError(f"{field} is outside the source snapshot")
        content = await _read_storage_object(key)
        if content is None:
            raise RuntimeError(f"Frozen textbook {field} is unavailable")
        files.append((f"{root}/inputs/source/{destination}", content))
        if field == "source_markdown_key":
            source = content
    if source is None:
        raise RuntimeError("Frozen textbook Markdown is unavailable")
    if hashlib.sha256(source).hexdigest() != str(
        item.get("source_content_sha256") or ""
    ):
        raise RuntimeError("Frozen textbook Markdown failed digest verification")
    try:
        source_text = source.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("Frozen textbook Markdown is not UTF-8") from exc

    manifest = item.get("source_asset_manifest") or []
    if not isinstance(manifest, list):
        raise ValueError("Textbook source asset manifest is invalid")
    for asset in manifest:
        if not isinstance(asset, Mapping):
            raise ValueError("Textbook source asset manifest is invalid")
        relative = str(asset.get("relative_path") or "")
        destination = _safe_snapshot_relative_path(relative)
        key = f"{prefix}artifacts/{relative}"
        content = await _read_storage_object(key)
        if content is None:
            raise RuntimeError("A frozen textbook source asset is unavailable")
        if hashlib.sha256(content).hexdigest() != str(asset.get("sha256") or ""):
            raise RuntimeError("A frozen textbook source asset failed verification")
        files.append((f"{root}/inputs/source/{destination}", content))

    if item.get("operation") == "material" and item.get("kind") == "material":
        structure, context_files = await _stage_material_context(
            item=item,
            source_text=source_text,
            root=root,
        )
        files.extend(context_files)
        files.append(
            (
                f"{root}/inputs/book-structure.json",
                json.dumps(
                    structure,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8"),
            )
        )
    elif item.get("operation") == "material" and item.get("kind") == "supplementary":
        files.extend(await _stage_supplementary_context(item=item, root=root))
    files.append(
        (
            f"{root}/inputs/task.json",
            json.dumps(
                task,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
        )
    )
    for path, content in files:
        if not await sandbox.aupload_file_bytes(path, content):
            raise RuntimeError("Could not stage managed textbook input")
    await sandbox.seal_directory_read_only(f"{root}/inputs")
    await sandbox.seal_directory_read_only(f"{root}/.agents/skills/more-to-skills")
    return {"source_total_lines": len(source_text.splitlines())}


async def finalize_book_item(
    *,
    item: Mapping[str, Any],
    task: Mapping[str, Any],
    sandbox: Any,
) -> dict[str, Any]:
    """Validate and commit one successful root run under its attempt fence."""

    operation = str(item.get("operation") or "")
    output = task.get("output")
    if not isinstance(output, Mapping):
        raise ValueError("Managed textbook task has no output contract")
    root = f"/managed/textbook-job/{_uuid(item.get('execution_id'), 'execution_id')}"
    if operation == "material" and item.get("kind") == "supplementary":
        paths = output.get("supplementary")
        if not isinstance(paths, list) or len(paths) != 3:
            raise ValueError("Supplementary output contract is invalid")
        files: dict[str, bytes] = {}
        for relative_path in paths:
            relative_path = str(relative_path)
            content = await sandbox.adownload_file_bytes(f"{root}/{relative_path}")
            if not content:
                raise RuntimeError("Managed supplementary output is missing")
            files[PurePosixPath(relative_path).name] = content
        return await store_supplementary(
            item_id=UUID(str(item["item_id"])),
            attempt_token=UUID(str(item["attempt_token"])),
            files=files,
        )
    if operation == "material":
        relative_path = str(output.get("material") or "")
        markdown = await sandbox.adownload_file_bytes(f"{root}/{relative_path}")
        if not markdown:
            raise RuntimeError("Managed material output is missing")
        return await store_material(
            item_id=UUID(str(item["item_id"])),
            attempt_token=UUID(str(item["attempt_token"])),
            markdown=markdown,
            generation_params={
                "depth": item.get("depth"),
                "requirements": item.get("requirements"),
                "execution_id": str(item["execution_id"]),
            },
        )
    if operation != "structure":
        raise ValueError("Unsupported education book operation")
    relative_path = str(output.get("structure") or "")
    raw_json = await sandbox.adownload_file_bytes(f"{root}/{relative_path}")
    if not raw_json:
        raise RuntimeError("Managed structure output is missing")
    total_lines = int(item.get("source_total_lines") or 0)
    if total_lines <= 0:
        raise ValueError("Managed structure source line count is invalid")
    parsed = parse_book_structure(
        trusted_source=TrustedBookSource(
            path="inputs/source/document.md",
            filename=str(item.get("source_filename") or ""),
            format=str(item.get("source_format") or ""),
            total_lines=total_lines,
            anchor_mode="source_lines",
            line_offset=0,
        ),
        raw_json=raw_json,
        allowed_output_paths=(),
    )
    return await commit_book_structure(
        textbook_id=item["textbook_id"],
        job_id=item["job_id"],
        item_id=item["item_id"],
        attempt_token=UUID(str(item["attempt_token"])),
        parsed=parsed,
        validated_identity=MoreToSkillsIdentity(
            version=str(item["more_to_skills_version"]),
            skill_sha256=str(item["skill_sha256"]),
            schema_sha256=str(item["schema_sha256"]),
        ),
    )


def _managed_identity(item: Mapping[str, Any]) -> dict[str, str]:
    return {
        "kind": "education_book",
        "operation": str(item["operation"]),
        "textbook_id": _uuid(item.get("textbook_id"), "textbook_id"),
        "job_id": _uuid(item.get("job_id"), "job_id"),
        "item_id": _uuid(item.get("item_id"), "item_id"),
        "execution_id": _uuid(item.get("execution_id"), "execution_id"),
        "attempt_token": _uuid(item.get("attempt_token"), "attempt_token"),
    }


async def launch_book_item(
    *,
    item: Mapping[str, Any],
    capacity_reservation: str,
) -> dict[str, str]:
    """Launch one claimed item through the normal root-run execution spine."""

    item = dict(item)
    _validate_book_execution_identity(item)
    identity = _managed_identity(item)
    task = build_execution_task(item)
    timings: dict[str, float] = {}
    prompt = managed_item_prompt(item)
    workspace_id = str(uuid4())
    thread_id: str | None = None
    run_handle = None
    activity_observer = BookActivityObserver(
        job_id=item["job_id"],
        item_id=item["item_id"],
        attempt_token=UUID(identity["attempt_token"]),
        item_kind=str(item["kind"]),
    )
    try:
        await activity_observer.report_service_stage("service_preparing")
        workspace = await create_workspace(
            user_id=str(item["requested_by_user_id"]),
            name="教材处理",
            description="service-owned managed textbook item execution",
            config={"managed_execution": identity},
            workspace_id=workspace_id,
            status="creating",
        )
        workspace_id = str(workspace["workspace_id"])
        thread = await create_thread(
            conversation_thread_id=str(uuid4()),
            workspace_id=workspace_id,
            current_status="completed",
            msg_type="ptc",
            title="教材处理",
            platform="education",
            metadata={"managed_execution": identity},
        )
        thread_id = str(thread["conversation_thread_id"])
        agent_config = await resolve_managed_education_agent_config(
            parent_user_id=str(item["requested_by_user_id"])
        )
        policy = education_book_policy(identity["execution_id"])
        with book_phase(item, "sandbox_preparation", measurements=timings):
            session = await WorkspaceManager.get_instance().provision_managed_textbook_session(
                workspace_id=workspace_id,
                policy=policy,
            )
        with book_phase(item, "input_staging", measurements=timings):
            staged = await stage_book_execution(
                item=item,
                task=task,
                sandbox=session.sandbox,
            )
        item.update(staged)
        run_id = str(uuid4())
        item["run_id"] = run_id
        run_handle = await RunCoordinator.get_instance().start_run(
            thread_id=thread_id,
            run_id=run_id,
            msg_type="ptc",
            request_key=identity["execution_id"],
            workspace_id=workspace_id,
            user_id=None,
            query=QuerySpec(
                query_id=str(uuid4()),
                content=prompt,
                query_type="system",
                metadata={"managed_execution": identity},
                created_at=datetime.now(),
            ),
            run_metadata={
                "managed_execution": identity,
                "task_schema_version": task["schema_version"],
                "suppress_lifecycle_hooks": True,
            },
        )
    except BaseException as exc:
        await _settle_failed_book_launch(
            item=item,
            identity=identity,
            workspace_id=workspace_id,
            thread_id=thread_id,
            run_handle=run_handle,
            error=exc,
        )
        raise
    try:
        await bind_book_item_runtime(
            item_id=item["item_id"],
            attempt_token=UUID(identity["attempt_token"]),
            workspace_id=workspace_id,
            thread_id=thread_id,
            run_id=run_id,
        )
        graph, input_state, graph_config = await build_managed_education_graph(
            session=session,
            thread_id=thread_id,
            run_handle=run_handle,
            policy=policy,
            agent_config=agent_config,
            prompt=prompt,
            tags=("managed", "education", "book", identity["operation"]),
            operation=identity["operation"],
            textbook_id=identity["textbook_id"],
            job_id=identity["job_id"],
            item_id=identity["item_id"],
            execution_id=identity["execution_id"],
            attempt_token=identity["attempt_token"],
            task_schema_version=task["schema_version"],
        )
        graph_config["metadata"]["education_preparation_ms"] = dict(timings)
        handler = RunSSEProducer(
            thread_id=thread_id,
            run_id=run_id,
            workflow_timeout=get_education_book_workflow_timeout(),
            replay_profile="education_compact",
            event_observer=activity_observer,
        )

        async def on_terminal(task_info: Any, status: str) -> None:
            retain_runtime_for_recovery = False
            try:
                stop_remaining = status != "completed" and not (
                    status == "error"
                    and _is_book_item_content_runtime_failure(task_info)
                )
                if status == "completed":
                    try:
                        await activity_observer.report_service_stage(
                            "service_finalizing"
                        )
                        with book_phase(item, "finalization"):
                            result = await finalize_book_item(
                                item=item,
                                task=task,
                                sandbox=session.sandbox,
                            )
                        await publish_book_activity_hint(
                            item["job_id"],
                            result.get("high_water_seq")
                            if isinstance(result, Mapping)
                            else None,
                        )
                        return
                    except BookActivityWriteError:
                        retain_runtime_for_recovery = True
                        logger.warning(
                            "Deferring textbook finalization until activity storage recovers"
                        )
                        return
                    except Exception as exc:
                        error = str(exc) or "Managed textbook output was invalid"
                        stop_remaining = _is_book_infrastructure_error(exc)
                else:
                    error = (
                        str(getattr(task_info, "error", "") or "")
                        or f"Managed textbook run ended with {status}"
                    )
                try:
                    failed_job = await fail_book_item(
                        item_id=item["item_id"],
                        attempt_token=UUID(identity["attempt_token"]),
                        safe_error=error[:2000],
                        stop_remaining=stop_remaining,
                    )
                    await publish_book_activity_hint(
                        item["job_id"], failed_job.get("high_water_seq")
                    )
                except BookActivityWriteError:
                    retain_runtime_for_recovery = True
                    logger.warning(
                        "Deferring textbook failure finalization until activity storage recovers"
                    )
                    return
                except RuntimeError:
                    # A user cancel or newer attempt won the fence.
                    return
            finally:
                if not retain_runtime_for_recovery:
                    await cleanup_book_item_candidates(
                        item_id=UUID(str(item["item_id"])),
                        attempt_token=UUID(identity["attempt_token"]),
                    )
                    await cleanup_managed_book_runtime(
                        workspace_id=workspace_id,
                        thread_id=thread_id,
                    )

        workflow = handler.stream_workflow(
            graph=graph,
            input_state=input_state,
            config=graph_config,
        )
        await LocalRunExecutor.get_instance().start_run(
            thread_id=thread_id,
            run_id=run_id,
            workflow_generator=workflow,
            metadata={
                "workspace_id": workspace_id,
                "managed_execution": identity,
                "started_at": datetime.now().isoformat(),
                "msg_type": "ptc",
                "handler": handler,
                "run_handle": run_handle,
            },
            completion_callback=None,
            terminal_callback=on_terminal,
            graph=graph,
            capacity_reservation=capacity_reservation,
        )
    except BaseException as exc:
        await _settle_failed_book_launch(
            item=item,
            identity=identity,
            workspace_id=workspace_id,
            thread_id=thread_id,
            run_handle=run_handle,
            error=exc,
        )
        raise
    return {
        "workspace_id": workspace_id,
        "thread_id": thread_id,
        "run_id": run_id,
    }


async def cancel_book_job(*, job_id: str) -> dict[str, Any]:
    """Cancel the durable runtime first, then fence the business queue."""

    def runtime_identity(context: Mapping[str, Any]) -> tuple[str, str] | None:
        thread_id = context.get("thread_id")
        run_id = context.get("run_id")
        if thread_id is None or run_id is None:
            return None
        return str(thread_id), str(run_id)

    normalized_job_id = UUID(job_id)
    context = await request_book_job_cancel(job_id=normalized_job_id)
    if context is None:
        raise LookupError("Active textbook job was not found")
    durable_cancelled: set[tuple[str, str]] = set()
    initial_runtime = runtime_identity(context)
    if initial_runtime is not None:
        thread_id, run_id = initial_runtime
        await request_run_cancel(run_id, thread_id=thread_id)
        durable_cancelled.add(initial_runtime)
    activity_error: BookActivityWriteError | None = None
    try:
        result = await mark_book_job_cancelled(
            job_id=normalized_job_id,
            item_id=context.get("item_id"),
            attempt_token=context.get("attempt_token"),
        )
    except BookActivityWriteError as exc:
        activity_error = exc
        result = None
        runtime_contexts = []
    else:
        await publish_book_activity_hint(
            normalized_job_id, result.get("high_water_seq")
        )
        runtime_contexts = result.pop("runtime_contexts", [])
    signalled: set[tuple[str, str]] = set()
    for runtime_context in (context, *runtime_contexts):
        identity = runtime_identity(runtime_context)
        if identity is None or identity in signalled:
            continue
        thread_id, run_id = identity
        if identity not in durable_cancelled:
            await request_run_cancel(run_id, thread_id=thread_id)
            durable_cancelled.add(identity)
        await LocalRunExecutor.get_instance().signal_cancel(thread_id, run_id)
        await publish_cancel_nudge(thread_id, run_id)
        signalled.add(identity)
    if activity_error is not None:
        raise activity_error
    assert result is not None
    return result


class EducationBookJobService:
    """Small polling owner for the PostgreSQL-backed textbook item queue."""

    _instance: "EducationBookJobService | None" = None

    def __init__(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        poll_interval: float,
    ) -> None:
        self.worker_id = worker_id
        self.lease_seconds = lease_seconds
        self.poll_interval = poll_interval
        self._stop_event = asyncio.Event()
        self._loop_task: asyncio.Task[None] | None = None

    @classmethod
    def get_instance(cls) -> "EducationBookJobService":
        if cls._instance is None:
            from src.config.settings import (
                get_education_book_item_lease_seconds,
                get_education_book_job_poll_interval,
            )

            cls._instance = cls(
                worker_id=f"education-book:{os.getpid()}",
                lease_seconds=get_education_book_item_lease_seconds(),
                poll_interval=get_education_book_job_poll_interval(),
            )
        return cls._instance

    async def scan_once(self) -> int:
        from src.server.services.education_book_recovery import (
            reconcile_book_jobs_once,
        )

        await reconcile_book_jobs_once(
            worker_id=self.worker_id,
            lease_seconds=self.lease_seconds,
        )
        await cleanup_settled_book_items_once()
        from src.server.services.education_book_deletion import (
            cleanup_deleted_textbooks_once,
        )

        await cleanup_deleted_textbooks_once()
        executor = LocalRunExecutor.get_instance()
        capacity_reservation = await executor.reserve_capacity()
        if capacity_reservation is None:
            return 0
        try:
            item = await claim_next_book_item(
                worker_id=self.worker_id,
                lease_seconds=self.lease_seconds,
            )
            if item is None:
                return 0
            renewed = await renew_book_item_lease(
                item_id=item["item_id"],
                attempt_token=item["attempt_token"],
                worker_id=self.worker_id,
                lease_seconds=self.lease_seconds,
            )
            if not renewed:
                return 1
            launch_finished = asyncio.Event()
            lease_task = asyncio.create_task(
                self._renew_lease_during_launch(item=item, finished=launch_finished),
                name=f"education-book-launch-lease:{item['item_id']}",
            )
            try:
                await launch_book_item(
                    item=item,
                    capacity_reservation=capacity_reservation,
                )
            except Exception:
                logger.exception("Managed textbook item launch failed")
                try:
                    await fail_book_item(
                        item_id=item["item_id"],
                        attempt_token=item["attempt_token"],
                        safe_error="Managed textbook execution could not start",
                        stop_remaining=True,
                    )
                except RuntimeError:
                    pass
            finally:
                launch_finished.set()
                await lease_task
            return 1
        finally:
            await executor.release_capacity_reservation(capacity_reservation)

    async def _renew_lease_during_launch(
        self,
        *,
        item: Mapping[str, Any],
        finished: asyncio.Event,
    ) -> None:
        interval = max(self.lease_seconds / 3, 0.01)
        while not finished.is_set():
            try:
                await asyncio.wait_for(finished.wait(), timeout=interval)
                return
            except TimeoutError:
                pass
            try:
                renewed = await renew_book_item_lease(
                    item_id=item["item_id"],
                    attempt_token=item["attempt_token"],
                    worker_id=self.worker_id,
                    lease_seconds=self.lease_seconds,
                )
            except Exception:
                logger.exception("Managed textbook launch lease renewal failed")
                return
            if not renewed:
                return

    def start(self) -> None:
        if self._loop_task is not None and not self._loop_task.done():
            return
        self._stop_event = asyncio.Event()
        self._loop_task = asyncio.create_task(
            self._loop(),
            name="education-book-job-service",
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._loop_task is None:
            return
        self._loop_task.cancel()
        try:
            await self._loop_task
        except asyncio.CancelledError:
            pass
        self._loop_task = None

    async def _loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                processed = await self.scan_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Managed textbook queue scan failed")
                processed = 0
            if processed:
                continue
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.poll_interval,
                )
            except TimeoutError:
                pass
