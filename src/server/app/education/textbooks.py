"""Parent textbook management and student deterministic-learning routes."""

from contextlib import aclosing
from datetime import UTC
from email.utils import format_datetime
import asyncio
from uuid import UUID
from typing import Literal
from pydantic import BaseModel

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import Response, StreamingResponse
from starlette.background import BackgroundTask
from src.server.documents.http_range import RangeNotSatisfiable

from src.server.app.education.book_models import (
    BookActivityPageResponse,
    BookAssignmentRequest,
    BookAssignmentResponse,
    BookJobCreateRequest,
    BookSourceListResponse,
    BookSourceSliceResponse,
    BookOriginalLocationResponse,
    BookStructureResponse,
    CreateBookRequest,
    CreateBookResponse,
    BookJobResponse,
    BookJobStatisticsResponse,
    BookLessonPdfRequest,
    KnowledgePointMaterialResponse,
    StudentBookAssignmentResponse,
    StudentBookStructureResponse,
    StudentKnowledgePointMaterialResponse,
    TextbookSummaryResponse,
    TextbookWorkbenchResponse,
)
from src.server.app.education.models import (
    CreateLearningItemRequest,
    LearningItemResponse,
    UpdateLearningItemRequest,
    UpdateKnowledgePointProgressRequest,
)
from src.server.database.education_book_jobs import get_book_job_for_parent
from src.server.services.education_book_activity import BookActivityService
from src.server.services.education_book_timing import get_book_job_statistics
from src.server.services.education_book_original import (
    get_book_original_location,
    open_book_original,
)
from src.server.utils.http_headers import content_disposition
from src.server.services.education_learning_assets import (
    add_learning_item,
    edit_learning_item,
    generate_node_summary,
    get_learning_items,
    remove_learning_item,
    update_learning_progress,
)
from src.server.services.education_textbooks import (
    TextbookError,
    TextbookNotFoundError,
    TextbookPermissionError,
    TextbookTransitionError,
    assign_managed_textbook,
    create_managed_textbook,
    delete_managed_textbook,
    create_managed_textbook_job,
    cancel_managed_textbook_job,
    get_managed_knowledge_point_material,
    get_managed_textbook_source,
    get_managed_textbook_structure,
    get_managed_textbook_workbench,
    get_student_kp_lesson,
    get_student_structure,
    list_managed_textbook_assignments,
    list_book_source_candidates,
    list_learning_assignments,
    list_managed_textbooks,
    open_managed_textbook_asset,
    retry_managed_textbook_job,
    revoke_managed_textbook,
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


def _textbook_http_error(exc: TextbookError) -> HTTPException:
    if isinstance(exc, TextbookPermissionError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, TextbookNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, TextbookTransitionError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


class BookReadingRequest(BaseModel):
    state: Literal["viewed", "asked"] = "viewed"


@router.get("/textbooks/{textbook_id}/reading-state", response_model=list[dict])
async def get_reading_state(textbook_id: UUID, user_id: CurrentUserId):
    from src.server.services.education_book_study import get_book_reading_states
    try:
        return await get_book_reading_states(user_id=user_id, textbook_id=str(textbook_id))
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post("/textbooks/{textbook_id}/knowledge-points/{knowledge_point_id}/reading-state", status_code=204)
async def record_reading_state(textbook_id: UUID, knowledge_point_id: UUID, request: BookReadingRequest, user_id: CurrentUserId):
    from src.server.services.education_book_study import record_book_reading
    try:
        await record_book_reading(user_id=user_id, textbook_id=str(textbook_id), knowledge_point_id=str(knowledge_point_id), state=request.state)
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc
    return Response(status_code=204)


@router.post("/textbooks/{textbook_id}/knowledge-points/{knowledge_point_id}/chat-space", response_model=dict)
async def get_parent_lesson_space(textbook_id: UUID, knowledge_point_id: UUID, user_id: CurrentUserId):
    from src.server.services.education_book_study import get_book_study_space
    try:
        return await get_book_study_space(user_id=user_id, textbook_id=str(textbook_id), knowledge_point_id=str(knowledge_point_id))
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get("/textbooks/{textbook_id}/knowledge-points/{knowledge_point_id}/questions", response_model=list[dict])
async def get_parent_lesson_history(textbook_id: UUID, knowledge_point_id: UUID, user_id: CurrentUserId, assignment_id: UUID | None = None):
    from src.server.services.education_book_study import get_book_study_history
    try:
        return await get_book_study_history(user_id=user_id, textbook_id=str(textbook_id), knowledge_point_id=str(knowledge_point_id), assignment_id=str(assignment_id) if assignment_id else None)
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post("/textbooks/{textbook_id}/knowledge-points/{knowledge_point_id}/export-pdf", response_class=Response)
async def export_book_lesson_pdf(textbook_id: UUID, knowledge_point_id: UUID, request: BookLessonPdfRequest, user_id: CurrentUserId):
    from src.server.services.education_lesson_export import export_lesson_pdf
    from src.server.services.pdf_render import PdfRenderError, PdfRenderTimeout, PdfRenderUnavailable

    try:
        pdf = await asyncio.wait_for(export_lesson_pdf(user_id=user_id, textbook_id=str(textbook_id), knowledge_point_id=str(knowledge_point_id), request=request), timeout=60)
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PdfRenderUnavailable as exc:
        raise HTTPException(status_code=503, detail="PDF 导出服务暂不可用，请稍后重试。") from exc
    except (PdfRenderTimeout, asyncio.TimeoutError) as exc:
        raise HTTPException(status_code=504, detail="PDF 导出超时，请稍后重试。") from exc
    except PdfRenderError as exc:
        raise HTTPException(status_code=502, detail="PDF 内容未能完整生成，请稍后重试。") from exc
    return Response(content=pdf.content, media_type="application/pdf", headers={
        "Content-Disposition": content_disposition(pdf.filename, disposition="attachment"),
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    })


def _managed_book_job_not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Book job not found")


@router.get("/textbooks/{textbook_id}/knowledge-points/{knowledge_point_id}/conversation/replay", response_model=list[dict])
async def get_lesson_conversation_replay(textbook_id: UUID, knowledge_point_id: UUID,
                                        user_id: CurrentUserId, assignment_id: UUID | None = None):
    from src.server.services.education_book_study import get_book_conversation_replay
    try:
        return await get_book_conversation_replay(
            user_id=user_id, textbook_id=str(textbook_id), knowledge_point_id=str(knowledge_point_id),
            assignment_id=str(assignment_id) if assignment_id else None,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get("/book-jobs/{job_id}", response_model=BookJobResponse)
async def get_managed_book_job(job_id: UUID, user_id: CurrentUserId):
    job = await get_book_job_for_parent(
        job_id=job_id,
        parent_user_id=user_id,
    )
    if job is None:
        raise _managed_book_job_not_found()
    return BookJobResponse.model_validate(job)


@router.get("/textbooks/{textbook_id}/knowledge-points/{knowledge_point_id}/conversation/status", response_model=dict)
async def get_lesson_conversation_status(textbook_id: UUID, knowledge_point_id: UUID,
                                        user_id: CurrentUserId, assignment_id: UUID | None = None):
    from src.server.services.education_book_study import get_book_conversation_status
    try:
        return await get_book_conversation_status(user_id=user_id, textbook_id=str(textbook_id),
            knowledge_point_id=str(knowledge_point_id), assignment_id=str(assignment_id) if assignment_id else None)
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/book-jobs/{job_id}/events",
    response_class=StreamingResponse,
)
async def stream_managed_book_job_events(
    job_id: UUID,
    user_id: CurrentUserId,
    after_seq: int = Query(0, ge=0),
):
    job = await get_book_job_for_parent(
        job_id=job_id,
        parent_user_id=user_id,
    )

    if job is None:
        raise _managed_book_job_not_found()

    async def event_generator():
        service = BookActivityService()
        pages = service.pages(
            job_id=job_id,
            parent_user_id=user_id,
            after_seq=after_seq,
        )
        async with aclosing(pages):
            async for raw_page in pages:
                page = BookActivityPageResponse.model_validate(raw_page)
                delivered_seq = max((event.seq for event in page.events), default=None)
                event_id = f"id: {delivered_seq}\n" if delivered_seq is not None else ""
                yield (f"{event_id}event: snapshot\ndata: {page.model_dump_json()}\n\n")

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers=_BOOK_PROGRESS_SSE_HEADERS,
    )


@router.get("/book-jobs/{job_id}/statistics", response_model=BookJobStatisticsResponse)
async def managed_book_job_statistics(
    job_id: UUID,
    user_id: CurrentUserId,
    cursor: str | None = Query(None, max_length=80),
    limit: int = Query(50, ge=1, le=100),
):
    try:
        result = await get_book_job_statistics(
            job_id=job_id, parent_user_id=user_id, cursor=cursor, limit=limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise _managed_book_job_not_found()
    return BookJobStatisticsResponse.model_validate(result)


@router.get("/textbook-sources", response_model=BookSourceListResponse)
async def list_managed_textbook_sources(user_id: CurrentUserId):
    try:
        return {"items": await list_book_source_candidates(parent_user_id=user_id)}
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get("/textbooks", response_model=list[TextbookSummaryResponse])
async def list_textbooks(user_id: CurrentUserId):
    try:
        return await list_managed_textbooks(parent_user_id=user_id)
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/textbooks",
    response_model=CreateBookResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_family_textbook(body: CreateBookRequest, user_id: CurrentUserId):
    try:
        return await create_managed_textbook(
            parent_user_id=user_id,
            parse_job_id=body.parse_job_id,
            primary_artifact_id=body.primary_artifact_id,
            title=body.title,
            idempotency_key=body.idempotency_key,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get("/textbooks/{textbook_id}", response_model=TextbookWorkbenchResponse)
async def get_family_textbook(textbook_id: UUID, user_id: CurrentUserId):
    try:
        return await get_managed_textbook_workbench(
            parent_user_id=user_id,
            textbook_id=textbook_id,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.delete("/textbooks/{textbook_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_family_textbook(textbook_id: UUID, user_id: CurrentUserId):
    try:
        await delete_managed_textbook(parent_user_id=user_id, textbook_id=textbook_id)
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/textbooks/{textbook_id}/structure",
    response_model=BookStructureResponse,
)
async def get_managed_structure(textbook_id: UUID, user_id: CurrentUserId):
    try:
        return await get_managed_textbook_structure(
            user_id=user_id,
            textbook_id=textbook_id,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/textbooks/{textbook_id}/source",
    response_model=BookSourceSliceResponse,
)
async def get_managed_source(
    textbook_id: UUID,
    user_id: CurrentUserId,
    start_line: int = Query(..., ge=1),
    end_line: int = Query(..., ge=1),
):
    try:
        return await get_managed_textbook_source(
            user_id=user_id,
            textbook_id=textbook_id,
            start_line=start_line,
            end_line=end_line,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get("/textbooks/{textbook_id}/original")
async def get_original_file(textbook_id: UUID, user_id: CurrentUserId, request: Request):
    try:
        range_header = request.headers.get('range')
        range_options = {'range_header': range_header, 'if_range': request.headers.get('if-range')} if range_header else {}
        download = await open_book_original(
            user_id=user_id, textbook_id=str(textbook_id), **range_options
        )
    except RangeNotSatisfiable as exc:
        return Response(status_code=416, headers={
            'Content-Range': f'bytes */{exc.total_length}', 'Cache-Control': 'private, no-store',
            'Content-Encoding': 'identity', 'Accept-Ranges': 'bytes',
        })
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc
    headers = {
        "Content-Disposition": content_disposition(download.filename),
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
        'Accept-Ranges': 'bytes',
        # Range offsets must describe the original PDF, not gzip-compressed bytes.
        'Content-Encoding': 'identity',
    }
    opened = download.object_download
    etag = getattr(opened, 'etag', None)
    modified = getattr(opened, 'last_modified', None)
    if etag:
        headers['ETag'] = etag
    if modified:
        headers['Last-Modified'] = format_datetime(modified.astimezone(UTC), usegmt=True)
    byte_range = getattr(download, 'byte_range', None)
    if byte_range:
        headers['Content-Range'] = f'bytes {byte_range.start}-{byte_range.end}/{download.total_length}'
    if download.object_download.content_length is not None:
        headers["Content-Length"] = str(download.object_download.content_length)
    return StreamingResponse(
        download.object_download.chunks,
        status_code=206 if byte_range else 200,
        media_type=download.media_type,
        headers=headers,
        background=BackgroundTask(download.object_download.close),
    )


@router.get(
    "/textbooks/{textbook_id}/original-location",
    response_model=BookOriginalLocationResponse,
)
async def get_original_location(
    textbook_id: UUID, user_id: CurrentUserId, start_line: int = Query(..., ge=1)
):
    try:
        return await get_book_original_location(
            user_id=user_id, textbook_id=str(textbook_id), start_line=start_line
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/textbooks/{textbook_id}/knowledge-points/{knowledge_point_id}/material",
    response_model=KnowledgePointMaterialResponse,
)
async def get_managed_material(
    textbook_id: UUID,
    knowledge_point_id: UUID,
    user_id: CurrentUserId,
):
    try:
        return await get_managed_knowledge_point_material(
            user_id=user_id,
            textbook_id=textbook_id,
            knowledge_point_id=knowledge_point_id,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get("/textbooks/{textbook_id}/assets/{asset_id}", response_class=Response)
async def get_managed_asset(
    textbook_id: UUID,
    asset_id: str,
    user_id: CurrentUserId,
):
    try:
        asset = await open_managed_textbook_asset(
            user_id=user_id,
            textbook_id=textbook_id,
            asset_id=asset_id,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc
    return Response(
        content=asset["content"],
        media_type=asset["media_type"],
        headers={
            "Cache-Control": "private, max-age=3600",
            "ETag": f'"{asset["sha256"]}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/textbooks/{textbook_id}/cover", response_class=Response)
async def get_textbook_cover(textbook_id: UUID, user_id: CurrentUserId):
    from src.server.services.education_textbook_cover import open_textbook_cover
    from src.server.services.education_textbook_cover import TextbookCoverStorageError

    try:
        cover = await open_textbook_cover(user_id=user_id, textbook_id=str(textbook_id))
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc
    except TextbookCoverStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return Response(
        content=cover["content"], media_type=cover["media_type"],
        headers={"Cache-Control": "private, max-age=3600", "ETag": f'"{cover["sha256"]}"', "X-Content-Type-Options": "nosniff"},
    )


@router.post("/textbooks/{textbook_id}/cover", response_model=dict)
async def upload_textbook_cover(
    textbook_id: UUID, user_id: CurrentUserId, file: UploadFile = File(...)
):
    from src.server.services.education_textbook_cover import (
        CoverUpload, TextbookCoverStorageError, TextbookCoverValidationError,
        replace_textbook_cover,
    )
    try:
        content = await file.read(10 * 1024 * 1024 + 1)
        return await replace_textbook_cover(
            parent_user_id=user_id, textbook_id=str(textbook_id),
            upload=CoverUpload(
                filename=file.filename or "cover", content_type=file.content_type or "", content=content
            ),
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc
    except TextbookCoverValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except TextbookCoverStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.delete("/textbooks/{textbook_id}/cover", response_model=dict)
async def delete_textbook_cover(textbook_id: UUID, user_id: CurrentUserId):
    from src.server.services.education_textbook_cover import remove_textbook_cover
    try:
        return await remove_textbook_cover(
            parent_user_id=user_id, textbook_id=str(textbook_id)
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/textbooks/{textbook_id}/jobs",
    response_model=BookJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_managed_job(
    textbook_id: UUID,
    body: BookJobCreateRequest,
    user_id: CurrentUserId,
):
    try:
        return await create_managed_textbook_job(
            parent_user_id=user_id,
            textbook_id=textbook_id,
            request=body,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/book-jobs/{job_id}/cancel",
    response_model=BookJobResponse,
)
async def cancel_managed_job(job_id: UUID, user_id: CurrentUserId):
    try:
        return await cancel_managed_textbook_job(
            parent_user_id=user_id,
            job_id=job_id,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/book-jobs/{job_id}/retry",
    response_model=BookJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_managed_job(job_id: UUID, user_id: CurrentUserId):
    try:
        return await retry_managed_textbook_job(
            parent_user_id=user_id,
            job_id=job_id,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/textbooks/{textbook_id}/assignments",
    response_model=list[BookAssignmentResponse],
)
async def list_managed_assignments(textbook_id: UUID, user_id: CurrentUserId):
    try:
        return await list_managed_textbook_assignments(
            parent_user_id=user_id,
            textbook_id=textbook_id,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/textbooks/{textbook_id}/assignments",
    response_model=list[BookAssignmentResponse],
)
async def assign_managed_students(
    textbook_id: UUID,
    body: BookAssignmentRequest,
    user_id: CurrentUserId,
):
    try:
        return await assign_managed_textbook(
            parent_user_id=user_id,
            textbook_id=textbook_id,
            student_user_ids=body.student_user_ids,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.delete(
    "/textbooks/{textbook_id}/assignments",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_managed_students(
    textbook_id: UUID,
    body: BookAssignmentRequest,
    user_id: CurrentUserId,
):
    try:
        await revoke_managed_textbook(
            parent_user_id=user_id,
            textbook_id=textbook_id,
            student_user_ids=body.student_user_ids,
        )
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/learning", response_model=list[StudentBookAssignmentResponse])
async def list_student_learning(user_id: CurrentUserId):
    try:
        return await list_learning_assignments(student_user_id=user_id)
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.get(
    "/learning/{assignment_id}/structure",
    response_model=StudentBookStructureResponse,
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
    response_model=StudentKnowledgePointMaterialResponse,
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
    skill_node_id: str | None = None,
    knowledge_point_id: UUID | None = None,
):
    try:
        return await get_learning_items(
            student_user_id=user_id,
            assignment_id=str(assignment_id),
            skill_node_id=skill_node_id,
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
            skill_node_id=body.skill_node_id,
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
    try:
        return await edit_learning_item(
            student_user_id=user_id,
            assignment_id=str(assignment_id),
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
    try:
        await remove_learning_item(
            student_user_id=user_id,
            assignment_id=str(assignment_id),
            item_id=str(item_id),
        )
        return {"deleted": True}
    except TextbookError as exc:
        raise _textbook_http_error(exc) from exc


@router.post(
    "/learning/{assignment_id}/nodes/{skill_node_id}/summaries",
    response_model=LearningItemResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_student_node_summary(
    assignment_id: UUID,
    skill_node_id: str,
    user_id: CurrentUserId,
):
    try:
        return await generate_node_summary(
            student_user_id=user_id,
            assignment_id=str(assignment_id),
            skill_node_id=skill_node_id,
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
