"""Server-owned contextual material for student Flash learning conversations."""

from typing import Any

from src.server.services.education_textbooks import (
    TextbookError,
    get_student_chapter_context,
)
from src.server.database.education_textbooks import (
    get_or_create_student_learning_space,
    get_student_learning_space_for_thread,
)


class EducationLearningChatContextError(ValueError):
    """The client supplied an incomplete or unauthorized learning context reference."""


async def get_learning_chat_space(
    *, user_id: str, assignment_id: str
) -> dict[str, Any]:
    """Return the student's durable Flash conversation for one publication snapshot."""
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
    chapter_id: str | None,
    additional_context: list[Any] | None,
) -> list[Any] | None:
    """Resolve published chapter material server-side and append one Flash directive."""
    if assignment_id is None and chapter_id is None:
        return additional_context
    if not assignment_id or not chapter_id:
        raise EducationLearningChatContextError(
            "Learning chat requires both an assignment and a chapter"
        )
    try:
        context = await get_student_chapter_context(
            student_user_id=user_id,
            assignment_id=assignment_id,
            chapter_id=chapter_id,
        )
    except TextbookError as exc:
        raise EducationLearningChatContextError(
            "Learning chapter is unavailable"
        ) from exc
    return [
        *(additional_context or []),
        {"type": "directive", "content": context["content"]},
    ]
