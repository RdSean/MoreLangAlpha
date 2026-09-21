"""Safe progress projection for textbook structure runs."""

import json

import pytest

from src.server.services import education_structure_progress
from src.server.services.education_textbooks import TextbookPermissionError


def _call(call_id: str, name: str, args: dict, timestamp: str = "t1") -> dict:
    return {
        "event": "tool_calls",
        "data": {
            "timestamp": timestamp,
            "tool_calls": [{"id": call_id, "name": name, "args": args}],
        },
    }


def _result(call_id: str, status: str = "success", content: str = "ok") -> dict:
    return {
        "event": "tool_call_result",
        "data": {
            "tool_call_id": call_id,
            "status": status,
            "content": content,
        },
    }


def test_projects_narrated_steps_and_never_leaks_payloads():
    secret = "SUPER-SECRET-TOOL-OUTPUT"
    events = [
        _call("c1", "Glob", {"pattern": "inputs/sources/*"}),
        _call("c2", "Read", {"file_path": "inputs/sources/01-rex.md"}, "t2"),
        _result("c2", content=secret),
        _call("c3", "Task", {"prompt": secret}, "t3"),
        {
            "event": "artifact",
            "data": {
                "artifact_id": "a1",
                "artifact_type": "file_operation",
                "timestamp": "t4",
                "payload": {
                    "file_path": "outputs/structure.json",
                    "line_count": 3165,
                    "content": secret,
                },
            },
        },
    ]

    projected, truncated = education_structure_progress.build_progress_events(events)

    assert truncated is False
    labels = [item["label"] for item in projected]
    assert labels == [
        "扫描可用源文件",
        "扫描源文档：01-rex.md",
        "派出并行子任务分析单元",
        "生成教材结构草稿",
    ]
    assert projected[1]["status"] == "completed"
    assert projected[2]["status"] == "running"
    assert projected[3]["detail"] == "3165 行"
    assert all(item["count"] == 1 for item in projected)
    serialized = json.dumps(projected, ensure_ascii=False)
    assert secret not in serialized
    assert "/managed/textbook-job" not in serialized


def test_marks_failed_tool_calls_and_hides_skill_reads():
    events = [
        _call("c1", "Read", {"file_path": "/managed/job/.agents/skills/book-to-skill/SKILL.md"}),
        _call("c2", "Write", {"file_path": "outputs/structure.json"}, "t2"),
        _result("c2", status="error", content="boom"),
    ]

    projected, _ = education_structure_progress.build_progress_events(events)

    assert [item["label"] for item in projected] == ["生成教材结构草稿"]
    assert projected[0]["status"] == "failed"


def test_merges_repeated_steps_and_marks_policy_rejections_skipped():
    events = []
    for index in range(4):
        events.append(_call(f"task-{index}", "Task", {"prompt": "unit"}))
        events.append(_result(f"task-{index}"))
    events.append(_call("bash-1", "Bash", {"command": "ls"}))
    events.append(
        _result(
            "bash-1",
            status="success",
            content="ERROR: command is not allowed in a managed textbook run",
        )
    )

    projected, _ = education_structure_progress.build_progress_events(events)

    by_label = {item["label"]: item for item in projected}
    assert by_label["派出并行子任务分析单元"]["count"] == 4
    assert by_label["执行环境命令"]["status"] == "skipped"


def test_caps_projected_events_and_flags_truncation():
    events = [
        _call(f"c{index}", "Read", {"file_path": f"inputs/sources/{index}.md"})
        for index in range(education_structure_progress._MAX_EVENTS + 5)
    ]

    projected, truncated = education_structure_progress.build_progress_events(events)

    assert len(projected) == education_structure_progress._MAX_EVENTS
    assert projected[0]["sequence"] == 0
    assert truncated is True


@pytest.mark.asyncio
async def test_progress_requires_parent(monkeypatch):
    async def no_household(_user_id: str):
        return None

    monkeypatch.setattr(
        education_structure_progress,
        "get_household_context_for_parent",
        no_household,
    )

    with pytest.raises(TextbookPermissionError):
        await education_structure_progress.get_structure_progress_for_parent(
            parent_user_id="student-1",
            generation_job_id="generation-1",
        )
