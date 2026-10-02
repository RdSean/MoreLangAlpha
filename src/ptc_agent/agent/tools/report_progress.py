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
    async def report_progress(stage: str) -> str:
        """Report entry into an allowed stage from the managed task contract.

        Call this only with a stage listed in ``task.json.progress.allowed_stages``.
        Progress is explanatory and does not complete or validate the task.

        Args:
            stage: One exact allowed stage identifier from the managed task.
        """
        if not _STAGE_PATTERN.fullmatch(stage):
            return "Invalid progress stage; continue the task."

        try:
            from langgraph.config import get_stream_writer

            writer = get_stream_writer()
            writer(
                {
                    "artifact_type": "report_progress",
                    "artifact_id": stage,
                    "status": "running",
                    "payload": {"stage": stage},
                }
            )
        except Exception:
            logger.debug("Managed progress stream is unavailable", exc_info=True)
            return "Progress reporting unavailable; continue the task."
        return "Progress reported."

    return report_progress
