from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from src.server.app.education.book_models import (
    BookActivityEventResponse,
    BookActivityPageResponse,
    BookJobCreateRequest,
    BookSourceSliceResponse,
    CreateBookRequest,
    KnowledgePointProjectionResponse,
)


def test_activity_event_exposes_only_projected_metadata() -> None:
    event = BookActivityEventResponse(
        seq=1,
        job_id="9998bb1a-687a-4d45-815d-5b1dd6ed2f17",
        item_id=UUID("86f03a73-7604-4097-905b-768e6ad0f644"),
        kind="tool",
        status="running",
        message="Running Read",
        metadata={"tool_name": "Read", "tool_call_id": "call-1"},
        created_at=datetime.now(timezone.utc),
    )

    assert event.metadata == {"tool_name": "Read", "tool_call_id": "call-1"}


def test_activity_page_exposes_unavailable_state() -> None:
    page = BookActivityPageResponse(
        job_id="9998bb1a-687a-4d45-815d-5b1dd6ed2f17",
        events=[],
        high_water_seq=0,
        cursor_expired=False,
        activity_status="unavailable",
    )

    assert page.activity_status == "unavailable"


def test_create_book_request_freezes_one_completed_parse_artifact() -> None:
    request = CreateBookRequest(
        parse_job_id="job-A1b2C3d4E5f6",
        primary_artifact_id="art-A1b2C3d4E5f6",
        title="Reading Explorer 3",
        idempotency_key="library-doc-1-job-A1b2C3d4E5f6",
    )

    assert request.title == "Reading Explorer 3"
    assert request.primary_artifact_id == "art-A1b2C3d4E5f6"


def test_material_job_targets_database_kp_uuids_not_skill_ids() -> None:
    kp_id = UUID("4c3f4d0c-a508-4bff-a89f-a3a584a2fe86")

    request = BookJobCreateRequest(
        kind="materials",
        knowledge_point_ids=[kp_id],
        depth="lesson",
        requirements="Focus on the diagrams.",
        replace_existing=False,
        include_supplementary=False,
        idempotency_key="generate-kp-1",
    )

    assert request.knowledge_point_ids == [kp_id]

    with pytest.raises(ValidationError):
        BookJobCreateRequest.model_validate(
            {
                "kind": "materials",
                "skill_kp_ids": ["unit-1-k1"],
                "knowledge_point_ids": [],
                "depth": "lesson",
                "idempotency_key": "wrong-identifier-kind",
            }
        )


def test_structure_job_rejects_material_targets() -> None:
    with pytest.raises(ValidationError, match="structure job"):
        BookJobCreateRequest(
            kind="structure",
            knowledge_point_ids=[UUID("4c3f4d0c-a508-4bff-a89f-a3a584a2fe86")],
            depth="lesson",
            idempotency_key="structure-with-target",
        )


def test_material_job_requires_at_least_one_target() -> None:
    with pytest.raises(ValidationError, match="material job"):
        BookJobCreateRequest(
            kind="materials",
            knowledge_point_ids=[],
            depth="lesson",
            idempotency_key="empty-material-job",
        )


def test_source_slice_uses_one_based_inclusive_coordinates() -> None:
    response = BookSourceSliceResponse(
        textbook_id="txt-A1b2C3d4E5f6",
        start_line=5,
        end_line=5,
        total_lines=80,
        markdown="A single source line",
    )

    assert response.start_line == response.end_line == 5

    with pytest.raises(ValidationError):
        BookSourceSliceResponse(
            textbook_id="txt-A1b2C3d4E5f6",
            start_line=5,
            end_line=4,
            total_lines=80,
            markdown="",
        )


def test_kp_projection_keeps_database_and_skill_identifiers_distinct() -> None:
    projection = KnowledgePointProjectionResponse(
        knowledge_point_id=UUID("4c3f4d0c-a508-4bff-a89f-a3a584a2fe86"),
        skill_kp_id="unit-1-k1",
        position=1,
        title="Global sport",
        unit_skill_node_id="unit-1",
        node_skill_ids=["unit-1-reading-a"],
        start_line=5,
        end_line=20,
        content_file=None,
        material_available=False,
    )

    assert str(projection.knowledge_point_id) != projection.skill_kp_id
