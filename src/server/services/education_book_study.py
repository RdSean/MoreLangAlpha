"""Lesson reading and parent contextual Flash chat, isolated from the runtime."""

from src.server.database.education_book_study import get_study_space, list_reading_states, mark_reading_state
from src.server.models.additional_context import DirectiveContext
from src.server.services.education_textbooks import (
    TextbookNotFoundError, get_managed_textbook_structure, get_managed_knowledge_point_material,
)


async def _lesson(*, user_id: str, textbook_id: str, knowledge_point_id: str):
    structure = await get_managed_textbook_structure(user_id=user_id, textbook_id=textbook_id)
    point = next((p for p in structure["knowledge_points"] if str(p["knowledge_point_id"]) == knowledge_point_id), None)
    if not point:
        raise TextbookNotFoundError("Current lesson not found")
    material = await get_managed_knowledge_point_material(user_id=user_id, textbook_id=textbook_id, knowledge_point_id=knowledge_point_id)
    if not material.get("material_available") or not material.get("markdown"):
        raise TextbookNotFoundError("Learning material is unavailable")
    return point, material


async def get_book_reading_states(*, user_id: str, textbook_id: str):
    await get_managed_textbook_structure(user_id=user_id, textbook_id=textbook_id)
    return await list_reading_states(user_id=user_id, textbook_id=textbook_id)


async def record_book_reading(*, user_id: str, textbook_id: str, knowledge_point_id: str, state: str):
    await _lesson(user_id=user_id, textbook_id=textbook_id, knowledge_point_id=knowledge_point_id)
    if not await mark_reading_state(user_id=user_id, textbook_id=textbook_id, knowledge_point_id=knowledge_point_id, state=state):
        raise TextbookNotFoundError("Reading target not found")


async def get_book_study_space(*, user_id: str, textbook_id: str, knowledge_point_id: str):
    await _lesson(user_id=user_id, textbook_id=textbook_id, knowledge_point_id=knowledge_point_id)
    space = await get_study_space(user_id=user_id, textbook_id=textbook_id, knowledge_point_id=knowledge_point_id, create=True)
    if not space:
        raise TextbookNotFoundError("Parent lesson conversation not found")
    return space


async def attach_book_study_context(*, user_id: str, textbook_id: str, knowledge_point_id: str, thread_id: str):
    point, material = await _lesson(user_id=user_id, textbook_id=textbook_id, knowledge_point_id=knowledge_point_id)
    space = await get_study_space(user_id=user_id, textbook_id=textbook_id, knowledge_point_id=knowledge_point_id)
    if not space or str(space["conversation_thread_id"]) != thread_id:
        raise TextbookNotFoundError("Learning conversation not found")
    return [DirectiveContext(content=f"# {point['title']}\n\n以下是本轮当前讲义。依据这份材料解释和引导学习，无法从材料确认的内容请明确说明。\n\n{material['markdown']}")]


async def get_book_study_history(*, user_id: str, textbook_id: str, knowledge_point_id: str, assignment_id: str | None = None):
    from src.server.database.conversation import get_replay_thread_data
    from src.server.services.education_learning_transcript import _get_replay_items, _messages_from_replay_items

    point, _ = await _lesson(user_id=user_id, textbook_id=textbook_id, knowledge_point_id=knowledge_point_id)
    if assignment_id:
        from src.server.services.education_textbooks import get_student_structure
        from src.server.database.education_learning import get_student_learning_space
        structure = await get_student_structure(student_user_id=user_id, assignment_id=assignment_id)
        if str(structure["textbook_id"]) != textbook_id:
            raise TextbookNotFoundError("Learning assignment not found")
        space = await get_student_learning_space(student_user_id=user_id, assignment_id=assignment_id)
    else:
        space = await get_study_space(user_id=user_id, textbook_id=textbook_id, knowledge_point_id=knowledge_point_id)
    if not space:
        return []
    thread_id = str(space["conversation_thread_id"])
    owner, thread, queries, responses, usages, provenance = await get_replay_thread_data(thread_id)
    if owner != user_id or not thread:
        raise TextbookNotFoundError("Learning conversation not found")
    items = await _get_replay_items(thread_id, thread, queries, responses, usages, provenance)
    if assignment_id:
        turns = {
            q["turn_index"] for q in queries
            if (q.get("metadata") or {}).get("education_knowledge_point_id") == knowledge_point_id
            or any(c.get("content", "").startswith(f"# {point['title']}\n")
                   for c in (q.get("metadata") or {}).get("additional_context", []) if isinstance(c, dict))
        }
        items = [item for item in items if (item.get("data") or {}).get("turn_index") in turns]
    items = [item for item in items if item.get("event") != "message_chunk"
             or (item.get("data") or {}).get("content_type", "text") == "text"]
    return _messages_from_replay_items(items)
