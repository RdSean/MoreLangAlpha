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


async def _book_conversation_source(*, user_id: str, textbook_id: str,
                                    knowledge_point_id: str, assignment_id: str | None = None):
    """Resolve current lesson authorization and the durable owner-bound thread."""
    from src.server.database.conversation import get_replay_thread_data

    if assignment_id:
        from src.server.database.education_learning import get_student_learning_space
        from src.server.services.education_textbooks import get_student_structure
        structure = await get_student_structure(student_user_id=user_id, assignment_id=assignment_id)
        if str(structure["textbook_id"]) != textbook_id:
            raise TextbookNotFoundError("Learning assignment not found")
        point = next((p for p in structure["knowledge_points"]
                      if str(p["knowledge_point_id"]) == knowledge_point_id), None)
        if not point:
            raise TextbookNotFoundError("Learning lesson not found")
        space = await get_student_learning_space(student_user_id=user_id, assignment_id=assignment_id)
    else:
        point, _ = await _lesson(user_id=user_id, textbook_id=textbook_id, knowledge_point_id=knowledge_point_id)
        space = await get_study_space(user_id=user_id, textbook_id=textbook_id, knowledge_point_id=knowledge_point_id)
    if not space:
        return None
    thread_id = str(space["conversation_thread_id"])
    owner, thread, queries, responses, usages, provenance = await get_replay_thread_data(thread_id)
    if owner != user_id or not thread:
        raise TextbookNotFoundError("Learning conversation not found")
    return point, thread_id, thread, queries, responses, usages, provenance


async def get_book_conversation_replay(*, user_id: str, textbook_id: str,
                                      knowledge_point_id: str, assignment_id: str | None = None):
    """Authorized structured replay; preserve the canonical event/card identities."""
    from src.server.services.education_learning_transcript import _get_replay_items

    source = await _book_conversation_source(user_id=user_id, textbook_id=textbook_id,
        knowledge_point_id=knowledge_point_id, assignment_id=assignment_id)
    if source is None:
        return []
    point, thread_id, thread, queries, responses, usages, provenance = source
    items = await _get_replay_items(thread_id, thread, queries, responses, usages, provenance)
    if not assignment_id:
        # Parent spaces are already bound to a single knowledge point.
        return items
    turns = set()
    for query in queries:
        metadata = query.get("metadata") or {}
        kp = metadata.get("education_knowledge_point_id")
        legacy = not kp and any(
            isinstance(c, dict) and c.get("content", "").startswith(f"# {point['title']}\n")
            for c in metadata.get("additional_context", [])
        )
        if kp == knowledge_point_id or legacy:
            turns.add(query["turn_index"])
    # Canonical replay is ordered by causal turn; trailing unindexed tip
    # interrupts belong to that final turn, not to whichever lesson is open.
    run_turns = {str(r["conversation_response_id"]): r.get("turn_index")
                 for r in responses if r.get("conversation_response_id")}
    selected = []
    active_turn = None
    for item in items:
        data = item.get("data") or {}
        turn = data.get("turn_index")
        if turn is None and data.get("run_id"):
            turn = run_turns.get(str(data["run_id"]))
        if turn is not None:
            active_turn = turn
        if (turn if turn is not None else active_turn) in turns:
            selected.append(item)
    return selected


async def get_book_conversation_status(*, user_id: str, textbook_id: str,
                                      knowledge_point_id: str, assignment_id: str | None = None):
    from src.server.services.thread_status import read_thread_runtime_status

    source = await _book_conversation_source(user_id=user_id, textbook_id=textbook_id,
        knowledge_point_id=knowledge_point_id, assignment_id=assignment_id)
    if source is None:
        return {"status": "completed", "can_reconnect": False, "lesson_active": False}
    _, thread_id, thread, queries, _, _, _ = source
    status = await read_thread_runtime_status(thread_id, msg_type=thread.get("msg_type"))
    latest = next((q for q in reversed(queries) if q.get("turn_index") == status.get("latest_turn_index")), {})
    matches = not assignment_id or (latest.get("metadata") or {}).get("education_knowledge_point_id") == knowledge_point_id
    if not matches:
        return {**status, "can_reconnect": False, "status": "completed", "active_tasks": [],
                "pending_report_back": False, "report_back_run_id": None, "lesson_active": False,
                "lesson_blocked": bool(status.get("can_reconnect") or status.get("status") == "interrupted")}
    return {**status, "lesson_active": True}


async def restore_book_continuation_context(*, request, thread_id: str):
    """Recover education references from durable data after the owner gate.

    This does not grant access: messaging still resolves current material and
    validates the mapped thread through the ordinary education authorization.
    """
    from src.server.database.conversation import get_queries_for_thread, get_thread_by_id

    thread = await get_thread_by_id(thread_id)
    education = ((thread or {}).get("metadata") or {}).get("education") or {}
    if not education:
        return request
    fields = {}
    if education.get("textbook_id"):
        fields = {"education_textbook_id": education["textbook_id"],
                  "education_knowledge_point_id": education.get("knowledge_point_id")}
    elif education.get("assignment_id"):
        if not request.hitl_response and not request.retry_of_run_id:
            return request
        queries, _ = await get_queries_for_thread(thread_id)
        latest = max(queries, key=lambda q: (q.get("turn_index", -1), str(q.get("created_at") or "")), default={})
        kp = (latest.get("metadata") or {}).get("education_knowledge_point_id")
        if not kp:
            raise TextbookNotFoundError("Original learning context is unavailable")
        fields = {"education_assignment_id": education["assignment_id"],
                  "education_knowledge_point_id": kp}
    for name in ("education_textbook_id", "education_assignment_id", "education_knowledge_point_id"):
        supplied = getattr(request, name, None)
        if supplied and supplied != fields.get(name):
            raise TextbookNotFoundError("Learning continuation context changed")
    return request.model_copy(update={**fields, "agent_mode": "flash"})
