"""Safe, high-level progress projection for textbook generation runs.

The raw run event stream contains model output, tool arguments and tool
results. None of that is safe or useful to render directly for a parent, so
this module maps the stream onto a short list of narrated progress steps:
which files were inspected, how many parallel unit workers were dispatched,
and whether the final structure was written. Raw chain-of-thought, prompts
and tool payloads never leave the server.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping
import unicodedata

from src.server.database.education_textbooks import (
    get_generation_job_for_parent,
    get_run_id_for_generation_job,
    get_run_sse_events,
    list_generation_progress_events,
)
from src.server.services.education_textbooks import (
    TextbookNotFoundError,
    TextbookPermissionError,
    get_household_context_for_parent,
)
from src.server.services.education_generation_progress import (
    is_accepted_progress_event,
)


_MAX_EVENTS = 80
_MAX_SEARCH_EVENTS = 240
_MAX_BOOK_STAGE_EVENTS = 8

BOOK_PIPELINE_STAGES = (
    ("chapter_analysis", "教材章节解析"),
    ("content_processing", "内容智能处理"),
    ("knowledge_point_generation", "知识点生成"),
    ("lesson_preparation", "课程制作"),
)
_BOOK_PIPELINE_STAGE_NAMES = frozenset(name for name, _ in BOOK_PIPELINE_STAGES)
_BOOK_PIPELINE_EVENT_STATUSES = frozenset(
    {"queued", "running", "completed", "failed", "skipped"}
)
_BOOK_PIPELINE_TERMINAL_STATUSES = frozenset({"completed", "failed", "skipped"})

_TOOL_LABELS = {
    "Read": "读取资料",
    "Write": "写入产物",
    "Edit": "修订产物",
    "Bash": "执行环境命令",
    "Glob": "扫描文件清单",
    "Grep": "检索章节信息",
    "Task": "派出并行子任务",
    "TaskOutput": "收集子任务结果",
}

_FILE_LABELS = {
    "inputs/manifest.json": "读取冻结输入清单",
    "outputs/structure.json": "生成教材结构草稿",
}

_IGNORED_PATH_MARKERS = (".agents/skills/", "/managed/")


def _basename(path: str) -> str:
    return path.replace("\\", "/").rstrip("/").split("/")[-1]


def _path_label(path: str) -> str | None:
    """Narrate a file operation without exposing the sandbox root."""
    normalized = path.replace("\\", "/")
    lowered = normalized.lower()
    for marker, label in _FILE_LABELS.items():
        if lowered.endswith(marker):
            return label
    if "/.agents/skills/" in normalized:
        return None
    if "/inputs/sources/" in normalized:
        return f"扫描源文档：{_basename(normalized)}"
    if "/outputs/" in normalized:
        return f"写入产物：{_basename(normalized)}"
    if "/inputs/assets/" in normalized:
        return "整理来源图片资源"
    if normalized.startswith("inputs/sources/"):
        return f"扫描源文档：{_basename(normalized)}"
    if normalized.startswith("outputs/"):
        return f"写入产物：{_basename(normalized)}"
    if any(marker in normalized for marker in _IGNORED_PATH_MARKERS):
        return None
    return f"处理文件：{_basename(normalized)}"


def _tool_progress(tool: Mapping[str, Any]) -> tuple[str, str | None] | None:
    name = str(tool.get("name") or "")
    if not name:
        return None
    args = tool.get("args")
    args = args if isinstance(args, Mapping) else {}
    if name in ("Read", "Write", "Edit"):
        path = str(args.get("file_path") or "")
        label = _path_label(path)
        if not label:
            return None
        return label, None
    if name == "Grep":
        pattern = str(args.get("pattern") or "")
        return "检索章节与知识点线索", f"匹配模式 {pattern}" if pattern else None
    if name == "Glob":
        pattern = str(args.get("pattern") or "")
        return "扫描可用源文件", pattern or None
    if name == "Task":
        return "派出并行子任务分析单元", None
    if name == "TaskOutput":
        return "收集子任务分析结果", None
    if name == "Bash":
        return "执行环境命令", None
    return name, None


def _run_status_from_result(status: Any, content: Any) -> str:
    if str(status or "").lower() in {"error", "failed", "failure"}:
        return "failed"
    text = str(content or "").strip().lower()
    if text.startswith("traceback"):
        return "failed"
    if any(
        marker in text[:400]
        for marker in ("not allowed in a managed", "outside the managed")
    ):
        return "skipped"
    if text.startswith("error:") or "failed to" in text[:200]:
        return "failed"
    return "completed"


def _progress_key(event: Mapping[str, Any], index: int) -> str:
    data = event.get("data")
    data = data if isinstance(data, Mapping) else {}
    key = data.get("tool_call_id") or data.get("artifact_id")
    if key:
        return str(key)
    return f"event-{index}"


def build_progress_events(events: list[Any]) -> tuple[list[dict[str, Any]], bool]:
    """Project raw run events onto narrated progress steps."""
    ordered: dict[str, dict[str, Any]] = {}
    dropped_history = False
    seen = 0
    for index, event in enumerate(events):
        if not isinstance(event, Mapping):
            continue
        name = event.get("event")
        if name not in ("tool_calls", "tool_call_result", "artifact"):
            continue
        seen += 1
        if seen > _MAX_SEARCH_EVENTS:
            dropped_history = True
        data = event.get("data")
        data = data if isinstance(data, Mapping) else {}
        timestamp = data.get("timestamp")
        timestamp = str(timestamp) if timestamp else None
        key = _progress_key(event, index)
        if name == "tool_calls":
            for offset, tool in enumerate(data.get("tool_calls") or []):
                if not isinstance(tool, Mapping):
                    continue
                projected = _tool_progress(tool)
                if not projected:
                    continue
                label, detail = projected
                if name == "Bash":
                    label = "执行环境命令"
                call_key = str(tool.get("id") or f"{key}-{offset}")
                entry = ordered.get(call_key)
                if entry is None:
                    entry = {
                        "sequence": index * 100 + offset,
                        "kind": "tool",
                        "label": label,
                        "detail": detail,
                        "status": "running",
                        "timestamp": timestamp,
                        "count": 1,
                    }
                    ordered[call_key] = entry
                else:
                    entry["sequence"] = max(entry["sequence"], index * 100 + offset)
                    entry["timestamp"] = timestamp or entry["timestamp"]
        elif name == "tool_call_result":
            entry = ordered.get(key)
            if entry is None:
                continue
            entry["status"] = _run_status_from_result(
                data.get("status"), data.get("content")
            )
            entry["sequence"] = max(entry["sequence"], index * 100)
            entry["timestamp"] = timestamp or entry["timestamp"]
        else:  # artifact
            artifact_type = str(data.get("artifact_type") or "")
            payload = data.get("payload")
            payload = payload if isinstance(payload, Mapping) else {}
            if artifact_type == "file_operation":
                label = _path_label(str(payload.get("file_path") or ""))
                if not label:
                    continue
                line_count = payload.get("line_count")
                ordered[str(data.get("artifact_id") or key)] = {
                    "sequence": index * 100,
                    "kind": "file",
                    "label": label,
                    "detail": f"{line_count} 行" if line_count else None,
                    "status": "completed",
                    "timestamp": timestamp,
                }
    deduped: dict[tuple[str, str, str], dict[str, Any]] = {}
    for entry in ordered.values():
        if entry["status"] == "running":
            key = (entry["label"], str(entry["detail"] or ""), entry["status"])
        else:
            key = (entry["label"], str(entry["detail"] or ""), "")
        existing = deduped.get(key)
        if existing is None:
            entry["count"] = 1
            deduped[key] = entry
            continue
        existing["count"] += 1
        existing["sequence"] = max(existing["sequence"], entry["sequence"])
        if entry["status"] == "failed":
            existing["status"] = "failed"
        if existing["timestamp"] is None:
            existing["timestamp"] = entry["timestamp"]
    projected = sorted(
        deduped.values(), key=lambda item: (item["sequence"], item["count"])
    )
    projected = projected[-_MAX_EVENTS:]
    for position, entry in enumerate(projected):
        entry["sequence"] = position
    if len(projected) == _MAX_EVENTS:
        dropped_history = True
    return projected, dropped_history


async def get_structure_progress_for_parent(
    *, parent_user_id: str, generation_job_id: str
) -> dict[str, Any]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can read textbook progress")
    job = await get_generation_job_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    if not job:
        raise TextbookNotFoundError("Textbook generation job not found")
    run = await get_run_id_for_generation_job(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    if not run or not run.get("root_run_id"):
        return {
            "generation_job_id": generation_job_id,
            "run_id": None,
            "status": str(job.get("status") or "queued"),
            "events": [],
            "truncated": False,
        }
    run_id = str(run["root_run_id"])
    events = await get_run_sse_events(run_id=run_id)
    projected, truncated = build_progress_events(events)
    return {
        "generation_job_id": generation_job_id,
        "run_id": run_id,
        "status": str(job.get("status") or "queued"),
        "events": projected,
        "truncated": truncated,
    }


def _progress_text(value: object, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    without_controls = "".join(
        character
        for character in text
        if not unicodedata.category(character).startswith("C")
    )
    return without_controls[:limit]


def _progress_optional_text(value: object, *, limit: int) -> str | None:
    normalized = _progress_text(value, limit=limit)
    return normalized or None


def _progress_integer(value: object, *, minimum: int = 0) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value if value >= minimum else None


def _book_progress_attempt_order(event: Mapping[str, Any]) -> tuple[str, str]:
    attempt_started_at = event.get("attempt_started_at")
    if isinstance(attempt_started_at, datetime):
        attempt_key = attempt_started_at.isoformat()
    else:
        attempt_key = str(attempt_started_at or "")
    return attempt_key, str(event.get("attempt_id") or "")


def _book_progress_event_order(event: Mapping[str, Any]) -> tuple[str, str, int]:
    sequence = _progress_integer(event.get("sequence"))
    return (
        *_book_progress_attempt_order(event),
        sequence if sequence is not None else 0,
    )


def _book_progress_is_fallback(event: Mapping[str, Any]) -> bool:
    metadata = event.get("metadata")
    return isinstance(metadata, Mapping) and metadata.get("fallback") is True


def _book_progress_effective_stage_events(
    stage_events: list[Mapping[str, Any]],
) -> tuple[list[Mapping[str, Any]], list[list[Mapping[str, Any]]]]:
    """Suppress fallback after terminal within each attempt, preserving attempt order."""
    attempt_groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for event in stage_events:
        attempt_key = _book_progress_attempt_order(event)
        attempt_events = attempt_groups.setdefault(attempt_key, [])
        terminal_seen = any(
            str(previous.get("status")) in _BOOK_PIPELINE_TERMINAL_STATUSES
            for previous in attempt_events
        )
        if terminal_seen and _book_progress_is_fallback(event):
            continue
        attempt_events.append(event)
    groups = list(attempt_groups.values())
    return [event for group in groups for event in group], groups


def _book_progress_event_projection(
    event: Mapping[str, Any],
) -> dict[str, Any]:
    created_at = event.get("created_at") or event.get("timestamp")
    if isinstance(created_at, datetime):
        timestamp = created_at.isoformat()
    else:
        timestamp = _progress_optional_text(created_at, limit=64)
    return {
        "sequence": _progress_integer(event.get("sequence")) or 0,
        "substage": _progress_optional_text(event.get("substage"), limit=64),
        "status": str(event.get("status") or "queued"),
        "label": _progress_text(event.get("label"), limit=200) or "处理中",
        "detail": _progress_optional_text(event.get("detail"), limit=1_000),
        "current": _progress_integer(event.get("current_value", event.get("current"))),
        "total": _progress_integer(event.get("total_value", event.get("total"))),
        "timestamp": timestamp,
    }


def _book_stage_lifecycle_status(
    *,
    stage_name: str,
    job_status: str,
    all_stages_empty: bool,
) -> str:
    if not all_stages_empty:
        return "queued"
    if job_status == "awaiting_review":
        return "completed" if stage_name == "chapter_analysis" else "queued"
    if job_status == "completed":
        return "queued" if stage_name == "lesson_preparation" else "completed"
    return "queued"


def build_book_pipeline_progress(
    *,
    job: Mapping[str, Any],
    events: list[Mapping[str, Any]],
    truncated: bool = False,
    include_sse_cursor: bool = False,
) -> dict[str, Any]:
    """Project durable book-pipeline events onto the fixed parent-facing timeline."""
    ordered = sorted(events, key=_book_progress_event_order)
    events_by_stage: dict[str, list[Mapping[str, Any]]] = {
        name: [] for name, _ in BOOK_PIPELINE_STAGES
    }
    last_ordered_event: Mapping[str, Any] | None = None
    for event in ordered:
        if not is_accepted_progress_event(event):
            continue
        stage_name = str(event.get("stage") or "")
        status = str(event.get("status") or "")
        if (
            stage_name not in _BOOK_PIPELINE_STAGE_NAMES
            or status not in _BOOK_PIPELINE_EVENT_STATUSES
        ):
            continue
        events_by_stage[stage_name].append(event)
        last_ordered_event = event

    all_stages_empty = not any(events_by_stage.values())
    job_status = str(job.get("status") or "queued")
    stages: list[dict[str, Any]] = []
    for stage_name, label in BOOK_PIPELINE_STAGES:
        effective_events, attempt_groups = _book_progress_effective_stage_events(
            events_by_stage[stage_name]
        )
        if attempt_groups:
            latest_attempt_events = attempt_groups[-1]
            stage_status = str(latest_attempt_events[-1].get("status"))
        else:
            latest_attempt_events = []
            stage_status = _book_stage_lifecycle_status(
                stage_name=stage_name,
                job_status=job_status,
                all_stages_empty=all_stages_empty,
            )

        latest_counts: Mapping[str, Any] | None = None
        for event in reversed(latest_attempt_events):
            if (
                _progress_integer(event.get("current_value", event.get("current")))
                is not None
                or _progress_integer(event.get("total_value", event.get("total")))
                is not None
            ):
                latest_counts = event
                break

        stages.append(
            {
                "name": stage_name,
                "label": label,
                "status": stage_status,
                "current": (
                    _progress_integer(
                        latest_counts.get(
                            "current_value",
                            latest_counts.get("current"),
                        )
                    )
                    if latest_counts is not None
                    else None
                ),
                "total": (
                    _progress_integer(
                        latest_counts.get(
                            "total_value",
                            latest_counts.get("total"),
                        )
                    )
                    if latest_counts is not None
                    else None
                ),
                "events": [
                    _book_progress_event_projection(event)
                    for event in effective_events[-_MAX_BOOK_STAGE_EVENTS:]
                ],
            }
        )

    last_sequence = (
        _progress_integer(last_ordered_event.get("sequence"))
        if last_ordered_event is not None
        else None
    )
    return {
        "job_id": job.get("generation_job_id"),
        "status": job_status,
        "error_code": job.get("error_code"),
        "error_message": job.get("error_message"),
        "stages": stages,
        "last_sequence": last_sequence or 0,
        "truncated": truncated,
        **(
            {
                "_sse_cursor": (
                    f"{last_ordered_event.get('attempt_id')}:{last_sequence or 0}"
                    if last_ordered_event is not None
                    else "0:0"
                )
            }
            if include_sse_cursor
            else {}
        ),
    }


async def get_book_pipeline_progress_for_parent(
    *,
    parent_user_id: str,
    generation_job_id: str,
    include_sse_cursor: bool = False,
) -> dict[str, Any]:
    """Read the durable four-stage projection for one parent-owned pipeline job."""
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError(
            "Only a parent can read textbook processing progress"
        )
    job = await get_generation_job_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    if not job or job.get("scope") != "book_pipeline":
        raise TextbookNotFoundError("Textbook processing job not found")
    events = await list_generation_progress_events(generation_job_id=generation_job_id)
    truncated = bool(events[0].get("progress_truncated")) if events else False
    return build_book_pipeline_progress(
        job=job,
        events=events,
        truncated=truncated,
        include_sse_cursor=include_sse_cursor,
    )
