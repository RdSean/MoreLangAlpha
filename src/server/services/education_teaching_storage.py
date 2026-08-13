"""Service-owned staging and private archive for managed teaching packages."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from pathlib import Path
from collections.abc import Mapping
from typing import Any, Protocol
from uuid import UUID

from src.utils.storage import upload_bytes


_SAFE_COMPONENT_RE = re.compile(r"[^0-9A-Za-z._-]+")
_MAX_CANDIDATE_BYTES = 4 * 1024 * 1024


class TeachingPackageStorageError(RuntimeError):
    """A sandbox transfer or private teaching-package archive failed."""


class ManagedTeachingSandbox(Protocol):
    async def aupload_files(self, files: list[tuple[str, bytes]]) -> object: ...

    async def adownload_file_bytes(self, path: str) -> bytes | None: ...


_MANAGED_SKILL_FILES: tuple[tuple[str, str], ...] = (
    ("book-to-skill", "SKILL.md"),
    ("book-to-skill", "reference/managed-textbook-contract.md"),
    ("the-knowledge-guy", "SKILL.md"),
    ("the-knowledge-guy", "reference/managed-textbook-contract.md"),
)


async def stage_managed_teaching_skills(
    job_id: str, sandbox: ManagedTeachingSandbox
) -> None:
    """Upload the two built-in managed contracts, and no workspace skills."""
    root = managed_job_root(job_id)
    repo_root = Path(__file__).resolve().parents[3]
    files: list[tuple[str, bytes]] = []
    for skill_name, relative_path in _MANAGED_SKILL_FILES:
        source = repo_root / "skills" / skill_name / relative_path
        try:
            content = source.read_bytes()
        except OSError as exc:
            raise TeachingPackageStorageError("Managed teaching skill is unavailable") from exc
        files.append((f"{root}/.agents/skills/{skill_name}/{relative_path}", content))
    await sandbox.aupload_files(files)


def _safe_component(value: object, fallback: str) -> str:
    normalized = _SAFE_COMPONENT_RE.sub("-", str(value).strip()).strip(".-").lower()
    return normalized[:80] or fallback


def managed_job_root(job_id: str) -> str:
    """Construct the sole sandbox namespace a managed task may use."""
    return f"/managed/textbook-job/{UUID(str(job_id))}"


def freeze_teaching_input(job: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the service-authorized content used by every managed attempt."""
    job_id = str(UUID(str(job["job_id"])))
    chapters = job.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise TeachingPackageStorageError("Teaching job has no frozen content chapters")
    normalized_chapters: list[dict[str, Any]] = []
    paths: set[str] = set()
    for chapter in chapters:
        if not isinstance(chapter, Mapping):
            raise TeachingPackageStorageError("Frozen content chapter is invalid")
        chapter_id = str(UUID(str(chapter["content_chapter_id"])))
        position = chapter.get("position")
        if not isinstance(position, int) or isinstance(position, bool) or position <= 0:
            raise TeachingPackageStorageError("Frozen content chapter position is invalid")
        slug = _safe_component(chapter.get("slug"), "chapter")
        markdown = chapter.get("markdown")
        if not isinstance(markdown, str) or not markdown.strip():
            raise TeachingPackageStorageError("Frozen content chapter text is invalid")
        path = f"chapters/{position:02d}-{slug}.md"
        if path in paths:
            raise TeachingPackageStorageError("Frozen content chapter paths must be unique")
        paths.add(path)
        normalized_chapters.append(
            {
                "content_chapter_id": chapter_id,
                "position": position,
                "slug": slug,
                "title": str(chapter.get("title") or slug),
                "content_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
                "path": path,
                "markdown": markdown,
            }
        )
    normalized_chapters.sort(key=lambda chapter: chapter["position"])
    return {
        "format": "langalpha-managed-textbook-input/v1",
        "job_id": job_id,
        "chapters": normalized_chapters,
    }


def build_staged_teaching_input(job: Mapping[str, Any]) -> dict[str, Any]:
    """Build the exact safe manifest and hash before it enters a sandbox."""
    frozen = freeze_teaching_input(job)
    manifest = {
        "format": frozen["format"],
        "job_id": frozen["job_id"],
        "chapters": [
            {
                key: chapter[key]
                for key in (
                    "content_chapter_id",
                    "position",
                    "slug",
                    "title",
                    "content_sha256",
                    "path",
                )
            }
            for chapter in frozen["chapters"]
        ],
    }
    manifest_bytes = json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return {
        "frozen": frozen,
        "manifest": manifest,
        "manifest_bytes": manifest_bytes,
        "manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
        "chapters": [
            {
                key: chapter[key]
                for key in (
                    "content_chapter_id",
                    "position",
                    "slug",
                    "title",
                    "content_sha256",
                )
            }
            for chapter in frozen["chapters"]
        ],
    }


async def stage_teaching_inputs(
    job: Mapping[str, Any], sandbox: ManagedTeachingSandbox
) -> dict[str, Any]:
    """Upload only frozen Markdown and a scrubbed manifest into one job root."""
    staged = build_staged_teaching_input(job)
    frozen = staged["frozen"]
    root = managed_job_root(frozen["job_id"])
    files: list[tuple[str, bytes]] = [
        (f"{root}/inputs/manifest.json", staged["manifest_bytes"])
    ]
    files.extend(
        (f"{root}/inputs/{chapter['path']}", chapter["markdown"].encode("utf-8"))
        for chapter in frozen["chapters"]
    )
    await sandbox.aupload_files(files)
    return {key: staged[key] for key in ("manifest", "manifest_sha256", "chapters")}


async def download_teaching_output(
    job_id: str, sandbox: ManagedTeachingSandbox
) -> dict[str, Any]:
    """Download the single contractually fixed candidate; never list paths."""
    path = f"{managed_job_root(job_id)}/outputs/teaching-package.json"
    content = await sandbox.adownload_file_bytes(path)
    if content is None:
        raise TeachingPackageStorageError("Managed teaching package output is unavailable")
    if len(content) > _MAX_CANDIDATE_BYTES:
        raise TeachingPackageStorageError("Managed teaching package output is too large")
    try:
        output = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TeachingPackageStorageError("Managed teaching package output is invalid") from exc
    if not isinstance(output, dict):
        raise TeachingPackageStorageError("Managed teaching package output is invalid")
    return output


async def _put(key: str, content: bytes, content_type: str) -> None:
    if not await asyncio.to_thread(upload_bytes, key, content, content_type):
        raise TeachingPackageStorageError("Could not store teaching package artifact")


def teaching_package_bundle_prefix(job: Mapping[str, Any]) -> str:
    try:
        content_sequence = int(job["content_version_sequence"])
        package_sequence = int(job["teaching_package_sequence"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TeachingPackageStorageError("Teaching package version sequence is invalid") from exc
    if content_sequence <= 0 or package_sequence <= 0:
        raise TeachingPackageStorageError("Teaching package version sequence is invalid")
    return "education/{}/{}/v{}/teaching/v{}".format(
        _safe_component(job.get("household_id"), "household"),
        _safe_component(job.get("slug"), "textbook"),
        content_sequence,
        package_sequence,
    )


async def write_teaching_package_bundle(
    job: Mapping[str, Any], package: Mapping[str, Any]
) -> str:
    """Archive a previously validated candidate under service-generated keys only."""
    prefix = teaching_package_bundle_prefix(job)
    frozen = freeze_teaching_input(job)
    chapters_by_id = {
        chapter["content_chapter_id"]: chapter for chapter in frozen["chapters"]
    }
    package_chapters = package.get("chapters")
    if not isinstance(package_chapters, list):
        raise TeachingPackageStorageError("Validated teaching package chapters are invalid")
    manifest_chapters: list[dict[str, Any]] = []
    for candidate in package_chapters:
        if not isinstance(candidate, Mapping):
            raise TeachingPackageStorageError("Validated teaching chapter is invalid")
        content_chapter = chapters_by_id.get(str(candidate.get("content_chapter_id")))
        if not content_chapter:
            raise TeachingPackageStorageError("Teaching package references an unknown chapter")
        material_relative = "chapters/{:02d}-{}-material.md".format(
            content_chapter["position"], content_chapter["slug"]
        )
        questions_relative = "chapters/{:02d}-{}-questions.json".format(
            content_chapter["position"], content_chapter["slug"]
        )
        material = str(candidate["teaching_material"]).encode("utf-8")
        questions = json.dumps(
            candidate["questions"], ensure_ascii=False, sort_keys=True, indent=2
        ).encode("utf-8")
        await _put(f"{prefix}/{material_relative}", material, "text/markdown; charset=utf-8")
        await _put(f"{prefix}/{questions_relative}", questions, "application/json")
        manifest_chapters.append(
            {
                "content_chapter_id": content_chapter["content_chapter_id"],
                "position": content_chapter["position"],
                "slug": content_chapter["slug"],
                "content_sha256": candidate["content_sha256"],
                "material_path": material_relative,
                "material_sha256": hashlib.sha256(material).hexdigest(),
                "questions_path": questions_relative,
                "questions_sha256": hashlib.sha256(questions).hexdigest(),
            }
        )
    manifest_chapters.sort(key=lambda chapter: chapter["position"])
    readme = "# 教学包\n\n本目录是冻结教材内容的候选教学包，须经服务端校验与家长审阅后才可发布。\n"
    manifest = {
        "format": "langalpha-family-teaching-package/v1",
        "content_version": job["content_version_sequence"],
        "teaching_package": job["teaching_package_sequence"],
        "chapters": manifest_chapters,
    }
    await _put(f"{prefix}/README.md", readme.encode("utf-8"), "text/markdown; charset=utf-8")
    await _put(
        f"{prefix}/manifest.json",
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"),
        "application/json",
    )
    return prefix
