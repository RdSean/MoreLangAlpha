"""Pydantic contracts for first-party family homework APIs."""

import unicodedata
from datetime import date, datetime
from typing import Any, Literal
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
    total_points: int = 0
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


class LearningItemResponse(BaseModel):
    item_id: UUID
    assignment_id: UUID
    skill_node_id: str | None = None
    knowledge_point_id: UUID | None = None
    kind: Literal["question", "highlight", "note", "summary"]
    content: str
    source_anchor: dict[str, Any] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class CreateLearningItemRequest(BaseModel):
    skill_node_id: str | None = Field(default=None, min_length=1, max_length=255)
    kind: Literal["question", "highlight", "note"]
    content: str = Field(min_length=1, max_length=20_000)
    source_anchor: dict[str, Any] | None = None


class UpdateLearningItemRequest(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)
    source_anchor: dict[str, Any] | None = None


class UpdateKnowledgePointProgressRequest(BaseModel):
    status: Literal["not_started", "learning", "read", "review_recommended"]
