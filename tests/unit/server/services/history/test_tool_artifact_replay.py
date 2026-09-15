"""A tool's artifact must survive into history replay.

This is the assumption the chat card for `get_homework_schedule` rests on. The
card renders the artifact rather than fetching anything, so if the artifact did
not come back when a thread is reopened, that card — and any future one built
the same way — would be blank on every reload while looking fine live.

The projector derives its own `artifact` SSE events for a few tools
(`_ARTIFACT_FROM_TOOL_MESSAGE`: widgets, preview URLs, chart annotations). Those
are a *different* channel from the tool message's own artifact, and the existing
tests only covered that derived channel. This pins the one the cards read.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, ToolMessage

from src.server.services.history.projector import (
    history_events_to_sse,
    messages_to_history_events,
)

THREAD_ID = "thread-artifact"

HOMEWORK_ARTIFACT = {
    "type": "homework_schedule",
    "window": "2w",
    "start_date": "2026-09-12",
    "end_date": "2026-09-25",
    "timezone": "Asia/Tokyo",
    "stats": {
        "today_count": 1,
        "week_count": 2,
        "overdue_count": 0,
        "completed_count": 0,
    },
    "days": [
        {
            "date": "2026-09-12",
            "task_count": 1,
            "completed_count": 0,
            "overdue_count": 0,
            "tasks": [
                {
                    "task_id": "task-1",
                    "task_rule_id": "rule-1",
                    "household_id": "household-1",
                    "assigned_student_id": "student-1",
                    "occurrence_date": "2026-09-12",
                    "due_at": "2026-09-12T10:30:00Z",
                    "title": "语文预习",
                    "description": "",
                    "subject_code": "chinese",
                    "subject_color": "#D95D39",
                    "type_code": "preview",
                    "practice_source_code": None,
                    "grade_code": "g6",
                    "status": "open",
                    "completed_at": None,
                    "created_at": None,
                    "is_completed": False,
                    "is_overdue": False,
                }
            ],
        }
    ],
    "student_names": {"student-1": "henry"},
}


def _replay(messages):
    return history_events_to_sse(
        messages_to_history_events(messages, agent="main"), thread_id=THREAD_ID
    )


def _tool_result_event(items):
    return next(i for i in items if i["event"] == "tool_call_result")


def test_a_tool_artifact_comes_back_on_replay():
    messages = [
        AIMessage(
            content="",
            id="ai-1",
            tool_calls=[
                {
                    "name": "get_homework_schedule",
                    "args": {"window": "2w"},
                    "id": "tc-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(
            content="Homework schedule: …",
            tool_call_id="tc-1",
            artifact=HOMEWORK_ARTIFACT,
        ),
    ]

    event = _tool_result_event(_replay(messages))

    # The card reads exactly this field. If it is absent, the transcript shows
    # nothing on reload.
    assert event["data"]["artifact"] == HOMEWORK_ARTIFACT


def test_a_tool_without_an_artifact_does_not_gain_one():
    # The projector must not invent an `artifact` key for tools that never had
    # one — the card dispatch treats its presence as "render this".
    messages = [
        AIMessage(
            content="",
            id="ai-1",
            tool_calls=[
                {
                    "name": "Read",
                    "args": {"file_path": "/x"},
                    "id": "tc-1",
                    "type": "tool_call",
                }
            ],
        ),
        ToolMessage(content="file body", tool_call_id="tc-1"),
    ]

    assert "artifact" not in _tool_result_event(_replay(messages))["data"]
