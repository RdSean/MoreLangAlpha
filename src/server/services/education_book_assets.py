"""Validation for optional book-to-skill chapter assets."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any


BOOK_ASSET_FORMAT = "langalpha-managed-book-assets/v1"
MAX_BOOK_ASSET_FILES = 500
MAX_BOOK_ASSET_BYTES = 4 * 1024 * 1024
SUPPORT_FILE_NAMES = (
    "glossary.md",
    "patterns.md",
    "cheatsheet.md",
    "nutshell.md",
)
_CHAPTER_FILE_RE = re.compile(
    r"chapters/[0-9A-Za-z][0-9A-Za-z._-]*\.md"
)


class BookAssetValidationError(ValueError):
    """A chapter asset bundle violates the managed output contract."""


def _safe_relative_path(value: object, *, kind: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BookAssetValidationError(f"{kind} path must be a non-empty string")
    path = PurePosixPath(value.strip())
    if (
        path.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise BookAssetValidationError(f"{kind} path is invalid")
    return path.as_posix()


def validate_book_asset_manifest(candidate: object) -> dict[str, Any]:
    """Return a normalized manifest containing only safe Markdown paths."""
    if not isinstance(candidate, Mapping):
        raise BookAssetValidationError("Book asset manifest must be an object")
    if candidate.get("format") != BOOK_ASSET_FORMAT:
        raise BookAssetValidationError("Book asset manifest format is invalid")
    raw_chapters = candidate.get("chapter_files")
    if not isinstance(raw_chapters, list) or not raw_chapters:
        raise BookAssetValidationError(
            "Book asset manifest must contain chapter files"
        )
    chapter_files = sorted(
        {
            _safe_relative_path(value, kind="chapter")
            for value in raw_chapters
        }
    )
    if any(not _CHAPTER_FILE_RE.fullmatch(path) for path in chapter_files):
        raise BookAssetValidationError("Chapter asset path is invalid")
    raw_support_files = candidate.get("support_files", [])
    if not isinstance(raw_support_files, list):
        raise BookAssetValidationError("Support files must be a list")
    support_files = sorted(
        {
            _safe_relative_path(value, kind="support")
            for value in raw_support_files
        }
    )
    if any(path not in SUPPORT_FILE_NAMES for path in support_files):
        raise BookAssetValidationError("Support file path is invalid")
    all_files = chapter_files + support_files
    if len(all_files) > MAX_BOOK_ASSET_FILES:
        raise BookAssetValidationError("Book asset manifest is too large")
    if len(all_files) != len(set(all_files)):
        raise BookAssetValidationError("Book asset paths must be unique")
    return {
        "format": BOOK_ASSET_FORMAT,
        "chapter_files": chapter_files,
        "support_files": support_files,
    }


def expected_book_asset_files(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        [
            *manifest.get("chapter_files", []),
            *manifest.get("support_files", []),
        ]
    )


def validate_book_asset_content(
    manifest: Mapping[str, Any],
    outputs: Mapping[str, bytes],
) -> dict[str, Any]:
    """Build a service-owned manifest with hashes after download."""
    files: list[dict[str, Any]] = []
    for relative_path in expected_book_asset_files(manifest):
        content = outputs.get(relative_path)
        if not isinstance(content, bytes) or not content.strip():
            raise BookAssetValidationError(
                f"Book asset file is missing: {relative_path}"
            )
        if len(content) > MAX_BOOK_ASSET_BYTES:
            raise BookAssetValidationError(
                f"Book asset file is too large: {relative_path}"
            )
        files.append(
            {
                "path": relative_path,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
    return {
        "format": BOOK_ASSET_FORMAT,
        "files": files,
    }
