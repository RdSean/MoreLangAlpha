"""Read-only student learning chat transcript contracts."""

from unittest.mock import AsyncMock

import pytest

from src.server.services import education_learning_transcript
from src.server.services.education_textbooks import TextbookNotFoundError


@pytest.mark.asyncio
async def test_parent_transcript_uses_only_the_assignment_mapped_thread(monkeypatch):
    get_space = AsyncMock(
        return_value={
            "assignment_id": "assignment-1",
            "student_user_id": "student-1",
            "conversation_thread_id": "thread-1",
            "textbook_title": "英语第二册",
        }
    )
    replay_rows = AsyncMock(
        return_value=(
            "student-1",
            {"conversation_thread_id": "thread-1"},
            [],
            [],
            [],
            [],
        )
    )
    monkeypatch.setattr(
        education_learning_transcript, "get_parent_learning_space", get_space
    )
    monkeypatch.setattr(
        education_learning_transcript, "get_replay_thread_data", replay_rows
    )
    monkeypatch.setattr(
        education_learning_transcript,
        "_get_transcript_replay_items",
        AsyncMock(
            return_value=[
                {
                    "event": "user_message",
                    "data": {"content": "这一章的重点是什么？", "timestamp": "t1"},
                },
                {
                    "event": "message_chunk",
                    "data": {
                        "role": "assistant",
                        "content": "重点是",
                        "timestamp": "t2",
                    },
                },
                {
                    "event": "message_chunk",
                    "data": {
                        "role": "assistant",
                        "content": "理解课文。",
                        "timestamp": "t2",
                    },
                },
            ]
        ),
    )

    transcript = await education_learning_transcript.get_parent_learning_transcript(
        parent_user_id="parent-1", assignment_id="assignment-1"
    )

    assert transcript["conversation_thread_id"] == "thread-1"
    assert transcript["messages"] == [
        {"role": "user", "content": "这一章的重点是什么？", "timestamp": "t1"},
        {"role": "assistant", "content": "重点是理解课文。", "timestamp": "t2"},
    ]
    get_space.assert_awaited_once_with(
        parent_user_id="parent-1", assignment_id="assignment-1"
    )
    replay_rows.assert_awaited_once_with("thread-1")


@pytest.mark.asyncio
async def test_parent_transcript_rejects_an_unrelated_assignment(monkeypatch):
    monkeypatch.setattr(
        education_learning_transcript,
        "get_parent_learning_space",
        AsyncMock(return_value=None),
    )

    with pytest.raises(TextbookNotFoundError):
        await education_learning_transcript.get_parent_learning_transcript(
            parent_user_id="parent-1", assignment_id="foreign-assignment"
        )
