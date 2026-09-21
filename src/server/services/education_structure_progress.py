"""Safe, high-level progress projection for textbook generation runs.

The raw run event stream contains model output, tool arguments and tool
results. None of that is safe or useful to render directly for a parent, so
this module maps the stream onto a short list of narrated progress steps:
which files were inspected, how many parallel unit workers were dispatched,
and whether the final structure was written. Raw chain-of-thought, prompts
and tool payloads never leave the server.
"""

from __future__ import annotations

from typing import Any, Mapping

from src.server.database.education_textbooks import (
    get_generation_job_for_parent,
    get_run_id_for_generation_job,
    get_run_sse_events,
)
from src.server.services.education_textbooks import (
    TextbookNotFoundError,
    TextbookPermissionError,
    get_household_context_for_parent,
)


_MAX_EVENTS = 80
_MAX_SEARCH_EVENTS = 240

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
    if any(marker in text[:400] for marker in ("not allowed in a managed", "outside the managed")):
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
    projected = sorted(deduped.values(), key=lambda item: (item["sequence"], item["count"]))
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
