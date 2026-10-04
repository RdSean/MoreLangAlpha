from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest
from pydantic import ValidationError

from src.server.app.education.book_models import (
    BookActivityEventResponse,
    BookActivityPageResponse,
    BookJobCreateRequest,
    BookJobItemResponse,
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
        metadata={
            "tool_name": "Read",
            "tool_call_id": "call-1",
            "budget_class": "detail",
            "activity_bytes": 256,
        },
        created_at=datetime.now(timezone.utc),
    )

    assert event.metadata == {"tool_name": "Read", "tool_call_id": "call-1"}


def test_activity_page_exposes_unavailable_state() -> None:
    page = BookActivityPageResponse(
        job_id="9998bb1a-687a-4d45-815d-5b1dd6ed2f17",
        status="running",
        events=[],
        high_water_seq=0,
        cursor_expired=False,
        activity_status="unavailable",
        has_more=False,
    )

    assert page.activity_status == "unavailable"


@pytest.mark.parametrize("missing", ["status", "has_more"])
def test_activity_page_requires_complete_repository_snapshot(missing: str) -> None:
    payload = {
        "job_id": "9998bb1a-687a-4d45-815d-5b1dd6ed2f17",
        "status": "running",
        "events": [],
        "high_water_seq": 0,
        "cursor_expired": False,
        "activity_status": "available",
        "has_more": False,
    }
    payload.pop(missing)

    with pytest.raises(ValidationError):
        BookActivityPageResponse.model_validate(payload)


def test_activity_page_requires_strictly_increasing_event_sequences() -> None:
    created_at = datetime.now(timezone.utc)
    event = {
        "seq": 2,
        "job_id": "9998bb1a-687a-4d45-815d-5b1dd6ed2f17",
        "item_id": None,
        "kind": "job",
        "status": "running",
        "message": "Job running",
        "metadata": {},
        "created_at": created_at,
    }

    with pytest.raises(ValidationError, match="strictly increasing"):
        BookActivityPageResponse(
            job_id=event["job_id"],
            status="running",
            events=[event, event],
            high_water_seq=2,
            cursor_expired=False,
            activity_status="available",
            has_more=False,
        )


def test_job_item_kind_distinguishes_supplementary_from_material() -> None:
    common = {
        "position": 1,
        "knowledge_point_id": None,
        "skill_kp_id": None,
        "status": "queued",
        "attempt": 0,
    }

    material = BookJobItemResponse(
        item_id=UUID("86f03a73-7604-4097-905b-768e6ad0f644"),
        kind="material",
        **common,
    )
    supplementary = BookJobItemResponse(
        item_id=UUID("a5f8dcd6-58c8-4ea7-b3dd-a1f8bf276a63"),
        kind="supplementary",
        **common,
    )

    assert material.kind == "material"
    assert supplementary.kind == "supplementary"


def test_job_item_projects_knowledge_point_title_and_allows_missing_title() -> None:
    common = {
        "item_id": UUID("86f03a73-7604-4097-905b-768e6ad0f644"),
        "kind": "material",
        "position": 1,
        "status": "running",
        "attempt": 1,
    }
    assert BookJobItemResponse(**common).knowledge_point_title is None
    assert (
        BookJobItemResponse(
            **common, knowledge_point_title="位值"
        ).knowledge_point_title
        == "位值"
    )


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


def _workbench_payload():
    return {
        "textbook_id": "txt-test", "title": "Book", "structure_status": "queued",
        "materials": {"total": 0, "ready": 0},
        "updated_at": datetime.now(timezone.utc),
        "source_status": "pending", "source": None,
        "selected_source": {
            "document_id": "doc-1", "parse_job_id": "parse-1",
            "primary_artifact_id": "artifact-1", "filename": "book.md",
            "media_type": "text/markdown", "parser_id": "parser-1",
            "parser_name": "Parser", "completed_at": datetime.now(timezone.utc),
            "content_sha256": "a" * 64, "size_bytes": 12, "image_count": 3,
        },
    }


def test_pending_source_is_metadata_only():
    from src.server.app.education.book_models import TextbookWorkbenchResponse

    payload = _workbench_payload()
    result = TextbookWorkbenchResponse.model_validate(payload)
    assert result.source is None
    assert result.source_frozen_at is None
    payload["source"] = dict(payload["selected_source"], frozen_at=None)
    with pytest.raises(ValidationError, match="ready"):
        TextbookWorkbenchResponse.model_validate(payload)


def test_ready_source_requires_verified_digest_but_old_frozen_time_can_be_unknown():
    from src.server.app.education.book_models import TextbookWorkbenchResponse

    payload = _workbench_payload()
    payload["source_status"] = "ready"
    with pytest.raises(ValidationError, match="ready"):
        TextbookWorkbenchResponse.model_validate(payload)
    payload["source"] = dict(payload["selected_source"], frozen_at=None)
    assert TextbookWorkbenchResponse.model_validate(payload).source.frozen_at is None
    payload["source"]["content_sha256"] = None
    with pytest.raises(ValidationError):
        TextbookWorkbenchResponse.model_validate(payload)


def test_acceptance_explicitly_distinguishes_new_and_reused():
    from src.server.app.education.book_models import CreateBookResponse

    ids = {"textbook_id": UUID(int=1), "job_id": UUID(int=2)}
    assert CreateBookResponse(**ids, acceptance="accepted_new").acceptance == "accepted_new"
    assert CreateBookResponse(**ids, acceptance="reused").acceptance == "reused"
    with pytest.raises(ValidationError):
        CreateBookResponse(**ids, acceptance="unknown")


def test_timing_unknown_is_not_zero_and_progress_is_not_delivery_count():
    from src.server.app.education.book_models import (
        BookAttemptTimingResponse, BookPreparationProgressResponse,
    )

    timing = BookAttemptTimingResponse(attempt=1, request_round=2)
    assert timing.total_ms is None
    assert timing.status == "unavailable"
    assert timing.phases == []
    progress = BookPreparationProgressResponse(total_resources=129, verified_resources=129)
    assert progress.model_dump() == {"total_resources": 129, "verified_resources": 129}
    with pytest.raises(ValidationError):
        BookPreparationProgressResponse(total_resources=2, verified_resources=3)
    with pytest.raises(ValidationError):
        BookAttemptTimingResponse(attempt=1, request_round=1, total_ms=-1)


def test_service_phases_are_finite_and_actions_do_not_claim_duration():
    from src.server.app.education.book_models import BookPhaseTimingResponse

    phase = BookPhaseTimingResponse(phase="ptc_execution")
    assert phase.measured_ms is None
    with pytest.raises(ValidationError):
        BookPhaseTimingResponse(phase="model_thinking")
    with pytest.raises(ValidationError):
        BookPhaseTimingResponse(phase="finalization", object_key="private")
