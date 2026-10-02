"""Layout-aware reads for immutable textbook source snapshots."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable, Mapping
from pathlib import PurePosixPath
from typing import Any

from src.utils.storage import get_bytes


class TextbookSnapshotReadError(RuntimeError):
    """A frozen snapshot object is missing or fails verification."""


class TextbookSnapshotDigestError(TextbookSnapshotReadError):
    """A frozen snapshot object is present but its digest does not match."""


def validated_snapshot_prefix(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("education/")
        or not value.endswith("/")
        or "\\" in value
        or "\x00" in value
    ):
        raise TextbookSnapshotReadError("A textbook snapshot prefix is invalid")
    raw_parts = value.rstrip("/").split("/")
    path = PurePosixPath(value.rstrip("/"))
    if (
        path.is_absolute()
        or any(part in {"", ".", ".."} for part in raw_parts)
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise TextbookSnapshotReadError("A textbook snapshot prefix is invalid")
    return value


def validated_snapshot_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise TextbookSnapshotReadError("A textbook snapshot path is invalid")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise TextbookSnapshotReadError("A textbook snapshot path is invalid")
    return path.as_posix()


async def read_snapshot_artifact_bytes(
    *,
    snapshot_prefix: str,
    relative_path: str,
    expected_sha256: str,
    max_bytes: int | None = None,
    read_bytes: Callable[[str], bytes | None] | None = None,
) -> tuple[bytes, str]:
    """Read only the canonical artifacts layout and verify the selected bytes."""
    prefix = validated_snapshot_prefix(snapshot_prefix)
    relative = validated_snapshot_relative_path(relative_path)
    current_relative = (
        relative if relative.startswith("artifacts/") else f"artifacts/{relative}"
    )
    key = f"{prefix}{current_relative}"
    content = await asyncio.to_thread(read_bytes or get_bytes, key)
    if content is None:
        raise TextbookSnapshotReadError("A textbook snapshot object is unavailable")
    if (
        not isinstance(content, bytes)
        or not content
        or (max_bytes is not None and len(content) > max_bytes)
    ):
        raise TextbookSnapshotReadError("A textbook snapshot object is invalid")
    if hashlib.sha256(content).hexdigest() != expected_sha256:
        raise TextbookSnapshotDigestError(
            "A textbook snapshot object digest does not match"
        )
    return content, key


def safe_asset_manifest_entry(value: Any) -> dict[str, str] | None:
    """Copy only the safe artifact metadata allowed into the database manifest."""
    if not isinstance(value, Mapping):
        return None
    fields = {
        field: str(value.get(field) or "")
        for field in (
            "artifact_id",
            "artifact_kind",
            "format",
            "media_type",
            "relative_path",
            "sha256",
        )
    }
    try:
        relative_path = validated_snapshot_relative_path(fields["relative_path"])
    except TextbookSnapshotReadError:
        return None
    fields["relative_path"] = relative_path.removeprefix("artifacts/")
    if not all(fields[field] for field in fields if field != "relative_path"):
        return None
    if len(fields["sha256"]) != 64 or any(
        character not in "0123456789abcdef" for character in fields["sha256"]
    ):
        return None
    return fields
