"""Read-only parent projection of a student's assignment-scoped Flash transcript."""

from typing import Any

from src.server.database.conversation import get_replay_thread_data
from src.server.database.education_textbooks import get_parent_learning_space
from src.server.services.education_textbooks import TextbookNotFoundError


async def _get_replay_items(
    thread_id: str,
    thread: dict[str, Any],
    queries: list[dict[str, Any]],
    responses: list[dict[str, Any]],
    usages: list[dict[str, Any]],
    provenance: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    # ``history`` imports application setup, which registers this education
    # router. Keep the dependency inside the request path to avoid an import
    # cycle during application construction.
    from src.server.services.history.replay import (
        CheckpointReplayUnavailable,
        build_checkpoint_replay_items,
        build_sse_replay_items,
    )

    responses_by_turn = {
        row.get("turn_index"): row for row in responses if isinstance(row, dict)
    }
    if thread.get("latest_checkpoint_id"):
        try:
            return await build_checkpoint_replay_items(
                thread_id,
                queries,
                responses_by_turn,
                branch_tip_checkpoint_id=thread["latest_checkpoint_id"],
                usages=usages,
                provenance=provenance,
            )
        except CheckpointReplayUnavailable:
            pass
        except Exception:
            # The regular replay endpoint has the same safe fallback to persisted
            # events when checkpoints cannot faithfully reconstruct a transcript.
            pass
    return build_sse_replay_items(thread_id, queries, responses_by_turn)


async def _get_transcript_replay_items(
    thread_id: str,
    thread: dict[str, Any],
    queries: list[dict[str, Any]],
    responses: list[dict[str, Any]],
    usages: list[dict[str, Any]],
    provenance: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Small seam for transcript tests and the request-owned replay projection."""
    return await _get_replay_items(
        thread_id, thread, queries, responses, usages, provenance
    )


def _messages_from_replay_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only original student and assistant text, coalescing streamed chunks."""
    messages: list[dict[str, Any]] = []
    for item in items:
        event = item.get("event")
        data = item.get("data") or {}
        if event == "user_message" and isinstance(data.get("content"), str):
            messages.append(
                {
                    "role": "user",
                    "content": data["content"],
                    "timestamp": data.get("timestamp"),
                }
            )
        elif (
            event == "message_chunk"
            and data.get("role") == "assistant"
            and isinstance(data.get("content"), str)
        ):
            if messages and messages[-1]["role"] == "assistant":
                messages[-1]["content"] += data["content"]
            else:
                messages.append(
                    {
                        "role": "assistant",
                        "content": data["content"],
                        "timestamp": data.get("timestamp"),
                    }
                )
    return messages


async def get_parent_learning_transcript(
    *, parent_user_id: str, assignment_id: str
) -> dict[str, Any]:
    """Return only an authorized assignment's original text transcript.

    This read model intentionally has no corresponding parent message or
    mutation operation. The ordinary thread replay route remains owner-only.
    """
    space = await get_parent_learning_space(
        parent_user_id=parent_user_id, assignment_id=assignment_id
    )
    if not space:
        raise TextbookNotFoundError("Learning assignment not found")
    thread_id = space.get("conversation_thread_id")
    if not thread_id:
        return {**space, "conversation_thread_id": None, "messages": []}

    (
        owner_id,
        thread,
        queries,
        responses,
        usages,
        provenance,
    ) = await get_replay_thread_data(str(thread_id))
    if owner_id != space["student_user_id"] or not thread:
        # A mapped thread is never exposed if its ownership is inconsistent.
        raise TextbookNotFoundError("Learning transcript not found")
    items = await _get_transcript_replay_items(
        str(thread_id), thread, queries, responses, usages, provenance
    )
    return {
        **space,
        "conversation_thread_id": str(thread_id),
        "messages": _messages_from_replay_items(items),
    }
