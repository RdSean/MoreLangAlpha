"""Freeze completed document parse bundles into private textbook snapshots."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID

from src.server.database.documents import list_artifacts
from src.server.database.education_textbooks import get_owned_parse_job
from src.utils.storage import delete_object, get_bytes, upload_bytes


logger = logging.getLogger(__name__)

_SAFE_COMPONENT = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._-]{0,254}$")
_MARKDOWN_MEDIA_TYPE = "text/markdown"


class TextbookSourceSnapshotError(RuntimeError):
    """A completed parse bundle could not be safely frozen for textbook use."""


def _uuid_component(value: str, label: str) -> str:
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError(f"{label} must be a UUID") from exc


def _safe_component(value: str, label: str) -> str:
    if ".." in value or not _SAFE_COMPONENT.fullmatch(value):
        raise ValueError(f"{label} must be a safe path component")
    return value


def build_snapshot_prefix(
    *,
    household_id: str,
    textbook_slug: str,
    version_id: str,
    position: int,
) -> str:
    """Derive the only valid immutable prefix for one selected source bundle."""
    household = _uuid_component(household_id, "household_id")
    version = _uuid_component(version_id, "version_id")
    slug = _safe_component(textbook_slug, "textbook_slug")
    if position < 1 or position > 99:
        raise ValueError("position must be between 1 and 99")
    return (
        f"education/{household}/{slug}/{version}/"
        f"source-bundles/{position:02d}/"
    )


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


async def _write_object(key: str, content: bytes, content_type: str) -> bool:
    return await asyncio.to_thread(upload_bytes, key, content, content_type)


async def _delete_object(key: str) -> bool:
    return await asyncio.to_thread(delete_object, key)


async def freeze_parse_job_source(
    *,
    owner_user_id: str,
    document_id: str,
    producer_job_id: str,
    household_id: str,
    textbook_slug: str,
    version_id: str,
    position: int,
) -> dict[str, Any]:
    """Copy one completed parse bundle and return only safe queueing metadata."""
    prefix = build_snapshot_prefix(
        household_id=household_id,
        textbook_slug=textbook_slug,
        version_id=version_id,
        position=position,
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
        raise TextbookSourceSnapshotError(
            "The primary parse artifact must be Markdown"
        )

    validated_artifacts: list[dict[str, Any]] = []
    relative_paths: set[str] = set()
    for artifact in artifacts:
        relative_path = _validated_relative_path(str(artifact.get("relative_path") or ""))
        if relative_path == "manifest.json" or relative_path in relative_paths:
            raise TextbookSourceSnapshotError(
                "A parse artifact would overwrite the snapshot manifest"
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
    try:
        for artifact in validated_artifacts:
            content = await _read_object(artifact["storage_key"])
            if content is None:
                raise TextbookSourceSnapshotError(
                    "A parse artifact is no longer available"
                )
            digest = hashlib.sha256(content).hexdigest()
            relative_path = artifact["relative_path"]
            destination_key = f"{prefix}{relative_path}"
            if not await _write_object(
                destination_key,
                content,
                str(artifact.get("media_type") or "application/octet-stream"),
            ):
                raise TextbookSourceSnapshotError(
                    "A textbook source snapshot object could not be stored"
                )
            written_keys.append(destination_key)
            manifest_artifacts.append(
                {
                    "artifact_id": str(artifact.get("artifact_id") or ""),
                    "artifact_kind": str(artifact.get("artifact_kind") or ""),
                    "format": str(artifact.get("format") or ""),
                    "media_type": str(artifact.get("media_type") or ""),
                    "relative_path": relative_path,
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
        if not await _write_object(
            manifest_key, manifest_bytes, "application/json"
        ):
            raise TextbookSourceSnapshotError(
                "A textbook source snapshot object could not be stored"
            )
        written_keys.append(manifest_key)
    except Exception as exc:
        for key in reversed(written_keys):
            try:
                await _delete_object(key)
            except Exception:
                logger.exception("Failed to remove incomplete textbook source snapshot")
        if isinstance(exc, TextbookSourceSnapshotError):
            raise
        raise TextbookSourceSnapshotError(
            "A textbook source snapshot could not be stored"
        ) from exc

    primary_manifest = next(
        (
            artifact
            for artifact in manifest_artifacts
            if artifact["artifact_id"] == primary_artifact_id
        ),
        None,
    )
    if primary_manifest is None:
        raise TextbookSourceSnapshotError(
            "The primary parse artifact was not copied"
        )
    return {
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
    }
