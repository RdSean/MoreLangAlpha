"""Small stream-only progress tool for explicitly enabled managed agents."""

from __future__ import annotations

import re

import structlog
from langchain_core.tools import BaseTool, tool


logger = structlog.get_logger(__name__)
_STAGE_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def create_report_progress_tool() -> BaseTool:
    """Create a tool that emits a bounded semantic stage to the custom stream."""

    @tool("report_progress")
    async def report_progress(stage: str, action: str | None = None) -> str:
        """Report entry into a stage or optional action you are actually performing.

        Use the managed task's progress catalog; it is not a required checklist.

        Args:
            stage: One exact allowed stage identifier from the managed task.
            action: Optional allowed action identifier matching this stage.

        Returns:
            Stream delivery acknowledgement, not confirmation of persistence or completion.

        If reporting is unavailable, stop reporting and continue the task.
        """
        if not _STAGE_PATTERN.fullmatch(stage):
            return "Invalid progress stage; continue the task."
        if action is not None and not _STAGE_PATTERN.fullmatch(action):
            return "Invalid progress action; continue the task."
        payload = {"stage": stage}
        if action is not None:
            payload["action"] = action

        try:
            from langgraph.config import get_stream_writer

            writer = get_stream_writer()
            writer(
                {
                    "artifact_type": "report_progress",
                    "artifact_id": stage,
                    "status": "running",
                    "payload": payload,
                }
            )
        except Exception:
            logger.debug("Managed progress stream is unavailable", exc_info=True)
            return "Progress reporting unavailable; continue the task."
        return "Progress reported."

    return report_progress
