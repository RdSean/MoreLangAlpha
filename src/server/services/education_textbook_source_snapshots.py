"""Freeze completed document parse bundles into private textbook snapshots."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from src.config.settings import get_document_parsing_config
from src.server.database.documents import list_artifacts
from src.server.database.education_books import (
    create_textbook_with_initial_job,
    get_existing_textbook_for_source,
    get_owned_parse_job,
)
from src.server.database.session_lock import await_settled
from src.utils.storage import delete_object, get_bytes, upload_bytes


logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from src.server.services.education_book_structure import MoreToSkillsIdentity

_MARKDOWN_MEDIA_TYPE = "text/markdown"
_MARKDOWN_FORMATS = frozenset({"gfm", "markdown"})


class TextbookSourceSnapshotError(RuntimeError):
    """A completed parse bundle could not be safely frozen for textbook use."""


@dataclass(frozen=True, slots=True)
class FrozenTextbookSource:
    """Private snapshot result; written keys never leave the service boundary."""

    source: dict[str, Any]
    written_keys: tuple[str, ...]


def _uuid_component(value: str, label: str) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{label} must be a UUID") from exc


def build_snapshot_prefix(*, household_id: str, textbook_id: str) -> str:
    """Derive the sole private single-source book layout."""
    household = _uuid_component(household_id, "household_id")
    textbook = _uuid_component(textbook_id, "textbook_id")
    return f"education/{household}/textbooks/{textbook}/source/"


def _validated_relative_path(value: str) -> str:
    if not value or "\\" in value or "\x00" in value:
        raise TextbookSourceSnapshotError("A parse artifact has an unsafe path")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path == PurePosixPath(".")
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise TextbookSourceSnapshotError("A parse artifact has an unsafe path")
    return path.as_posix()


async def _read_object(key: str) -> bytes | None:
    return await asyncio.to_thread(get_bytes, key)


async def _write_object(
    key: str,
    content: bytes,
    content_type: str,
    *,
    max_size: int,
) -> bool:
    upload_task = asyncio.ensure_future(
        asyncio.to_thread(
            upload_bytes,
            key,
            content,
            content_type,
            max_size=max_size,
        )
    )
    return await await_settled(upload_task)


async def _delete_object(key: str) -> bool:
    return await asyncio.to_thread(delete_object, key)


async def cleanup_snapshot_objects(keys: Iterable[str]) -> None:
    """Delete only explicitly tracked snapshot keys, newest first."""
    tracked_keys = tuple(dict.fromkeys(keys))
    if not tracked_keys:
        return

    async def remove_keys() -> None:
        for key in reversed(tracked_keys):
            try:
                await _delete_object(key)
            except BaseException:
                logger.exception("Failed to remove textbook source snapshot object")

    cleanup_task = asyncio.create_task(remove_keys())
    try:
        await asyncio.shield(cleanup_task)
    except asyncio.CancelledError:
        await cleanup_task
        raise


async def freeze_parse_job_source(
    *,
    owner_user_id: str,
    document_id: str,
    producer_job_id: str,
    household_id: str,
    textbook_id: str,
) -> FrozenTextbookSource:
    """Copy one completed parse bundle and return only safe queueing metadata."""
    prefix = build_snapshot_prefix(
        household_id=household_id,
        textbook_id=textbook_id,
    )
    job = await get_owned_parse_job(
        owner_user_id=owner_user_id,
        producer_job_id=producer_job_id,
    )
    if not job or str(job.get("document_id") or "") != str(document_id):
        raise TextbookSourceSnapshotError("The parse job source was not found")
    if str(job.get("status") or "") != "completed":
        raise TextbookSourceSnapshotError("The parse job source is not completed")

    artifacts = await list_artifacts(
        owner_user_id=owner_user_id,
        document_id=document_id,
        producer_job_id=producer_job_id,
    )
    primary_artifacts = [
        artifact
        for artifact in artifacts
        if artifact.get("artifact_kind") == "primary_document"
    ]
    if len(primary_artifacts) != 1:
        raise TextbookSourceSnapshotError(
            "A parse job source must contain exactly one primary document"
        )
    primary = primary_artifacts[0]
    primary_artifact_id = str(primary.get("artifact_id") or "")
    if primary_artifact_id != str(job.get("primary_artifact_id") or ""):
        raise TextbookSourceSnapshotError(
            "The parse job primary artifact does not match its completed bundle"
        )
    primary_media_type = str(primary.get("media_type") or "").split(";", 1)[0].lower()
    if primary_media_type != _MARKDOWN_MEDIA_TYPE:
        raise TextbookSourceSnapshotError("The primary parse artifact must be Markdown")
    primary_format = str(primary.get("format") or "").strip().lower()
    if primary_format not in _MARKDOWN_FORMATS:
        raise TextbookSourceSnapshotError(
            "The primary parse artifact has an unsupported format"
        )

    validated_artifacts: list[dict[str, Any]] = []
    relative_paths: set[str] = set()
    for artifact in artifacts:
        relative_path = _validated_relative_path(
            str(artifact.get("relative_path") or "")
        )
        if relative_path in relative_paths:
            raise TextbookSourceSnapshotError(
                "A parse bundle contains duplicate artifact paths"
            )
        storage_key = str(artifact.get("storage_key") or "")
        if not storage_key:
            raise TextbookSourceSnapshotError("A parse artifact has no source object")
        relative_paths.add(relative_path)
        validated_artifacts.append(
            {
                **artifact,
                "relative_path": relative_path,
                "storage_key": storage_key,
            }
        )

    written_keys: list[str] = []
    manifest_artifacts: list[dict[str, Any]] = []
    reserved_destination_keys: set[str] = set()
    max_upload_bytes = get_document_parsing_config().max_upload_bytes
    try:
        for artifact in validated_artifacts:
            content = await _read_object(artifact["storage_key"])
            if content is None:
                raise TextbookSourceSnapshotError(
                    "A parse artifact is no longer available"
                )
            digest = hashlib.sha256(content).hexdigest()
            relative_path = artifact["relative_path"]
            destination_relative_path = f"artifacts/{relative_path}"
            destination_key = f"{prefix}{destination_relative_path}"
            if destination_key in reserved_destination_keys:
                raise TextbookSourceSnapshotError(
                    "A snapshot destination key would be reused"
                )
            reserved_destination_keys.add(destination_key)
            try:
                uploaded = await _write_object(
                    destination_key,
                    content,
                    str(artifact.get("media_type") or "application/octet-stream"),
                    max_size=max_upload_bytes,
                )
            except BaseException:
                await cleanup_snapshot_objects([destination_key])
                raise
            if not uploaded:
                raise TextbookSourceSnapshotError(
                    "A textbook source snapshot object could not be stored"
                )
            written_keys.append(destination_key)
            stored_content = await _read_object(destination_key)
            if (
                stored_content is None
                or hashlib.sha256(stored_content).hexdigest() != digest
            ):
                raise TextbookSourceSnapshotError(
                    "A textbook source snapshot object failed verification"
                )
            manifest_artifacts.append(
                {
                    "artifact_id": str(artifact.get("artifact_id") or ""),
                    "artifact_kind": str(artifact.get("artifact_kind") or ""),
                    "format": str(artifact.get("format") or ""),
                    "media_type": str(artifact.get("media_type") or ""),
                    "relative_path": destination_relative_path,
                    "sha256": digest,
                    "schema_name": artifact.get("schema_name"),
                    "schema_version": artifact.get("schema_version"),
                }
            )

        manifest_bytes = json.dumps(
            {
                "format": "langalpha-textbook-source-snapshot/v1",
                "document_id": str(document_id),
                "producer_job_id": str(producer_job_id),
                "primary_artifact_id": primary_artifact_id,
                "parser": {
                    "id": str(job.get("parser_id") or ""),
                    "name": str(job.get("parser_name") or ""),
                    "version": job.get("parser_version"),
                },
                "artifacts": manifest_artifacts,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        manifest_key = f"{prefix}manifest.json"
        if manifest_key in reserved_destination_keys:
            raise TextbookSourceSnapshotError(
                "A snapshot destination key would be reused"
            )
        reserved_destination_keys.add(manifest_key)
        try:
            uploaded_manifest = await _write_object(
                manifest_key,
                manifest_bytes,
                "application/json",
                max_size=max_upload_bytes,
            )
        except BaseException:
            await cleanup_snapshot_objects([manifest_key])
            raise
        if not uploaded_manifest:
            raise TextbookSourceSnapshotError(
                "A textbook source snapshot object could not be stored"
            )
        written_keys.append(manifest_key)
        stored_manifest = await _read_object(manifest_key)
        if (
            stored_manifest is None
            or hashlib.sha256(stored_manifest).hexdigest()
            != hashlib.sha256(manifest_bytes).hexdigest()
        ):
            raise TextbookSourceSnapshotError(
                "A textbook source snapshot object failed verification"
            )
    except BaseException as exc:
        await cleanup_snapshot_objects(written_keys)
        if isinstance(exc, (TextbookSourceSnapshotError, asyncio.CancelledError)):
            raise
        if isinstance(exc, Exception):
            raise TextbookSourceSnapshotError(
                "A textbook source snapshot could not be stored"
            ) from exc
        raise

    primary_manifest = next(
        (
            artifact
            for artifact in manifest_artifacts
            if artifact["artifact_id"] == primary_artifact_id
        ),
        None,
    )
    if primary_manifest is None:
        raise TextbookSourceSnapshotError("The primary parse artifact was not copied")
    asset_manifest = [
        {
            "artifact_id": artifact["artifact_id"],
            "artifact_kind": artifact["artifact_kind"],
            "format": artifact["format"],
            "media_type": artifact["media_type"],
            "relative_path": artifact["relative_path"].removeprefix("artifacts/"),
            "sha256": artifact["sha256"],
        }
        for artifact in manifest_artifacts
    ]
    return FrozenTextbookSource(
        source={
            "document_id": str(document_id),
            "producer_job_id": str(producer_job_id),
            "primary_artifact_id": primary_artifact_id,
            "primary_sha256": primary_manifest["sha256"],
            "filename": str(job.get("original_filename") or ""),
            "media_type": str(job.get("media_type") or ""),
            "format": str(job.get("document_format") or ""),
            "parser_id": str(job.get("parser_id") or ""),
            "parser_name": str(job.get("parser_name") or ""),
            "parser_version": job.get("parser_version"),
            "completed_at": job.get("completed_at"),
            "asset_manifest": asset_manifest,
        },
        written_keys=tuple(written_keys),
    )


async def _normalize_book_source(
    *,
    frozen: FrozenTextbookSource,
    document_id: str,
    parse_job_id: str,
    primary_artifact_id: str,
    prefix: str,
) -> FrozenTextbookSource:
    source = frozen.source
    manifest = list(source.get("asset_manifest") or [])
    primary = next(
        (
            entry
            for entry in manifest
            if str(entry.get("artifact_id") or "") == primary_artifact_id
        ),
        None,
    )
    if primary is None:
        raise TextbookSourceSnapshotError("The frozen primary artifact was not found")
    markdown_key = f"{prefix}artifacts/{primary['relative_path']}"
    markdown = await _read_object(markdown_key)
    if not markdown:
        raise TextbookSourceSnapshotError("The frozen primary artifact is unavailable")
    digest = hashlib.sha256(markdown).hexdigest()
    if digest != str(primary.get("sha256") or ""):
        raise TextbookSourceSnapshotError(
            "The frozen primary artifact failed verification"
        )

    def artifact_key(*names: str) -> str | None:
        for entry in manifest:
            relative = str(entry.get("relative_path") or "")
            if PurePosixPath(relative).name in names:
                return f"{prefix}artifacts/{relative}"
        return None

    normalized = {
        "document_id": document_id,
        "parse_job_id": parse_job_id,
        "primary_artifact_id": primary_artifact_id,
        "filename": source["filename"],
        "media_type": source["media_type"],
        "format": source["format"],
        "parser_id": source["parser_id"],
        "parser_name": source["parser_name"],
        "parser_version": source.get("parser_version"),
        "parse_completed_at": source["completed_at"],
        "content_sha256": digest,
        "size_bytes": len(markdown),
        "snapshot_prefix": prefix,
        "markdown_key": markdown_key,
        "blocks_key": artifact_key("blocks.json", "layout.json"),
        "report_key": artifact_key("report.json", "parse-report.json"),
        "asset_manifest": manifest,
        "snapshot": {
            "format": "langalpha-textbook-source-snapshot/v2",
            "manifest_key": f"{prefix}manifest.json",
        },
    }
    return FrozenTextbookSource(
        source=normalized,
        written_keys=frozen.written_keys,
    )


async def freeze_book_source(
    *,
    owner_user_id: str,
    parse_job_id: str,
    primary_artifact_id: str,
    household_id: str,
    textbook_id: str,
) -> FrozenTextbookSource:
    """Freeze one library bundle into the new single-source textbook layout."""

    job = await get_owned_parse_job(
        owner_user_id=owner_user_id,
        producer_job_id=parse_job_id,
    )
    if not job or str(job.get("status") or "") != "completed":
        raise TextbookSourceSnapshotError("The parse job source is not completed")
    if str(job.get("primary_artifact_id") or "") != primary_artifact_id:
        raise TextbookSourceSnapshotError(
            "The selected primary artifact does not belong to the parse job"
        )
    document_id = str(job.get("document_id") or "")
    if not document_id:
        raise TextbookSourceSnapshotError("The parse job source was not found")
    frozen = await freeze_parse_job_source(
        owner_user_id=owner_user_id,
        document_id=document_id,
        producer_job_id=parse_job_id,
        household_id=household_id,
        textbook_id=textbook_id,
    )
    prefix = build_snapshot_prefix(
        household_id=household_id,
        textbook_id=textbook_id,
    )
    try:
        return await _normalize_book_source(
            frozen=frozen,
            document_id=document_id,
            parse_job_id=parse_job_id,
            primary_artifact_id=primary_artifact_id,
            prefix=prefix,
        )
    except BaseException as exc:
        await cleanup_snapshot_objects(frozen.written_keys)
        if isinstance(exc, (TextbookSourceSnapshotError, asyncio.CancelledError)):
            raise
        if isinstance(exc, Exception):
            raise TextbookSourceSnapshotError(
                "The textbook source snapshot could not be normalized"
            ) from exc
        raise


async def create_textbook_from_library_source(
    *,
    parent_user_id: str,
    household_id: str,
    title: str,
    slug: str,
    parse_job_id: str,
    primary_artifact_id: str,
    idempotency_key: str,
    identity: MoreToSkillsIdentity,
) -> dict[str, Any]:
    """Preflight, freeze, and atomically create one source-bound textbook."""

    existing = await get_existing_textbook_for_source(
        parent_user_id=parent_user_id,
        household_id=household_id,
        source_parse_job_id=parse_job_id,
        source_primary_artifact_id=primary_artifact_id,
    )
    if existing is not None:
        return existing

    textbook_id = uuid4()
    frozen = await freeze_book_source(
        owner_user_id=parent_user_id,
        parse_job_id=parse_job_id,
        primary_artifact_id=primary_artifact_id,
        household_id=household_id,
        textbook_id=str(textbook_id),
    )
    try:
        created = await create_textbook_with_initial_job(
            textbook_id=textbook_id,
            parent_user_id=parent_user_id,
            household_id=household_id,
            title=title,
            slug=slug,
            source=frozen.source,
            idempotency_key=idempotency_key,
            identity=identity,
        )
    except BaseException as create_error:
        try:
            recovered = await get_existing_textbook_for_source(
                parent_user_id=parent_user_id,
                household_id=household_id,
                source_parse_job_id=parse_job_id,
                source_primary_artifact_id=primary_artifact_id,
            )
        except BaseException:
            raise create_error
        if recovered is None:
            await cleanup_snapshot_objects(frozen.written_keys)
            raise
        if UUID(str(recovered["textbook_id"])) != textbook_id:
            await cleanup_snapshot_objects(frozen.written_keys)
        if isinstance(create_error, asyncio.CancelledError):
            raise
        return recovered
    if UUID(str(created["textbook_id"])) != textbook_id:
        await cleanup_snapshot_objects(frozen.written_keys)
    return created
