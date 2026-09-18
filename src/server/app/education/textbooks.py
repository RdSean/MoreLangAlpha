"""Parent textbook management and student deterministic-learning routes."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from src.server.app.education.models import (
    AnswerLearningQuestionRequest,
    AssignTextbookPublicationRequest,
    ApproveKnowledgePointLessonRequest,
    CreateKnowledgePointLessonRevisionRequest,
    CreateTextbookRequest,
    GenerateKnowledgePointLessonRequest,
    KnowledgePointLessonResponse,
    LearningAnswerResponse,
    LearningProgressResponse,
    PublishTextbookVersionRequest,
    PublishTextbookStructureRequest,
    StartTextbookProcessingRequest,
    StructureGenerationJobResponse,
    TextbookAssignmentResponse,
    TextbookDetailResponse,
    TextbookParseJobCandidateResponse,
    TextbookProcessingResponse,
    TextbookPublicationResponse,
    TextbookResponse,
    TextbookStructurePublicationResponse,
    TextbookStructureResponse,
    TeachingJobResponse,
    TeachingPackageAssetSummaryResponse,
    TeachingChapterAssetResponse,
    TeachingReviewAssetKind,
    UpdateLearningProgressRequest,
    UpdateTextbookStructureRequest,
)
from src.server.services.education_structure_review import (
    accept_structure_for_parent,
    get_structure_for_parent,
    get_structure_generation_job,
    get_latest_structure_for_parent,
    queue_structure_for_parent,
    replace_structure_for_parent,
)
from src.server.services.education_lesson_review import (
    approve_lesson_for_parent,
    create_manual_lesson_revision,
    get_lesson_for_parent,
    get_lesson_for_knowledge_point,
    publish_structure_for_parent,
    queue_lesson_for_parent,
)
from src.server.services.education_textbooks import (
    TextbookError,
    TextbookNotFoundError,
    TextbookPermissionError,
    TextbookTransitionError,
    answer_learning_question,
    assign_publication,
    cancel_teaching_job_for_parent,
    create_textbook,
    get_parent_learning_records,
    get_parent_textbook,
    get_teaching_asset_summary,
    get_teaching_chapter_asset,
    get_teaching_job_projection,
    get_student_chapter_context,
    get_student_learning,
    list_learning_assignments,
    list_completed_textbook_parse_jobs,
    list_parent_textbooks,
    publish_version,
    queue_teaching_package_for_parent,
    record_learning_progress,
    retry_processing_for_parent,
    run_processing_for_parent,
    resume_teaching_job_for_parent,
    start_processing,
    start_processing_from_parse_jobs,
)
from src.server.services.education_learning_chat import get_learning_chat_space
from src.server.services.education_learning_transcript import (
    get_parent_learning_transcript,
)
from src.server.utils.api import CurrentUserId


router = APIRouter(prefix="/api/v1/education", tags=["Education textbooks"])


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
    "/textbook-versions/{content_version_id}/structures",
    response_model=StructureGenerationJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_family_textbook_structure(
    content_version_id: UUID,
    user_id: CurrentUserId,
):
    try:
        return await queue_structure_for_parent(
            parent_user_id=user_id,
            content_version_id=str(content_version_id),
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


@router.get(
    "/teaching-packages/{teaching_package_id}/assets",
    response_model=TeachingPackageAssetSummaryResponse,
)
async def get_family_teaching_asset_summary(
    teaching_package_id: UUID, user_id: CurrentUserId
):
    try:
        return await get_teaching_asset_summary(
            parent_user_id=user_id, teaching_package_id=str(teaching_package_id)
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/teaching-packages/{teaching_package_id}/chapters/{chapter_id}/assets/{kind}",
    response_model=TeachingChapterAssetResponse,
)
async def get_family_teaching_chapter_asset(
    teaching_package_id: UUID,
    chapter_id: UUID,
    kind: TeachingReviewAssetKind,
    user_id: CurrentUserId,
):
    try:
        return await get_teaching_chapter_asset(
            parent_user_id=user_id,
            teaching_package_id=str(teaching_package_id),
            chapter_id=str(chapter_id),
            kind=kind,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/textbook-versions/{content_version_id}/teaching-packages",
    response_model=TeachingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def queue_family_teaching_package(content_version_id: UUID, user_id: CurrentUserId):
    try:
        return await queue_teaching_package_for_parent(
            parent_user_id=user_id, content_version_id=str(content_version_id)
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get("/teaching-jobs/{job_id}", response_model=TeachingJobResponse)
async def get_family_teaching_job(job_id: UUID, user_id: CurrentUserId):
    try:
        return await get_teaching_job_projection(
            parent_user_id=user_id, job_id=str(job_id)
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/teaching-jobs/{job_id}/cancel", response_model=TeachingJobResponse
)
async def cancel_family_teaching_job(job_id: UUID, user_id: CurrentUserId):
    try:
        return await cancel_teaching_job_for_parent(
            parent_user_id=user_id, job_id=str(job_id)
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/teaching-jobs/{job_id}/resume",
    response_model=TeachingJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_family_teaching_job(job_id: UUID, user_id: CurrentUserId):
    try:
        return await resume_teaching_job_for_parent(
            parent_user_id=user_id, job_id=str(job_id)
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
    "/textbooks/{textbook_id}/versions/{version_id}/publish",
    response_model=TextbookPublicationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def publish_family_textbook_version(
    textbook_id: UUID,
    version_id: UUID,
    body: PublishTextbookVersionRequest,
    user_id: CurrentUserId,
):
    try:
        return await publish_version(
            parent_user_id=user_id,
            textbook_id=str(textbook_id),
            version_id=str(version_id),
            teaching_package_id=str(body.teaching_package_id),
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


@router.get("/learning/{assignment_id}", response_model=dict)
async def get_student_assignment_learning(assignment_id: UUID, user_id: CurrentUserId):
    try:
        return await get_student_learning(
            student_user_id=user_id, assignment_id=str(assignment_id)
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/learning/{assignment_id}/chapters/{chapter_id}/context", response_model=dict
)
async def get_student_learning_chapter_context(
    assignment_id: UUID, chapter_id: UUID, user_id: CurrentUserId
):
    try:
        return await get_student_chapter_context(
            student_user_id=user_id,
            assignment_id=str(assignment_id),
            chapter_id=str(chapter_id),
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


@router.post(
    "/learning/{assignment_id}/chapters/{chapter_id}/progress",
    response_model=LearningProgressResponse,
)
async def update_student_learning_progress(
    assignment_id: UUID,
    chapter_id: UUID,
    body: UpdateLearningProgressRequest,
    user_id: CurrentUserId,
):
    try:
        return await record_learning_progress(
            student_user_id=user_id,
            assignment_id=str(assignment_id),
            chapter_id=str(chapter_id),
            status=body.status,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/learning/{assignment_id}/questions/{question_id}/answers",
    response_model=LearningAnswerResponse,
    status_code=status.HTTP_201_CREATED,
)
async def answer_student_learning_question(
    assignment_id: UUID,
    question_id: UUID,
    body: AnswerLearningQuestionRequest,
    user_id: CurrentUserId,
):
    try:
        return await answer_learning_question(
            student_user_id=user_id,
            assignment_id=str(assignment_id),
            question_id=str(question_id),
            selected_option=body.selected_option,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get("/learning/{assignment_id}/records", response_model=dict)
async def get_parent_student_learning_records(
    assignment_id: UUID, user_id: CurrentUserId
):
    try:
        return await get_parent_learning_records(
            parent_user_id=user_id, assignment_id=str(assignment_id)
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


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
