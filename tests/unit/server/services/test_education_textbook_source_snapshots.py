"""Immutable snapshot contracts for completed document-library parse bundles."""

from __future__ import annotations

import asyncio
from hashlib import sha256
import json
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.server.services import education_textbook_source_snapshots as snapshots


HOUSEHOLD_ID = "6eebf7fb-9579-4c5d-825a-2e595b7f1b18"
TEXTBOOK_ID = "f5761267-11d1-4977-8107-e2671c99a2f0"
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
        "source_sha256": "f" * 64,
        "source_size_bytes": 1024,
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
    monkeypatch.setattr(snapshots, "get_owned_parse_job", AsyncMock(return_value=job))
    monkeypatch.setattr(snapshots, "list_artifacts", AsyncMock(return_value=artifacts))

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


def test_snapshot_prefix_rejects_legacy_version_layout():
    with pytest.raises(TypeError):
        snapshots.build_snapshot_prefix(
            household_id=HOUSEHOLD_ID,
            textbook_slug="reading-explorer-3",
            version_id=TEXTBOOK_ID,
            position=1,
        )


def test_snapshot_prefix_uses_the_single_source_book_identity():
    prefix = snapshots.build_snapshot_prefix(
        household_id=HOUSEHOLD_ID,
        textbook_id=TEXTBOOK_ID,
    )

    assert prefix == (f"education/{HOUSEHOLD_ID}/textbooks/{TEXTBOOK_ID}/source/")


@pytest.mark.asyncio
async def test_acceptance_pins_metadata_without_any_object_io(monkeypatch):
    from src.server.services.education_book_structure import MoreToSkillsIdentity

    primary = _artifact(
        artifact_id=PRIMARY_ARTIFACT_ID,
        artifact_kind="primary_document",
        relative_path="document.md",
        storage_key=f"documents/{DOCUMENT_ID}/artifacts/{PRODUCER_JOB_ID}/document.md",
    )
    monkeypatch.setattr(
        snapshots, "get_owned_parse_job", AsyncMock(return_value=_parse_job())
    )
    monkeypatch.setattr(snapshots, "list_artifacts", AsyncMock(return_value=[primary]))
    forbidden_read = AsyncMock(side_effect=AssertionError("request read object bytes"))
    forbidden_write = AsyncMock(side_effect=AssertionError("request uploaded bytes"))
    monkeypatch.setattr(snapshots, "_read_object", forbidden_read)
    monkeypatch.setattr(snapshots, "_write_object", forbidden_write)
    create = AsyncMock(
        return_value={
            "textbook_id": TEXTBOOK_ID,
            "job_id": TEXTBOOK_ID,
            "acceptance": "accepted_new",
        }
    )
    monkeypatch.setattr(snapshots, "create_textbook_with_initial_job", create)
    result = await snapshots.create_textbook_from_library_source(
        parent_user_id="parent-1",
        household_id=HOUSEHOLD_ID,
        title="Book",
        slug="book",
        parse_job_id=PRODUCER_JOB_ID,
        primary_artifact_id=PRIMARY_ARTIFACT_ID,
        idempotency_key="fast-accept",
        identity=MoreToSkillsIdentity(
            version="2", skill_sha256="a" * 64, schema_sha256="b" * 64
        ),
    )
    assert result["acceptance"] == "accepted_new"
    source = create.await_args.kwargs["source"]
    assert source["source_status"] == "pending"
    assert source.get("markdown_key") is None
    assert source.get("content_sha256") is None
    assert source["selected_source"]["content_sha256"] == "f" * 64
    assert (
        source["preparation_descriptor"]["artifacts"][0]["artifact_id"]
        == PRIMARY_ARTIFACT_ID
    )
    forbidden_read.assert_not_awaited()
    forbidden_write.assert_not_awaited()


@pytest.mark.asyncio
async def test_background_freeze_uses_pinned_bundle_and_reports_only_readback_verified_resources(
    monkeypatch,
):
    from uuid import UUID

    content = b"# Fixed book\n"
    artifact = _artifact(
        artifact_id=PRIMARY_ARTIFACT_ID,
        artifact_kind="primary_document",
        relative_path="document.md",
        storage_key=f"documents/{DOCUMENT_ID}/artifacts/{PRODUCER_JOB_ID}/document.md",
    )
    artifact["metadata"] = {"sha256": sha256(content).hexdigest()}
    uploads, _ = _configure_store(
        monkeypatch,
        job=_parse_job(),
        artifacts=[artifact],
        objects={str(artifact["storage_key"]): content},
    )
    pinned = await snapshots.preflight_book_source(
        owner_user_id="parent-1",
        parse_job_id=PRODUCER_JOB_ID,
        primary_artifact_id=PRIMARY_ARTIFACT_ID,
    )
    lookup = AsyncMock(side_effect=AssertionError("background reread latest bundle"))
    monkeypatch.setattr(snapshots, "get_owned_parse_job", lookup)
    monkeypatch.setattr(snapshots, "list_artifacts", lookup)
    token = UUID(int=1)
    candidates: list[str] = []
    progress: list[tuple[int, int]] = []

    async def before_write(key):
        assert key not in uploads
        candidates.append(key)

    async def verified(count, total):
        assert len(uploads) == count
        progress.append((count, total))

    frozen = await snapshots.freeze_book_source(
        owner_user_id="parent-1",
        parse_job_id=PRODUCER_JOB_ID,
        primary_artifact_id=PRIMARY_ARTIFACT_ID,
        household_id=HOUSEHOLD_ID,
        textbook_id=TEXTBOOK_ID,
        pinned_bundle=pinned["preparation_descriptor"],
        attempt_token=token,
        before_write=before_write,
        on_verified=verified,
    )
    assert progress == [(1, 1)]
    assert candidates == list(uploads)
    assert f"/source/attempts/{token}/" in frozen.source["markdown_key"]
    assert frozen.source["content_sha256"] == sha256(content).hexdigest()
    lookup.assert_not_awaited()


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
        textbook_id=TEXTBOOK_ID,
    )

    prefix = snapshots.build_snapshot_prefix(
        household_id=HOUSEHOLD_ID,
        textbook_id=TEXTBOOK_ID,
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
        "asset_manifest": [
            {
                "artifact_id": PRIMARY_ARTIFACT_ID,
                "artifact_kind": "primary_document",
                "format": "gfm",
                "media_type": "text/markdown",
                "relative_path": "document.md",
                "sha256": sha256(primary_bytes).hexdigest(),
            },
            {
                "artifact_id": IMAGE_ARTIFACT_ID,
                "artifact_kind": "embedded_image",
                "format": "png",
                "media_type": "image/png",
                "relative_path": "images/figure.png",
                "sha256": sha256(image_bytes).hexdigest(),
            },
        ],
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

    with pytest.raises(snapshots.TextbookSourceSnapshotError, match="not completed"):
        await snapshots.freeze_parse_job_source(
            owner_user_id="parent-1",
            document_id=DOCUMENT_ID,
            producer_job_id=PRODUCER_JOB_ID,
            household_id=HOUSEHOLD_ID,
            textbook_id=TEXTBOOK_ID,
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
            textbook_id=TEXTBOOK_ID,
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
            textbook_id=TEXTBOOK_ID,
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

    with pytest.raises(snapshots.TextbookSourceSnapshotError, match="exactly one"):
        await snapshots.freeze_parse_job_source(
            owner_user_id="parent-1",
            document_id=DOCUMENT_ID,
            producer_job_id=PRODUCER_JOB_ID,
            household_id=HOUSEHOLD_ID,
            textbook_id=TEXTBOOK_ID,
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
            textbook_id=TEXTBOOK_ID,
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
        textbook_id=TEXTBOOK_ID,
    )

    prefix = snapshots.build_snapshot_prefix(
        household_id=HOUSEHOLD_ID,
        textbook_id=TEXTBOOK_ID,
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
        textbook_id=TEXTBOOK_ID,
    )
    destination_key = f"{prefix}artifacts/document.md"
    uploads, deleted = _configure_store(
        monkeypatch,
        job=_parse_job(),
        artifacts=[primary],
        objects={str(primary["storage_key"]): b"# Book\n"},
        readback_overrides={destination_key: b"tampered"},
    )

    with pytest.raises(snapshots.TextbookSourceSnapshotError, match="verification"):
        await snapshots.freeze_parse_job_source(
            owner_user_id="parent-1",
            document_id=DOCUMENT_ID,
            producer_job_id=PRODUCER_JOB_ID,
            household_id=HOUSEHOLD_ID,
            textbook_id=TEXTBOOK_ID,
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
        textbook_id=TEXTBOOK_ID,
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
            textbook_id=TEXTBOOK_ID,
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
            textbook_id=TEXTBOOK_ID,
        )

    assert list(uploads) == [
        (
            f"education/{HOUSEHOLD_ID}/textbooks/{TEXTBOOK_ID}/source/artifacts/document.md"
        )
    ]
    assert deleted == [
        (
            f"education/{HOUSEHOLD_ID}/textbooks/{TEXTBOOK_ID}/source/artifacts/images/figure.png"
        ),
        next(iter(uploads)),
    ]


@pytest.mark.asyncio
async def test_snapshot_cancellation_waits_for_blocked_upload_then_deletes_key(
    monkeypatch,
):
    primary_bytes = b"# Book\n"
    primary = _artifact(
        artifact_id=PRIMARY_ARTIFACT_ID,
        artifact_kind="primary_document",
        relative_path="document.md",
        storage_key=f"documents/{DOCUMENT_ID}/document.md",
    )
    prefix = snapshots.build_snapshot_prefix(
        household_id=HOUSEHOLD_ID,
        textbook_id=TEXTBOOK_ID,
    )
    destination_key = f"{prefix}artifacts/document.md"
    started = threading.Event()
    release = threading.Event()
    finished = threading.Event()
    deleted: list[str] = []

    def blocking_upload(
        key: str,
        data: bytes,
        content_type: str | None = None,
        max_size: int | None = None,
    ) -> bool:
        started.set()
        release.wait(timeout=2)
        finished.set()
        return True

    def record_delete(key: str) -> bool:
        deleted.append(key)
        return True

    monkeypatch.setattr(
        snapshots,
        "get_owned_parse_job",
        AsyncMock(return_value=_parse_job()),
    )
    monkeypatch.setattr(
        snapshots,
        "list_artifacts",
        AsyncMock(return_value=[primary]),
    )
    monkeypatch.setattr(
        snapshots, "_read_object", AsyncMock(return_value=primary_bytes)
    )
    monkeypatch.setattr(snapshots, "upload_bytes", blocking_upload)
    monkeypatch.setattr(snapshots, "delete_object", record_delete)
    monkeypatch.setattr(
        snapshots,
        "get_document_parsing_config",
        lambda: SimpleNamespace(max_upload_bytes=1024),
    )

    task = asyncio.create_task(
        snapshots.freeze_parse_job_source(
            owner_user_id="parent-1",
            document_id=DOCUMENT_ID,
            producer_job_id=PRODUCER_JOB_ID,
            household_id=HOUSEHOLD_ID,
            textbook_id=TEXTBOOK_ID,
        )
    )
    assert await asyncio.to_thread(started.wait, 1)
    task.cancel()
    await asyncio.sleep(0)
    release.set()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert await asyncio.to_thread(finished.wait, 1)
    assert deleted == [destination_key]


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
            textbook_id=TEXTBOOK_ID,
        )

    assert list(uploads) == [
        (
            f"education/{HOUSEHOLD_ID}/textbooks/{TEXTBOOK_ID}/source/artifacts/document.md"
        ),
        (
            f"education/{HOUSEHOLD_ID}/textbooks/{TEXTBOOK_ID}/source/artifacts/images/figure.png"
        ),
    ]
    assert deleted == list(reversed(list(uploads)))
