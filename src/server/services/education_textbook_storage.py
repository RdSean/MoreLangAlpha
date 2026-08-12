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


async def write_textbook_bundle(job: dict[str, Any], package: dict[str, Any]) -> str:
    """Write human-readable README/manifest/materials under the scoped education prefix."""
    prefix = textbook_bundle_prefix(job)
    artifacts: list[dict[str, str]] = []
    for chapter in package["chapters"]:
        await _put(
            chapter["markdown_key"],
            chapter["markdown"].encode(),
            "text/markdown; charset=utf-8",
        )
        await _put(
            chapter["teaching_material_key"],
            chapter["teaching_material"].encode(),
            "text/markdown; charset=utf-8",
        )
        questions_key = f"{prefix}/teaching/{chapter['position']:02d}-{chapter['slug']}-questions.json"
        question_bytes = json.dumps(
            chapter["questions"], ensure_ascii=False, indent=2
        ).encode()
        await _put(questions_key, question_bytes, "application/json")
        artifacts.extend(
            [
                {
                    "key": chapter["markdown_key"],
                    "sha256": hashlib.sha256(chapter["markdown"].encode()).hexdigest(),
                },
                {
                    "key": chapter["teaching_material_key"],
                    "sha256": hashlib.sha256(
                        chapter["teaching_material"].encode()
                    ).hexdigest(),
                },
                {
                    "key": questions_key,
                    "sha256": hashlib.sha256(question_bytes).hexdigest(),
                },
            ]
        )
    source_entries = []
    for source in job["sources"]:
        filename = _safe_component(source["original_filename"], "source")
        source_key = f"{prefix}/sources/{source['asset_id']}-{filename}"
        source_bytes = await asyncio.to_thread(get_bytes, source["storage_key"])
        if source_bytes is None:
            raise TextbookBundleStorageError(
                "A frozen textbook source is no longer available"
            )
        await _put(source_key, source_bytes, source["content_type"])
        source_entries.append(
            {
                "asset_id": str(source["asset_id"]),
                "filename": source["original_filename"],
                "key": source_key,
                "sha256": hashlib.sha256(source_bytes).hexdigest(),
            }
        )
    readme = "# {}\n\n版本：v{}\n\n本目录由 LangAlpha 家庭教材本地加工器生成，可凭 `manifest.json` 重建索引。\n".format(
        job["title"], job["version_sequence"]
    )
    manifest = {
        "format": "langalpha-family-textbook/v1",
        "title": job["title"],
        "version": job["version_sequence"],
        "extractor": package["extractor"],
        "sources": source_entries,
        "chapters": [
            {
                "position": c["position"],
                "slug": c["slug"],
                "title": c["title"],
                "markdown_key": c["markdown_key"],
                "teaching_material_key": c["teaching_material_key"],
            }
            for c in package["chapters"]
        ],
        "artifacts": artifacts,
    }
    await _put(f"{prefix}/README.md", readme.encode(), "text/markdown; charset=utf-8")
    await _put(
        f"{prefix}/manifest.json",
        json.dumps(manifest, ensure_ascii=False, indent=2).encode(),
        "application/json",
    )
    return prefix
