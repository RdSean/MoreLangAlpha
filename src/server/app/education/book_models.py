"""API contracts for the more-to-skills textbook workbench."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


BookJobKind = Literal["structure", "materials"]
BookMaterialDepth = Literal["summary", "lesson", "deep"]
BookJobStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "partially_succeeded",
    "failed",
    "cancelled",
]
BookJobItemStatus = Literal[
    "queued",
    "running",
    "succeeded",
    "failed",
    "cancelled",
    "not_run",
]
BookJobItemKind = Literal["structure", "material", "supplementary"]
BookStructureStatus = Literal["queued", "running", "ready", "failed"]
BookActivityStatus = Literal["available", "unavailable"]
BookSourceStatus = Literal["pending", "preparing", "ready", "failed", "cancelled"]
BookExecutionPhase = Literal[
    "initial_queue",
    "source_freezing",
    "runtime_queue",
    "sandbox_preparation",
    "input_staging",
    "ptc_execution",
    "finalization",
]
BookTimingStatus = Literal["available", "partial", "unavailable"]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateBookRequest(_StrictModel):
    parse_job_id: str = Field(min_length=1, max_length=128)
    primary_artifact_id: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=240)
    idempotency_key: str = Field(min_length=1, max_length=160)


class CreateBookResponse(_StrictModel):
    textbook_id: UUID
    job_id: UUID
    acceptance: Literal["accepted_new", "reused"] = "accepted_new"


class BookSourceCandidateResponse(_StrictModel):
    document_id: str
    parse_job_id: str
    primary_artifact_id: str
    filename: str
    media_type: str
    parser_id: str
    parser_name: str
    completed_at: datetime
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)
    image_count: int = Field(ge=0)


class BookSourceListResponse(_StrictModel):
    items: list[BookSourceCandidateResponse]


class FrozenBookSourceResponse(BookSourceCandidateResponse):
    frozen_at: datetime | None = None


class BookPreparationProgressResponse(_StrictModel):
    total_resources: int | None = Field(default=None, ge=0)
    verified_resources: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _verified_is_bounded(self) -> BookPreparationProgressResponse:
        if (
            self.total_resources is not None
            and self.verified_resources > self.total_resources
        ):
            raise ValueError("verified resources cannot exceed total")
        return self


class BookPhaseTimingResponse(_StrictModel):
    phase: BookExecutionPhase
    status: BookTimingStatus = "unavailable"
    started_at: datetime | None = None
    ended_at: datetime | None = None
    measured_ms: int | None = Field(default=None, ge=0)
    segment_count: int = Field(default=0, ge=0)


class BookAttemptTimingResponse(_StrictModel):
    attempt: int = Field(ge=1)
    request_round: int = Field(ge=1)
    status: BookTimingStatus = "unavailable"
    queued_at: datetime | None = None
    claimed_at: datetime | None = None
    terminal_at: datetime | None = None
    total_ms: int | None = Field(default=None, ge=0)
    phases: list[BookPhaseTimingResponse] = Field(default_factory=list)


class BookBatchProgressResponse(_StrictModel):
    completed: int = Field(ge=0)
    total: int = Field(ge=0)


class BookJobSummaryResponse(_StrictModel):
    job_id: str
    kind: BookJobKind
    status: BookJobStatus
    total_items: int = Field(ge=0)
    succeeded_items: int = Field(ge=0)
    failed_items: int = Field(ge=0)
    cancelled_items: int = Field(ge=0)
    not_run_items: int = Field(ge=0)
    high_water_seq: int = Field(ge=0)
    activity_status: BookActivityStatus = "available"
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    safe_error: str | None = None
    request_round: int = Field(default=1, ge=1)
    round_accepted_at: datetime | None = None
    server_now: datetime | None = None
    material_progress: BookBatchProgressResponse | None = None


class BookMaterialCountsResponse(_StrictModel):
    total: int = Field(ge=0)
    ready: int = Field(ge=0)

    @model_validator(mode="after")
    def _ready_does_not_exceed_total(self) -> BookMaterialCountsResponse:
        if self.ready > self.total:
            raise ValueError("ready material count cannot exceed total")
        return self


class TextbookSummaryResponse(_StrictModel):
    textbook_id: str
    title: str
    structure_status: BookStructureStatus
    materials: BookMaterialCountsResponse
    current_job: BookJobSummaryResponse | None = None
    updated_at: datetime
    source_status: BookSourceStatus = "ready"


class TextbookWorkbenchResponse(TextbookSummaryResponse):
    source: FrozenBookSourceResponse | None = None
    selected_source: BookSourceCandidateResponse | None = None
    source_frozen_at: datetime | None = None
    current_structure_id: UUID | None = None
    recent_job: BookJobSummaryResponse | None = None
    assigned_student_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _source_matches_readiness(self) -> TextbookWorkbenchResponse:
        if (self.source_status == "ready") != (self.source is not None):
            raise ValueError("only ready source may expose frozen content")
        if self.source_status != "ready" and self.selected_source is None:
            raise ValueError("pending source must expose selected metadata")
        return self


class KnowledgePointProjectionResponse(_StrictModel):
    knowledge_point_id: UUID
    skill_kp_id: str = Field(min_length=1, max_length=64)
    position: int = Field(ge=1)
    title: str = Field(min_length=1)
    unit_skill_node_id: str | None = None
    node_skill_ids: list[str] = Field(default_factory=list)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    content_file: str | None = None
    material_available: bool

    @model_validator(mode="after")
    def _range_is_inclusive(self) -> KnowledgePointProjectionResponse:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        return self


class BookStructureResponse(_StrictModel):
    textbook_id: str
    structure_id: UUID
    schema_version: str
    structure: dict[str, Any]
    knowledge_points: list[KnowledgePointProjectionResponse]
    warnings: list[str] = Field(default_factory=list)


class BookSourceSliceResponse(_StrictModel):
    textbook_id: str
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    total_lines: int = Field(ge=1)
    markdown: str

    @model_validator(mode="after")
    def _range_is_one_based_inclusive(self) -> BookSourceSliceResponse:
        if self.end_line < self.start_line:
            raise ValueError("end_line must be greater than or equal to start_line")
        if self.end_line > self.total_lines:
            raise ValueError("end_line cannot exceed total_lines")
        return self


class KnowledgePointMaterialResponse(_StrictModel):
    textbook_id: str
    knowledge_point_id: UUID
    skill_kp_id: str
    material_available: bool
    markdown: str | None = None
    generated_at: datetime | None = None
    depth: BookMaterialDepth | None = None
    requirements: str | None = None
    content_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _material_state_is_explicit(self) -> KnowledgePointMaterialResponse:
        if self.material_available != (self.markdown is not None):
            raise ValueError("material_available must match markdown presence")
        return self


class StudentBookAssignmentResponse(_StrictModel):
    assignment_id: UUID
    textbook_id: str
    textbook_title: str
    structure_id: UUID | None = None
    knowledge_point_count: int = Field(ge=0)
    completed_knowledge_point_count: int = Field(ge=0)
    created_at: datetime


class StudentBookStructureResponse(BookStructureResponse):
    assignment_id: UUID
    textbook_title: str


class StudentKnowledgePointMaterialResponse(KnowledgePointMaterialResponse):
    assignment_id: UUID


class BookJobCreateRequest(_StrictModel):
    kind: BookJobKind
    knowledge_point_ids: list[UUID] = Field(default_factory=list, max_length=1000)
    depth: BookMaterialDepth = "lesson"
    requirements: str | None = Field(default=None, max_length=8000)
    replace_existing: bool = False
    include_supplementary: bool = False
    idempotency_key: str = Field(min_length=1, max_length=160)

    @model_validator(mode="after")
    def _targets_match_kind(self) -> BookJobCreateRequest:
        if self.kind == "structure" and self.knowledge_point_ids:
            raise ValueError("structure job must not include material targets")
        if self.kind == "materials" and not self.knowledge_point_ids:
            raise ValueError("material job must include at least one target")
        if len(set(self.knowledge_point_ids)) != len(self.knowledge_point_ids):
            raise ValueError("knowledge_point_ids must be unique")
        return self


class BookJobItemResponse(_StrictModel):
    item_id: UUID
    kind: BookJobItemKind
    position: int = Field(ge=1)
    knowledge_point_id: UUID | None = None
    skill_kp_id: str | None = None
    knowledge_point_title: str | None = None
    status: BookJobItemStatus
    attempt: int = Field(ge=0)
    safe_error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    execution_phase: BookExecutionPhase | None = None
    queued_at: datetime | None = None
    preparation_progress: BookPreparationProgressResponse | None = None
    timing_summary: BookAttemptTimingResponse | None = None


class BookAttemptStatisticsResponse(_StrictModel):
    item_id: UUID
    kind: BookJobItemKind
    status: BookJobItemStatus | Literal["interrupted"]
    knowledge_point_title: str | None = None
    timing: BookAttemptTimingResponse


class BookJobStatisticsResponse(_StrictModel):
    job_id: str
    request_round: int = Field(ge=1)
    server_now: datetime
    status: BookTimingStatus
    round_total_ms: int | None = Field(default=None, ge=0)
    material_sample_count: int = Field(default=0, ge=0)
    material_median_ms: int | None = Field(default=None, ge=0)
    material_longest_ms: int | None = Field(default=None, ge=0)
    supplementary: list[BookAttemptStatisticsResponse] = Field(default_factory=list)
    attempts: list[BookAttemptStatisticsResponse] = Field(default_factory=list)
    next_cursor: str | None = None


class BookJobResponse(BookJobSummaryResponse):
    textbook_id: str
    depth: BookMaterialDepth | None = None
    requirements: str | None = None
    replace_existing: bool = False
    include_supplementary: bool = False
    items: list[BookJobItemResponse] = Field(default_factory=list)


class BookActivityEventResponse(_StrictModel):
    seq: int = Field(ge=1)
    job_id: str
    item_id: UUID | None = None
    kind: str
    status: str
    message: str = Field(max_length=512)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    @field_validator("metadata", mode="before")
    @classmethod
    def _hide_internal_budget_metadata(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        public = dict(value)
        public.pop("budget_class", None)
        public.pop("activity_bytes", None)
        return public


class BookActivityPageResponse(_StrictModel):
    job_id: str
    status: BookJobStatus
    events: list[BookActivityEventResponse]
    high_water_seq: int = Field(ge=0)
    activity_status: BookActivityStatus
    cursor_expired: bool
    has_more: bool

    @model_validator(mode="after")
    def _events_are_strictly_increasing(self) -> BookActivityPageResponse:
        sequences = [event.seq for event in self.events]
        if any(
            current <= previous for previous, current in zip(sequences, sequences[1:])
        ):
            raise ValueError("activity event sequences must be strictly increasing")
        return self


class BookAssignmentRequest(_StrictModel):
    student_user_ids: list[str] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _student_ids_are_unique(self) -> BookAssignmentRequest:
        if len(set(self.student_user_ids)) != len(self.student_user_ids):
            raise ValueError("student_user_ids must be unique")
        return self


class BookAssignmentResponse(_StrictModel):
    textbook_id: str
    student_user_id: str
    assigned_at: datetime
