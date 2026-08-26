"""Role-bound FastAPI routes for materialized family homework tasks."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

from src.server.app.education.models import (
    CheckInEducationTaskRequest,
    CreateEducationTaskRequest,
    EducationReviewResponse,
    EducationSubmissionResponse,
    EducationTaskDetailResponse,
    EducationTaskResponse,
    EducationHomeworkDictionariesResponse,
    ReviewEducationTaskRequest,
    SubmitEducationTaskRequest,
)
from src.server.services.education_homework import (
    EducationDictionaryPermissionError,
    get_homework_dictionaries,
)
from src.server.services.education_tasks import (
    EducationTaskAssetError,
    EducationTaskError,
    EducationTaskNotFoundError,
    EducationTaskPermissionError,
    EducationTaskTransitionError,
    append_revision_submission,
    cancel_task,
    check_in_task,
    create_task,
    get_task_detail,
    list_tasks,
    review_task,
    stop_task_rule,
    submit_task,
)
from src.server.utils.api import CurrentUserId


router = APIRouter(prefix="/api/v1/education", tags=["Education tasks"])


def _task_http_error(exc: EducationTaskError) -> HTTPException:
    if isinstance(exc, EducationTaskPermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, EducationTaskNotFoundError):
        return HTTPException(status_code=404, detail="Homework task not found")
    if isinstance(exc, EducationTaskTransitionError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, EducationTaskAssetError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/dictionaries", response_model=EducationHomeworkDictionariesResponse)
async def get_education_homework_dictionaries(user_id: CurrentUserId):
    try:
        return await get_homework_dictionaries(user_id)
    except EducationDictionaryPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc


@router.get("/tasks", response_model=list[EducationTaskResponse], response_model_exclude_none=True)
async def list_education_tasks(user_id: CurrentUserId):
    return await list_tasks(user_id)


@router.get(
    "/tasks/{task_id}",
    response_model=EducationTaskDetailResponse,
    response_model_exclude_none=True,
)
async def get_education_task_detail(task_id: UUID, user_id: CurrentUserId):
    try:
        return await get_task_detail(user_id=user_id, task_id=str(task_id))
    except EducationTaskError as exc:
        raise _task_http_error(exc) from exc


@router.post("/tasks", response_model=EducationTaskResponse, response_model_exclude_none=True, status_code=status.HTTP_201_CREATED)
async def create_education_task(body: CreateEducationTaskRequest, user_id: CurrentUserId):
    try:
        return await create_task(
            parent_user_id=user_id,
            assigned_student_id=body.assigned_student_id,
            title=body.title,
            description=body.description,
            due_at=body.due_at,
            subject_code=body.subject_code,
            type_code=body.type_code,
            practice_source_code=body.practice_source_code,
            frequency=body.frequency,
            weekdays=body.weekdays,
            material_asset_ids=[str(asset_id) for asset_id in body.material_asset_ids],
        )
    except EducationTaskError as exc:
        raise _task_http_error(exc) from exc


@router.post("/tasks/{task_id}/submissions", response_model=EducationSubmissionResponse, response_model_exclude_none=True, status_code=status.HTTP_201_CREATED)
async def create_education_submission(
    task_id: UUID, body: SubmitEducationTaskRequest, user_id: CurrentUserId
):
    try:
        return await submit_task(
            student_user_id=user_id,
            task_id=str(task_id),
            submission_text=body.submission_text,
            idempotency_key=str(body.idempotency_key) if body.idempotency_key else None,
            asset_ids=[str(asset_id) for asset_id in body.asset_ids],
        )
    except EducationTaskError as exc:
        raise _task_http_error(exc) from exc


@router.post("/tasks/{task_id}/check-in", response_model=EducationSubmissionResponse, response_model_exclude_none=True, status_code=status.HTTP_201_CREATED)
async def check_in_education_task(
    task_id: UUID, body: CheckInEducationTaskRequest, user_id: CurrentUserId
):
    try:
        return await check_in_task(
            student_user_id=user_id,
            task_id=str(task_id),
            submission_text=body.submission_text,
            idempotency_key=str(body.idempotency_key) if body.idempotency_key else None,
            asset_ids=[str(asset_id) for asset_id in body.asset_ids],
        )
    except EducationTaskError as exc:
        raise _task_http_error(exc) from exc


@router.post("/tasks/{task_id}/revisions", response_model=EducationSubmissionResponse, response_model_exclude_none=True, status_code=status.HTTP_201_CREATED)
async def create_education_revision(
    task_id: UUID, body: SubmitEducationTaskRequest, user_id: CurrentUserId
):
    try:
        return await append_revision_submission(
            student_user_id=user_id,
            task_id=str(task_id),
            submission_text=body.submission_text,
            idempotency_key=str(body.idempotency_key) if body.idempotency_key else None,
            asset_ids=[str(asset_id) for asset_id in body.asset_ids],
        )
    except EducationTaskError as exc:
        raise _task_http_error(exc) from exc


@router.post("/tasks/{task_id}/reviews", response_model=EducationReviewResponse, response_model_exclude_none=True, status_code=status.HTTP_201_CREATED)
async def create_education_review(
    task_id: UUID, body: ReviewEducationTaskRequest, user_id: CurrentUserId
):
    try:
        return await review_task(
            parent_user_id=user_id,
            task_id=str(task_id),
            feedback_text=body.feedback_text,
            decision=body.decision,
        )
    except EducationTaskError as exc:
        raise _task_http_error(exc) from exc


@router.post("/tasks/{task_id}/cancel", response_model=EducationTaskResponse, response_model_exclude_none=True)
async def cancel_education_task(task_id: UUID, user_id: CurrentUserId):
    try:
        return await cancel_task(parent_user_id=user_id, task_id=str(task_id))
    except EducationTaskError as exc:
        raise _task_http_error(exc) from exc


@router.post("/tasks/rules/{task_rule_id}/stop", status_code=status.HTTP_204_NO_CONTENT)
async def stop_education_task_rule(task_rule_id: UUID, user_id: CurrentUserId):
    try:
        await stop_task_rule(parent_user_id=user_id, task_rule_id=str(task_rule_id))
    except EducationTaskError as exc:
        raise _task_http_error(exc) from exc
