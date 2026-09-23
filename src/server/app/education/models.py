"""Pydantic contracts for first-party family homework APIs."""

import unicodedata
from datetime import date, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, StrictInt, field_validator, model_validator


_ALLOWED_BRIEF_CONTROL_CHARS = frozenset("\t\n\r")
_ALLOWED_SUMMARY_CONTROL_CHARS = frozenset("\n\r")


def _reject_control_characters(
    value: str,
    *,
    allowed: frozenset[str] = frozenset(),
    field_name: str,
) -> str:
    if any(
        unicodedata.category(character) == "Cc" and character not in allowed
        for character in value
    ):
        raise ValueError(f"{field_name} contains unsupported control characters")
    return value


class EducationStudentProfileResponse(BaseModel):
    household_id: UUID
    user_id: str
    grade_code: str | None = None


class UpdateEducationStudentProfileRequest(BaseModel):
    grade_code: str | None = Field(default=..., max_length=4)


class EducationHomeworkTypeResponse(BaseModel):
    code: str
    name: str
    sort_order: int


class EducationSubjectDictionaryResponse(BaseModel):
    code: str
    name: str
    color: str
    sort_order: int
    homework_types: list[EducationHomeworkTypeResponse]


class EducationGradeLevelResponse(BaseModel):
    code: str
    name: str
    stage: str
    sort_order: int


class EducationPracticeSourceResponse(BaseModel):
    code: str
    name: str
    sort_order: int


class EducationHomeworkDictionariesResponse(BaseModel):
    timezone: str
    subjects: list[EducationSubjectDictionaryResponse]
    grade_levels: list[EducationGradeLevelResponse]
    practice_sources: list[EducationPracticeSourceResponse]


class CreateEducationTaskRequest(BaseModel):
    idempotency_key: UUID
    assigned_student_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10_000)
    due_at: datetime
    subject_code: str = Field(min_length=1, max_length=16)
    type_code: str = Field(min_length=1, max_length=16)
    practice_source_code: str | None = Field(default=None, max_length=16)
    frequency: Literal["once", "daily", "weekdays", "weekly"] = "once"
    weekdays: list[StrictInt] | None = Field(default=None, max_length=7)
    material_asset_ids: list[UUID] = Field(default_factory=list, max_length=20)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title is required")
        return value.strip()

    @model_validator(mode="after")
    def validate_recurrence(self) -> "CreateEducationTaskRequest":
        if self.frequency == "weekly":
            if (
                not self.weekdays
                or len(set(self.weekdays)) != len(self.weekdays)
                or any(day not in range(1, 8) for day in self.weekdays)
            ):
                raise ValueError(
                    "weekly tasks require a nonempty unique ISO weekday list"
                )
        elif self.weekdays:
            raise ValueError("weekdays are only valid for weekly tasks")
        return self


class SubmitEducationTaskRequest(BaseModel):
    submission_text: str = Field(default="", max_length=10_000)
    idempotency_key: UUID | None = None
    asset_ids: list[UUID] = Field(default_factory=list, max_length=20)


class CheckInEducationTaskRequest(SubmitEducationTaskRequest):
    """The initial check-in deliberately permits no text or attachments."""


class ReviewEducationTaskRequest(BaseModel):
    decision: Literal["feedback", "revision_requested"]
    feedback_text: str = Field(min_length=1, max_length=10_000)

    @field_validator("feedback_text")
    @classmethod
    def validate_feedback(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("feedback_text is required")
        return value.strip()


class EducationTaskResponse(BaseModel):
    task_id: UUID
    task_rule_id: UUID
    household_id: UUID
    assigned_student_id: str
    occurrence_date: date
    due_at: datetime
    title: str
    description: str
    subject_code: str | None = None
    type_code: str | None = None
    practice_source_code: str | None = None
    grade_code: str | None = None
    status: str
    completed_at: datetime | None = None
    created_at: datetime | None = None
    latest_review_decision: Literal["feedback", "revision_requested"] | None = None
    latest_feedback_text: str | None = None


class EducationSubmissionResponse(BaseModel):
    submission_id: UUID
    task_id: UUID
    sequence: int
    submission_text: str
    submitted_by_user_id: str | None = None
    idempotency_key: UUID | None = None
    submission_kind: Literal["check_in", "revision"] | None = None
    created_at: datetime | None = None


class EducationReviewResponse(BaseModel):
    review_id: UUID
    submission_id: UUID
    decision: Literal["feedback", "revision_requested"]
    feedback_text: str
    reviewed_by_user_id: str | None = None
    created_at: datetime | None = None


class EducationTaskAssetResponse(BaseModel):
    """Client-safe attachment metadata for a task timeline."""

    asset_id: UUID
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime | None = None
    download_endpoint: str


class EducationTaskSubmissionDetailResponse(EducationSubmissionResponse):
    assets: list[EducationTaskAssetResponse]
    reviews: list[EducationReviewResponse]


class EducationTaskDetailResponse(EducationTaskResponse):
    parent_materials: list[EducationTaskAssetResponse]
    submissions: list[EducationTaskSubmissionDetailResponse]


class EducationCalendarTaskResponse(BaseModel):
    task_id: UUID
    task_rule_id: UUID
    household_id: UUID
    assigned_student_id: str
    occurrence_date: date
    due_at: datetime
    title: str
    description: str
    subject_code: str | None = None
    subject_color: str | None = None
    type_code: str | None = None
    practice_source_code: str | None = None
    grade_code: str | None = None
    status: str
    completed_at: datetime | None = None
    created_at: datetime | None = None
    is_completed: bool
    is_overdue: bool


class EducationCalendarDayResponse(BaseModel):
    date: date
    task_count: int
    completed_count: int
    overdue_count: int
    tasks: list[EducationCalendarTaskResponse]


class EducationCalendarStatsResponse(BaseModel):
    today_count: int
    week_count: int
    overdue_count: int
    completed_count: int


class EducationTaskCalendarResponse(BaseModel):
    student_id: str | None = None
    start_date: date
    end_date: date
    days: list[EducationCalendarDayResponse]
    stats: EducationCalendarStatsResponse


class CreateTextbookRequest(BaseModel):
    title: str = Field(min_length=1, max_length=255)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title is required")
        return normalized


class StartTextbookProcessingRequest(BaseModel):
    source_asset_ids: list[UUID] = Field(default_factory=list, max_length=20)
    source_parse_job_ids: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("source_parse_job_ids")
    @classmethod
    def validate_parse_job_ids(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values]
        if any(not value for value in normalized):
            raise ValueError("source_parse_job_ids must not contain empty values")
        return normalized

    @model_validator(mode="after")
    def validate_source_selection(self) -> "StartTextbookProcessingRequest":
        if bool(self.source_asset_ids) == bool(self.source_parse_job_ids):
            raise ValueError(
                "provide exactly one of source_asset_ids or source_parse_job_ids"
            )
        return self


class AssignTextbookPublicationRequest(BaseModel):
    student_user_id: str = Field(min_length=1, max_length=255)


class UpdateLearningProgressRequest(BaseModel):
    status: Literal["learning", "read", "check_completed", "review_recommended"]


class AnswerLearningQuestionRequest(BaseModel):
    selected_option: str = Field(min_length=1, max_length=32)


class TextbookResponse(BaseModel):
    textbook_id: UUID
    household_id: UUID
    title: str
    slug: str
    created_by_user_id: str | None = None
    created_at: datetime | None = None


class ArtifactTextbookSourceResponse(BaseModel):
    legacy: Literal[False] = False
    position: int
    document_id: str
    producer_job_id: str
    primary_artifact_id: str
    filename: str
    media_type: str
    format: str
    parser_id: str
    parser_name: str
    parser_version: str | None = None
    parse_completed_at: datetime | None = None
    primary_sha256: str
    document_deleted: bool
    document_accessible: bool


class LegacyTextbookSourceResponse(BaseModel):
    legacy: Literal[True] = True
    position: int
    asset_id: UUID
    original_filename: str
    content_type: str
    size_bytes: int


TextbookSourceResponse = Annotated[
    ArtifactTextbookSourceResponse | LegacyTextbookSourceResponse,
    Field(discriminator="legacy"),
]


class TextbookParseJobCandidateResponse(BaseModel):
    producer_job_id: str
    document_id: str
    primary_artifact_id: str
    filename: str
    media_type: str
    format: str
    parser_id: str
    parser_name: str
    parser_version: str | None = None
    parse_completed_at: datetime | None = None
    size_bytes: int
    artifact_count: int


class StructureSourceRefResponse(BaseModel):
    source_id: str = Field(min_length=1, max_length=255)
    start: int | None = Field(default=None, ge=0)
    end: int | None = Field(default=None, gt=0)
    quote: str | None = Field(default=None, max_length=500)
    heading_path: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_range(self) -> "StructureSourceRefResponse":
        if self.start is None or self.end is None:
            if self.start is not None or self.end is not None:
                raise ValueError(
                    "source reference offsets must be both set or both empty"
                )
            return self
        if self.end <= self.start:
            raise ValueError("source reference end must be greater than start")
        return self


class StructureKnowledgePointWrite(BaseModel):
    position: int = Field(gt=0)
    slug: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(default="", max_length=30_000)
    scope_slot: Literal["reading_a", "reading_b"] | None = None
    source_refs: list[StructureSourceRefResponse] = Field(
        default_factory=list, max_length=32
    )
    confidence: float = Field(ge=0, le=1)


class StructureScopeResponse(BaseModel):
    unit_id: UUID
    slot: Literal["reading_a", "reading_b"]
    title: str
    summary: str = ""
    reading_skill: str = ""
    vocabulary_building: str = ""
    critical_thinking: str = ""
    source_id: str
    line_start: int
    line_end: int
    char_start: int
    char_end: int
    verified: bool


class StructureUnitWrite(BaseModel):
    position: int = Field(gt=0)
    slug: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(default="", max_length=30_000)
    unit_type: Literal["teaching", "front_matter", "reference", "appendix"]
    source_refs: list[StructureSourceRefResponse] = Field(
        default_factory=list, max_length=32
    )
    confidence: float = Field(ge=0, le=1)
    knowledge_points: list[StructureKnowledgePointWrite] = Field(
        default_factory=list,
        max_length=200,
    )


class UpdateTextbookStructureRequest(BaseModel):
    units: list[StructureUnitWrite] = Field(min_length=1, max_length=500)


class ProcessingProfileRequest(BaseModel):
    subject: Literal["english", "math", "chinese", "science", "other"] = "other"
    grade_band: Literal["primary", "middle", "high", "adult"] = "middle"
    language: Literal["zh-CN", "en", "bilingual"] = "zh-CN"
    depth: Literal["overview", "standard", "deep"] = "standard"
    question_types: list[Literal["choice", "fill", "short_answer", "mixed"]] = Field(
        default_factory=lambda: ["choice", "mixed"], max_length=4
    )
    prompt_fragment: str = Field(default="", max_length=2_000)
    allowed_skills: list[str] = Field(default_factory=list, max_length=8)


class CreateTextbookStructureRequest(BaseModel):
    profile_id: UUID | None = None
    profile: ProcessingProfileRequest | None = None


class CreateBookPipelineRequest(BaseModel):
    processing_brief: str = Field(default="", max_length=4_000)
    request_id: UUID | None = None
    pause_after_chapter_analysis: bool = False

    @field_validator("processing_brief", mode="before")
    @classmethod
    def normalize_processing_brief(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        if any(
            unicodedata.category(character) == "Cc"
            and character not in _ALLOWED_BRIEF_CONTROL_CHARS
            for character in value
        ):
            raise ValueError("processing_brief contains unsupported control characters")
        return value.strip()


KnowledgePointCandidateStatus = Literal[
    "pending", "accepted", "rejected", "merged", "split"
]


class KnowledgePointCandidateResponse(BaseModel):
    knowledge_point_id: UUID
    content_structure_id: UUID
    content_node_id: UUID
    candidate_key: str
    point_type: str
    origin: Literal["generated"]
    candidate_status: KnowledgePointCandidateStatus
    position: int
    slug: str
    title: str
    summary: str
    source_refs: list[StructureSourceRefResponse] = Field(default_factory=list)
    confidence: float
    status: str
    created_at: datetime | None = None


class KnowledgePointCandidateNodeResponse(BaseModel):
    node_id: UUID
    structure_id: UUID
    parent_node_id: UUID | None = None
    node_key: str
    node_type: str
    label: str | None = None
    position: int
    slug: str
    title: str
    summary: str
    source_refs: list[StructureSourceRefResponse] = Field(default_factory=list)
    candidates: list[KnowledgePointCandidateResponse] = Field(default_factory=list)


class KnowledgePointCandidateReviewResponse(BaseModel):
    structure_id: UUID
    version_id: UUID
    nodes: list[KnowledgePointCandidateNodeResponse]


class UpdateKnowledgePointCandidateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    summary: str | None = Field(default=None, max_length=30_000)
    point_type: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("title", "point_type")
    @classmethod
    def normalize_required_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _reject_control_characters(
            value,
            field_name="candidate text",
        ).strip()
        if not normalized:
            raise ValueError("value is required")
        return normalized

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _reject_control_characters(
            value,
            allowed=_ALLOWED_SUMMARY_CONTROL_CHARS,
            field_name="candidate summary",
        )

    @model_validator(mode="after")
    def require_update(self) -> "UpdateKnowledgePointCandidateRequest":
        if self.title is None and self.summary is None and self.point_type is None:
            raise ValueError("at least one candidate field is required")
        return self


class KnowledgePointCandidateIdsRequest(BaseModel):
    candidate_ids: list[UUID] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def require_unique_candidates(self) -> "KnowledgePointCandidateIdsRequest":
        if len(set(self.candidate_ids)) != len(self.candidate_ids):
            raise ValueError("candidate_ids must be unique")
        return self


class MergeKnowledgePointCandidatesRequest(BaseModel):
    source_ids: list[UUID] = Field(min_length=2, max_length=100)
    target_id: UUID | None = None
    title: str | None = Field(default=None, min_length=1, max_length=255)
    summary: str | None = Field(default=None, max_length=30_000)
    point_type: str | None = Field(default=None, min_length=1, max_length=64)
    accept: bool = False

    @field_validator("title", "point_type")
    @classmethod
    def normalize_required_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = _reject_control_characters(
            value,
            field_name="candidate text",
        ).strip()
        if not normalized:
            raise ValueError("value is required")
        return normalized

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _reject_control_characters(
            value,
            allowed=_ALLOWED_SUMMARY_CONTROL_CHARS,
            field_name="candidate summary",
        )

    @model_validator(mode="after")
    def validate_target(self) -> "MergeKnowledgePointCandidatesRequest":
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("source_ids must be unique")
        if self.target_id is not None and self.target_id not in self.source_ids:
            raise ValueError("target_id must be one of source_ids")
        if self.target_id is None and (self.title is None or self.point_type is None):
            raise ValueError("a new merged candidate requires title and point_type")
        if self.target_id is None and self.accept:
            raise ValueError("a new merged candidate must remain pending")
        return self


class SplitKnowledgePointCandidateItem(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(default="", max_length=30_000)
    point_type: str = Field(min_length=1, max_length=64)

    @field_validator("title", "point_type")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        normalized = _reject_control_characters(
            value,
            field_name="candidate text",
        ).strip()
        if not normalized:
            raise ValueError("value is required")
        return normalized

    @field_validator("summary")
    @classmethod
    def validate_summary(cls, value: str) -> str:
        return _reject_control_characters(
            value,
            allowed=_ALLOWED_SUMMARY_CONTROL_CHARS,
            field_name="candidate summary",
        )


class SplitKnowledgePointCandidateRequest(BaseModel):
    candidate_id: UUID
    items: list[SplitKnowledgePointCandidateItem] = Field(
        min_length=2,
        max_length=100,
    )


class BookPipelineJobResponse(BaseModel):
    generation_job_id: UUID
    version_id: UUID
    scope: Literal["book_pipeline"]
    structure_id: UUID | None = None
    knowledge_point_id: UUID | None = None
    status: str
    attempt_count: int
    pause_after_chapter_analysis: bool
    reused_existing_job: bool = False
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    root_run_id: UUID | None = None
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None


BookPipelineStageName = Literal[
    "chapter_analysis",
    "content_processing",
    "knowledge_point_generation",
    "lesson_preparation",
]


class BookPipelineProgressEventResponse(BaseModel):
    sequence: int
    substage: str | None = None
    status: Literal["queued", "running", "completed", "failed", "skipped"]
    label: str
    detail: str | None = None
    current: int | None = None
    total: int | None = None
    timestamp: str | None = None


class BookPipelineProgressStageResponse(BaseModel):
    name: BookPipelineStageName
    label: str
    status: Literal["queued", "running", "completed", "failed", "skipped"]
    current: int | None = None
    total: int | None = None
    events: list[BookPipelineProgressEventResponse] = Field(default_factory=list)


class BookPipelineProgressResponse(BaseModel):
    job_id: UUID
    status: str
    error_code: str | None = None
    error_message: str | None = None
    stages: list[BookPipelineProgressStageResponse]
    last_sequence: int = 0
    truncated: bool = False


class StructureKnowledgePointResponse(StructureKnowledgePointWrite):
    knowledge_point_id: UUID
    status: str
    lesson_status: str | None = None
    lesson_revision_id: UUID | None = None


class StructureUnitResponse(StructureUnitWrite):
    unit_id: UUID
    status: str
    scopes: list[StructureScopeResponse] = Field(default_factory=list)
    knowledge_points: list[StructureKnowledgePointResponse]


class TextbookLessonSummaryResponse(BaseModel):
    total: int = 0
    accepted: int = 0
    generated: int = 0
    approved: int = 0


class StructureGenerationJobSummaryResponse(BaseModel):
    generation_job_id: UUID
    status: str
    attempt_count: int
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    root_run_id: UUID | None = None
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None


class TextbookStructureResponse(BaseModel):
    structure_id: UUID
    version_id: UUID
    sequence: int
    status: str
    schema_version: str
    processing_profile_id: UUID | None = None
    processing_profile_sha256: str
    input_manifest_sha256: str
    source_revision: str
    created_at: datetime | None = None
    reviewed_at: datetime | None = None
    book_asset_prefix: str | None = None
    book_asset_manifest: dict[str, Any] = Field(default_factory=dict)
    validation_warnings: list[str] = Field(default_factory=list)
    units: list[StructureUnitResponse]
    lesson_summary: TextbookLessonSummaryResponse = Field(
        default_factory=TextbookLessonSummaryResponse
    )
    latest_generation_job_id: UUID | None = None
    latest_generation_job: StructureGenerationJobSummaryResponse | None = None


class StructureGenerationJobResponse(BaseModel):
    generation_job_id: UUID
    version_id: UUID
    scope: Literal["structure", "assets", "lesson", "book_pipeline"]
    structure_id: UUID | None = None
    status: str
    attempt_count: int
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    root_run_id: UUID | None = None
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    structure_sequence: int | None = None
    structure_status: str | None = None
    structure_bundle_prefix: str | None = None


class GenerateKnowledgePointLessonRequest(BaseModel):
    auto_grading: bool = False


class KnowledgePointLessonRevisionResponse(BaseModel):
    revision_id: UUID
    revision: int
    format: Literal["markdown"]
    content_sha256: str
    size_bytes: int
    processing_profile_sha256: str
    created_at: datetime | None = None


class KnowledgePointLessonResponse(BaseModel):
    lesson_id: UUID
    status: str
    latest_revision_id: UUID | None = None
    knowledge_point_id: UUID
    knowledge_point_title: str
    structure_id: UUID
    unit_id: UUID
    unit_title: str
    content_markdown: str
    revisions: list[KnowledgePointLessonRevisionResponse]


class KnowledgePointSourceSnippetResponse(BaseModel):
    source_id: str
    source_title: str | None = None
    start: int | None = None
    end: int | None = None
    quote: str | None = None
    markdown: str
    truncated_before: bool = False
    truncated_after: bool = False


class KnowledgePointSourcePreviewResponse(BaseModel):
    knowledge_point_id: UUID
    knowledge_point_title: str
    unit_id: UUID
    unit_title: str
    snippets: list[KnowledgePointSourceSnippetResponse]


class KnowledgePointProgressEventResponse(BaseModel):
    sequence: int
    kind: str
    label: str
    detail: str | None = None
    status: str
    timestamp: str | None = None
    count: int = 1


class KnowledgePointProgressResponse(BaseModel):
    generation_job_id: UUID
    run_id: UUID | None = None
    status: str
    events: list[KnowledgePointProgressEventResponse]
    truncated: bool = False


class LessonGenerationStatusResponse(BaseModel):
    knowledge_point_id: UUID
    generating: bool
    generation_job_id: UUID | None = None
    status: str | None = None
    attempt_count: int = 0
    auto_grading: bool = False
    error_code: str | None = None
    error_message: str | None = None
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    root_run_id: UUID | None = None
    source_kind: Literal["legacy_reading", "content_node"] = "legacy_reading"
    candidate_status: str | None = None
    content_node_id: UUID | None = None
    content_node_title: str | None = None
    content_asset_available: bool = False


class CreateKnowledgePointLessonRevisionRequest(BaseModel):
    content_markdown: str = Field(min_length=1, max_length=200_000)


class ApproveKnowledgePointLessonRequest(BaseModel):
    revision_id: UUID


class PublishTextbookStructureRequest(BaseModel):
    structure_id: UUID


class StudentKnowledgePointResponse(BaseModel):
    knowledge_point_id: UUID
    position: int
    slug: str
    title: str
    summary: str
    has_lesson: bool


class StudentStructureUnitResponse(BaseModel):
    unit_id: UUID
    position: int
    slug: str
    title: str
    summary: str
    unit_type: str
    knowledge_points: list[StudentKnowledgePointResponse]


class StudentTextbookStructureResponse(BaseModel):
    assignment_id: UUID
    publication_id: UUID
    textbook_id: UUID
    textbook_title: str
    textbook_slug: str
    version_sequence: int
    structure_id: UUID
    structure_sequence: int
    units: list[StudentStructureUnitResponse]


class StudentKnowledgePointLessonResponse(BaseModel):
    assignment_id: UUID
    knowledge_point_id: UUID
    knowledge_point_title: str
    unit_id: UUID
    unit_title: str
    revision_id: UUID
    revision: int
    format: Literal["markdown"]
    content_sha256: str
    size_bytes: int
    content_markdown: str


class LearningItemResponse(BaseModel):
    item_id: UUID
    assignment_id: UUID
    unit_id: UUID | None = None
    knowledge_point_id: UUID | None = None
    kind: Literal["question", "highlight", "note", "summary"]
    content: str
    source_anchor: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CreateLearningItemRequest(BaseModel):
    unit_id: UUID | None = None
    knowledge_point_id: UUID | None = None
    kind: Literal["question", "highlight", "note"]
    content: str = Field(min_length=1, max_length=20_000)
    source_anchor: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "CreateLearningItemRequest":
        if self.unit_id is None and self.knowledge_point_id is None:
            raise ValueError("a Unit or knowledge point is required")
        return self


class UpdateLearningItemRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    source_anchor: dict[str, Any] | None = None


class UpdateKnowledgePointProgressRequest(BaseModel):
    status: Literal["not_started", "learning", "read", "review_recommended"]


class TextbookQuestionResponse(BaseModel):
    question_id: UUID
    position: int
    prompt: str
    options: dict[str, str]
    correct_option: str
    explanation: str
    knowledge_point: str


class TextbookChapterResponse(BaseModel):
    chapter_id: UUID
    position: int
    slug: str
    title: str
    page_start: int | None = None
    page_end: int | None = None
    markdown: str
    questions: list[TextbookQuestionResponse]


class TextbookAssignmentSummaryResponse(BaseModel):
    assignment_id: UUID
    student_user_id: str
    student_name: str | None = None
    created_at: datetime | None = None


class TextbookVersionResponse(BaseModel):
    version_id: UUID
    sequence: int
    status: str
    extractor_name: str | None = None
    extractor_version: str | None = None
    processing_error: str | None = None
    processing_job_id: str | None = None
    processing_job_scope: str | None = None
    processing_job_status: str | None = None
    processing_attempt_count: int | None = None
    chapter_count: int
    is_published: bool
    publication_id: UUID | None = None
    sources: list[TextbookSourceResponse]
    chapters: list[TextbookChapterResponse]
    assignments: list[TextbookAssignmentSummaryResponse]


class TextbookDetailResponse(TextbookResponse):
    versions: list[TextbookVersionResponse]


class TextbookProcessingResponse(BaseModel):
    job_id: UUID
    version_id: UUID
    status: str
    attempt_count: int | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class TextbookStructurePublicationResponse(BaseModel):
    publication_id: UUID
    version_id: UUID
    structure_id: UUID
    published_by_user_id: str | None = None
    created_at: datetime | None = None


class TextbookAssignmentResponse(BaseModel):
    assignment_id: UUID
    publication_id: UUID
    student_user_id: str
    assigned_by_user_id: str | None = None
    created_at: datetime | None = None


class LearningProgressResponse(BaseModel):
    assignment_id: UUID
    chapter_id: UUID
    status: str
    last_read_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime | None = None


class LearningAnswerResponse(BaseModel):
    answer_id: UUID
    assignment_id: UUID
    question_id: UUID
    selected_option: str
    is_correct: bool
    answered_at: datetime | None = None
