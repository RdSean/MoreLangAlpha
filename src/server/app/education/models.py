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
