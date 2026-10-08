from unittest.mock import AsyncMock

import pytest

from src.server.services import education_book_study as study
from src.server.services.education_textbooks import TextbookNotFoundError


@pytest.mark.asyncio
async def test_context_uses_authorized_material_and_bound_thread(monkeypatch):
    monkeypatch.setattr(study, "get_managed_textbook_structure", AsyncMock(return_value={
        "knowledge_points": [{"knowledge_point_id": "kp", "title": "Lesson"}]
    }))
    monkeypatch.setattr(study, "get_managed_knowledge_point_material", AsyncMock(return_value={
        "material_available": True, "markdown": "Frozen lesson"
    }))
    monkeypatch.setattr(study, "get_study_space", AsyncMock(return_value={
        "conversation_thread_id": "thread"
    }))
    context = await study.attach_book_study_context(
        user_id="parent", textbook_id="book", knowledge_point_id="kp", thread_id="thread"
    )
    assert "Frozen lesson" in context[0].content
    with pytest.raises(TextbookNotFoundError):
        await study.attach_book_study_context(
            user_id="parent", textbook_id="book", knowledge_point_id="kp", thread_id="foreign"
        )


@pytest.mark.asyncio
async def test_unavailable_material_cannot_create_study_chat(monkeypatch):
    monkeypatch.setattr(study, "get_managed_textbook_structure", AsyncMock(return_value={
        "knowledge_points": [{"knowledge_point_id": "kp", "title": "Lesson"}]
    }))
    monkeypatch.setattr(study, "get_managed_knowledge_point_material", AsyncMock(return_value={
        "material_available": False, "markdown": None
    }))
    space = AsyncMock()
    monkeypatch.setattr(study, "get_study_space", space)
    with pytest.raises(TextbookNotFoundError):
        await study.attach_book_study_context(
            user_id="student", textbook_id="book", knowledge_point_id="kp", thread_id="thread"
        )
    space.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("assignment", [None, "assignment"])
async def test_history_filters_reasoning_and_other_student_lessons(monkeypatch, assignment):
    from src.server.database import conversation, education_learning
    from src.server.services import education_learning_transcript, education_textbooks

    monkeypatch.setattr(study, "_lesson", AsyncMock(return_value=({"title": "Lesson"}, {})))
    space = {"conversation_thread_id": "thread"}
    monkeypatch.setattr(study, "get_study_space", AsyncMock(return_value=space))
    monkeypatch.setattr(education_learning, "get_student_learning_space", AsyncMock(return_value=space))
    monkeypatch.setattr(education_textbooks, "get_student_structure", AsyncMock(return_value={"textbook_id": "book"}))
    queries = [{"turn_index": 1, "metadata": {"education_knowledge_point_id": "kp"}}]
    monkeypatch.setattr(conversation, "get_replay_thread_data", AsyncMock(return_value=("owner", {"title": "Lesson"}, queries, [], [], [])))
    items = [
        {"event": "user_message", "data": {"turn_index": 1, "content": "Question"}},
        {"event": "message_chunk", "data": {"turn_index": 1, "role": "assistant", "content_type": "reasoning", "content": "Internal"}},
        {"event": "message_chunk", "data": {"turn_index": 1, "role": "assistant", "content_type": "text", "content": "Answer"}},
    ]
    if assignment:
        items.append({"event": "user_message", "data": {"turn_index": 2, "content": "Other lesson"}})
    monkeypatch.setattr(education_learning_transcript, "_get_replay_items", AsyncMock(return_value=items))
    result = await study.get_book_study_history(user_id="owner", textbook_id="book", knowledge_point_id="kp", assignment_id=assignment)
    assert [(m["role"], m["content"]) for m in result] == [("user", "Question"), ("assistant", "Answer")]


@pytest.mark.asyncio
async def test_student_cannot_create_parent_lesson_space(monkeypatch):
    monkeypatch.setattr(study, "_lesson", AsyncMock(return_value=({}, {})))
    monkeypatch.setattr(study, "get_study_space", AsyncMock(return_value=None))
    with pytest.raises(TextbookNotFoundError):
        await study.get_book_study_space(user_id="student", textbook_id="book", knowledge_point_id="kp")


@pytest.mark.asyncio
async def test_conversation_replay_preserves_unindexed_cards_and_isolates_lessons(monkeypatch):
    from src.server.database import conversation, education_learning
    from src.server.services import education_learning_transcript, education_textbooks

    monkeypatch.setattr(education_textbooks, "get_student_structure", AsyncMock(return_value={
        "textbook_id": "book", "knowledge_points": [{"knowledge_point_id": "kp", "title": "Lesson"}]
    }))
    monkeypatch.setattr(education_learning, "get_student_learning_space", AsyncMock(return_value={"conversation_thread_id": "thread"}))
    queries = [
        {"turn_index": 1, "metadata": {"education_knowledge_point_id": "kp"}},
        {"turn_index": 2, "metadata": {"education_knowledge_point_id": "other"}},
    ]
    monkeypatch.setattr(conversation, "get_replay_thread_data", AsyncMock(return_value=("student", {}, queries, [], [], [])))
    # Thread records are nonempty in production.
    conversation.get_replay_thread_data.return_value = ("student", {"thread_id": "thread"}, queries, [], [], [])
    items = [
        {"event": "user_message", "data": {"turn_index": 1, "content": "Why?"}},
        {"event": "interrupt", "data": {"interrupt_id": "stable-card"}},
        {"event": "artifact", "data": {"artifact_type": "html_widget", "artifact_id": "widget"}},
        {"event": "user_message", "data": {"turn_index": 2, "content": "Other"}},
        {"event": "interrupt", "data": {"interrupt_id": "other-card"}},
    ]
    monkeypatch.setattr(education_learning_transcript, "_get_replay_items", AsyncMock(return_value=items))
    result = await study.get_book_conversation_replay(user_id="student", textbook_id="book", knowledge_point_id="kp", assignment_id="assignment")
    assert result == items[:3]
    assert result[1]["data"]["interrupt_id"] == "stable-card"
    with pytest.raises(TextbookNotFoundError):
        await study.get_book_conversation_replay(user_id="stranger", textbook_id="book", knowledge_point_id="kp", assignment_id="assignment")


@pytest.mark.asyncio
async def test_continuation_restores_original_lesson_not_current_selection(monkeypatch):
    from src.server.database import conversation
    from src.server.models.chat import ChatRequest

    monkeypatch.setattr(conversation, "get_thread_by_id", AsyncMock(return_value={
        "metadata": {"education": {"textbook_id": "book", "knowledge_point_id": "kp"}}
    }))
    monkeypatch.setattr(conversation, "get_queries_for_thread", AsyncMock(return_value=([
        {"turn_index": 1, "metadata": {"education_knowledge_point_id": "kp"}}
    ], 1)))
    request = ChatRequest(workspace_id="ws", messages=[], hitl_response={"card": {"decisions": [{"type": "approve"}]}})
    result = await study.restore_book_continuation_context(request=request, thread_id="thread")
    assert result.education_textbook_id == "book"
    assert result.education_knowledge_point_id == "kp"
    fresh = await study.restore_book_continuation_context(request=ChatRequest(workspace_id="ws", messages=[{"role": "user", "content": "Next question"}]), thread_id="thread")
    assert fresh.education_textbook_id == "book"
    assert fresh.education_knowledge_point_id == "kp"
    with pytest.raises(TextbookNotFoundError):
        await study.restore_book_continuation_context(request=request.model_copy(update={"education_knowledge_point_id": "other"}), thread_id="thread")


@pytest.mark.asyncio
async def test_student_status_never_attaches_another_lesson_run(monkeypatch):
    from src.server.database import conversation, education_learning
    from src.server.services import education_textbooks, thread_status
    monkeypatch.setattr(education_textbooks, "get_student_structure", AsyncMock(return_value={
        "textbook_id": "book", "knowledge_points": [{"knowledge_point_id": "kp", "title": "Lesson"}]
    }))
    monkeypatch.setattr(education_learning, "get_student_learning_space", AsyncMock(return_value={"conversation_thread_id": "thread"}))
    queries = [{"turn_index": 2, "metadata": {"education_knowledge_point_id": "other"}}]
    monkeypatch.setattr(conversation, "get_replay_thread_data", AsyncMock(return_value=("student", {"msg_type": "flash"}, queries, [], [], [])))
    monkeypatch.setattr(thread_status, "read_thread_runtime_status", AsyncMock(return_value={
        "status": "interrupted", "can_reconnect": True, "run_id": "other-run", "latest_turn_index": 2,
        "active_tasks": ["other-task"], "pending_report_back": True,
    }))
    result = await study.get_book_conversation_status(user_id="student", textbook_id="book", knowledge_point_id="kp", assignment_id="assignment")
    assert result["can_reconnect"] is False
    assert result["active_tasks"] == []
    assert result["pending_report_back"] is False
    assert result["lesson_active"] is False


@pytest.mark.asyncio
async def test_student_retry_restores_and_validates_original_assignment(monkeypatch):
    from src.server.database import conversation
    from src.server.models.chat import ChatRequest

    monkeypatch.setattr(conversation, "get_thread_by_id", AsyncMock(return_value={
        "metadata": {"education": {"assignment_id": "assignment"}}
    }))
    monkeypatch.setattr(conversation, "get_queries_for_thread", AsyncMock(return_value=([
        {"turn_index": 2, "metadata": {"education_knowledge_point_id": "original"}},
        {"turn_index": 1, "metadata": {"education_knowledge_point_id": "previous"}},
    ], 2)))
    retry = ChatRequest(workspace_id="ws", messages=[], retry_of_run_id="run")
    restored = await study.restore_book_continuation_context(request=retry, thread_id="thread")
    assert restored.education_assignment_id == "assignment"
    assert restored.education_knowledge_point_id == "original"
    assert restored.agent_mode == "flash"
    with pytest.raises(TextbookNotFoundError):
        await study.restore_book_continuation_context(request=retry.model_copy(update={"education_knowledge_point_id": "previous"}), thread_id="thread")
