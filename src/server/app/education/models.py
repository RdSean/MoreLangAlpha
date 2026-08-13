"""Pydantic contracts for first-party family homework APIs."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CreateEducationTaskRequest(BaseModel):
    assigned_student_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=10_000)
    due_at: datetime
    frequency: Literal["once", "daily"] = "once"
    material_asset_ids: list[UUID] = Field(default_factory=list, max_length=20)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title is required")
        return value.strip()


class SubmitEducationTaskRequest(BaseModel):
    submission_text: str = Field(default="", max_length=10_000)
    idempotency_key: UUID | None = None
    asset_ids: list[UUID] = Field(default_factory=list, max_length=20)


class ReviewEducationTaskRequest(BaseModel):
    decision: Literal["revision_requested", "completed"]
    feedback_text: str = Field(min_length=1, max_length=10_000)

    @field_validator("feedback_text")
    @classmethod
    def validate_feedback(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("feedback_text is required")
        return value.strip()


class EducationTaskResponse(BaseModel):
    task_id: str
    task_rule_id: str
    household_id: str
    assigned_student_id: str
    occurrence_date: date
    due_at: datetime
    title: str
    description: str
    status: str
    created_at: datetime | None = None
    latest_review_decision: Literal["revision_requested", "completed"] | None = None
    latest_feedback_text: str | None = None


class EducationSubmissionResponse(BaseModel):
    submission_id: str
    task_id: str
    sequence: int
    submission_text: str
    submitted_by_user_id: str | None = None
    idempotency_key: str | None = None
    created_at: datetime | None = None


class EducationReviewResponse(BaseModel):
    review_id: str
    submission_id: str
    decision: Literal["revision_requested", "completed"]
    feedback_text: str
    reviewed_by_user_id: str | None = None
    created_at: datetime | None = None


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
    source_asset_ids: list[UUID] = Field(min_length=1, max_length=20)


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


class TextbookSourceResponse(BaseModel):
    asset_id: UUID
    original_filename: str
    content_type: str
    size_bytes: int


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
    teaching_material: str
    questions: list[TextbookQuestionResponse]


class TextbookAssignmentSummaryResponse(BaseModel):
    assignment_id: UUID
    student_user_id: str
    student_name: str | None = None
    created_at: datetime | None = None


class TeachingPackageSummaryResponse(BaseModel):
    teaching_package_id: UUID
    sequence: int
    status: str
    chapter_count: int
    question_count: int


class TextbookVersionResponse(BaseModel):
    version_id: UUID
    sequence: int
    status: str
    extractor_name: str | None = None
    extractor_version: str | None = None
    processing_error: str | None = None
    processing_job_id: str | None = None
    processing_job_status: str | None = None
    processing_attempt_count: int | None = None
    chapter_count: int
    is_published: bool
    publication_id: UUID | None = None
    sources: list[TextbookSourceResponse]
    chapters: list[TextbookChapterResponse]
    teaching_packages: list[TeachingPackageSummaryResponse] = Field(default_factory=list)
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


class TextbookPublicationResponse(BaseModel):
    publication_id: UUID
    version_id: UUID
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
