"""Authenticated REST and SSE surface for the document knowledge library."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import (
    JSONResponse,
    RedirectResponse,
    Response,
    StreamingResponse,
)

from src.server.database.documents import DocumentListFilter
from src.server.documents.contracts import (
    DocumentDomainError,
    FileTooLargeError,
    ParserIncompatibleError,
    ParserUnavailableError,
    UnsupportedMediaTypeError,
)
from src.server.documents.inspection import DocumentInspectionService
from src.server.documents.jobs import DocumentParseJobService
from src.server.documents.library import DocumentLibraryService
from src.server.documents.storage import S3CompatibleDocumentStore
from src.server.models.documents import (
    ArtifactListResponse,
    ArtifactResponse,
    CreateParseJobRequest,
    DatasetCreate,
    DatasetListResponse,
    DatasetResponse,
    DatasetUpdate,
    DocumentListResponse,
    DocumentResponse,
    DocumentUpdate,
    InspectionOutcomeResponse,
    InspectionResponse,
    ParseJobListResponse,
    ParseJobResponse,
    ParserOptionResponse,
    ParserOptionsResponse,
    TagCreate,
    TagResponse,
)
from src.server.services.document_job_events import (
    DocumentJobEventService,
    publish_document_job_hint,
)
from src.server.services.education_access import require_nonstudent_agent_features
from src.server.utils.api import CurrentUserId


logger = logging.getLogger(__name__)


def get_document_library_service() -> DocumentLibraryService:
    return DocumentLibraryService(object_store=S3CompatibleDocumentStore())


def get_document_inspection_service() -> DocumentInspectionService:
    return DocumentInspectionService(object_store=S3CompatibleDocumentStore())


def get_document_job_service() -> DocumentParseJobService:
    return DocumentParseJobService(
        object_store=S3CompatibleDocumentStore(),
        notifier=publish_document_job_hint,
    )


def get_document_event_service() -> DocumentJobEventService:
    return DocumentJobEventService()


LibraryService = Annotated[
    DocumentLibraryService, Depends(get_document_library_service)
]
InspectionService = Annotated[
    DocumentInspectionService, Depends(get_document_inspection_service)
]
JobService = Annotated[DocumentParseJobService, Depends(get_document_job_service)]
EventService = Annotated[DocumentJobEventService, Depends(get_document_event_service)]


async def _require_document_access(user_id: CurrentUserId) -> None:
    await require_nonstudent_agent_features(user_id)


router = APIRouter(
    prefix="/api/v1",
    tags=["Documents"],
    dependencies=[Depends(_require_document_access)],
)


def _not_found(resource: str) -> HTTPException:
    return HTTPException(status_code=404, detail=f"{resource} not found")


def _domain_error(error: DocumentDomainError) -> HTTPException:
    status_code = 422
    if isinstance(error, FileTooLargeError):
        status_code = 413
    elif isinstance(error, UnsupportedMediaTypeError):
        status_code = 415
    elif isinstance(error, (ParserUnavailableError, ParserIncompatibleError)):
        status_code = 409
    return HTTPException(
        status_code=status_code,
        detail={"code": error.code, "message": error.safe_message},
    )


@router.post("/document-datasets", response_model=DatasetResponse, status_code=201)
async def create_dataset(
    request: DatasetCreate, user_id: CurrentUserId, service: LibraryService
) -> DatasetResponse:
    row = await service.create_dataset(
        owner_user_id=user_id, name=request.name, description=request.description
    )
    return DatasetResponse.model_validate(row)


@router.get("/document-datasets", response_model=DatasetListResponse)
async def list_datasets(
    user_id: CurrentUserId,
    service: LibraryService,
    query: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> DatasetListResponse:
    rows, total = await service.list_datasets(
        owner_user_id=user_id, query=query, limit=limit, offset=offset
    )
    return DatasetListResponse(
        items=[DatasetResponse.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/document-datasets/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(
    dataset_id: str, user_id: CurrentUserId, service: LibraryService
) -> DatasetResponse:
    row = await service.get_dataset(owner_user_id=user_id, dataset_id=dataset_id)
    if row is None:
        raise _not_found("Dataset")
    return DatasetResponse.model_validate(row)


@router.patch("/document-datasets/{dataset_id}", response_model=DatasetResponse)
async def update_dataset(
    dataset_id: str,
    request: DatasetUpdate,
    user_id: CurrentUserId,
    service: LibraryService,
) -> DatasetResponse:
    row = await service.patch_dataset(
        owner_user_id=user_id,
        dataset_id=dataset_id,
        name=request.name,
        description=request.description,
    )
    if row is None:
        raise _not_found("Dataset")
    return DatasetResponse.model_validate(row)


@router.delete("/document-datasets/{dataset_id}", status_code=204)
async def delete_dataset(
    dataset_id: str, user_id: CurrentUserId, service: LibraryService
) -> Response:
    if (
        await service.delete_dataset(owner_user_id=user_id, dataset_id=dataset_id)
        is None
    ):
        raise _not_found("Dataset")
    return Response(status_code=204)


@router.get("/document-tags", response_model=list[TagResponse])
async def list_tags(
    user_id: CurrentUserId, service: LibraryService
) -> list[TagResponse]:
    rows = await service.list_tags(owner_user_id=user_id)
    return [TagResponse.model_validate(row) for row in rows]


@router.post("/document-tags", response_model=TagResponse, status_code=201)
async def create_tag(
    request: TagCreate, user_id: CurrentUserId, service: LibraryService
) -> TagResponse:
    row = await service.create_tag(owner_user_id=user_id, name=request.name)
    return TagResponse.model_validate(row)


@router.delete("/document-tags/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: str, user_id: CurrentUserId, service: LibraryService
) -> Response:
    if await service.delete_tag(owner_user_id=user_id, tag_id=tag_id) is None:
        raise _not_found("Tag")
    return Response(status_code=204)


async def _upload_chunks(file: UploadFile) -> AsyncIterator[bytes]:
    while chunk := await file.read(1024 * 1024):
        yield chunk


@router.post("/documents", response_model=DocumentResponse, status_code=201)
async def upload_document(
    user_id: CurrentUserId,
    service: LibraryService,
    file: Annotated[UploadFile, File()],
    dataset_ids: Annotated[list[str] | None, Form()] = None,
    tag_ids: Annotated[list[str] | None, Form()] = None,
) -> DocumentResponse:
    try:
        row = await service.upload_pdf(
            owner_user_id=user_id,
            original_filename=file.filename or "",
            declared_media_type=file.content_type or "",
            chunks=_upload_chunks(file),
            declared_length=file.size,
            dataset_ids=tuple(dataset_ids or ()),
            tag_ids=tuple(tag_ids or ()),
        )
    except DocumentDomainError as error:
        raise _domain_error(error) from error
    return DocumentResponse.model_validate(row)


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    user_id: CurrentUserId,
    service: LibraryService,
    query: str | None = None,
    dataset_id: str | None = None,
    tag_ids: Annotated[list[str] | None, Query()] = None,
    media_type: str | None = None,
    classification: str | None = None,
    parse_status: str | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> DocumentListResponse:
    rows, total = await service.list_documents(
        owner_user_id=user_id,
        filters=DocumentListFilter(
            query=query,
            dataset_id=dataset_id,
            tag_ids=tuple(tag_ids or ()),
            media_type=media_type,
            classification=classification,
            parse_status=parse_status,
            limit=limit,
            offset=offset,
        ),
    )
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str, user_id: CurrentUserId, service: LibraryService
) -> DocumentResponse:
    row = await service.get_document(owner_user_id=user_id, document_id=document_id)
    if row is None:
        raise _not_found("Document")
    return DocumentResponse.model_validate(row)


@router.patch("/documents/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    request: DocumentUpdate,
    user_id: CurrentUserId,
    service: LibraryService,
) -> DocumentResponse:
    row = await service.patch_document(
        owner_user_id=user_id,
        document_id=document_id,
        original_filename=request.original_filename,
        dataset_ids=None if request.dataset_ids is None else tuple(request.dataset_ids),
        tag_ids=None if request.tag_ids is None else tuple(request.tag_ids),
    )
    if row is None:
        raise _not_found("Document")
    return DocumentResponse.model_validate(row)


@router.delete("/documents/{document_id}", status_code=204)
async def delete_document(
    document_id: str, user_id: CurrentUserId, service: LibraryService
) -> Response:
    try:
        row = await service.delete_document(
            owner_user_id=user_id, document_id=document_id
        )
    except DocumentDomainError as error:
        raise _domain_error(error) from error
    if row is None:
        raise _not_found("Document")
    return Response(status_code=204)


@router.post(
    "/documents/{document_id}/inspections",
    response_model=InspectionOutcomeResponse,
    status_code=201,
)
async def inspect_document(
    document_id: str, user_id: CurrentUserId, service: InspectionService
) -> InspectionOutcomeResponse:
    outcome = await service.inspect(owner_user_id=user_id, document_id=document_id)
    if outcome is None:
        raise _not_found("Document")
    return InspectionOutcomeResponse(
        inspection=InspectionResponse.model_validate(outcome.inspection),
        parser_options=[
            ParserOptionResponse.model_validate(option)
            for option in outcome.parser_options
        ],
    )


@router.get(
    "/documents/{document_id}/parse-options", response_model=ParserOptionsResponse
)
async def get_parse_options(
    document_id: str,
    user_id: CurrentUserId,
    service: InspectionService,
    inspection_id: str | None = None,
) -> ParserOptionsResponse:
    options = await service.get_parser_options(
        owner_user_id=user_id,
        document_id=document_id,
        inspection_id=inspection_id,
    )
    if options is None:
        raise _not_found("Inspection")
    return ParserOptionsResponse(
        items=[ParserOptionResponse.model_validate(option) for option in options]
    )


@router.post("/documents/{document_id}/parse-jobs", response_model=None)
async def create_parse_job(
    document_id: str,
    request: CreateParseJobRequest,
    user_id: CurrentUserId,
    service: JobService,
    events: EventService,
) -> JSONResponse:
    try:
        job = await service.create_job(
            owner_user_id=user_id,
            document_id=document_id,
            inspection_id=request.inspection_id,
            parser_id=request.parser_id,
            parser_options=request.options,
            request_mode=request.mode,
        )
    except DocumentDomainError as error:
        raise _domain_error(error) from error
    if job is None:
        raise _not_found("Inspection")

    status_code = 202
    if request.mode == "sync":
        job = await events.wait_for_terminal_job(
            owner_user_id=user_id, job_id=str(job["job_id"])
        )
        if job is None:
            raise _not_found("Parse job")
        if job.get("status") in {"completed", "failed", "cancelled"}:
            status_code = 200
    payload = ParseJobResponse.model_validate(job).model_dump(mode="json")
    return JSONResponse(payload, status_code=status_code)


@router.get("/documents/{document_id}/parse-jobs", response_model=ParseJobListResponse)
async def list_parse_jobs(
    document_id: str,
    user_id: CurrentUserId,
    service: JobService,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> ParseJobListResponse:
    rows = await service.list_jobs(
        owner_user_id=user_id,
        document_id=document_id,
        limit=limit,
        offset=offset,
    )
    return ParseJobListResponse(
        items=[ParseJobResponse.model_validate(row) for row in rows],
        limit=limit,
        offset=offset,
    )


@router.get("/documents/{document_id}/artifacts", response_model=ArtifactListResponse)
async def list_artifacts(
    document_id: str,
    user_id: CurrentUserId,
    service: JobService,
    producer_job_id: str | None = None,
) -> ArtifactListResponse:
    rows = await service.list_artifacts(
        owner_user_id=user_id,
        document_id=document_id,
        producer_job_id=producer_job_id,
    )
    return ArtifactListResponse(
        items=[ArtifactResponse.model_validate(row) for row in rows]
    )


@router.get("/document-jobs/{job_id}", response_model=ParseJobResponse)
async def get_parse_job(
    job_id: str, user_id: CurrentUserId, service: JobService
) -> ParseJobResponse:
    job = await service.get_job(owner_user_id=user_id, job_id=job_id)
    if job is None:
        raise _not_found("Parse job")
    return ParseJobResponse.model_validate(job)


@router.post("/document-jobs/{job_id}/cancel", response_model=ParseJobResponse)
async def cancel_parse_job(
    job_id: str, user_id: CurrentUserId, service: JobService
) -> ParseJobResponse:
    job = await service.cancel_job(owner_user_id=user_id, job_id=job_id)
    if job is None:
        raise _not_found("Parse job")
    return ParseJobResponse.model_validate(job)


@router.get("/document-jobs/{job_id}/events")
async def stream_parse_job(
    job_id: str,
    user_id: CurrentUserId,
    service: JobService,
    events: EventService,
    after_status_version: int = Query(-1, ge=-1),
) -> StreamingResponse:
    if await service.get_job(owner_user_id=user_id, job_id=job_id) is None:
        raise _not_found("Parse job")

    async def frames() -> AsyncIterator[str]:
        async for snapshot in events.snapshots(
            owner_user_id=user_id,
            job_id=job_id,
            after_status_version=after_status_version,
        ):
            model = ParseJobResponse.model_validate(snapshot)
            yield (
                f"id: {model.status_version}\n"
                "event: snapshot\n"
                f"data: {model.model_dump_json()}\n\n"
            )

    return StreamingResponse(
        frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/document-artifacts/{artifact_id}/download")
async def download_artifact(
    artifact_id: str, user_id: CurrentUserId, service: JobService
) -> RedirectResponse:
    try:
        download = await service.create_artifact_download(
            owner_user_id=user_id, artifact_id=artifact_id
        )
    except DocumentDomainError as error:
        raise _domain_error(error) from error
    if download is None:
        raise _not_found("Artifact")
    return RedirectResponse(download["url"], status_code=307)
