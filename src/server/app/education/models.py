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
    textbook_id: str
    household_id: str
    title: str
    slug: str
    created_by_user_id: str | None = None
    created_at: datetime | None = None


class TextbookProcessingResponse(BaseModel):
    job_id: str
    version_id: str
    status: str
    attempt_count: int | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None


class TextbookPublicationResponse(BaseModel):
    publication_id: str
    version_id: str
    published_by_user_id: str | None = None
    created_at: datetime | None = None


class TextbookAssignmentResponse(BaseModel):
    assignment_id: str
    publication_id: str
    student_user_id: str
    assigned_by_user_id: str | None = None
    created_at: datetime | None = None


class LearningProgressResponse(BaseModel):
    assignment_id: str
    chapter_id: str
    status: str
    last_read_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime | None = None


class LearningAnswerResponse(BaseModel):
    answer_id: str
    assignment_id: str
    question_id: str
    selected_option: str
    is_correct: bool
    answered_at: datetime | None = None
