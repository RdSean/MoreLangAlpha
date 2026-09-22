"""Service contract for the unified managed book-processing job."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from src.server.database.education_textbooks import (
    get_generation_job_for_parent,
    pause_book_pipeline_for_chapter_review,
    queue_book_pipeline_job,
    resume_book_pipeline_job,
)
from src.server.services.education_textbooks import (
    TextbookNotFoundError,
    TextbookPermissionError,
    TextbookTransitionError,
    get_household_context_for_parent,
)


def _processing_profile_sha256() -> str:
    return hashlib.sha256(
        json.dumps(
            {
                "mode": "book-pipeline-v1",
                "skill": "book-to-skill",
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _job_projection(job: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: job.get(key)
        for key in (
            "generation_job_id",
            "version_id",
            "scope",
            "structure_id",
            "knowledge_point_id",
            "status",
            "attempt_count",
            "pause_after_chapter_analysis",
            "error_code",
            "error_message",
            "created_at",
            "updated_at",
            "root_run_id",
            "started_at",
            "heartbeat_at",
        )
    }


async def queue_book_pipeline_for_parent(
    *,
    parent_user_id: str,
    content_version_id: str,
    pause_after_chapter_analysis: bool = False,
) -> dict[str, Any]:
    """Create or reuse one parent-owned unified processing job."""
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError(
            "Only a parent can create textbook processing jobs"
        )
    job = await queue_book_pipeline_job(
        parent_user_id=parent_user_id,
        content_version_id=content_version_id,
        processing_profile_sha256=_processing_profile_sha256(),
        pause_after_chapter_analysis=pause_after_chapter_analysis,
    )
    if not job:
        raise TextbookNotFoundError("Reviewable textbook content version not found")
    return _job_projection(job)


async def get_book_pipeline_job_for_parent(
    *,
    parent_user_id: str,
    generation_job_id: str,
) -> dict[str, Any]:
    """Return one parent-owned unified processing job."""
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can read textbook processing jobs")
    job = await get_generation_job_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    if not job or job.get("scope") != "book_pipeline":
        raise TextbookNotFoundError("Textbook processing job not found")
    return _job_projection(job)


async def pause_book_pipeline_for_parent(
    *,
    parent_user_id: str,
    generation_job_id: str,
    attempt_id: str,
) -> dict[str, Any]:
    """Finish the current attempt at the chapter-analysis review checkpoint."""
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError(
            "Only a parent can update textbook processing jobs"
        )
    job = await pause_book_pipeline_for_chapter_review(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
        attempt_id=attempt_id,
    )
    if not job:
        raise TextbookTransitionError("Textbook processing job cannot pause for review")
    return _job_projection(job)


async def resume_book_pipeline_for_parent(
    *,
    parent_user_id: str,
    generation_job_id: str,
) -> dict[str, Any]:
    """Requeue one unified job waiting at the chapter-analysis checkpoint."""
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError(
            "Only a parent can resume textbook processing jobs"
        )
    job = await get_generation_job_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    if not job or job.get("scope") != "book_pipeline":
        raise TextbookNotFoundError("Textbook processing job not found")
    if job.get("status") != "awaiting_review":
        raise TextbookTransitionError(
            "Only a chapter-analysis checkpoint can be resumed"
        )
    resumed = await resume_book_pipeline_job(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    if not resumed:
        raise TextbookTransitionError("Textbook processing job cannot be resumed")
    return _job_projection(resumed)
