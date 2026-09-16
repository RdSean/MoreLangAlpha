"""Service-owned staging and private archive for managed teaching packages."""

from __future__ import annotations

import asyncio
import hashlib
import io
import json
import re
import zipfile
from collections.abc import Mapping
from typing import Any, Protocol
from uuid import UUID

from src.server.services.education_teaching_assets import expected_teaching_asset_paths
from src.utils.storage import upload_bytes


_SAFE_COMPONENT_RE = re.compile(r"[^0-9A-Za-z._-]+")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_CANDIDATE_BYTES = 4 * 1024 * 1024
_MAX_ARCHIVE_STAGE_BYTES = 64 * 1024 * 1024
_ARCHIVE_PUT_RETRY_DELAYS = (5, 10, 20, 40, 60)


class TeachingPackageStorageError(RuntimeError):
    """A sandbox transfer or private teaching-package archive failed."""

    def __init__(self, message: str, *, relative_path: str | None = None) -> None:
        super().__init__(message)
        self.relative_path = relative_path


class ManagedTeachingSandbox(Protocol):
    async def aupload_file_bytes(self, filepath: str, content: bytes) -> bool: ...

    async def adownload_file_bytes(self, path: str) -> bytes | None: ...


_MANAGED_SKILL_NAMES = ("book-to-skill", "the-knowledge-guy")
_STATIC_SKILL_SUFFIXES = frozenset({".css", ".html", ".json", ".md"})


async def _upload_staged_files(
    sandbox: ManagedTeachingSandbox, files: list[tuple[str, bytes]]
) -> None:
    """Write fixed staged files through PTCSandbox's public byte API."""
    for path, content in files:
        if not await sandbox.aupload_file_bytes(path, content):
            raise TeachingPackageStorageError("Could not stage managed teaching input")


async def stage_managed_teaching_skills(
    job_id: str, sandbox: ManagedTeachingSandbox
) -> None:
    """Stage the two complete static built-in skills, never executable helpers."""
    root = managed_job_root(job_id)
    from ptc_agent.config.agent import host_skill_dirs

    files: list[tuple[str, bytes]] = []
    for skill_name in _MANAGED_SKILL_NAMES:
        source_root = next(
            (
                root_dir / skill_name
                for root_dir in host_skill_dirs()
                if (root_dir / skill_name / "SKILL.md").is_file()
            ),
            None,
        )
        if source_root is None:
            raise TeachingPackageStorageError("Managed teaching skill is unavailable")
        for source in sorted(source_root.rglob("*")):
            if (
                not source.is_file()
                or source.is_symlink()
                or source.suffix.lower() not in _STATIC_SKILL_SUFFIXES
            ):
                continue
            try:
                content = source.read_bytes()
            except OSError as exc:
                raise TeachingPackageStorageError("Managed teaching skill is unavailable") from exc
            relative_path = source.relative_to(source_root).as_posix()
            files.append((f"{root}/.agents/skills/{skill_name}/{relative_path}", content))
    await _upload_staged_files(sandbox, files)


def _safe_component(value: object, fallback: str) -> str:
    normalized = _SAFE_COMPONENT_RE.sub("-", str(value).strip()).strip(".-").lower()
    return normalized[:80] or fallback


def managed_job_root(job_id: str) -> str:
    """Construct the sole sandbox namespace a managed task may use."""
    return f"/managed/textbook-job/{UUID(str(job_id))}"


def freeze_teaching_input(job: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize the service-authorized content used by every managed attempt."""
    job_id = str(UUID(str(job["job_id"])))
    sources = job.get("sources")
    if (
        isinstance(sources, list)
        and sources
        and all(
            isinstance(source, Mapping)
            and source.get("markdown") is not None
            and source.get("content_chapter_id") is not None
            for source in sources
        )
    ):
        normalized_sources: list[dict[str, Any]] = []
        normalized_chapters: list[dict[str, Any]] = []
        paths: set[str] = set()
        positions: set[int] = set()
        for source in sources:
            if not isinstance(source, Mapping):
                raise TeachingPackageStorageError("Frozen source is invalid")
            source_id = str(
                source.get("source_id") or source.get("content_chapter_id") or ""
            )
            if not source_id:
                raise TeachingPackageStorageError("Frozen source identity is invalid")
            content_chapter_id = str(
                UUID(str(source.get("content_chapter_id") or source_id))
            )
            position = source.get("position")
            if (
                not isinstance(position, int)
                or isinstance(position, bool)
                or position <= 0
                or position in positions
            ):
                raise TeachingPackageStorageError(
                    "Frozen source position is invalid"
                )
            positions.add(position)
            slug = _safe_component(source.get("slug"), "source")
            markdown = source.get("markdown")
            if not isinstance(markdown, str) or not markdown.strip():
                raise TeachingPackageStorageError("Frozen source text is invalid")
            content_sha256 = hashlib.sha256(markdown.encode("utf-8")).hexdigest()
            provided_sha256 = source.get("content_sha256")
            if provided_sha256 is not None and (
                not isinstance(provided_sha256, str)
                or not _SHA256_RE.fullmatch(provided_sha256)
                or provided_sha256 != content_sha256
            ):
                raise TeachingPackageStorageError("Frozen source hash is invalid")
            path = f"sources/{position:02d}-{slug}.md"
            if path in paths:
                raise TeachingPackageStorageError("Frozen source paths must be unique")
            paths.add(path)
            title = str(source.get("title") or slug)
            normalized_sources.append(
                {
                    "source_id": source_id,
                    "content_chapter_id": content_chapter_id,
                    "document_id": (
                        str(source["document_id"])
                        if source.get("document_id") is not None
                        else None
                    ),
                    "position": position,
                    "slug": slug,
                    "title": title,
                    "content_sha256": content_sha256,
                    "path": path,
                    "asset_paths": [],
                    "markdown": markdown,
                }
            )
            normalized_chapters.append(
                {
                    "content_chapter_id": content_chapter_id,
                    "position": position,
                    "slug": slug,
                    "title": title,
                    "content_sha256": content_sha256,
                    "markdown": markdown,
                }
            )
        normalized_sources.sort(key=lambda source: source["position"])
        normalized_chapters.sort(key=lambda chapter: chapter["position"])
        return {
            "format": "langalpha-managed-textbook-input/v2",
            "job_id": job_id,
            "sources": normalized_sources,
            "chapters": normalized_chapters,
        }

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
    if frozen["format"] == "langalpha-managed-textbook-input/v2":
        manifest = {
            "format": frozen["format"],
            "job_id": frozen["job_id"],
            "sources": [
                {
                    key: source[key]
                    for key in (
                        "source_id",
                        "content_chapter_id",
                        "document_id",
                        "position",
                        "slug",
                        "title",
                        "content_sha256",
                        "path",
                        "asset_paths",
                    )
                }
                for source in frozen["sources"]
            ],
        }
    else:
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
        (f"{root}/inputs/manifest.json", staged["manifest_bytes"]),
        # The Docker job root is service-created. Seed the two fixed writable
        # directories through the sandbox API so later relative Bash commands
        # do not fail on its ownership boundary.
        (f"{root}/work/knowledge-skill/.keep", b""),
        (f"{root}/outputs/knowledge/.keep", b""),
        (f"{root}/outputs/chapters/.keep", b""),
    ]
    if frozen["format"] == "langalpha-managed-textbook-input/v2":
        files.extend(
            (
                f"{root}/inputs/{source['path']}",
                source["markdown"].encode("utf-8"),
            )
            for source in frozen["sources"]
        )
    else:
        files.extend(
            (f"{root}/inputs/{chapter['path']}", chapter["markdown"].encode("utf-8"))
            for chapter in frozen["chapters"]
        )
    await _upload_staged_files(sandbox, files)
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


async def download_teaching_asset_outputs(
    job_id: str, frozen_input: Mapping[str, Any], sandbox: ManagedTeachingSandbox
) -> dict[str, bytes]:
    """Download every v2 candidate from service-derived paths without listing."""
    paths = expected_teaching_asset_paths(frozen_input)
    root = managed_job_root(job_id)
    outputs: dict[str, bytes] = {}
    for path in sorted(paths.all_paths):
        content = await sandbox.adownload_file_bytes(f"{root}/{path}")
        if content is None:
            raise TeachingPackageStorageError(
                "Managed teaching bundle is incomplete", relative_path=path
            )
        if not isinstance(content, bytes) or len(content) > _MAX_CANDIDATE_BYTES:
            raise TeachingPackageStorageError("Managed teaching bundle asset is invalid")
        outputs[path] = content
    return outputs


def encode_teaching_archive_stage(
    frozen_input: Mapping[str, Any], outputs: Mapping[str, bytes]
) -> bytes:
    """Pack one validated fixed-output set for internal archive recovery."""
    paths = expected_teaching_asset_paths(frozen_input)
    if set(outputs) != set(paths.all_paths):
        raise TeachingPackageStorageError("Teaching archive stage paths are invalid")
    total_size = 0
    buffer = io.BytesIO()
    with zipfile.ZipFile(
        buffer, mode="w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        for path in sorted(paths.all_paths):
            content = outputs[path]
            if not isinstance(content, bytes) or len(content) > _MAX_CANDIDATE_BYTES:
                raise TeachingPackageStorageError("Teaching archive stage content is invalid")
            total_size += len(content)
            if total_size > _MAX_ARCHIVE_STAGE_BYTES:
                raise TeachingPackageStorageError("Teaching archive stage is too large")
            archive.writestr(path, content)
    staged = buffer.getvalue()
    if len(staged) > _MAX_ARCHIVE_STAGE_BYTES:
        raise TeachingPackageStorageError("Teaching archive stage is too large")
    return staged


def decode_teaching_archive_stage(
    frozen_input: Mapping[str, Any], staged: bytes
) -> dict[str, bytes]:
    """Restore only the exact fixed outputs from a service-owned archive stage."""
    if not isinstance(staged, bytes) or not staged or len(staged) > _MAX_ARCHIVE_STAGE_BYTES:
        raise TeachingPackageStorageError("Teaching archive stage is invalid")
    paths = expected_teaching_asset_paths(frozen_input)
    try:
        with zipfile.ZipFile(io.BytesIO(staged)) as archive:
            infos = archive.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)) or set(names) != set(paths.all_paths):
                raise TeachingPackageStorageError("Teaching archive stage paths are invalid")
            total_size = 0
            outputs: dict[str, bytes] = {}
            for info in infos:
                if info.is_dir() or info.file_size > _MAX_CANDIDATE_BYTES:
                    raise TeachingPackageStorageError("Teaching archive stage content is invalid")
                total_size += info.file_size
                if total_size > _MAX_ARCHIVE_STAGE_BYTES:
                    raise TeachingPackageStorageError("Teaching archive stage is too large")
                content = archive.read(info)
                if len(content) != info.file_size:
                    raise TeachingPackageStorageError("Teaching archive stage content is invalid")
                outputs[info.filename] = content
    except (OSError, zipfile.BadZipFile, zipfile.LargeZipFile) as exc:
        raise TeachingPackageStorageError("Teaching archive stage is invalid") from exc
    return outputs


async def _put(key: str, content: bytes, content_type: str) -> None:
    for retry_delay in (*_ARCHIVE_PUT_RETRY_DELAYS, None):
        if await asyncio.to_thread(upload_bytes, key, content, content_type):
            return
        if retry_delay is not None:
            await asyncio.sleep(retry_delay)
    raise TeachingPackageStorageError("Could not store teaching package artifact")


def _asset_content_type(path: str) -> str:
    return "application/json" if path.endswith(".json") else "text/markdown; charset=utf-8"


def _safe_asset_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Copy only the service-produced asset summary, not caller-controlled paths."""
    if manifest.get("format") != "langalpha-family-teaching-assets/v2":
        raise TeachingPackageStorageError("Teaching asset manifest is invalid")
    concept_index = manifest.get("concept_index")
    coverage_audit = manifest.get("coverage_audit")
    chapters = manifest.get("chapters")
    if not isinstance(concept_index, Mapping) or not isinstance(coverage_audit, Mapping):
        raise TeachingPackageStorageError("Teaching asset manifest is invalid")
    if not isinstance(chapters, list):
        raise TeachingPackageStorageError("Teaching asset manifest is invalid")
    safe_chapters: list[dict[str, Any]] = []
    for chapter in chapters:
        if not isinstance(chapter, Mapping):
            raise TeachingPackageStorageError("Teaching asset manifest is invalid")
        assets = chapter.get("assets")
        if not isinstance(assets, list):
            raise TeachingPackageStorageError("Teaching asset manifest is invalid")
        safe_assets = []
        for asset in assets:
            if not isinstance(asset, Mapping):
                raise TeachingPackageStorageError("Teaching asset manifest is invalid")
            safe_assets.append(
                {
                    "kind": asset.get("kind"),
                    "size_bytes": asset.get("size_bytes"),
                    "sha256": asset.get("sha256"),
                }
            )
        safe_chapters.append(
            {
                "content_chapter_id": chapter.get("content_chapter_id"),
                "content_sha256": chapter.get("content_sha256"),
                "coverage_status": chapter.get("coverage_status"),
                "concept_count": chapter.get("concept_count"),
                "assets": safe_assets,
            }
        )
    return {
        "format": "langalpha-family-teaching-assets/v2",
        "concept_index": {
            "sha256": concept_index.get("sha256"),
            "size_bytes": concept_index.get("size_bytes"),
            "concept_count": concept_index.get("concept_count"),
        },
        "coverage_audit": {
            "sha256": coverage_audit.get("sha256"),
            "size_bytes": coverage_audit.get("size_bytes"),
            "status": coverage_audit.get("status"),
        },
        "chapters": safe_chapters,
    }


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


async def write_teaching_asset_bundle(
    job: Mapping[str, Any], manifest: Mapping[str, Any], outputs: Mapping[str, bytes]
) -> str:
    """Archive a validated v2 output set under private service-generated keys."""
    frozen_input = freeze_teaching_input(job)
    paths = expected_teaching_asset_paths(frozen_input)
    if set(outputs) != set(paths.all_paths):
        raise TeachingPackageStorageError("Teaching asset bundle paths are invalid")
    prefix = teaching_package_bundle_prefix(job)
    for source_path in sorted(paths.all_paths):
        content = outputs[source_path]
        if not isinstance(content, bytes):
            raise TeachingPackageStorageError("Teaching asset bundle content is invalid")
        archive_path = source_path.removeprefix("outputs/")
        await _put(f"{prefix}/{archive_path}", content, _asset_content_type(archive_path))
    safe_manifest = _safe_asset_manifest(manifest)
    safe_manifest.update(
        {
            "content_version": job["content_version_sequence"],
            "teaching_package": job["teaching_package_sequence"],
        }
    )
    readme = "# 教学知识资产\n\n本目录由受管教材任务生成，须经服务端校验与家长审阅后才可发布。\n"
    await _put(f"{prefix}/README.md", readme.encode("utf-8"), "text/markdown; charset=utf-8")
    await _put(
        f"{prefix}/manifest.json",
        json.dumps(safe_manifest, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8"),
        "application/json",
    )
    return prefix


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
