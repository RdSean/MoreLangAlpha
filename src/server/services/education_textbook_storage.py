"""Recoverable object bundles for processed family textbook versions."""

import asyncio
import hashlib
import json
import re
from typing import Any

from src.utils.storage import get_bytes, upload_bytes


class TextbookBundleStorageError(RuntimeError):
    """A private textbook artifact could not be stored."""


def _safe_component(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^0-9A-Za-z._-]+", "-", value.strip()).strip(".-").lower()
    return normalized[:80] or fallback


def textbook_bundle_prefix(job: dict[str, Any]) -> str:
    return "education/{}/{}/v{}".format(
        job["household_id"],
        _safe_component(job["slug"], "textbook"),
        job["version_sequence"],
    )


async def _put(key: str, content: bytes, content_type: str) -> None:
    if not await asyncio.to_thread(upload_bytes, key, content, content_type):
        raise TextbookBundleStorageError(f"Could not store textbook artifact: {key}")


async def write_textbook_content_bundle(job: dict[str, Any], package: dict[str, Any]) -> str:
    """Persist extracted Markdown and source snapshots for textbook processing."""
    prefix = textbook_bundle_prefix(job)
    source_entries: list[dict[str, str]] = []
    chapter_entries: list[dict[str, Any]] = []
    for chapter in package["chapters"]:
        relative_path = f"chapters/{chapter['slug']}.md"
        await _put(
            chapter["markdown_key"],
            chapter["markdown"].encode(),
            "text/markdown; charset=utf-8",
        )
        chapter_entries.append(
            {
                "position": chapter["position"],
                "slug": chapter["slug"],
                "title": chapter["title"],
                "page_start": chapter.get("page_start"),
                "page_end": chapter.get("page_end"),
                "path": relative_path,
                "sha256": hashlib.sha256(chapter["markdown"].encode()).hexdigest(),
            }
        )
    for source in job["sources"]:
        filename = _safe_component(source["original_filename"], "source")
        relative_path = f"sources/{source['asset_id']}-{filename}"
        source_bytes = await asyncio.to_thread(get_bytes, source["storage_key"])
        if source_bytes is None:
            raise TextbookBundleStorageError(
                "A frozen textbook source is no longer available"
            )
        await _put(
            f"{prefix}/{relative_path}", source_bytes, source["content_type"]
        )
        source_entries.append(
            {
                "asset_id": str(source["asset_id"]),
                "filename": source["original_filename"],
                "path": relative_path,
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
            }
        )
    readme = "# {}\n\n版本：v{}\n\n本目录保存冻结教材内容。后续结构与知识点课程由教材库基于 `book-to-skill` 生成。\n".format(
        job["title"], job["version_sequence"]
    )
    manifest = {
        "format": "langalpha-family-textbook-content/v1",
        "title": job["title"],
        "version": job["version_sequence"],
        "extractor": package["extractor"],
        "sources": source_entries,
        "chapters": chapter_entries,
    }
    await _put(f"{prefix}/README.md", readme.encode(), "text/markdown; charset=utf-8")
    await _put(
        f"{prefix}/manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2).encode(),
        "application/json",
    )
    return prefix
