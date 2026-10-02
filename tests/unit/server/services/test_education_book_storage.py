"""Tests for immutable textbook material object handling."""

from __future__ import annotations

from hashlib import sha256
from unittest.mock import AsyncMock, call
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_read_material_bytes_verifies_owned_pointer_and_digest(
    monkeypatch,
) -> None:
    from src.server.services import education_book_storage as storage

    household_id = uuid4()
    textbook_id = uuid4()
    knowledge_point_id = uuid4()
    attempt_token = uuid4()
    content = b"# Lesson\n"
    digest = sha256(content).hexdigest()
    content_key = (
        f"education/{household_id}/textbooks/{textbook_id}/materials/"
        f"{knowledge_point_id}/attempts/{attempt_token}/{digest}.md"
    )
    read = AsyncMock(return_value=content)
    monkeypatch.setattr(storage, "_read", read)

    result = await storage.read_material_bytes(
        household_id=household_id,
        textbook_id=textbook_id,
        knowledge_point_id=knowledge_point_id,
        content_key=content_key,
        expected_sha256=digest,
        expected_size=len(content),
    )

    assert result == content
    read.assert_awaited_once_with(content_key)


@pytest.mark.asyncio
async def test_read_material_bytes_rejects_an_unowned_storage_key(monkeypatch) -> None:
    from src.server.services import education_book_storage as storage

    read = AsyncMock(return_value=b"# Lesson\n")
    monkeypatch.setattr(storage, "_read", read)

    with pytest.raises(storage.BookStorageError, match="pointer is invalid"):
        await storage.read_material_bytes(
            household_id=uuid4(),
            textbook_id=uuid4(),
            knowledge_point_id=uuid4(),
            content_key="education/another-household/textbooks/other/materials/file.md",
            expected_sha256="a" * 64,
            expected_size=9,
        )

    read.assert_not_awaited()


def test_source_snapshot_prefix_uses_textbook_identity_only() -> None:
    from src.server.services.education_textbook_source_snapshots import (
        build_snapshot_prefix,
    )

    household_id = uuid4()
    textbook_id = uuid4()

    assert (
        build_snapshot_prefix(
            household_id=str(household_id),
            textbook_id=str(textbook_id),
        )
        == f"education/{household_id}/textbooks/{textbook_id}/source/"
    )


@pytest.mark.asyncio
async def test_freeze_book_source_derives_document_and_new_storage_fields(
    monkeypatch,
) -> None:
    from src.server.services import education_textbook_source_snapshots as snapshots

    household_id = uuid4()
    textbook_id = uuid4()
    markdown = b"# Frozen book\n"
    markdown_sha256 = sha256(markdown).hexdigest()
    prefix = f"education/{household_id}/textbooks/{textbook_id}/source/"
    monkeypatch.setattr(
        snapshots,
        "get_owned_parse_job",
        AsyncMock(
            return_value={
                "document_id": "doc-1",
                "primary_artifact_id": "artifact-1",
                "status": "completed",
            }
        ),
    )
    frozen = snapshots.FrozenTextbookSource(
        source={
            "document_id": "doc-1",
            "producer_job_id": "parse-1",
            "primary_artifact_id": "artifact-1",
            "primary_sha256": markdown_sha256,
            "filename": "book.pdf",
            "media_type": "application/pdf",
            "format": "pdf",
            "parser_id": "datalab",
            "parser_name": "Datalab",
            "parser_version": "2",
            "completed_at": "2026-10-01T00:00:00+00:00",
            "asset_manifest": [
                {
                    "artifact_id": "artifact-1",
                    "artifact_kind": "primary_document",
                    "format": "gfm",
                    "media_type": "text/markdown",
                    "relative_path": "document.md",
                    "sha256": markdown_sha256,
                }
            ],
        },
        written_keys=(f"{prefix}artifacts/document.md", f"{prefix}manifest.json"),
    )
    freeze = AsyncMock(return_value=frozen)
    monkeypatch.setattr(snapshots, "freeze_parse_job_source", freeze)
    monkeypatch.setattr(snapshots, "_read_object", AsyncMock(return_value=markdown))

    result = await snapshots.freeze_book_source(
        owner_user_id="parent-1",
        parse_job_id="parse-1",
        primary_artifact_id="artifact-1",
        household_id=str(household_id),
        textbook_id=str(textbook_id),
    )

    freeze.assert_awaited_once_with(
        owner_user_id="parent-1",
        document_id="doc-1",
        producer_job_id="parse-1",
        household_id=str(household_id),
        textbook_id=str(textbook_id),
    )
    assert result.source["parse_job_id"] == "parse-1"
    assert result.source["content_sha256"] == markdown_sha256
    assert result.source["size_bytes"] == len(markdown)
    assert result.source["snapshot_prefix"] == prefix
    assert result.source["markdown_key"] == f"{prefix}artifacts/document.md"


@pytest.mark.asyncio
async def test_freeze_book_source_cleans_only_tracked_keys_after_normalization_failure(
    monkeypatch,
) -> None:
    from src.server.services import education_textbook_source_snapshots as snapshots

    household_id = uuid4()
    textbook_id = uuid4()
    prefix = f"education/{household_id}/textbooks/{textbook_id}/source/"
    written_keys = (f"{prefix}artifacts/document.md", f"{prefix}manifest.json")
    monkeypatch.setattr(
        snapshots,
        "get_owned_parse_job",
        AsyncMock(
            return_value={
                "document_id": "doc-1",
                "primary_artifact_id": "artifact-1",
                "status": "completed",
            }
        ),
    )
    monkeypatch.setattr(
        snapshots,
        "freeze_parse_job_source",
        AsyncMock(
            return_value=snapshots.FrozenTextbookSource(
                source={
                    "asset_manifest": [
                        {
                            "artifact_id": "artifact-1",
                            "relative_path": "document.md",
                            "sha256": "a" * 64,
                        }
                    ]
                },
                written_keys=written_keys,
            )
        ),
    )
    monkeypatch.setattr(snapshots, "_read_object", AsyncMock(return_value=None))
    cleanup = AsyncMock()
    monkeypatch.setattr(snapshots, "cleanup_snapshot_objects", cleanup)

    with pytest.raises(snapshots.TextbookSourceSnapshotError):
        await snapshots.freeze_book_source(
            owner_user_id="parent-1",
            parse_job_id="parse-1",
            primary_artifact_id="artifact-1",
            household_id=str(household_id),
            textbook_id=str(textbook_id),
        )

    cleanup.assert_awaited_once_with(written_keys)


@pytest.mark.asyncio
async def test_create_from_library_cleans_snapshot_when_source_race_returns_existing(
    monkeypatch,
) -> None:
    from src.server.services import education_textbook_source_snapshots as snapshots
    from src.server.services.education_book_structure import MoreToSkillsIdentity

    household_id = uuid4()
    reserved_id = uuid4()
    existing_id = uuid4()
    written_keys = (
        f"education/{household_id}/textbooks/{reserved_id}/source/manifest.json",
    )
    monkeypatch.setattr(snapshots, "uuid4", lambda: reserved_id)
    monkeypatch.setattr(
        snapshots,
        "get_existing_textbook_for_source",
        AsyncMock(return_value=None),
    )
    freeze = AsyncMock(
        return_value=snapshots.FrozenTextbookSource(
            source={"parse_job_id": "parse-1", "primary_artifact_id": "artifact-1"},
            written_keys=written_keys,
        )
    )
    monkeypatch.setattr(snapshots, "freeze_book_source", freeze)
    monkeypatch.setattr(
        snapshots,
        "create_textbook_with_initial_job",
        AsyncMock(
            return_value={
                "textbook_id": existing_id,
                "job_id": uuid4(),
                "item_id": uuid4(),
            }
        ),
    )
    cleanup = AsyncMock()
    monkeypatch.setattr(snapshots, "cleanup_snapshot_objects", cleanup)

    result = await snapshots.create_textbook_from_library_source(
        parent_user_id="parent-1",
        household_id=str(household_id),
        title="Book",
        slug="book",
        parse_job_id="parse-1",
        primary_artifact_id="artifact-1",
        idempotency_key="create-1",
        identity=MoreToSkillsIdentity(
            version="2.1.0",
            skill_sha256="a" * 64,
            schema_sha256="b" * 64,
        ),
    )

    freeze.assert_awaited_once_with(
        owner_user_id="parent-1",
        parse_job_id="parse-1",
        primary_artifact_id="artifact-1",
        household_id=str(household_id),
        textbook_id=str(reserved_id),
    )
    cleanup.assert_awaited_once_with(written_keys)
    assert result["textbook_id"] == existing_id


@pytest.mark.asyncio
async def test_create_from_library_preserves_snapshot_after_ambiguous_commit(
    monkeypatch,
) -> None:
    from src.server.services import education_textbook_source_snapshots as snapshots
    from src.server.services.education_book_structure import MoreToSkillsIdentity

    household_id = uuid4()
    reserved_id = uuid4()
    recovered = {
        "textbook_id": reserved_id,
        "job_id": uuid4(),
        "item_id": uuid4(),
    }
    written_keys = (
        f"education/{household_id}/textbooks/{reserved_id}/source/manifest.json",
    )
    monkeypatch.setattr(snapshots, "uuid4", lambda: reserved_id)
    lookup = AsyncMock(side_effect=[None, recovered])
    monkeypatch.setattr(snapshots, "get_existing_textbook_for_source", lookup)
    monkeypatch.setattr(
        snapshots,
        "freeze_book_source",
        AsyncMock(
            return_value=snapshots.FrozenTextbookSource(
                source={
                    "parse_job_id": "parse-1",
                    "primary_artifact_id": "artifact-1",
                },
                written_keys=written_keys,
            )
        ),
    )
    monkeypatch.setattr(
        snapshots,
        "create_textbook_with_initial_job",
        AsyncMock(side_effect=RuntimeError("connection lost after commit")),
    )
    cleanup = AsyncMock()
    monkeypatch.setattr(snapshots, "cleanup_snapshot_objects", cleanup)

    result = await snapshots.create_textbook_from_library_source(
        parent_user_id="parent-1",
        household_id=str(household_id),
        title="Book",
        slug="book",
        parse_job_id="parse-1",
        primary_artifact_id="artifact-1",
        idempotency_key="create-1",
        identity=MoreToSkillsIdentity(
            version="2.1.0",
            skill_sha256="a" * 64,
            schema_sha256="b" * 64,
        ),
    )

    assert result == recovered
    assert lookup.await_count == 2
    cleanup.assert_not_awaited()


@pytest.mark.asyncio
async def test_store_material_records_candidate_before_upload_and_finalizes(
    monkeypatch,
) -> None:
    from src.server.services import education_book_storage as storage

    calls: list[str] = []
    objects: dict[str, bytes] = {}

    async def record(**_kwargs) -> None:
        calls.append("record")

    async def upload(key, content, _content_type, *, max_size):
        assert len(content) <= max_size
        calls.append("upload")
        objects[key] = content
        return True

    async def read(key):
        calls.append("read")
        return objects.get(key)

    async def finalize(**kwargs):
        calls.append("finalize")
        return {"material_id": uuid4(), **kwargs}

    monkeypatch.setattr(storage, "record_candidate_object", record)
    context = {
        "household_id": uuid4(),
        "textbook_id": uuid4(),
        "knowledge_point_id": uuid4(),
    }
    monkeypatch.setattr(
        storage,
        "get_material_attempt_context",
        AsyncMock(return_value=context),
    )
    monkeypatch.setattr(storage, "_upload", upload)
    monkeypatch.setattr(storage, "_read", read)
    monkeypatch.setattr(storage, "finalize_material", finalize)

    result = await storage.store_material(
        item_id=uuid4(),
        attempt_token=uuid4(),
        markdown=b"# Lesson\n",
        generation_params={},
    )

    assert calls == ["record", "upload", "read", "finalize"]
    assert result["content_sha256"]
    assert result["content_key"].startswith("education/")


@pytest.mark.asyncio
async def test_store_material_does_not_finalize_after_upload_failure(
    monkeypatch,
) -> None:
    from src.server.services import education_book_storage as storage

    record = AsyncMock()
    finalize = AsyncMock()
    monkeypatch.setattr(storage, "record_candidate_object", record)
    monkeypatch.setattr(
        storage,
        "get_material_attempt_context",
        AsyncMock(
            return_value={
                "household_id": uuid4(),
                "textbook_id": uuid4(),
                "knowledge_point_id": uuid4(),
            }
        ),
    )
    monkeypatch.setattr(storage, "_upload", AsyncMock(return_value=False))
    monkeypatch.setattr(storage, "finalize_material", finalize)

    with pytest.raises(storage.BookStorageError, match="could not be stored"):
        await storage.store_material(
            item_id=uuid4(),
            attempt_token=uuid4(),
            markdown=b"# Lesson\n",
            generation_params={},
        )

    record.assert_awaited_once()
    finalize.assert_not_awaited()


@pytest.mark.asyncio
async def test_store_material_leaves_tracked_object_when_pg_finalize_fails(
    monkeypatch,
) -> None:
    from src.server.services import education_book_storage as storage

    deleted = AsyncMock()
    monkeypatch.setattr(storage, "record_candidate_object", AsyncMock())
    monkeypatch.setattr(
        storage,
        "get_material_attempt_context",
        AsyncMock(
            return_value={
                "household_id": uuid4(),
                "textbook_id": uuid4(),
                "knowledge_point_id": uuid4(),
            }
        ),
    )
    monkeypatch.setattr(storage, "_upload", AsyncMock(return_value=True))
    monkeypatch.setattr(storage, "_read", AsyncMock(return_value=b"# Lesson\n"))
    monkeypatch.setattr(
        storage,
        "finalize_material",
        AsyncMock(side_effect=RuntimeError("postgres unavailable")),
    )
    monkeypatch.setattr(storage, "_delete", deleted)

    with pytest.raises(RuntimeError, match="postgres unavailable"):
        await storage.store_material(
            item_id=uuid4(),
            attempt_token=uuid4(),
            markdown=b"# Lesson\n",
            generation_params={},
        )

    deleted.assert_not_awaited()


@pytest.mark.asyncio
async def test_cleanup_candidates_deletes_only_uncommitted_explicit_keys(monkeypatch):
    from src.server.services import education_book_storage as storage

    item_id = uuid4()
    attempt_token = uuid4()
    household_id = uuid4()
    textbook_id = uuid4()
    knowledge_point_id = uuid4()
    prefix = (
        f"education/{household_id}/textbooks/{textbook_id}/materials/"
        f"{knowledge_point_id}/attempts/{attempt_token}/"
    )
    committed = f"{prefix}committed.md"
    orphan = f"{prefix}orphan.md"
    invalid = "education/unrelated-homework/attachment.md"
    monkeypatch.setattr(
        storage,
        "get_book_item_candidate_cleanup_context",
        AsyncMock(
            return_value={
                "candidate_objects": [committed, orphan, invalid],
                "result_snapshot": {"content_key": committed},
                "kind": "material",
                "household_id": household_id,
                "textbook_id": textbook_id,
                "knowledge_point_id": knowledge_point_id,
            }
        ),
    )
    delete = AsyncMock(return_value=True)
    read = AsyncMock(return_value=b"candidate")
    forget = AsyncMock(return_value=True)
    monkeypatch.setattr(storage, "_delete", delete)
    monkeypatch.setattr(storage, "_read", read)
    monkeypatch.setattr(storage, "forget_book_candidate_object", forget)

    cleaned = await storage.cleanup_book_item_candidates(
        item_id=item_id,
        attempt_token=attempt_token,
    )

    assert cleaned == 2
    delete.assert_awaited_once_with(orphan)
    assert forget.await_args_list == [
        call(
            item_id=item_id,
            attempt_token=attempt_token,
            content_key=committed,
        ),
        call(
            item_id=item_id,
            attempt_token=attempt_token,
            content_key=orphan,
        ),
    ]


@pytest.mark.asyncio
async def test_cleanup_keeps_candidate_while_registered_upload_is_not_visible(
    monkeypatch,
):
    from src.server.services import education_book_storage as storage

    item_id = uuid4()
    attempt_token = uuid4()
    household_id = uuid4()
    textbook_id = uuid4()
    knowledge_point_id = uuid4()
    candidate = (
        f"education/{household_id}/textbooks/{textbook_id}/materials/"
        f"{knowledge_point_id}/attempts/{attempt_token}/pending.md"
    )
    monkeypatch.setattr(
        storage,
        "get_book_item_candidate_cleanup_context",
        AsyncMock(
            return_value={
                "candidate_objects": [candidate],
                "result_snapshot": None,
                "kind": "material",
                "household_id": household_id,
                "textbook_id": textbook_id,
                "knowledge_point_id": knowledge_point_id,
            }
        ),
    )
    monkeypatch.setattr(storage, "_read", AsyncMock(return_value=None))
    delete = AsyncMock(return_value=True)
    forget = AsyncMock(return_value=True)
    monkeypatch.setattr(storage, "_delete", delete)
    monkeypatch.setattr(storage, "forget_book_candidate_object", forget)

    cleaned = await storage.cleanup_book_item_candidates(
        item_id=item_id,
        attempt_token=attempt_token,
    )

    assert cleaned == 0
    delete.assert_not_awaited()
    forget.assert_not_awaited()
