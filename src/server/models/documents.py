"""HTTP contracts for the user-private document knowledge library."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class _RowModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="ignore")


class DatasetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)


class DatasetUpdate(DatasetCreate):
    pass


class DatasetResponse(_RowModel):
    dataset_id: str
    name: str
    description: str | None = None
    document_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DatasetListResponse(BaseModel):
    items: list[DatasetResponse]
    total: int
    limit: int
    offset: int


class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class TagResponse(_RowModel):
    tag_id: str
    name: str
    document_count: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DatasetRef(_RowModel):
    dataset_id: str
    name: str


class TagRef(_RowModel):
    tag_id: str
    name: str


class DocumentResponse(_RowModel):
    document_id: str
    original_filename: str
    media_type: str
    document_format: str
    source_size_bytes: int
    source_sha256: str
    datasets: list[DatasetRef] = Field(default_factory=list)
    tags: list[TagRef] = Field(default_factory=list)
    classification: str | None = None
    parse_status: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class DocumentTeachingUsage(_RowModel):
    document_id: str
    producer_job_id: str
    primary_artifact_id: str
    textbook_id: str
    textbook_title: str
    content_version_id: str
    content_version_sequence: int
    artifact_position: int
    teaching_package_id: str | None = None
    teaching_package_sequence: int | None = None
    status: str | None = None
    publication_id: str | None = None
    is_published: bool = False
    has_asset_manifest: bool = False
    created_at: datetime | None = None


class DocumentTeachingUsageResponse(BaseModel):
    items: list[DocumentTeachingUsage]


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]
    total: int
    limit: int
    offset: int


class DocumentUpdate(BaseModel):
    original_filename: str = Field(min_length=1, max_length=512)
    dataset_ids: list[str] | None = None
    tag_ids: list[str] | None = None


class InspectionResponse(_RowModel):
    inspection_id: str
    document_id: str
    inspector_id: str
    inspector_name: str
    inspector_version: str | None = None
    status: Literal["pending", "completed", "failed"]
    detected_format: str | None = None
    classification: str | None = None
    summary: dict[str, JsonValue] = Field(default_factory=dict)
    details: dict[str, JsonValue] = Field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class ParserOptionResponse(_RowModel):
    parser_id: str
    display_name: str
    version: str | None = None
    supported_formats: frozenset[str]
    supported_classifications: frozenset[str]
    available: bool
    reason: str
    warning: str | None = None
    recommended: bool = False


class InspectionOutcomeResponse(BaseModel):
    inspection: InspectionResponse
    parser_options: list[ParserOptionResponse]


class ParserOptionsResponse(BaseModel):
    items: list[ParserOptionResponse]


class CreateParseJobRequest(BaseModel):
    inspection_id: str
    parser_id: str
    mode: Literal["sync", "async"] = "async"
    options: dict[str, JsonValue] = Field(default_factory=dict)


class ParseJobResponse(_RowModel):
    job_id: str
    document_id: str
    inspection_id: str
    parser_id: str
    parser_name: str
    parser_version: str | None = None
    parser_options: dict[str, JsonValue] = Field(default_factory=dict)
    request_mode: Literal["sync", "async"]
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    stage: Literal[
        "queued", "preparing", "parsing", "storing", "completed", "failed", "cancelled"
    ]
    percentage: int = Field(ge=0, le=100)
    status_version: int = Field(ge=0)
    attempt_count: int = Field(ge=0)
    primary_artifact_id: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    cancellation_requested_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None


class ParseJobListResponse(BaseModel):
    items: list[ParseJobResponse]
    limit: int
    offset: int


class ArtifactResponse(_RowModel):
    artifact_id: str
    document_id: str
    producer_job_id: str
    artifact_kind: Literal[
        "primary_document", "embedded_image", "structured_data", "manifest"
    ]
    format: str
    media_type: str
    schema_name: str | None = None
    schema_version: str | None = None
    relative_path: str
    locator: dict[str, JsonValue] | None = None
    metadata: dict[str, JsonValue] | None = None
    created_at: datetime | None = None


class ArtifactListResponse(BaseModel):
    items: list[ArtifactResponse]
