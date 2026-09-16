"""Immutable snapshot contracts for completed document-library parse bundles."""

from __future__ import annotations

from hashlib import sha256
import json
from unittest.mock import AsyncMock

import pytest

from src.server.services import education_textbook_source_snapshots as snapshots


HOUSEHOLD_ID = "6eebf7fb-9579-4c5d-825a-2e595b7f1b18"
VERSION_ID = "f5761267-11d1-4977-8107-e2671c99a2f0"
PRODUCER_JOB_ID = "job-A1b2C3d4E5f6"
DOCUMENT_ID = "doc-A1b2C3d4E5f6"
PRIMARY_ARTIFACT_ID = "art-A1b2C3d4E5f6"
IMAGE_ARTIFACT_ID = "art-B1b2C3d4E5f6"


def _parse_job(*, status: str = "completed") -> dict[str, object]:
    return {
        "producer_job_id": PRODUCER_JOB_ID,
        "document_id": DOCUMENT_ID,
        "primary_artifact_id": PRIMARY_ARTIFACT_ID,
        "status": status,
        "original_filename": "reading-explorer.pdf",
        "media_type": "application/pdf",
        "document_format": "pdf",
        "parser_id": "datalab",
        "parser_name": "Datalab",
        "parser_version": "2",
        "completed_at": "2026-09-16T10:00:00+00:00",
        "primary_sha256": "f" * 64,
    }


def _artifact(
    *,
    artifact_id: str,
    artifact_kind: str,
    relative_path: str,
    storage_key: str,
    format: str = "gfm",
    media_type: str = "text/markdown",
) -> dict[str, object]:
    return {
        "artifact_id": artifact_id,
        "document_id": DOCUMENT_ID,
        "producer_job_id": PRODUCER_JOB_ID,
        "artifact_kind": artifact_kind,
        "format": format,
        "media_type": media_type,
        "relative_path": relative_path,
        "storage_key": storage_key,
        "schema_name": None,
        "schema_version": None,
    }


def _configure_store(
    monkeypatch: pytest.MonkeyPatch,
    *,
    job: dict[str, object] | None,
    artifacts: list[dict[str, object]],
    objects: dict[str, bytes],
    fail_manifest: bool = False,
) -> tuple[dict[str, bytes], list[str]]:
    uploads: dict[str, bytes] = {}
    deleted: list[str] = []
    monkeypatch.setattr(
        snapshots, "get_owned_parse_job", AsyncMock(return_value=job)
    )
    monkeypatch.setattr(
        snapshots, "list_artifacts", AsyncMock(return_value=artifacts)
    )

    async def read_object(key: str) -> bytes | None:
        return objects.get(key)

    async def write_object(key: str, content: bytes, _content_type: str) -> bool:
        if fail_manifest and key.endswith("/manifest.json"):
            return False
        uploads[key] = content
        return True

    async def delete_object_key(key: str) -> bool:
        deleted.append(key)
        return True

    monkeypatch.setattr(snapshots, "_read_object", read_object)
    monkeypatch.setattr(snapshots, "_write_object", write_object)
    monkeypatch.setattr(snapshots, "_delete_object", delete_object_key)
    return uploads, deleted


def test_snapshot_prefix_uses_the_pregenerated_version_and_safe_components():
    prefix = snapshots.build_snapshot_prefix(
        household_id=HOUSEHOLD_ID,
        textbook_slug="reading-explorer-3",
        version_id=VERSION_ID,
        position=1,
    )

    assert prefix == (
        f"education/{HOUSEHOLD_ID}/reading-explorer-3/{VERSION_ID}/"
        "source-bundles/01/"
    )


@pytest.mark.asyncio
async def test_completed_owned_bundle_preserves_paths_hashes_and_manifest(monkeypatch):
    primary_bytes = b"# Reading Explorer\n\n![figure](images/figure.png)\n"
    image_bytes = b"image-bytes"
    primary = _artifact(
        artifact_id=PRIMARY_ARTIFACT_ID,
        artifact_kind="primary_document",
        relative_path="document.md",
        storage_key=f"documents/{DOCUMENT_ID}/artifacts/{PRODUCER_JOB_ID}/document.md",
    )
    image = _artifact(
        artifact_id=IMAGE_ARTIFACT_ID,
        artifact_kind="embedded_image",
        relative_path="images/figure.png",
        storage_key=(
            f"documents/{DOCUMENT_ID}/artifacts/{PRODUCER_JOB_ID}/images/figure.png"
        ),
        format="png",
        media_type="image/png",
    )
    uploads, _deleted = _configure_store(
        monkeypatch,
        job=_parse_job(),
        artifacts=[primary, image],
        objects={
            str(primary["storage_key"]): primary_bytes,
            str(image["storage_key"]): image_bytes,
        },
    )

    source = await snapshots.freeze_parse_job_source(
        owner_user_id="parent-1",
        document_id=DOCUMENT_ID,
        producer_job_id=PRODUCER_JOB_ID,
        household_id=HOUSEHOLD_ID,
        textbook_slug="reading-explorer-3",
        version_id=VERSION_ID,
        position=1,
    )

    prefix = snapshots.build_snapshot_prefix(
        household_id=HOUSEHOLD_ID,
        textbook_slug="reading-explorer-3",
        version_id=VERSION_ID,
        position=1,
    )
    assert set(uploads) == {
        f"{prefix}document.md",
        f"{prefix}images/figure.png",
        f"{prefix}manifest.json",
    }
    manifest = json.loads(uploads[f"{prefix}manifest.json"])
    assert [entry["relative_path"] for entry in manifest["artifacts"]] == [
        "document.md",
        "images/figure.png",
    ]
    assert manifest["artifacts"][0]["sha256"] == sha256(primary_bytes).hexdigest()
    assert manifest["artifacts"][1]["sha256"] == sha256(image_bytes).hexdigest()
    assert source == {
        "document_id": DOCUMENT_ID,
        "producer_job_id": PRODUCER_JOB_ID,
        "primary_artifact_id": PRIMARY_ARTIFACT_ID,
        "primary_sha256": sha256(primary_bytes).hexdigest(),
        "filename": "reading-explorer.pdf",
        "media_type": "application/pdf",
        "format": "pdf",
        "parser_id": "datalab",
        "parser_name": "Datalab",
        "parser_version": "2",
        "completed_at": "2026-09-16T10:00:00+00:00",
    }
    assert "storage_key" not in repr(source)
    assert "documents/" not in repr(source)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["queued", "failed", "cancelled"])
async def test_snapshot_rejects_incomplete_parse_jobs(monkeypatch, status):
    _configure_store(
        monkeypatch,
        job=_parse_job(status=status),
        artifacts=[],
        objects={},
    )

    with pytest.raises(
        snapshots.TextbookSourceSnapshotError, match="not completed"
    ):
        await snapshots.freeze_parse_job_source(
            owner_user_id="parent-1",
            document_id=DOCUMENT_ID,
            producer_job_id=PRODUCER_JOB_ID,
            household_id=HOUSEHOLD_ID,
            textbook_slug="reading-explorer-3",
            version_id=VERSION_ID,
            position=1,
        )


@pytest.mark.asyncio
async def test_snapshot_rejects_missing_or_foreign_parse_jobs(monkeypatch):
    _configure_store(
        monkeypatch,
        job=None,
        artifacts=[],
        objects={},
    )

    with pytest.raises(snapshots.TextbookSourceSnapshotError, match="not found"):
        await snapshots.freeze_parse_job_source(
            owner_user_id="parent-1",
            document_id=DOCUMENT_ID,
            producer_job_id=PRODUCER_JOB_ID,
            household_id=HOUSEHOLD_ID,
            textbook_slug="reading-explorer-3",
            version_id=VERSION_ID,
            position=1,
        )


@pytest.mark.asyncio
async def test_snapshot_requires_exactly_one_markdown_primary_artifact(monkeypatch):
    primary = _artifact(
        artifact_id=PRIMARY_ARTIFACT_ID,
        artifact_kind="primary_document",
        relative_path="document.md",
        storage_key=f"documents/{DOCUMENT_ID}/document.md",
    )
    second_primary = _artifact(
        artifact_id=IMAGE_ARTIFACT_ID,
        artifact_kind="primary_document",
        relative_path="other.md",
        storage_key=f"documents/{DOCUMENT_ID}/other.md",
    )
    _configure_store(
        monkeypatch,
        job=_parse_job(),
        artifacts=[primary, second_primary],
        objects={},
    )

    with pytest.raises(snapshots.TextbookSourceSnapshotError, match="exactly one"):
        await snapshots.freeze_parse_job_source(
            owner_user_id="parent-1",
            document_id=DOCUMENT_ID,
            producer_job_id=PRODUCER_JOB_ID,
            household_id=HOUSEHOLD_ID,
            textbook_slug="reading-explorer-3",
            version_id=VERSION_ID,
            position=1,
        )


@pytest.mark.asyncio
async def test_snapshot_failure_deletes_only_exact_uploaded_keys(monkeypatch):
    primary = _artifact(
        artifact_id=PRIMARY_ARTIFACT_ID,
        artifact_kind="primary_document",
        relative_path="document.md",
        storage_key=f"documents/{DOCUMENT_ID}/document.md",
    )
    image = _artifact(
        artifact_id=IMAGE_ARTIFACT_ID,
        artifact_kind="embedded_image",
        relative_path="images/figure.png",
        storage_key=f"documents/{DOCUMENT_ID}/figure.png",
        format="png",
        media_type="image/png",
    )
    uploads, deleted = _configure_store(
        monkeypatch,
        job=_parse_job(),
        artifacts=[primary, image],
        objects={
            str(primary["storage_key"]): b"# Book\n",
            str(image["storage_key"]): b"image",
        },
        fail_manifest=True,
    )

    with pytest.raises(
        snapshots.TextbookSourceSnapshotError, match="could not be stored"
    ):
        await snapshots.freeze_parse_job_source(
            owner_user_id="parent-1",
            document_id=DOCUMENT_ID,
            producer_job_id=PRODUCER_JOB_ID,
            household_id=HOUSEHOLD_ID,
            textbook_slug="reading-explorer-3",
            version_id=VERSION_ID,
            position=1,
        )

    assert list(uploads) == [
        (
            f"education/{HOUSEHOLD_ID}/reading-explorer-3/{VERSION_ID}/"
            "source-bundles/01/document.md"
        ),
        (
            f"education/{HOUSEHOLD_ID}/reading-explorer-3/{VERSION_ID}/"
            "source-bundles/01/images/figure.png"
        ),
    ]
    assert deleted == list(reversed(list(uploads)))
