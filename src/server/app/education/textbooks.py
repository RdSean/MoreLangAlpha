"""Parent textbook management and student deterministic-learning routes."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from src.server.app.education.models import (
    AnswerLearningQuestionRequest,
    AssignTextbookPublicationRequest,
    CreateTextbookRequest,
    LearningAnswerResponse,
    LearningProgressResponse,
    StartTextbookProcessingRequest,
    TextbookAssignmentResponse,
    TextbookProcessingResponse,
    TextbookPublicationResponse,
    TextbookResponse,
    UpdateLearningProgressRequest,
)
from src.server.services.education_textbooks import (
    TextbookError,
    TextbookNotFoundError,
    TextbookPermissionError,
    TextbookTransitionError,
    answer_learning_question,
    assign_publication,
    create_textbook,
    get_parent_learning_records,
    get_parent_textbook,
    get_student_chapter_context,
    get_student_learning,
    list_learning_assignments,
    list_parent_textbooks,
    publish_version,
    record_learning_progress,
    retry_processing_for_parent,
    run_processing_for_parent,
    start_processing,
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


@router.get("/textbooks/{textbook_id}", response_model=dict)
async def get_family_textbook(textbook_id: UUID, user_id: CurrentUserId):
    try:
        return await get_parent_textbook(
            parent_user_id=user_id, textbook_id=str(textbook_id)
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
    textbook_id: UUID, version_id: UUID, user_id: CurrentUserId
):
    try:
        return await publish_version(
            parent_user_id=user_id,
            textbook_id=str(textbook_id),
            version_id=str(version_id),
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
