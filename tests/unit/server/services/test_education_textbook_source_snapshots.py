"""Immutable snapshot contracts for completed document-library parse bundles."""

from __future__ import annotations

import asyncio
from hashlib import sha256
import json
from types import SimpleNamespace
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
    readback_overrides: dict[str, bytes | None] | None = None,
    max_upload_bytes: int | None = None,
    captured_max_sizes: list[int] | None = None,
    cancel_write_number: int | None = None,
) -> tuple[dict[str, bytes], list[str]]:
    uploads: dict[str, bytes] = {}
    deleted: list[str] = []
    write_count = 0
    monkeypatch.setattr(
        snapshots, "get_owned_parse_job", AsyncMock(return_value=job)
    )
    monkeypatch.setattr(
        snapshots, "list_artifacts", AsyncMock(return_value=artifacts)
    )

    async def read_object(key: str) -> bytes | None:
        if readback_overrides is not None and key in readback_overrides:
            return readback_overrides[key]
        return objects.get(key)

    async def write_object(
        key: str,
        content: bytes,
        _content_type: str,
        *,
        max_size: int,
    ) -> bool:
        nonlocal write_count
        write_count += 1
        if captured_max_sizes is not None:
            captured_max_sizes.append(max_size)
        if cancel_write_number == write_count:
            raise asyncio.CancelledError
        if max_upload_bytes is not None and len(content) > max_upload_bytes:
            return False
        if fail_manifest and key.endswith("/manifest.json"):
            return False
        uploads[key] = content
        objects[key] = content
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
        f"education/{HOUSEHOLD_ID}/reading-explorer-3/source-bundles/"
        f"{VERSION_ID}/01/"
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

    frozen = await snapshots.freeze_parse_job_source(
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
        f"{prefix}artifacts/document.md",
        f"{prefix}artifacts/images/figure.png",
        f"{prefix}manifest.json",
    }
    assert frozen.written_keys == tuple(uploads)
    manifest = json.loads(uploads[f"{prefix}manifest.json"])
    assert [entry["relative_path"] for entry in manifest["artifacts"]] == [
        "artifacts/document.md",
        "artifacts/images/figure.png",
    ]
    assert manifest["artifacts"][0]["sha256"] == sha256(primary_bytes).hexdigest()
    assert manifest["artifacts"][1]["sha256"] == sha256(image_bytes).hexdigest()
    source = frozen.source
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
    assert "storage_key" not in repr(frozen.written_keys)
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
async def test_snapshot_rejects_a_bundle_without_a_primary_artifact(monkeypatch):
    image = _artifact(
        artifact_id=IMAGE_ARTIFACT_ID,
        artifact_kind="embedded_image",
        relative_path="images/figure.png",
        storage_key=f"documents/{DOCUMENT_ID}/images/figure.png",
        format="png",
        media_type="image/png",
    )
    _configure_store(
        monkeypatch,
        job=_parse_job(),
        artifacts=[image],
        objects={},
    )

    with pytest.raises(
        snapshots.TextbookSourceSnapshotError, match="exactly one"
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
async def test_snapshot_rejects_unsupported_primary_format(monkeypatch):
    primary = _artifact(
        artifact_id=PRIMARY_ARTIFACT_ID,
        artifact_kind="primary_document",
        relative_path="document.md",
        storage_key=f"documents/{DOCUMENT_ID}/document.md",
        format="pdf",
    )
    _configure_store(
        monkeypatch,
        job=_parse_job(),
        artifacts=[primary],
        objects={},
    )

    with pytest.raises(snapshots.TextbookSourceSnapshotError, match="format"):
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
async def test_snapshot_preserves_a_source_manifest_under_artifacts(monkeypatch):
    primary_bytes = b"# Book\n"
    source_manifest_bytes = b'{"source":"manifest"}'
    primary = _artifact(
        artifact_id=PRIMARY_ARTIFACT_ID,
        artifact_kind="primary_document",
        relative_path="document.md",
        storage_key=f"documents/{DOCUMENT_ID}/document.md",
    )
    source_manifest = _artifact(
        artifact_id=IMAGE_ARTIFACT_ID,
        artifact_kind="manifest",
        relative_path="manifest.json",
        storage_key=f"documents/{DOCUMENT_ID}/manifest.json",
        format="json",
        media_type="application/json",
    )
    uploads, _deleted = _configure_store(
        monkeypatch,
        job=_parse_job(),
        artifacts=[primary, source_manifest],
        objects={
            str(primary["storage_key"]): primary_bytes,
            str(source_manifest["storage_key"]): source_manifest_bytes,
        },
    )

    frozen = await snapshots.freeze_parse_job_source(
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
    assert f"{prefix}artifacts/manifest.json" in uploads
    assert f"{prefix}manifest.json" in uploads
    manifest = json.loads(uploads[f"{prefix}manifest.json"])
    assert [entry["relative_path"] for entry in manifest["artifacts"]] == [
        "artifacts/document.md",
        "artifacts/manifest.json",
    ]
    assert frozen.source["primary_sha256"] == sha256(primary_bytes).hexdigest()


@pytest.mark.asyncio
async def test_snapshot_failure_when_destination_hash_differs_cleans_exact_key(
    monkeypatch,
):
    primary = _artifact(
        artifact_id=PRIMARY_ARTIFACT_ID,
        artifact_kind="primary_document",
        relative_path="document.md",
        storage_key=f"documents/{DOCUMENT_ID}/document.md",
    )
    prefix = snapshots.build_snapshot_prefix(
        household_id=HOUSEHOLD_ID,
        textbook_slug="reading-explorer-3",
        version_id=VERSION_ID,
        position=1,
    )
    destination_key = f"{prefix}artifacts/document.md"
    uploads, deleted = _configure_store(
        monkeypatch,
        job=_parse_job(),
        artifacts=[primary],
        objects={str(primary["storage_key"]): b"# Book\n"},
        readback_overrides={destination_key: b"tampered"},
    )

    with pytest.raises(
        snapshots.TextbookSourceSnapshotError, match="verification"
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

    assert list(uploads) == [destination_key]
    assert deleted == [destination_key]


@pytest.mark.asyncio
async def test_snapshot_upload_just_below_document_cap_succeeds(monkeypatch):
    cap = 1024
    primary = _artifact(
        artifact_id=PRIMARY_ARTIFACT_ID,
        artifact_kind="primary_document",
        relative_path="document.md",
        storage_key=f"documents/{DOCUMENT_ID}/document.md",
    )
    max_sizes: list[int] = []
    uploads, _deleted = _configure_store(
        monkeypatch,
        job=_parse_job(),
        artifacts=[primary],
        objects={str(primary["storage_key"]): b"x" * (cap - 1)},
        max_upload_bytes=cap,
        captured_max_sizes=max_sizes,
    )
    monkeypatch.setattr(
        snapshots,
        "get_document_parsing_config",
        lambda: SimpleNamespace(max_upload_bytes=cap),
    )

    await snapshots.freeze_parse_job_source(
        owner_user_id="parent-1",
        document_id=DOCUMENT_ID,
        producer_job_id=PRODUCER_JOB_ID,
        household_id=HOUSEHOLD_ID,
        textbook_slug="reading-explorer-3",
        version_id=VERSION_ID,
        position=1,
    )

    assert uploads
    assert max_sizes and set(max_sizes) == {cap}


@pytest.mark.asyncio
async def test_snapshot_upload_above_document_cap_is_rejected(monkeypatch):
    cap = 1024
    primary = _artifact(
        artifact_id=PRIMARY_ARTIFACT_ID,
        artifact_kind="primary_document",
        relative_path="document.md",
        storage_key=f"documents/{DOCUMENT_ID}/document.md",
    )
    max_sizes: list[int] = []
    uploads, _deleted = _configure_store(
        monkeypatch,
        job=_parse_job(),
        artifacts=[primary],
        objects={str(primary["storage_key"]): b"x" * (cap + 1)},
        max_upload_bytes=cap,
        captured_max_sizes=max_sizes,
    )
    monkeypatch.setattr(
        snapshots,
        "get_document_parsing_config",
        lambda: SimpleNamespace(max_upload_bytes=cap),
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

    assert uploads == {}
    assert max_sizes == [cap]


@pytest.mark.asyncio
async def test_snapshot_cancellation_cleans_the_completed_write(monkeypatch):
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
        cancel_write_number=2,
    )
    monkeypatch.setattr(
        snapshots,
        "get_document_parsing_config",
        lambda: SimpleNamespace(max_upload_bytes=1024),
    )

    with pytest.raises(asyncio.CancelledError):
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
            f"education/{HOUSEHOLD_ID}/reading-explorer-3/source-bundles/"
            f"{VERSION_ID}/01/artifacts/document.md"
        )
    ]
    assert deleted == list(uploads)


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
            f"education/{HOUSEHOLD_ID}/reading-explorer-3/source-bundles/"
            f"{VERSION_ID}/01/artifacts/document.md"
        ),
        (
            f"education/{HOUSEHOLD_ID}/reading-explorer-3/source-bundles/"
            f"{VERSION_ID}/01/artifacts/images/figure.png"
        ),
    ]
    assert deleted == list(reversed(list(uploads)))
