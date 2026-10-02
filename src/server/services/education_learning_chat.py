"""Server-owned contextual material for student Flash learning conversations."""

from typing import Any

from src.server.services.education_textbooks import (
    TextbookError,
    get_student_kp_lesson,
    get_student_structure,
)
from src.server.database.education_learning import (
    get_or_create_student_learning_space,
    get_student_learning_space_for_thread,
)


class EducationLearningChatContextError(ValueError):
    """The client supplied an incomplete or unauthorized learning context reference."""


async def get_learning_chat_space(
    *, user_id: str, assignment_id: str
) -> dict[str, Any]:
    """Return the student's durable Flash conversation for one assignment."""
    space = await get_or_create_student_learning_space(
        student_user_id=user_id, assignment_id=assignment_id
    )
    if not space:
        raise EducationLearningChatContextError("Learning assignment is unavailable")
    return space


async def require_learning_chat_thread(
    *, user_id: str, assignment_id: str, thread_id: str
) -> None:
    """Require contextual learning messages to use their assignment's sole thread."""
    space = await get_learning_chat_space(user_id=user_id, assignment_id=assignment_id)
    if str(space["conversation_thread_id"]) != thread_id:
        raise EducationLearningChatContextError(
            "Learning chat must use its assignment conversation"
        )


async def reject_unscoped_learning_thread(*, user_id: str, thread_id: str) -> None:
    """Prevent mapped learning threads from accepting ordinary Flash messages."""
    space = await get_student_learning_space_for_thread(
        student_user_id=user_id, conversation_thread_id=thread_id
    )
    if space:
        raise EducationLearningChatContextError(
            "Learning conversations require an assignment and chapter context"
        )


async def attach_learning_chat_context(
    *,
    user_id: str,
    assignment_id: str | None,
    knowledge_point_id: str | None,
    additional_context: list[Any] | None,
) -> list[Any] | None:
    """Freeze the currently authorized material into this Flash request."""
    if assignment_id is None and knowledge_point_id is None:
        return additional_context
    if not assignment_id or not knowledge_point_id:
        raise EducationLearningChatContextError(
            "Learning chat requires an assignment and knowledge point"
        )
    try:
        material = await get_student_kp_lesson(
            student_user_id=user_id,
            assignment_id=assignment_id,
            knowledge_point_id=knowledge_point_id,
        )
        markdown = material.get("markdown")
        if not material.get("material_available") or not isinstance(markdown, str):
            raise EducationLearningChatContextError("Learning material is unavailable")
        structure = await get_student_structure(
            student_user_id=user_id,
            assignment_id=assignment_id,
        )
        point = next(
            (
                item
                for item in structure.get("knowledge_points", [])
                if str(item.get("knowledge_point_id")) == knowledge_point_id
            ),
            None,
        )
        if point is None or not str(point.get("title") or "").strip():
            raise EducationLearningChatContextError("Learning material is unavailable")
        context = {
            "content": "\n\n".join(
                [
                    f"# {point['title']}",
                    "以下是学生当前获授权教材中的成功讲义。只根据这份冻结到本轮请求"
                    "的材料解释、提问和引导学习；不要声称能访问其他学生记录或家长管理资料。",
                    markdown,
                ]
            )
        }
    except EducationLearningChatContextError:
        raise
    except TextbookError as exc:
        raise EducationLearningChatContextError(
            "Learning lesson is unavailable"
        ) from exc
    # Discard client context so it cannot change or dilute the assigned material.
    del additional_context
    return [{"type": "directive", "content": context["content"]}]
