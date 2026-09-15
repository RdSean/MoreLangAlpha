"""Pydantic payloads the education tools hand to the chat transcript."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from src.server.app.education.models import EducationTaskResponse


class EducationHomeworkArtifact(BaseModel):
    """What `education_create_homework` returns alongside its content.

    This exists because the tool used to build its artifact as a raw dict: the
    frontend dispatches on an artifact's ``type``, and a type that is not
    published in ``web/src/contracts/artifact-types.json`` is a type no card
    can be registered for — the transcript showed the tool step and nothing
    else. Declaring the model here is what publishes it (see
    ``scripts/contracts/export_schemas.py``), and the coverage test in
    ``artifactIdCoverage.test.ts`` then refuses to let it render as a blank.
    """

    type: Literal["education_homework"] = "education_homework"
    """Discriminator the frontend dispatches on, kept to a literal so the
    generated schema carries a `const` rather than a free string."""

    success: bool
    task_id: str
    student_name: str = Field(description="Display name, resolved by the tool.")
    due_at: str = Field(
        description=(
            "ISO 8601 due timestamp already converted to the household's "
            "timezone. A string rather than a datetime on purpose: Pydantic "
            "would re-serialise a datetime as UTC and quietly undo the "
            "household-local conversion."
        )
    )
    destination: str = Field(description="Where the task can be seen, e.g. /education.")
    attachments_supported: bool
    task: EducationTaskResponse = Field(description="The created task row as stored.")
