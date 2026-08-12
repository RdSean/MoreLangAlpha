"""Versioning, explicit local processing, and authorization for family textbooks."""

from typing import Any

from src.server.database.education_tasks import get_household_context_for_parent
from src.server.database.education_textbooks import (
    assign_textbook_publication,
    claim_textbook_processing_job,
    complete_textbook_processing_job,
    create_textbook_record,
    fail_textbook_processing_job,
    get_processing_job_for_parent,
    get_student_learning as get_student_learning_record,
    get_textbook_for_parent,
    list_student_assignments,
    list_student_learning_records,
    list_textbooks_for_parent,
    publish_textbook_version,
    queue_textbook_processing,
    submit_student_answer,
    update_student_progress,
)
from src.server.database.education_members import get_membership_for_user
from src.server.services.education_textbook_storage import write_textbook_bundle


_VALID_VERSION_TRANSITIONS = {
    ("draft", "processing"),
    ("processing", "review"),
    ("processing", "failed"),
    ("failed", "processing"),
    ("review", "published"),
}


class TextbookError(RuntimeError):
    """Base exception for family textbook operations."""


class TextbookTransitionError(TextbookError, ValueError):
    """A textbook version state change violates publication immutability."""


class TextbookPermissionError(TextbookError, PermissionError):
    """The caller does not own the required household teaching capability."""


class TextbookNotFoundError(TextbookError, LookupError):
    """The requested textbook record is absent or outside its visible scope."""


class TextbookProcessingError(TextbookError):
    """The durable local processing job failed after it was claimed."""


def assert_version_transition(*, current: str, target: str) -> None:
    if (current, target) not in _VALID_VERSION_TRANSITIONS:
        raise TextbookTransitionError(
            f"Cannot transition textbook version from {current} to {target}"
        )


def _required_title(value: str) -> str:
    title = value.strip()
    if not title:
        raise TextbookError("textbook title is required")
    return title


def _slug(value: str) -> str:
    import re

    return (
        re.sub(r"[^0-9A-Za-z._-]+", "-", value.strip()).strip(".-").lower()[:80]
        or "textbook"
    )


async def create_textbook(*, parent_user_id: str, title: str) -> dict[str, Any]:
    context = await get_household_context_for_parent(parent_user_id)
    if not context:
        raise TextbookPermissionError("Only a parent can create family textbooks")
    textbook = await create_textbook_record(
        household_id=str(context["household_id"]),
        parent_user_id=parent_user_id,
        title=_required_title(title),
        slug=_slug(title),
    )
    if not textbook:
        raise TextbookPermissionError(
            "Only a household parent can create family textbooks"
        )
    return textbook


async def start_processing(
    *,
    parent_user_id: str,
    textbook_id: str,
    source_asset_ids: list[str],
    extractor_name: str = "local_fixture",
    extractor_version: str = "1",
) -> dict[str, Any]:
    """Explicitly freeze sources into a queued local processing job; no upload is implicitly included."""
    context = await get_household_context_for_parent(parent_user_id)
    if not context:
        raise TextbookPermissionError("Only a parent can start textbook processing")
    if not source_asset_ids:
        raise TextbookError("At least one textbook source is required")
    job = await queue_textbook_processing(
        parent_user_id=parent_user_id,
        household_id=str(context["household_id"]),
        textbook_id=textbook_id,
        source_asset_ids=list(dict.fromkeys(source_asset_ids)),
        extractor_name=extractor_name,
        extractor_version=extractor_version,
    )
    if not job:
        raise TextbookNotFoundError("Textbook not found")
    return job


def build_local_fixture_package(job: dict[str, Any]) -> dict[str, Any]:
    """Generate deterministic review material; a PTC/Datalab extractor can replace this adapter later."""
    chapter_slug = "01-overview"
    source_names = "、".join(source["original_filename"] for source in job["sources"])
    markdown_key = f"education/{job['household_id']}/{_slug(job['slug'])}/v{job['version_sequence']}/chapters/{chapter_slug}.md"
    teaching_key = f"education/{job['household_id']}/{_slug(job['slug'])}/v{job['version_sequence']}/teaching/{chapter_slug}-material.md"
    title = f"{job['title']}：导读"
    return {
        "extractor": {"name": "local_fixture", "version": "1"},
        "chapters": [
            {
                "position": 1,
                "slug": chapter_slug,
                "title": title,
                "page_start": None,
                "page_end": None,
                "markdown_key": markdown_key,
                "teaching_material_key": teaching_key,
                "markdown": f"# {title}\n\n本章基于已冻结资料：{source_names}。\n\n请先阅读资料，再用自己的话说明本章的学习目标。\n",
                "teaching_material": f"# {title} 学习材料\n\n## 学习目标\n\n- 能识别本教材的已冻结资料来源。\n- 能完成本章的基础知识检查。\n\n## 学习建议\n\n阅读后完成右侧知识检查；答错时回到本章材料复习。\n",
                "questions": [
                    {
                        "position": 1,
                        "prompt": "完成本章学习后，下一步应该做什么？",
                        "options": {
                            "A": "完成知识检查",
                            "B": "跳过所有材料",
                            "C": "修改已发布版本",
                            "D": "删除原始资料",
                        },
                        "correct_option": "A",
                        "explanation": "知识检查用于形成可追溯的学习证据。",
                        "knowledge_point": "学习证据",
                    }
                ],
            }
        ],
    }


async def process_textbook_job(*, job_id: str) -> dict[str, Any]:
    """Claim a persisted job, write its recoverable bundle, then make it reviewable."""
    job = await claim_textbook_processing_job(job_id=job_id)
    if not job:
        raise TextbookNotFoundError("Textbook processing job is not queued")
    try:
        package = build_local_fixture_package(job)
        prefix = await write_textbook_bundle(job, package)
        completed = await complete_textbook_processing_job(
            job_id=str(job["job_id"]),
            version_id=str(job["version_id"]),
            bundle_prefix=prefix,
            chapters=package["chapters"],
        )
        if not completed:
            raise TextbookProcessingError("Textbook processing claim was lost")
        return completed
    except Exception as exc:
        await fail_textbook_processing_job(
            job_id=str(job["job_id"]),
            version_id=str(job["version_id"]),
            error_message=str(exc),
        )
        if isinstance(exc, TextbookError):
            raise
        raise TextbookProcessingError("Local textbook processing failed") from exc


async def list_parent_textbooks(*, parent_user_id: str) -> list[dict[str, Any]]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can manage family textbooks")
    return await list_textbooks_for_parent(parent_user_id)


async def get_parent_textbook(
    *, parent_user_id: str, textbook_id: str
) -> dict[str, Any]:
    textbook = await get_textbook_for_parent(
        parent_user_id=parent_user_id, textbook_id=textbook_id
    )
    if not textbook:
        raise TextbookNotFoundError("Textbook not found")
    return textbook


async def run_processing_for_parent(
    *, parent_user_id: str, job_id: str
) -> dict[str, Any]:
    job = await get_processing_job_for_parent(
        parent_user_id=parent_user_id, job_id=job_id
    )
    if not job:
        raise TextbookNotFoundError("Textbook processing job not found")
    if job["status"] != "queued":
        raise TextbookTransitionError(
            f"Textbook processing job cannot run from {job['status']}"
        )
    return await process_textbook_job(job_id=job_id)


async def publish_version(
    *, parent_user_id: str, textbook_id: str, version_id: str
) -> dict[str, Any]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can publish textbook versions")
    try:
        publication = await publish_textbook_version(
            parent_user_id=parent_user_id,
            textbook_id=textbook_id,
            version_id=version_id,
        )
    except ValueError as exc:
        raise TextbookTransitionError(str(exc)) from exc
    if not publication:
        raise TextbookNotFoundError("Textbook version not found")
    return publication


async def assign_publication(
    *, parent_user_id: str, publication_id: str, student_user_id: str
) -> dict[str, Any]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can assign textbook publications")
    assignment = await assign_textbook_publication(
        parent_user_id=parent_user_id,
        publication_id=publication_id,
        student_user_id=student_user_id,
    )
    if not assignment:
        raise TextbookNotFoundError("Publication or household student not found")
    return assignment


async def list_learning_assignments(*, student_user_id: str) -> list[dict[str, Any]]:
    membership = await get_membership_for_user(student_user_id)
    if not membership or membership["role"] != "student":
        raise TextbookPermissionError("Only a student can access learning assignments")
    return await list_student_assignments(student_user_id)


async def get_student_learning(
    *, student_user_id: str, assignment_id: str
) -> dict[str, Any]:
    membership = await get_membership_for_user(student_user_id)
    if not membership or membership["role"] != "student":
        raise TextbookPermissionError("Only a student can access learning assignments")
    learning = await get_student_learning_record(
        student_user_id=student_user_id, assignment_id=assignment_id
    )
    if not learning:
        raise TextbookNotFoundError("Learning assignment not found")
    return learning


async def record_learning_progress(
    *, student_user_id: str, assignment_id: str, chapter_id: str, status: str
) -> dict[str, Any]:
    if status not in {"learning", "read", "check_completed", "review_recommended"}:
        raise TextbookError("Learning progress status is invalid")
    membership = await get_membership_for_user(student_user_id)
    if not membership or membership["role"] != "student":
        raise TextbookPermissionError("Only a student can record learning progress")
    progress = await update_student_progress(
        student_user_id=student_user_id,
        assignment_id=assignment_id,
        chapter_id=chapter_id,
        status=status,
    )
    if not progress:
        raise TextbookNotFoundError("Learning chapter not found")
    return progress


async def answer_learning_question(
    *, student_user_id: str, assignment_id: str, question_id: str, selected_option: str
) -> dict[str, Any]:
    option = selected_option.strip().upper()
    if not option or len(option) > 32:
        raise TextbookError("A valid answer option is required")
    membership = await get_membership_for_user(student_user_id)
    if not membership or membership["role"] != "student":
        raise TextbookPermissionError("Only a student can answer learning questions")
    answer = await submit_student_answer(
        student_user_id=student_user_id,
        assignment_id=assignment_id,
        question_id=question_id,
        selected_option=option,
    )
    if not answer:
        raise TextbookNotFoundError("Learning question not found")
    return answer


async def get_parent_learning_records(
    *, parent_user_id: str, assignment_id: str
) -> dict[str, Any]:
    if not await get_household_context_for_parent(parent_user_id):
        raise TextbookPermissionError("Only a parent can read learning records")
    records = await list_student_learning_records(
        parent_user_id=parent_user_id, assignment_id=assignment_id
    )
    if not records:
        raise TextbookNotFoundError("Learning assignment not found")
    return records
