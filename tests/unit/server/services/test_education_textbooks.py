"""Contract tests for versioned family textbook learning."""

import asyncio
import json
import logging
from unittest.mock import AsyncMock
from types import SimpleNamespace
import sys
from hashlib import sha256
from uuid import UUID

import pytest

from src.server.services import education_textbooks


ARTIFACT_VERSION_ID = "f5761267-11d1-4977-8107-e2671c99a2f0"


def _artifact_processing_job(*sources: dict) -> dict:
    return {
        "job_id": "job-1",
        "version_id": ARTIFACT_VERSION_ID,
        "textbook_id": "textbook-1",
        "household_id": "household-1",
        "title": "英语第二册",
        "slug": "english-2",
        "version_sequence": 1,
        "attempt_count": 1,
        "sources": list(sources),
    }


def _artifact_source(
    *,
    position: int,
    filename: str,
    markdown: bytes,
    artifact_id: str | None = None,
) -> tuple[dict, str, str]:
    artifact_id = artifact_id or f"artifact-{position}"
    prefix = (
        "education/household-1/english-2/source-bundles/"
        f"{ARTIFACT_VERSION_ID}/{position:02d}/"
    )
    manifest_key = f"{prefix}manifest.json"
    artifact_key = f"{prefix}artifacts/document.md"
    source = {
        "document_id": f"doc-{position}",
        "producer_job_id": f"job-parse-{position}",
        "primary_artifact_id": artifact_id,
        "position": position,
        "source_filename": filename,
        "source_media_type": "application/pdf",
        "source_format": "pdf",
        "primary_sha256": sha256(markdown).hexdigest(),
        "snapshot_prefix": prefix,
    }
    return source, manifest_key, artifact_key


def _artifact_manifest(source: dict, markdown: bytes) -> dict:
    return {
        "format": "langalpha-textbook-source-snapshot/v1",
        "document_id": source["document_id"],
        "producer_job_id": source["producer_job_id"],
        "primary_artifact_id": source["primary_artifact_id"],
        "artifacts": [
            {
                "artifact_id": source["primary_artifact_id"],
                "artifact_kind": "primary_document",
                "format": "gfm",
                "media_type": "text/markdown",
                "relative_path": "artifacts/document.md",
                "sha256": sha256(markdown).hexdigest(),
            }
        ],
    }


def test_version_transition_requires_review_before_publication():
    education_textbooks.assert_version_transition(current="review", target="published")

    with pytest.raises(education_textbooks.TextbookTransitionError):
        education_textbooks.assert_version_transition(
            current="draft", target="published"
        )


@pytest.mark.asyncio
async def test_only_parent_can_start_a_frozen_textbook_processing_job(monkeypatch):
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value=None),
    )

    with pytest.raises(education_textbooks.TextbookPermissionError):
        await education_textbooks.start_processing(
            parent_user_id="student-1",
            textbook_id="textbook-1",
            source_asset_ids=["asset-1"],
        )


@pytest.mark.asyncio
async def test_completed_parse_job_candidates_require_a_parent(monkeypatch):
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value=None),
    )

    with pytest.raises(education_textbooks.TextbookPermissionError):
        await education_textbooks.list_completed_textbook_parse_jobs(
            parent_user_id="student-1"
        )


@pytest.mark.asyncio
async def test_completed_parse_job_candidates_delegate_to_the_read_model(monkeypatch):
    candidates = [{"producer_job_id": "job-parse-1"}]
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    listed = AsyncMock(return_value=candidates)
    monkeypatch.setattr(
        education_textbooks,
        "list_completed_parse_jobs_for_parent",
        listed,
    )

    result = await education_textbooks.list_completed_textbook_parse_jobs(
        parent_user_id="parent-1"
    )

    assert result == candidates
    listed.assert_awaited_once_with(parent_user_id="parent-1")


@pytest.mark.asyncio
async def test_creating_chinese_textbooks_uses_distinct_storage_slugs(monkeypatch):
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    create = AsyncMock(return_value={"textbook_id": "textbook-1"})
    monkeypatch.setattr(education_textbooks, "create_textbook_record", create)

    await education_textbooks.create_textbook(
        parent_user_id="parent-1", title="语文上册"
    )
    await education_textbooks.create_textbook(
        parent_user_id="parent-1", title="数学上册"
    )

    slugs = [call.kwargs["slug"] for call in create.await_args_list]
    assert len(set(slugs)) == 2
    assert all(slug.startswith("textbook-") for slug in slugs)


@pytest.mark.asyncio
async def test_start_processing_freezes_sources_before_queueing(monkeypatch):
    context = {"household_id": "household-1", "timezone": "Asia/Tokyo"}
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value=context),
    )
    queue = AsyncMock(return_value={"job_id": "job-1", "status": "queued"})
    monkeypatch.setattr(education_textbooks, "queue_textbook_processing", queue)

    result = await education_textbooks.start_processing(
        parent_user_id="parent-1",
        textbook_id="textbook-1",
        source_asset_ids=["asset-1", "asset-2"],
    )

    assert result == {"job_id": "job-1", "status": "queued"}
    assert queue.await_args.kwargs == {
        "parent_user_id": "parent-1",
        "household_id": "household-1",
        "textbook_id": "textbook-1",
        "source_asset_ids": ["asset-1", "asset-2"],
        "extractor_name": "local_fixture",
        "extractor_version": "1",
    }


@pytest.mark.asyncio
async def test_parse_job_processing_freezes_every_bundle_before_queueing(monkeypatch):
    version_id = "f5761267-11d1-4977-8107-e2671c99a2f0"
    job_id = "7bc1e58d-5a34-49d6-8c5c-70703e989bd4"
    textbook_id = "5e3a0b43-8378-4b6c-926f-0f053577501d"
    events: list[str] = []
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_textbook_for_parent",
        AsyncMock(
            return_value={
                "textbook_id": textbook_id,
                "household_id": "household-1",
                "slug": "reading-explorer-3",
            }
        ),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_owned_parse_job",
        AsyncMock(
            side_effect=[
                {"document_id": "doc-1", "status": "completed"},
                {"document_id": "doc-2", "status": "completed"},
            ]
        ),
    )

    async def freeze(**kwargs):
        events.append(f"freeze:{kwargs['position']}")
        return SimpleNamespace(
            source={
                "document_id": kwargs["document_id"],
                "producer_job_id": kwargs["producer_job_id"],
                "primary_artifact_id": f"art-{kwargs['position']}",
                "primary_sha256": str(kwargs["position"]) * 64,
            },
            written_keys=(f"snapshot-key-{kwargs['position']}",),
        )

    async def queue(**kwargs):
        events.append("queue")
        assert kwargs["version_id"] == version_id
        assert kwargs["job_id"] == job_id
        assert all("written_keys" not in source for source in kwargs["sources"])
        return {"job_id": job_id, "version_id": version_id, "status": "queued"}

    monkeypatch.setattr(
        education_textbooks, "freeze_parse_job_source", freeze, raising=False
    )
    monkeypatch.setattr(
        education_textbooks,
        "queue_textbook_processing_from_artifacts",
        queue,
        raising=False,
    )
    generated_ids = iter([UUID(version_id), UUID(job_id)])
    monkeypatch.setattr(education_textbooks, "uuid4", lambda: next(generated_ids))

    result = await education_textbooks.start_processing_from_parse_jobs(
        parent_user_id="parent-1",
        textbook_id=textbook_id,
        source_parse_job_ids=["job-parse-1", "job-parse-2"],
    )

    assert result["status"] == "queued"
    assert events == ["freeze:1", "freeze:2", "queue"]


@pytest.mark.asyncio
async def test_parse_job_processing_does_not_queue_when_a_snapshot_fails(monkeypatch):
    textbook_id = "5e3a0b43-8378-4b6c-926f-0f053577501d"
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_textbook_for_parent",
        AsyncMock(
            return_value={
                "textbook_id": textbook_id,
                "household_id": "household-1",
                "slug": "reading-explorer-3",
            }
        ),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_owned_parse_job",
        AsyncMock(return_value={"document_id": "doc-1", "status": "completed"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "freeze_parse_job_source",
        AsyncMock(side_effect=education_textbooks.TextbookError("snapshot failed")),
        raising=False,
    )
    queue = AsyncMock()
    monkeypatch.setattr(
        education_textbooks,
        "queue_textbook_processing_from_artifacts",
        queue,
        raising=False,
    )

    with pytest.raises(education_textbooks.TextbookError, match="snapshot failed"):
        await education_textbooks.start_processing_from_parse_jobs(
            parent_user_id="parent-1",
            textbook_id=textbook_id,
            source_parse_job_ids=["job-parse-1"],
        )

    queue.assert_not_awaited()


@pytest.mark.asyncio
async def test_parse_job_processing_cleans_prior_snapshots_when_a_later_source_fails(
    monkeypatch,
):
    textbook_id = "5e3a0b43-8378-4b6c-926f-0f053577501d"
    version_id = "f5761267-11d1-4977-8107-e2671c99a2f0"
    job_id = "7bc1e58d-5a34-49d6-8c5c-70703e989bd4"
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_textbook_for_parent",
        AsyncMock(
            return_value={
                "textbook_id": textbook_id,
                "household_id": "household-1",
                "slug": "reading-explorer-3",
            }
        ),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_owned_parse_job",
        AsyncMock(
            side_effect=[
                {"document_id": "doc-1", "status": "completed"},
                {"document_id": "doc-2", "status": "completed"},
            ]
        ),
    )
    first = SimpleNamespace(
        source={"document_id": "doc-1"},
        written_keys=("snapshot-key-1", "snapshot-key-2"),
    )
    monkeypatch.setattr(
        education_textbooks,
        "freeze_parse_job_source",
        AsyncMock(
            side_effect=[
                first,
                education_textbooks.TextbookError("second snapshot failed"),
            ]
        ),
        raising=False,
    )
    cleanup = AsyncMock()
    monkeypatch.setattr(
        education_textbooks,
        "cleanup_snapshot_objects",
        cleanup,
        raising=False,
    )
    queue = AsyncMock()
    monkeypatch.setattr(
        education_textbooks,
        "queue_textbook_processing_from_artifacts",
        queue,
        raising=False,
    )
    generated_ids = iter([UUID(version_id), UUID(job_id)])
    monkeypatch.setattr(education_textbooks, "uuid4", lambda: next(generated_ids))

    with pytest.raises(education_textbooks.TextbookError, match="second snapshot"):
        await education_textbooks.start_processing_from_parse_jobs(
            parent_user_id="parent-1",
            textbook_id=textbook_id,
            source_parse_job_ids=["job-parse-1", "job-parse-2"],
        )

    cleanup.assert_awaited_once_with(["snapshot-key-1", "snapshot-key-2"])
    queue.assert_not_awaited()


@pytest.mark.asyncio
async def test_parse_job_processing_cleans_snapshots_on_known_queue_validation_error(
    monkeypatch,
):
    textbook_id = "5e3a0b43-8378-4b6c-926f-0f053577501d"
    version_id = "f5761267-11d1-4977-8107-e2671c99a2f0"
    job_id = "7bc1e58d-5a34-49d6-8c5c-70703e989bd4"
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_textbook_for_parent",
        AsyncMock(
            return_value={
                "textbook_id": textbook_id,
                "household_id": "household-1",
                "slug": "reading-explorer-3",
            }
        ),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_owned_parse_job",
        AsyncMock(return_value={"document_id": "doc-1", "status": "completed"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "freeze_parse_job_source",
        AsyncMock(
            return_value=SimpleNamespace(
                source={"document_id": "doc-1"},
                written_keys=("snapshot-key-1", "snapshot-key-2"),
            )
        ),
        raising=False,
    )
    cleanup = AsyncMock()
    monkeypatch.setattr(
        education_textbooks,
        "cleanup_snapshot_objects",
        cleanup,
        raising=False,
    )
    queue = AsyncMock(
        side_effect=education_textbooks.TextbookQueueValidationError(
            "invalid source"
        )
    )
    monkeypatch.setattr(
        education_textbooks,
        "queue_textbook_processing_from_artifacts",
        queue,
        raising=False,
    )
    generated_ids = iter([UUID(version_id), UUID(job_id)])
    monkeypatch.setattr(education_textbooks, "uuid4", lambda: next(generated_ids))

    with pytest.raises(education_textbooks.TextbookError):
        await education_textbooks.start_processing_from_parse_jobs(
            parent_user_id="parent-1",
            textbook_id=textbook_id,
            source_parse_job_ids=["job-parse-1"],
        )

    cleanup.assert_awaited_once_with(["snapshot-key-1", "snapshot-key-2"])


@pytest.mark.asyncio
async def test_parse_job_processing_cleans_snapshots_when_queue_returns_none(
    monkeypatch,
):
    textbook_id = "5e3a0b43-8378-4b6c-926f-0f053577501d"
    version_id = "f5761267-11d1-4977-8107-e2671c99a2f0"
    job_id = "7bc1e58d-5a34-49d6-8c5c-70703e989bd4"
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_textbook_for_parent",
        AsyncMock(
            return_value={
                "textbook_id": textbook_id,
                "household_id": "household-1",
                "slug": "reading-explorer-3",
            }
        ),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_owned_parse_job",
        AsyncMock(return_value={"document_id": "doc-1", "status": "completed"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "freeze_parse_job_source",
        AsyncMock(
            return_value=SimpleNamespace(
                source={"document_id": "doc-1"},
                written_keys=("snapshot-key-1", "snapshot-key-2"),
            )
        ),
        raising=False,
    )
    cleanup = AsyncMock()
    monkeypatch.setattr(
        education_textbooks,
        "cleanup_snapshot_objects",
        cleanup,
        raising=False,
    )
    monkeypatch.setattr(
        education_textbooks,
        "queue_textbook_processing_from_artifacts",
        AsyncMock(return_value=None),
        raising=False,
    )
    generated_ids = iter([UUID(version_id), UUID(job_id)])
    monkeypatch.setattr(education_textbooks, "uuid4", lambda: next(generated_ids))

    with pytest.raises(education_textbooks.TextbookNotFoundError):
        await education_textbooks.start_processing_from_parse_jobs(
            parent_user_id="parent-1",
            textbook_id=textbook_id,
            source_parse_job_ids=["job-parse-1"],
        )

    cleanup.assert_awaited_once_with(["snapshot-key-1", "snapshot-key-2"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("durable_state", "should_cleanup"),
    [
        (False, True),
        (True, False),
    ],
)
async def test_parse_job_processing_reconciles_unknown_queue_exception_with_durable_state(
    monkeypatch, durable_state, should_cleanup
):
    textbook_id = "5e3a0b43-8378-4b6c-926f-0f053577501d"
    version_id = "f5761267-11d1-4977-8107-e2671c99a2f0"
    job_id = "7bc1e58d-5a34-49d6-8c5c-70703e989bd4"
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_textbook_for_parent",
        AsyncMock(
            return_value={
                "textbook_id": textbook_id,
                "household_id": "household-1",
                "slug": "reading-explorer-3",
            }
        ),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_owned_parse_job",
        AsyncMock(return_value={"document_id": "doc-1", "status": "completed"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "freeze_parse_job_source",
        AsyncMock(
            return_value=SimpleNamespace(
                source={"document_id": "doc-1"},
                written_keys=("snapshot-key-1", "snapshot-key-2"),
            )
        ),
        raising=False,
    )
    cleanup = AsyncMock()
    monkeypatch.setattr(
        education_textbooks,
        "cleanup_snapshot_objects",
        cleanup,
        raising=False,
    )
    monkeypatch.setattr(
        education_textbooks,
        "queue_textbook_processing_from_artifacts",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
        raising=False,
    )
    state_check = AsyncMock(return_value=durable_state)
    monkeypatch.setattr(
        education_textbooks,
        "textbook_processing_job_exists",
        state_check,
        raising=False,
    )
    generated_ids = iter([UUID(version_id), UUID(job_id)])
    monkeypatch.setattr(education_textbooks, "uuid4", lambda: next(generated_ids))

    with pytest.raises(RuntimeError, match="database unavailable"):
        await education_textbooks.start_processing_from_parse_jobs(
            parent_user_id="parent-1",
            textbook_id=textbook_id,
            source_parse_job_ids=["job-parse-1"],
        )

    state_check.assert_awaited_once_with(job_id=job_id, version_id=version_id)
    if should_cleanup:
        cleanup.assert_awaited_once_with(["snapshot-key-1", "snapshot-key-2"])
    else:
        cleanup.assert_not_awaited()


@pytest.mark.asyncio
async def test_parse_job_processing_retries_state_probe_before_cleanup(
    monkeypatch,
):
    monkeypatch.setattr(
        education_textbooks,
        "_STATE_PROBE_BACKOFF_SECONDS",
        0,
        raising=False,
    )
    textbook_id = "5e3a0b43-8378-4b6c-926f-0f053577501d"
    version_id = "f5761267-11d1-4977-8107-e2671c99a2f0"
    job_id = "7bc1e58d-5a34-49d6-8c5c-70703e989bd4"
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_textbook_for_parent",
        AsyncMock(
            return_value={
                "textbook_id": textbook_id,
                "household_id": "household-1",
                "slug": "reading-explorer-3",
            }
        ),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_owned_parse_job",
        AsyncMock(return_value={"document_id": "doc-1", "status": "completed"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "freeze_parse_job_source",
        AsyncMock(
            return_value=SimpleNamespace(
                source={"document_id": "doc-1"},
                written_keys=("snapshot-key-1", "snapshot-key-2"),
            )
        ),
        raising=False,
    )
    cleanup = AsyncMock()
    monkeypatch.setattr(
        education_textbooks,
        "cleanup_snapshot_objects",
        cleanup,
        raising=False,
    )
    monkeypatch.setattr(
        education_textbooks,
        "queue_textbook_processing_from_artifacts",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
        raising=False,
    )
    monkeypatch.setattr(
        education_textbooks,
        "textbook_processing_job_exists",
        AsyncMock(side_effect=[RuntimeError("probe unavailable"), False]),
        raising=False,
    )
    generated_ids = iter([UUID(version_id), UUID(job_id)])
    monkeypatch.setattr(education_textbooks, "uuid4", lambda: next(generated_ids))

    with pytest.raises(RuntimeError, match="database unavailable"):
        await education_textbooks.start_processing_from_parse_jobs(
            parent_user_id="parent-1",
            textbook_id=textbook_id,
            source_parse_job_ids=["job-parse-1"],
        )

    cleanup.assert_awaited_once_with(["snapshot-key-1", "snapshot-key-2"])


@pytest.mark.asyncio
async def test_parse_job_processing_warns_and_retains_when_state_probe_is_exhausted(
    monkeypatch, caplog
):
    monkeypatch.setattr(
        education_textbooks,
        "_STATE_PROBE_BACKOFF_SECONDS",
        0,
        raising=False,
    )
    textbook_id = "5e3a0b43-8378-4b6c-926f-0f053577501d"
    version_id = "f5761267-11d1-4977-8107-e2671c99a2f0"
    job_id = "7bc1e58d-5a34-49d6-8c5c-70703e989bd4"
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_textbook_for_parent",
        AsyncMock(
            return_value={
                "textbook_id": textbook_id,
                "household_id": "household-1",
                "slug": "reading-explorer-3",
            }
        ),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_owned_parse_job",
        AsyncMock(return_value={"document_id": "doc-1", "status": "completed"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "freeze_parse_job_source",
        AsyncMock(
            return_value=SimpleNamespace(
                source={"document_id": "doc-1"},
                written_keys=("snapshot-key-1", "snapshot-key-2"),
            )
        ),
        raising=False,
    )
    cleanup = AsyncMock()
    monkeypatch.setattr(
        education_textbooks,
        "cleanup_snapshot_objects",
        cleanup,
        raising=False,
    )
    monkeypatch.setattr(
        education_textbooks,
        "queue_textbook_processing_from_artifacts",
        AsyncMock(side_effect=RuntimeError("database unavailable")),
        raising=False,
    )
    state_check = AsyncMock(
        side_effect=[
            RuntimeError("probe unavailable"),
            RuntimeError("probe unavailable"),
            RuntimeError("probe unavailable"),
        ]
    )
    monkeypatch.setattr(
        education_textbooks,
        "textbook_processing_job_exists",
        state_check,
        raising=False,
    )
    generated_ids = iter([UUID(version_id), UUID(job_id)])
    monkeypatch.setattr(education_textbooks, "uuid4", lambda: next(generated_ids))

    with (
        caplog.at_level(
            logging.WARNING, logger=education_textbooks.__name__
        ),
        pytest.raises(RuntimeError, match="database unavailable"),
    ):
        await education_textbooks.start_processing_from_parse_jobs(
            parent_user_id="parent-1",
            textbook_id=textbook_id,
            source_parse_job_ids=["job-parse-1"],
        )

    assert state_check.await_count == 3
    cleanup.assert_not_awaited()
    records = [
        record
        for record in caplog.records
        if record.message == "textbook_source_snapshot_state_indeterminate"
    ]
    assert len(records) == 1
    assert records[0].version_id == version_id
    assert records[0].job_id == job_id
    assert "snapshot-key" not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state_mode", "should_cleanup", "expected_probe_calls", "expect_warning"),
    [
        ("absent", True, 1, False),
        ("present", False, 1, False),
        ("indeterminate", False, 3, True),
    ],
)
async def test_parse_job_processing_reconciles_cancellation_during_queueing(
    monkeypatch,
    caplog,
    state_mode,
    should_cleanup,
    expected_probe_calls,
    expect_warning,
):
    monkeypatch.setattr(
        education_textbooks,
        "_STATE_PROBE_BACKOFF_SECONDS",
        0,
        raising=False,
    )
    textbook_id = "5e3a0b43-8378-4b6c-926f-0f053577501d"
    version_id = "f5761267-11d1-4977-8107-e2671c99a2f0"
    job_id = "7bc1e58d-5a34-49d6-8c5c-70703e989bd4"
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_textbook_for_parent",
        AsyncMock(
            return_value={
                "textbook_id": textbook_id,
                "household_id": "household-1",
                "slug": "reading-explorer-3",
            }
        ),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_owned_parse_job",
        AsyncMock(return_value={"document_id": "doc-1", "status": "completed"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "freeze_parse_job_source",
        AsyncMock(
            return_value=SimpleNamespace(
                source={"document_id": "doc-1"},
                written_keys=("snapshot-key-1", "snapshot-key-2"),
            )
        ),
        raising=False,
    )
    cleanup = AsyncMock()
    monkeypatch.setattr(
        education_textbooks,
        "cleanup_snapshot_objects",
        cleanup,
        raising=False,
    )
    monkeypatch.setattr(
        education_textbooks,
        "queue_textbook_processing_from_artifacts",
        AsyncMock(side_effect=asyncio.CancelledError()),
        raising=False,
    )
    if state_mode == "absent":
        state_check = AsyncMock(return_value=False)
    elif state_mode == "present":
        state_check = AsyncMock(return_value=True)
    else:
        state_check = AsyncMock(
            side_effect=[
                RuntimeError("probe unavailable"),
                RuntimeError("probe unavailable"),
                RuntimeError("probe unavailable"),
            ]
        )
    monkeypatch.setattr(
        education_textbooks,
        "textbook_processing_job_exists",
        state_check,
        raising=False,
    )
    generated_ids = iter([UUID(version_id), UUID(job_id)])
    monkeypatch.setattr(education_textbooks, "uuid4", lambda: next(generated_ids))

    with (
        caplog.at_level(
            logging.WARNING, logger=education_textbooks.__name__
        ),
        pytest.raises(asyncio.CancelledError),
    ):
        await education_textbooks.start_processing_from_parse_jobs(
            parent_user_id="parent-1",
            textbook_id=textbook_id,
            source_parse_job_ids=["job-parse-1"],
        )

    assert state_check.await_count == expected_probe_calls
    if should_cleanup:
        cleanup.assert_awaited_once_with(["snapshot-key-1", "snapshot-key-2"])
    else:
        cleanup.assert_not_awaited()
    warning_records = [
        record
        for record in caplog.records
        if record.message == "textbook_source_snapshot_state_indeterminate"
    ]
    assert len(warning_records) == int(expect_warning)
    if warning_records:
        assert warning_records[0].version_id == version_id
        assert warning_records[0].job_id == job_id
    assert "snapshot-key" not in caplog.text


@pytest.mark.asyncio
async def test_parse_job_processing_cleans_prior_snapshots_on_cancellation(
    monkeypatch,
):
    textbook_id = "5e3a0b43-8378-4b6c-926f-0f053577501d"
    version_id = "f5761267-11d1-4977-8107-e2671c99a2f0"
    job_id = "7bc1e58d-5a34-49d6-8c5c-70703e989bd4"
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_textbook_for_parent",
        AsyncMock(
            return_value={
                "textbook_id": textbook_id,
                "household_id": "household-1",
                "slug": "reading-explorer-3",
            }
        ),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_owned_parse_job",
        AsyncMock(
            side_effect=[
                {"document_id": "doc-1", "status": "completed"},
                {"document_id": "doc-2", "status": "completed"},
            ]
        ),
    )
    first = SimpleNamespace(
        source={"document_id": "doc-1"},
        written_keys=("snapshot-key-1", "snapshot-key-2"),
    )
    monkeypatch.setattr(
        education_textbooks,
        "freeze_parse_job_source",
        AsyncMock(side_effect=[first, asyncio.CancelledError()]),
        raising=False,
    )
    cleanup = AsyncMock()
    monkeypatch.setattr(
        education_textbooks,
        "cleanup_snapshot_objects",
        cleanup,
        raising=False,
    )
    generated_ids = iter([UUID(version_id), UUID(job_id)])
    monkeypatch.setattr(education_textbooks, "uuid4", lambda: next(generated_ids))

    with pytest.raises(asyncio.CancelledError):
        await education_textbooks.start_processing_from_parse_jobs(
            parent_user_id="parent-1",
            textbook_id=textbook_id,
            source_parse_job_ids=["job-parse-1", "job-parse-2"],
        )

    cleanup.assert_awaited_once_with(["snapshot-key-1", "snapshot-key-2"])


@pytest.mark.asyncio
async def test_processing_job_writes_a_bundle_before_making_a_version_reviewable(
    monkeypatch,
):
    job = {
        "job_id": "job-1",
        "version_id": "version-1",
        "textbook_id": "textbook-1",
        "household_id": "household-1",
        "title": "英语第二册",
        "slug": "english-2",
        "version_sequence": 1,
        "attempt_count": 1,
        "sources": [{"asset_id": "asset-1", "original_filename": "book.pdf"}],
    }
    monkeypatch.setattr(
        education_textbooks,
        "claim_textbook_processing_job",
        AsyncMock(return_value=job),
    )
    bundle = AsyncMock(return_value="education/household-1/english-2/v1")
    complete = AsyncMock(return_value={"job_id": "job-1", "status": "completed"})
    monkeypatch.setattr(
        education_textbooks, "write_textbook_content_bundle", bundle, raising=False
    )
    monkeypatch.setattr(
        education_textbooks, "complete_textbook_processing_job", complete
    )

    result = await education_textbooks.process_textbook_job(job_id="job-1")

    assert result["status"] == "completed"
    assert bundle.await_args.args[0] == job
    assert (
        complete.await_args.kwargs["bundle_prefix"]
        == "education/household-1/english-2/v1"
    )
    assert complete.await_args.kwargs["extractor"] == {
        "name": "local_fixture",
        "version": "1",
    }


@pytest.mark.asyncio
async def test_artifact_processing_skips_pdf_pipeline_and_persists_complete_sources_in_order(
    monkeypatch,
):
    first_markdown = "# First source\n\nComplete first Markdown.\n"
    second_markdown = "# Second source\n\nComplete second Markdown.\n"
    first, first_manifest_key, first_artifact_key = _artifact_source(
        position=1,
        filename="reading-explorer.pdf",
        markdown=first_markdown.encode(),
    )
    second, second_manifest_key, second_artifact_key = _artifact_source(
        position=2,
        filename="workbook.pdf",
        markdown=second_markdown.encode(),
    )
    objects = {
        first_manifest_key: json.dumps(
            _artifact_manifest(first, first_markdown.encode())
        ).encode(),
        first_artifact_key: first_markdown.encode(),
        second_manifest_key: json.dumps(
            {
                **_artifact_manifest(second, second_markdown.encode()),
                "artifacts": [
                    {
                        **_artifact_manifest(second, second_markdown.encode())[
                            "artifacts"
                        ][0],
                        "format": "markdown",
                        "media_type": "text/markdown; charset=utf-8",
                    }
                ],
            }
        ).encode(),
        second_artifact_key: second_markdown.encode(),
    }
    job = _artifact_processing_job(first, second)
    monkeypatch.setattr(
        education_textbooks,
        "claim_textbook_processing_job",
        AsyncMock(return_value=job),
    )
    monkeypatch.setattr(education_textbooks, "get_bytes", objects.get)
    build_pdf = AsyncMock(side_effect=AssertionError("pypdf path must not run"))
    write_bundle = AsyncMock(side_effect=AssertionError("legacy bundle must not run"))
    complete = AsyncMock(return_value={"job_id": "job-1", "status": "completed"})
    monkeypatch.setattr(
        education_textbooks, "build_local_pdf_package", build_pdf, raising=False
    )
    monkeypatch.setattr(
        education_textbooks,
        "write_textbook_content_bundle",
        write_bundle,
        raising=False,
    )
    monkeypatch.setattr(
        education_textbooks, "complete_textbook_processing_job", complete
    )

    result = await education_textbooks.process_textbook_job(job_id="job-1")

    assert result["status"] == "completed"
    build_pdf.assert_not_awaited()
    write_bundle.assert_not_awaited()
    chapters = complete.await_args.kwargs["chapters"]
    assert [chapter["position"] for chapter in chapters] == [1, 2]
    assert [chapter["title"] for chapter in chapters] == [
        "reading-explorer.pdf",
        "workbook.pdf",
    ]
    assert [chapter["markdown"] for chapter in chapters] == [
        first_markdown,
        second_markdown,
    ]
    assert [chapter["markdown_key"] for chapter in chapters] == [
        first_artifact_key,
        second_artifact_key,
    ]
    assert complete.await_args.kwargs["bundle_prefix"] == (
        "education/household-1/english-2/source-bundles/"
        f"{ARTIFACT_VERSION_ID}"
    )
    assert complete.await_args.kwargs["extractor"] == {
        "name": "managed_ptc",
        "version": "1",
    }


@pytest.mark.asyncio
async def test_artifact_processing_reads_legacy_root_snapshot_layout(monkeypatch):
    markdown = "# Legacy root source\n\nComplete Markdown.\n"
    source, manifest_key, _current_artifact_key = _artifact_source(
        position=1,
        filename="legacy.pdf",
        markdown=markdown.encode(),
    )
    legacy_artifact_key = f"{source['snapshot_prefix']}document.md"
    manifest = _artifact_manifest(source, markdown.encode())
    manifest["artifacts"][0]["relative_path"] = "document.md"
    objects = {
        manifest_key: json.dumps(manifest).encode(),
        legacy_artifact_key: markdown.encode(),
    }
    monkeypatch.setattr(
        education_textbooks,
        "claim_textbook_processing_job",
        AsyncMock(return_value=_artifact_processing_job(source)),
    )
    monkeypatch.setattr(education_textbooks, "get_bytes", objects.get)
    complete = AsyncMock(return_value={"job_id": "job-1", "status": "completed"})
    monkeypatch.setattr(
        education_textbooks, "complete_textbook_processing_job", complete
    )

    await education_textbooks.process_textbook_job(job_id="job-1")

    assert complete.await_args.kwargs["chapters"][0]["markdown"] == markdown
    assert complete.await_args.kwargs["chapters"][0]["markdown_key"] == (
        legacy_artifact_key
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        "missing_manifest",
        "invalid_manifest",
        "missing_primary",
        "bad_digest",
        "oversized",
        "invalid_utf8",
    ],
)
async def test_artifact_processing_fails_closed_on_invalid_snapshot(
    monkeypatch, failure
):
    markdown = b"# Complete source\n"
    source, manifest_key, artifact_key = _artifact_source(
        position=1,
        filename="reading-explorer.pdf",
        markdown=markdown,
    )
    manifest = _artifact_manifest(source, markdown)
    objects = {manifest_key: json.dumps(manifest).encode(), artifact_key: markdown}
    if failure == "missing_manifest":
        objects.pop(manifest_key)
    elif failure == "invalid_manifest":
        objects[manifest_key] = b"not-json"
    elif failure == "missing_primary":
        manifest["primary_artifact_id"] = "missing-artifact"
    elif failure == "bad_digest":
        objects[artifact_key] = b"# changed\n"
    elif failure == "oversized":
        objects[artifact_key] = b"x" * 65
        manifest["artifacts"][0]["sha256"] = sha256(objects[artifact_key]).hexdigest()
        source["primary_sha256"] = sha256(objects[artifact_key]).hexdigest()
    elif failure == "invalid_utf8":
        objects[artifact_key] = b"\xff\xfe"
        manifest["artifacts"][0]["sha256"] = sha256(objects[artifact_key]).hexdigest()
        source["primary_sha256"] = sha256(objects[artifact_key]).hexdigest()
    if failure != "invalid_manifest":
        objects[manifest_key] = json.dumps(manifest).encode()

    monkeypatch.setattr(
        education_textbooks,
        "claim_textbook_processing_job",
        AsyncMock(return_value=_artifact_processing_job(source)),
    )
    monkeypatch.setattr(education_textbooks, "get_bytes", objects.get)
    monkeypatch.setattr(
        education_textbooks,
        "get_document_parsing_config",
        lambda: SimpleNamespace(max_upload_bytes=64),
        raising=False,
    )
    complete = AsyncMock()
    failed = AsyncMock()
    monkeypatch.setattr(education_textbooks, "complete_textbook_processing_job", complete)
    monkeypatch.setattr(education_textbooks, "fail_textbook_processing_job", failed)

    with pytest.raises(education_textbooks.TextbookProcessingError):
        await education_textbooks.process_textbook_job(job_id="job-1")

    complete.assert_not_awaited()
    failed.assert_awaited_once()


@pytest.mark.asyncio
async def test_legacy_processing_keeps_the_pdf_and_content_bundle_path(monkeypatch):
    job = {
        "job_id": "job-1",
        "version_id": "version-1",
        "textbook_id": "textbook-1",
        "household_id": "household-1",
        "title": "英语第二册",
        "slug": "english-2",
        "version_sequence": 1,
        "attempt_count": 1,
        "sources": [
            {
                "asset_id": "asset-1",
                "storage_key": "education/household-1/source.pdf",
                "content_type": "application/pdf",
                "original_filename": "source.pdf",
            }
        ],
    }
    package = {
        "extractor": {"name": "local_pypdf", "version": "1"},
        "chapters": [
            {
                "position": 1,
                "slug": "pages-1",
                "title": "第 1 页",
                "markdown_key": (
                    "education/household-1/english-2/v1/chapters/pages-1.md"
                ),
                "markdown": "# 第 1 页",
            }
        ],
    }
    monkeypatch.setattr(
        education_textbooks,
        "claim_textbook_processing_job",
        AsyncMock(return_value=job),
    )
    build_pdf = AsyncMock(return_value=package)
    write_bundle = AsyncMock(return_value="education/household-1/english-2/v1")
    complete = AsyncMock(return_value={"job_id": "job-1", "status": "completed"})
    monkeypatch.setattr(education_textbooks, "build_local_pdf_package", build_pdf)
    monkeypatch.setattr(
        education_textbooks, "write_textbook_content_bundle", write_bundle
    )
    monkeypatch.setattr(
        education_textbooks, "complete_textbook_processing_job", complete
    )

    await education_textbooks.process_textbook_job(job_id="job-1")

    build_pdf.assert_awaited_once_with(job)
    write_bundle.assert_awaited_once_with(job, package)
    assert complete.await_args.kwargs["bundle_prefix"] == (
        "education/household-1/english-2/v1"
    )


def test_local_fixture_processing_creates_content_without_teaching_material():
    package = education_textbooks.build_local_fixture_package(
        {
            "household_id": "household-1",
            "title": "英语第二册",
            "slug": "english-2",
            "version_sequence": 1,
            "sources": [{"original_filename": "book.pdf"}],
        }
    )

    chapter = package["chapters"][0]
    assert "teaching_material" not in chapter
    assert "teaching_material_key" not in chapter
    assert "questions" not in chapter


@pytest.mark.asyncio
async def test_content_bundle_uses_the_frozen_chapter_object_keys(monkeypatch):
    from src.server.services import education_textbook_storage

    uploads: list[str] = []

    async def put(key: str, _content: bytes, _content_type: str) -> None:
        uploads.append(key)

    monkeypatch.setattr(education_textbook_storage, "_put", put)
    monkeypatch.setattr(education_textbook_storage, "get_bytes", lambda _key: b"pdf")
    job = {
        "household_id": "household-1",
        "title": "英语第二册",
        "slug": "english-2",
        "version_sequence": 1,
        "sources": [
            {
                "asset_id": "asset-1",
                "original_filename": "book.pdf",
                "storage_key": "education/household-1/asset-1.pdf",
                "content_type": "application/pdf",
            }
        ],
    }
    package = education_textbooks.build_local_fixture_package(job)

    await education_textbook_storage.write_textbook_content_bundle(job, package)

    assert package["chapters"][0]["markdown_key"] in uploads


@pytest.mark.asyncio
async def test_parent_retry_requeues_only_a_failed_frozen_job(monkeypatch):
    retry = AsyncMock(
        return_value={"job_id": "job-1", "status": "queued", "attempt_count": 1}
    )
    monkeypatch.setattr(education_textbooks, "retry_textbook_processing_job", retry)

    result = await education_textbooks.retry_processing_for_parent(
        parent_user_id="parent-1", job_id="job-1"
    )

    assert result["status"] == "queued"
    retry.assert_awaited_once_with(parent_user_id="parent-1", job_id="job-1")


@pytest.mark.asyncio
async def test_managed_teaching_queue_freezes_input_and_skill_contracts_before_launch(
    monkeypatch,
):
    """A parent request persists exact inputs before the long-running PTC root starts."""
    content_version_id = "f5761267-11d1-4977-8107-e2671c99a2f0"
    job_id = "7bc1e58d-5a34-49d6-8c5c-70703e989bd4"
    frozen = {
        "content_version_id": content_version_id,
        "content_version_sequence": 1,
        "household_id": "household-1",
        "slug": "english-2",
        "title": "英语第二册",
        "chapters": [
            {
                "content_chapter_id": "8a77d086-0b23-4a1e-89d0-f163fa23d5d1",
                "position": 1,
                "slug": "overview",
                "title": "导读",
                "markdown": "# 导读\n\n教材正文。",
            }
        ],
    }
    queued = AsyncMock(
        return_value={
            "job_id": job_id,
            "teaching_package_id": "5e3a0b43-8378-4b6c-926f-0f053577501d",
            "content_version_id": content_version_id,
            "status": "queued",
        }
    )
    launched = AsyncMock(return_value={"root_run_id": "root-1"})
    projected = {
        "job_id": job_id,
        "teaching_package_id": "5e3a0b43-8378-4b6c-926f-0f053577501d",
        "content_version_id": content_version_id,
        "status": "running",
        "phase": "preparing",
        "attempt_count": 1,
        "completed_chapter_count": 0,
        "total_chapter_count": 1,
        "events": [],
        "attempts": [],
    }
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_teaching_input_for_parent",
        AsyncMock(return_value=frozen),
    )
    monkeypatch.setattr(education_textbooks, "queue_teaching_package", queued)
    monkeypatch.setattr(
        education_textbooks,
        "get_teaching_job_projection",
        AsyncMock(return_value=projected),
    )
    monkeypatch.setattr(education_textbooks, "uuid4", lambda: job_id)
    monkeypatch.setattr(
        education_textbooks,
        "_managed_skill_hash",
        lambda skill: {"book-to-skill": "a" * 64, "the-knowledge-guy": "b" * 64}[skill],
    )
    from src.server.services import education_managed_ptc

    monkeypatch.setattr(education_managed_ptc, "launch_teaching_attempt", launched)

    result = await education_textbooks.queue_teaching_package_for_parent(
        parent_user_id="parent-1", content_version_id=content_version_id
    )

    assert result == projected
    queued.assert_awaited_once()
    queue_args = queued.await_args.kwargs
    assert queue_args["parent_user_id"] == "parent-1"
    assert queue_args["content_version_id"] == content_version_id
    assert queue_args["job_id"] == job_id
    assert queue_args["hashes"].input_manifest_sha256
    assert queue_args["hashes"].book_to_skill_sha256 == "a" * 64
    assert queue_args["hashes"].knowledge_guy_sha256 == "b" * 64
    assert queue_args["hashes"].adapter_prompt_sha256
    launched.assert_awaited_once_with(parent_user_id="parent-1", job_id=job_id)


@pytest.mark.asyncio
async def test_parent_can_cancel_and_resume_only_via_the_managed_job_state_machine(
    monkeypatch,
):
    """Public controls delegate to the existing durable cancellation and retry paths."""
    projection = {
        "job_id": "job-1",
        "teaching_package_id": "package-1",
        "content_version_id": "version-1",
        "status": "cancelled",
        "phase": "cancelled",
        "attempt_count": 1,
        "completed_chapter_count": 0,
        "total_chapter_count": 1,
        "events": [],
        "attempts": [],
    }
    get_projection = AsyncMock(return_value=projection)
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(education_textbooks, "get_teaching_job_projection", get_projection)
    from src.server.services import education_managed_ptc, education_teaching_jobs

    cancel = AsyncMock()
    resume = AsyncMock(return_value={"root_run_id": "root-2"})
    monkeypatch.setattr(education_teaching_jobs, "cancel_teaching_job", cancel)
    monkeypatch.setattr(education_managed_ptc, "resume_teaching_job", resume)

    cancelled = await education_textbooks.cancel_teaching_job_for_parent(
        parent_user_id="parent-1", job_id="job-1"
    )
    resumed = await education_textbooks.resume_teaching_job_for_parent(
        parent_user_id="parent-1", job_id="job-1"
    )

    assert cancelled == projection
    assert resumed == projection
    cancel.assert_awaited_once_with(parent_user_id="parent-1", job_id="job-1")
    resume.assert_awaited_once_with(parent_user_id="parent-1", job_id="job-1")


@pytest.mark.asyncio
async def test_parent_resume_returns_failed_safe_projection_when_managed_launch_fails(
    monkeypatch,
):
    projection = {
        "job_id": "job-1",
        "teaching_package_id": "package-1",
        "content_version_id": "version-1",
        "status": "failed",
        "phase": "failed",
        "attempt_count": 2,
        "completed_chapter_count": 0,
        "total_chapter_count": 1,
        "actions": ["resume"],
        "events": [],
        "attempts": [],
    }
    monkeypatch.setattr(
        education_textbooks,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_teaching_job_projection_for_parent",
        AsyncMock(return_value=projection),
    )
    from src.server.services import education_managed_ptc

    monkeypatch.setattr(
        education_managed_ptc,
        "resume_teaching_job",
        AsyncMock(side_effect=RuntimeError("no credential available")),
    )

    resumed = await education_textbooks.resume_teaching_job_for_parent(
        parent_user_id="parent-1", job_id="job-1"
    )

    assert resumed["status"] == "failed"
    assert resumed["actions"] == ["resume"]


def test_safe_teaching_projection_never_relays_managed_runtime_fields():
    job = {
        "job_id": "job-1",
        "teaching_package_id": "package-1",
        "content_version_id": "version-1",
        "status": "running",
        "phase": "generating_teaching",
        "attempt_count": 1,
        "completed_chapter_count": 1,
        "total_chapter_count": 2,
        "storage_key": "education/private/key",
        "events": [
            {
                "sequence": 1,
                "phase": "generating_teaching",
                "summary": "已完成第 1 章教学材料生成",
                "managed_path": "/managed/private",
            }
        ],
        "attempts": [
            {
                "attempt_id": "attempt-1",
                "status": "running",
                "managed_workspace_id": "workspace-1",
            }
        ],
    }

    projected = education_textbooks._safe_teaching_projection(job)

    assert projected["actions"] == ["cancel"]
    assert "storage_key" not in repr(projected)
    assert "/managed/" not in repr(projected)


def test_active_teaching_projection_uses_latest_autonomous_milestone_but_review_is_verified():
    active = education_textbooks._safe_teaching_projection(
        {
            "job_id": "job-1",
            "teaching_package_id": "package-1",
            "content_version_id": "version-1",
            "status": "running",
            "phase": "building_skill",
            "attempt_count": 1,
            "completed_chapter_count": 1,
            "total_chapter_count": 2,
            "events": [
                {"sequence": 1, "phase": "planning", "summary": "Agent 已报告：正在规划"},
                {"sequence": 2, "phase": "practice_build", "summary": "Agent 已报告：第 1 章已完成练习构建"},
            ],
            "attempts": [],
        }
    )
    completed = education_textbooks._safe_teaching_projection(
        {
            "job_id": "job-1",
            "teaching_package_id": "package-1",
            "content_version_id": "version-1",
            "status": "completed",
            "phase": "review",
            "attempt_count": 1,
            "completed_chapter_count": 2,
            "total_chapter_count": 2,
            "events": [{"sequence": 2, "phase": "validating_bundle", "summary": "Agent 已报告：正在校验"}],
            "attempts": [],
        }
    )

    assert active["phase"] == "practice_build"
    assert completed["phase"] == "review"


@pytest.mark.asyncio
async def test_local_processor_makes_stable_chapters_from_extractable_pdf_pages(monkeypatch):
    class Page:
        def extract_text(self):
            return "教材正文"

    monkeypatch.setitem(sys.modules, "pypdf", SimpleNamespace(PdfReader=lambda _stream: SimpleNamespace(pages=[Page(), Page()])))
    monkeypatch.setattr(education_textbooks, "get_bytes", lambda _key: b"%PDF-1.7")
    job = {
        "household_id": "household-1",
        "title": "英语第二册",
        "slug": "english-2",
        "version_sequence": 1,
        "sources": [{"storage_key": "education/h/book.pdf", "content_type": "application/pdf", "original_filename": "book.pdf"}],
    }

    package = await education_textbooks.build_local_pdf_package(job)

    assert package["extractor"] == {"name": "local_pypdf", "version": "1"}
    assert package["knowledge_foundations"] == ["book-to-skill", "the-knowledge-guy"]
    assert package["chapters"][0]["markdown"].endswith("教材正文\n\n教材正文")
    assert "teaching_material" not in package["chapters"][0]
    assert "questions" not in package["chapters"][0]


@pytest.mark.asyncio
async def test_parent_reads_only_manifest_verified_private_teaching_asset(monkeypatch):
    package_id = "5e3a0b43-8378-4b6c-926f-0f053577501d"
    chapter_id = "f5761267-11d1-4977-8107-e2671c99a2f0"
    toolkit = "# 导读工具包\n\n核心概念".encode("utf-8")
    review = {
        "teaching_package_id": package_id,
        "bundle_prefix": "education/household-1/english-2/v1/teaching/v2",
        "asset_manifest": {
            "format": "langalpha-family-teaching-assets/v2",
            "concept_index": {"size_bytes": 2, "concept_count": 1},
            "coverage_audit": {"size_bytes": 2, "status": "complete"},
            "chapters": [
                {
                    "content_chapter_id": chapter_id,
                    "content_sha256": "a" * 64,
                    "coverage_status": "complete",
                    "concept_count": 1,
                    "assets": [
                        {"kind": "knowledge", "size_bytes": 2, "sha256": "b" * 64},
                        {
                            "kind": "toolkit",
                            "size_bytes": len(toolkit),
                            "sha256": sha256(toolkit).hexdigest(),
                        },
                        {"kind": "practice", "size_bytes": 2, "sha256": "c" * 64},
                    ],
                }
            ],
        },
        "chapters": [
            {
                "content_chapter_id": chapter_id,
                "position": 1,
                "slug": "overview",
                "title": "导读",
            }
        ],
    }
    get_review = AsyncMock(return_value=review)
    requested_keys: list[str] = []

    def get_asset(key: str):
        requested_keys.append(key)
        return toolkit

    monkeypatch.setattr(education_textbooks, "get_teaching_asset_review_for_parent", get_review)
    monkeypatch.setattr(education_textbooks, "get_bytes", get_asset)

    asset = await education_textbooks.get_teaching_chapter_asset(
        parent_user_id="parent-1",
        teaching_package_id=package_id,
        chapter_id=chapter_id,
        kind="toolkit",
    )

    assert asset == {
        "teaching_package_id": package_id,
        "chapter_id": chapter_id,
        "kind": "toolkit",
        "content": toolkit.decode("utf-8"),
    }
    assert requested_keys == [
        "education/household-1/english-2/v1/teaching/v2/chapters/01-overview-toolkit.md"
    ]
    assert "education/" not in repr(asset)


@pytest.mark.asyncio
async def test_parent_asset_read_rejects_bytes_that_do_not_match_manifest(monkeypatch):
    chapter_id = "f5761267-11d1-4977-8107-e2671c99a2f0"
    review = {
        "teaching_package_id": "5e3a0b43-8378-4b6c-926f-0f053577501d",
        "bundle_prefix": "education/household-1/english-2/v1/teaching/v2",
        "asset_manifest": {
            "format": "langalpha-family-teaching-assets/v2",
            "concept_index": {"size_bytes": 2, "concept_count": 1},
            "coverage_audit": {"size_bytes": 2, "status": "complete"},
            "chapters": [
                {
                    "content_chapter_id": chapter_id,
                    "content_sha256": "a" * 64,
                    "coverage_status": "complete",
                    "concept_count": 1,
                    "assets": [
                        {"kind": "knowledge", "size_bytes": 2, "sha256": "b" * 64},
                        {"kind": "toolkit", "size_bytes": 1, "sha256": "c" * 64},
                        {"kind": "practice", "size_bytes": 2, "sha256": "d" * 64},
                    ],
                }
            ],
        },
        "chapters": [
            {"content_chapter_id": chapter_id, "position": 1, "slug": "overview", "title": "导读"}
        ],
    }
    monkeypatch.setattr(
        education_textbooks, "get_teaching_asset_review_for_parent", AsyncMock(return_value=review)
    )
    monkeypatch.setattr(education_textbooks, "get_bytes", lambda _key: b"tampered")

    with pytest.raises(education_textbooks.TextbookNotFoundError):
        await education_textbooks.get_teaching_chapter_asset(
            parent_user_id="parent-1",
            teaching_package_id=review["teaching_package_id"],
            chapter_id=chapter_id,
            kind="toolkit",
        )
