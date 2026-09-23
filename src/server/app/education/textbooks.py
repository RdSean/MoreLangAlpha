"""Parent textbook management and student deterministic-learning routes."""

import asyncio
import json
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse

from src.server.app.education.models import (
    AssignTextbookPublicationRequest,
    ApproveKnowledgePointLessonRequest,
    BookPipelineJobResponse,
    BookPipelineProgressResponse,
    CreateBookPipelineRequest,
    CreateKnowledgePointLessonRevisionRequest,
    CreateLearningItemRequest,
    CreateTextbookRequest,
    CreateTextbookStructureRequest,
    GenerateKnowledgePointLessonRequest,
    KnowledgePointCandidateIdsRequest,
    KnowledgePointCandidateResponse,
    KnowledgePointCandidateReviewResponse,
    KnowledgePointLessonResponse,
    KnowledgePointProgressResponse,
    KnowledgePointSourcePreviewResponse,
    LessonGenerationStatusResponse,
    LearningItemResponse,
    PublishTextbookStructureRequest,
    StartTextbookProcessingRequest,
    MergeKnowledgePointCandidatesRequest,
    SplitKnowledgePointCandidateRequest,
    StructureGenerationJobResponse,
    StudentKnowledgePointLessonResponse,
    StudentTextbookStructureResponse,
    TextbookAssignmentResponse,
    TextbookDetailResponse,
    TextbookParseJobCandidateResponse,
    TextbookProcessingResponse,
    TextbookResponse,
    TextbookStructurePublicationResponse,
    TextbookStructureResponse,
    UpdateLearningItemRequest,
    UpdateKnowledgePointCandidateRequest,
    UpdateKnowledgePointProgressRequest,
    UpdateTextbookStructureRequest,
)
from src.server.services.education_candidate_review import (
    accept_knowledge_point_candidates_for_parent,
    list_knowledge_point_candidates_for_parent,
    merge_knowledge_point_candidates_for_parent,
    reject_knowledge_point_candidates_for_parent,
    split_knowledge_point_candidate_for_parent,
    update_knowledge_point_candidate_for_parent,
)
from src.server.services.education_structure_review import (
    accept_structure_for_parent,
    get_structure_for_parent,
    get_structure_generation_job,
    get_latest_structure_for_parent,
    get_knowledge_point_source_preview,
    queue_structure_for_parent,
    replace_structure_for_parent,
    resume_structure_generation_for_parent,
)
from src.server.services.education_structure_progress import (
    get_book_pipeline_progress_for_parent,
    get_structure_progress_for_parent,
)
from src.server.services.education_lesson_review import (
    approve_lesson_for_parent,
    create_manual_lesson_revision,
    get_lesson_for_parent,
    get_lesson_for_knowledge_point,
    get_lesson_generation_status_for_parent,
    publish_structure_for_parent,
    queue_lesson_for_parent,
)
from src.server.services.education_book_asset_jobs import (
    launch_book_asset_generation,
    queue_book_assets_for_parent,
)
from src.server.services.education_book_pipeline_jobs import (
    cancel_book_pipeline_for_parent,
    get_book_pipeline_job_for_parent,
    queue_and_launch_book_pipeline_for_parent,
    resume_book_pipeline_for_parent,
)
from src.server.services.education_learning_assets import (
    add_learning_item,
    edit_learning_item,
    generate_unit_summary,
    get_learning_items,
    remove_learning_item,
    update_learning_progress,
)
from src.server.services.education_textbooks import (
    TextbookError,
    TextbookNotFoundError,
    TextbookPermissionError,
    TextbookTransitionError,
    assign_publication,
    create_textbook,
    get_parent_textbook,
    get_student_kp_lesson,
    get_student_structure,
    list_learning_assignments,
    list_completed_textbook_parse_jobs,
    list_parent_textbooks,
    retry_processing_for_parent,
    run_processing_for_parent,
    start_processing,
    start_processing_from_parse_jobs,
)
from src.server.services.education_learning_chat import get_learning_chat_space
from src.server.services.education_learning_transcript import (
    get_parent_learning_transcript,
)
from src.server.utils.api import CurrentUserId


router = APIRouter(prefix="/api/v1/education", tags=["Education textbooks"])

_BOOK_PROGRESS_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
    "Connection": "keep-alive",
}
_BOOK_PROGRESS_POLL_SECONDS = 2.0
_BOOK_PROGRESS_STREAM_STOP_STATUSES = frozenset(
    {"awaiting_review", "completed", "failed", "cancelled"}
)


def _textbook_http_error(exc: TextbookError) -> HTTPException:
    if isinstance(exc, TextbookPermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, TextbookNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, TextbookTransitionError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/textbooks", response_model=list[dict])
async def list_textbooks(user_id: CurrentUserId):
    try:
        return await list_parent_textbooks(parent_user_id=user_id)
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/textbooks", response_model=TextbookResponse, status_code=status.HTTP_201_CREATED
)
async def create_family_textbook(body: CreateTextbookRequest, user_id: CurrentUserId):
    try:
        return await create_textbook(parent_user_id=user_id, title=body.title)
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get("/textbooks/{textbook_id}", response_model=TextbookDetailResponse)
async def get_family_textbook(textbook_id: UUID, user_id: CurrentUserId):
    try:
        return await get_parent_textbook(
            parent_user_id=user_id, textbook_id=str(textbook_id)
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/textbook-parse-jobs/completed",
    response_model=list[TextbookParseJobCandidateResponse],
)
async def list_completed_parse_jobs(user_id: CurrentUserId):
    try:
        return await list_completed_textbook_parse_jobs(parent_user_id=user_id)
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/textbook-versions/{content_version_id}/book-pipeline-jobs",
    response_model=BookPipelineJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_family_book_pipeline(
    content_version_id: UUID,
    user_id: CurrentUserId,
    body: CreateBookPipelineRequest | None = None,
):
    try:
        return await queue_and_launch_book_pipeline_for_parent(
            parent_user_id=user_id,
            content_version_id=str(content_version_id),
            processing_brief=(body.processing_brief if body is not None else ""),
            request_id=str(body.request_id) if body and body.request_id else None,
            pause_after_chapter_analysis=(
                body.pause_after_chapter_analysis if body is not None else False
            ),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/book-pipeline-jobs/{generation_job_id}",
    response_model=BookPipelineJobResponse,
)
async def get_family_book_pipeline_job(
    generation_job_id: UUID,
    user_id: CurrentUserId,
):
    try:
        return await get_book_pipeline_job_for_parent(
            parent_user_id=user_id,
            generation_job_id=str(generation_job_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/book-pipeline-jobs/{generation_job_id}/cancel",
    response_model=BookPipelineJobResponse,
)
async def cancel_family_book_pipeline_job(
    generation_job_id: UUID,
    user_id: CurrentUserId,
):
    try:
        return await cancel_book_pipeline_for_parent(
            parent_user_id=user_id,
            generation_job_id=str(generation_job_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/jobs/{generation_job_id}/progress",
    response_model=BookPipelineProgressResponse,
)
async def get_book_pipeline_progress(
    generation_job_id: UUID,
    user_id: CurrentUserId,
):
    try:
        return await get_book_pipeline_progress_for_parent(
            parent_user_id=user_id,
            generation_job_id=str(generation_job_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/jobs/{generation_job_id}/progress/stream",
    response_class=StreamingResponse,
)
async def stream_book_pipeline_progress(
    generation_job_id: UUID,
    user_id: CurrentUserId,
):
    try:
        initial = await get_book_pipeline_progress_for_parent(
            parent_user_id=user_id,
            generation_job_id=str(generation_job_id),
            include_sse_cursor=True,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc

    async def event_generator():
        snapshot = initial
        while True:
            cursor = str(snapshot.pop("_sse_cursor", "0:0"))
            payload = json.dumps(
                snapshot,
                ensure_ascii=False,
                separators=(",", ":"),
                default=str,
            )
            yield f"id: {cursor}\nevent: progress\ndata: {payload}\n\n"
            if str(snapshot.get("status") or "") in _BOOK_PROGRESS_STREAM_STOP_STATUSES:
                return
            await asyncio.sleep(_BOOK_PROGRESS_POLL_SECONDS)
            try:
                snapshot = await get_book_pipeline_progress_for_parent(
                    parent_user_id=user_id,
                    generation_job_id=str(generation_job_id),
                    include_sse_cursor=True,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                yield 'event: error\ndata: {"error":"progress unavailable"}\n\n'
                return

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=_BOOK_PROGRESS_SSE_HEADERS,
    )


@router.post(
    "/book-pipeline-jobs/{generation_job_id}/resume",
    response_model=BookPipelineJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_family_book_pipeline_job(
    generation_job_id: UUID,
    user_id: CurrentUserId,
):
    try:
        return await resume_book_pipeline_for_parent(
            parent_user_id=user_id,
            generation_job_id=str(generation_job_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/textbook-versions/{content_version_id}/structures",
    response_model=StructureGenerationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_family_textbook_structure(
    content_version_id: UUID,
    user_id: CurrentUserId,
    body: CreateTextbookStructureRequest | None = None,
):
    try:
        return await queue_structure_for_parent(
            parent_user_id=user_id,
            content_version_id=str(content_version_id),
            profile_input=body.profile.model_dump(mode="python")
            if body and body.profile
            else None,
            profile_id=str(body.profile_id) if body and body.profile_id else None,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/textbook-versions/{content_version_id}/structure",
    response_model=TextbookStructureResponse | None,
)
async def get_latest_family_textbook_structure(
    content_version_id: UUID,
    user_id: CurrentUserId,
):
    try:
        return await get_latest_structure_for_parent(
            parent_user_id=user_id,
            content_version_id=str(content_version_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/structures/{structure_id}/candidates",
    response_model=KnowledgePointCandidateReviewResponse,
)
async def list_family_knowledge_point_candidates(
    structure_id: UUID,
    user_id: CurrentUserId,
):
    try:
        return await list_knowledge_point_candidates_for_parent(
            parent_user_id=user_id,
            structure_id=str(structure_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.patch(
    "/candidates/{candidate_id}",
    response_model=KnowledgePointCandidateResponse,
)
async def update_family_knowledge_point_candidate(
    candidate_id: UUID,
    body: UpdateKnowledgePointCandidateRequest,
    user_id: CurrentUserId,
):
    try:
        return await update_knowledge_point_candidate_for_parent(
            parent_user_id=user_id,
            candidate_id=str(candidate_id),
            title=body.title,
            summary=body.summary,
            point_type=body.point_type,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/candidates/accept",
    response_model=list[KnowledgePointCandidateResponse],
)
async def accept_family_knowledge_point_candidates(
    body: KnowledgePointCandidateIdsRequest,
    user_id: CurrentUserId,
):
    try:
        return await accept_knowledge_point_candidates_for_parent(
            parent_user_id=user_id,
            candidate_ids=[str(candidate_id) for candidate_id in body.candidate_ids],
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/candidates/reject",
    response_model=list[KnowledgePointCandidateResponse],
)
async def reject_family_knowledge_point_candidates(
    body: KnowledgePointCandidateIdsRequest,
    user_id: CurrentUserId,
):
    try:
        return await reject_knowledge_point_candidates_for_parent(
            parent_user_id=user_id,
            candidate_ids=[str(candidate_id) for candidate_id in body.candidate_ids],
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/candidates/merge",
    response_model=list[KnowledgePointCandidateResponse],
)
async def merge_family_knowledge_point_candidates(
    body: MergeKnowledgePointCandidatesRequest,
    user_id: CurrentUserId,
):
    try:
        return await merge_knowledge_point_candidates_for_parent(
            parent_user_id=user_id,
            source_ids=[str(candidate_id) for candidate_id in body.source_ids],
            target_id=str(body.target_id) if body.target_id is not None else None,
            title=body.title,
            summary=body.summary,
            point_type=body.point_type,
            accept=body.accept,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/candidates/split",
    response_model=list[KnowledgePointCandidateResponse],
)
async def split_family_knowledge_point_candidate(
    body: SplitKnowledgePointCandidateRequest,
    user_id: CurrentUserId,
):
    try:
        return await split_knowledge_point_candidate_for_parent(
            parent_user_id=user_id,
            candidate_id=str(body.candidate_id),
            items=[item.model_dump(mode="python") for item in body.items],
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/structure-generation-jobs/{generation_job_id}",
    response_model=StructureGenerationJobResponse,
)
async def get_family_structure_generation_job(
    generation_job_id: UUID,
    user_id: CurrentUserId,
):
    try:
        return await get_structure_generation_job(
            parent_user_id=user_id,
            generation_job_id=str(generation_job_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/structure-generation-jobs/{generation_job_id}/progress",
    response_model=KnowledgePointProgressResponse,
)
async def get_family_structure_generation_progress(
    generation_job_id: UUID,
    user_id: CurrentUserId,
):
    try:
        return await get_structure_progress_for_parent(
            parent_user_id=user_id,
            generation_job_id=str(generation_job_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/structure-generation-jobs/{generation_job_id}/resume",
    response_model=StructureGenerationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_family_structure_generation_job(
    generation_job_id: UUID,
    user_id: CurrentUserId,
):
    try:
        return await resume_structure_generation_for_parent(
            parent_user_id=user_id,
            generation_job_id=str(generation_job_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/textbook-structures/{structure_id}/book-assets",
    response_model=StructureGenerationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_family_book_assets(
    structure_id: UUID,
    user_id: CurrentUserId,
):
    try:
        queued = await queue_book_assets_for_parent(
            parent_user_id=user_id,
            structure_id=str(structure_id),
        )
        await launch_book_asset_generation(
            parent_user_id=user_id,
            generation_job_id=str(queued["generation_job_id"]),
        )
        return queued
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/textbook-structures/{structure_id}",
    response_model=TextbookStructureResponse,
)
async def get_family_textbook_structure(
    structure_id: UUID,
    user_id: CurrentUserId,
):
    try:
        return await get_structure_for_parent(
            parent_user_id=user_id,
            structure_id=str(structure_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.put(
    "/textbook-structures/{structure_id}",
    response_model=TextbookStructureResponse,
)
async def update_family_textbook_structure(
    structure_id: UUID,
    body: UpdateTextbookStructureRequest,
    user_id: CurrentUserId,
):
    try:
        await replace_structure_for_parent(
            parent_user_id=user_id,
            structure_id=str(structure_id),
            units=[unit.model_dump(mode="python") for unit in body.units],
        )
        return await get_structure_for_parent(
            parent_user_id=user_id,
            structure_id=str(structure_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/textbook-structures/{structure_id}/review",
    response_model=TextbookStructureResponse,
)
async def accept_family_textbook_structure(
    structure_id: UUID,
    user_id: CurrentUserId,
):
    try:
        await accept_structure_for_parent(
            parent_user_id=user_id,
            structure_id=str(structure_id),
        )
        return await get_structure_for_parent(
            parent_user_id=user_id,
            structure_id=str(structure_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/knowledge-points/{knowledge_point_id}/lessons",
    response_model=StructureGenerationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def generate_family_knowledge_point_lesson(
    knowledge_point_id: UUID,
    body: GenerateKnowledgePointLessonRequest,
    user_id: CurrentUserId,
):
    try:
        return await queue_lesson_for_parent(
            parent_user_id=user_id,
            knowledge_point_id=str(knowledge_point_id),
            auto_grading=body.auto_grading,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/knowledge-points/{knowledge_point_id}/lesson",
    response_model=KnowledgePointLessonResponse | None,
)
async def get_family_knowledge_point_lesson_by_point(
    knowledge_point_id: UUID,
    user_id: CurrentUserId,
):
    try:
        return await get_lesson_for_knowledge_point(
            parent_user_id=user_id,
            knowledge_point_id=str(knowledge_point_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/knowledge-points/{knowledge_point_id}/lesson-generation",
    response_model=LessonGenerationStatusResponse,
)
async def get_family_lesson_generation_status(
    knowledge_point_id: UUID,
    user_id: CurrentUserId,
):
    try:
        return await get_lesson_generation_status_for_parent(
            parent_user_id=user_id,
            knowledge_point_id=str(knowledge_point_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/knowledge-points/{knowledge_point_id}/source-preview",
    response_model=KnowledgePointSourcePreviewResponse,
)
async def get_family_knowledge_point_source_preview(
    knowledge_point_id: UUID,
    user_id: CurrentUserId,
):
    try:
        return await get_knowledge_point_source_preview(
            parent_user_id=user_id,
            knowledge_point_id=str(knowledge_point_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/knowledge-point-lessons/{lesson_id}",
    response_model=KnowledgePointLessonResponse,
)
async def get_family_knowledge_point_lesson(
    lesson_id: UUID,
    user_id: CurrentUserId,
):
    try:
        return await get_lesson_for_parent(
            parent_user_id=user_id,
            lesson_id=str(lesson_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/knowledge-point-lessons/{lesson_id}/revisions",
    response_model=KnowledgePointLessonResponse,
)
async def create_family_knowledge_point_lesson_revision(
    lesson_id: UUID,
    body: CreateKnowledgePointLessonRevisionRequest,
    user_id: CurrentUserId,
):
    try:
        await create_manual_lesson_revision(
            parent_user_id=user_id,
            lesson_id=str(lesson_id),
            content_markdown=body.content_markdown,
        )
        return await get_lesson_for_parent(
            parent_user_id=user_id,
            lesson_id=str(lesson_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/knowledge-point-lessons/{lesson_id}/review",
    response_model=KnowledgePointLessonResponse,
)
async def approve_family_knowledge_point_lesson(
    lesson_id: UUID,
    body: ApproveKnowledgePointLessonRequest,
    user_id: CurrentUserId,
):
    try:
        await approve_lesson_for_parent(
            parent_user_id=user_id,
            lesson_id=str(lesson_id),
            revision_id=str(body.revision_id),
        )
        return await get_lesson_for_parent(
            parent_user_id=user_id,
            lesson_id=str(lesson_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/textbook-versions/{version_id}/structure-publications",
    response_model=TextbookStructurePublicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def publish_family_textbook_structure(
    version_id: UUID,
    body: PublishTextbookStructureRequest,
    user_id: CurrentUserId,
):
    try:
        return await publish_structure_for_parent(
            parent_user_id=user_id,
            version_id=str(version_id),
            structure_id=str(body.structure_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/textbooks/{textbook_id}/processing",
    response_model=TextbookProcessingResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_family_textbook_processing(
    textbook_id: UUID, body: StartTextbookProcessingRequest, user_id: CurrentUserId
):
    try:
        if body.source_parse_job_ids:
            return await start_processing_from_parse_jobs(
                parent_user_id=user_id,
                textbook_id=str(textbook_id),
                source_parse_job_ids=body.source_parse_job_ids,
            )
        return await start_processing(
            parent_user_id=user_id,
            textbook_id=str(textbook_id),
            source_asset_ids=[str(asset_id) for asset_id in body.source_asset_ids],
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/textbook-processing/{job_id}/run", response_model=TextbookProcessingResponse
)
async def run_family_textbook_processing(job_id: UUID, user_id: CurrentUserId):
    try:
        return await run_processing_for_parent(
            parent_user_id=user_id, job_id=str(job_id)
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/textbook-processing/{job_id}/retry",
    response_model=TextbookProcessingResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_family_textbook_processing(job_id: UUID, user_id: CurrentUserId):
    try:
        return await retry_processing_for_parent(
            parent_user_id=user_id, job_id=str(job_id)
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/textbook-publications/{publication_id}/assignments",
    response_model=TextbookAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_family_textbook_publication(
    publication_id: UUID, body: AssignTextbookPublicationRequest, user_id: CurrentUserId
):
    try:
        return await assign_publication(
            parent_user_id=user_id,
            publication_id=str(publication_id),
            student_user_id=body.student_user_id,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get("/learning", response_model=list[dict])
async def list_student_learning(user_id: CurrentUserId):
    try:
        return await list_learning_assignments(student_user_id=user_id)
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/learning/{assignment_id}/structure",
    response_model=StudentTextbookStructureResponse,
)
async def get_student_assignment_structure(
    assignment_id: UUID,
    user_id: CurrentUserId,
):
    try:
        return await get_student_structure(
            student_user_id=user_id,
            assignment_id=str(assignment_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/learning/{assignment_id}/knowledge-points/{knowledge_point_id}",
    response_model=StudentKnowledgePointLessonResponse,
)
async def get_student_assignment_knowledge_point_lesson(
    assignment_id: UUID,
    knowledge_point_id: UUID,
    user_id: CurrentUserId,
):
    try:
        return await get_student_kp_lesson(
            student_user_id=user_id,
            assignment_id=str(assignment_id),
            knowledge_point_id=str(knowledge_point_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/learning/{assignment_id}/knowledge-points/{knowledge_point_id}/progress",
    response_model=dict,
)
async def update_student_kp_progress(
    assignment_id: UUID,
    knowledge_point_id: UUID,
    body: UpdateKnowledgePointProgressRequest,
    user_id: CurrentUserId,
):
    try:
        return await update_learning_progress(
            student_user_id=user_id,
            assignment_id=str(assignment_id),
            knowledge_point_id=str(knowledge_point_id),
            status=body.status,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/learning/{assignment_id}/items",
    response_model=list[LearningItemResponse],
)
async def list_student_learning_items(
    assignment_id: UUID,
    user_id: CurrentUserId,
    unit_id: UUID | None = None,
    knowledge_point_id: UUID | None = None,
):
    try:
        return await get_learning_items(
            student_user_id=user_id,
            assignment_id=str(assignment_id),
            unit_id=str(unit_id) if unit_id else None,
            knowledge_point_id=(
                str(knowledge_point_id) if knowledge_point_id else None
            ),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/learning/{assignment_id}/knowledge-points/{knowledge_point_id}/items",
    response_model=LearningItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_student_learning_item(
    assignment_id: UUID,
    knowledge_point_id: UUID,
    body: CreateLearningItemRequest,
    user_id: CurrentUserId,
):
    try:
        return await add_learning_item(
            student_user_id=user_id,
            assignment_id=str(assignment_id),
            unit_id=str(body.unit_id) if body.unit_id else None,
            knowledge_point_id=str(knowledge_point_id),
            kind=body.kind,
            content=body.content,
            source_anchor=body.source_anchor,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.patch(
    "/learning/{assignment_id}/items/{item_id}",
    response_model=LearningItemResponse,
)
async def update_student_learning_item(
    assignment_id: UUID,
    item_id: UUID,
    body: UpdateLearningItemRequest,
    user_id: CurrentUserId,
):
    del assignment_id
    try:
        return await edit_learning_item(
            student_user_id=user_id,
            item_id=str(item_id),
            content=body.content,
            source_anchor=body.source_anchor,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.delete(
    "/learning/{assignment_id}/items/{item_id}",
    response_model=dict,
)
async def delete_student_learning_item(
    assignment_id: UUID,
    item_id: UUID,
    user_id: CurrentUserId,
):
    del assignment_id
    try:
        await remove_learning_item(
            student_user_id=user_id,
            item_id=str(item_id),
        )
        return {"deleted": True}
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/learning/{assignment_id}/units/{unit_id}/summaries",
    response_model=LearningItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_student_unit_summary(
    assignment_id: UUID,
    unit_id: UUID,
    user_id: CurrentUserId,
):
    try:
        return await generate_unit_summary(
            student_user_id=user_id,
            assignment_id=str(assignment_id),
            unit_id=str(unit_id),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get("/learning/{assignment_id}/chat-space", response_model=dict)
async def get_student_learning_chat_space(assignment_id: UUID, user_id: CurrentUserId):
    try:
        return await get_learning_chat_space(
            user_id=user_id, assignment_id=str(assignment_id)
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/learning/{assignment_id}/chat-transcript", response_model=dict)
async def get_parent_student_learning_chat_transcript(
    assignment_id: UUID, user_id: CurrentUserId
):
    try:
        return await get_parent_learning_transcript(
            parent_user_id=user_id, assignment_id=str(assignment_id)
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc
