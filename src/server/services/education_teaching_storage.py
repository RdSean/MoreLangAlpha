"""Service-owned staging and private archive for managed teaching packages."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import unquote
from uuid import UUID

from src.server.services.education_book_assets import (
    expected_book_asset_files,
    validate_book_asset_content,
    validate_book_asset_manifest,
)
from src.server.services.education_book_package import (
    BOOK_PACKAGE_FORMAT,
    BookPackageValidationError,
    validate_book_package,
)
from src.server.services.education_generation_progress import progress_helper_source
from src.server.services.education_reading_assets import (
    READING_ASSET_FORMAT,
    build_reading_asset_inputs,
    expected_reading_asset_files,
    validate_reading_asset_content,
    validate_reading_asset_manifest,
)
from src.server.services.education_textbook_snapshot_reads import (
    TextbookSnapshotDigestError,
    TextbookSnapshotReadError,
    read_snapshot_artifact_bytes,
    safe_asset_manifest_entry,
    validated_snapshot_prefix,
)
from src.utils.storage import get_bytes, upload_bytes


_SAFE_COMPONENT_RE = re.compile(r"[^0-9A-Za-z._-]+")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_SNAPSHOT_FORMAT = "langalpha-textbook-source-snapshot/v1"
_CHECKPOINT_BUNDLE_PREFIX_RE = re.compile(
    r"^education/"
    r"[0-9A-Za-z][0-9A-Za-z._-]{0,79}/"
    r"[0-9A-Za-z][0-9A-Za-z._-]{0,79}/"
    r"v[1-9][0-9]*/book-pipeline-checkpoints/"
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}/"
    r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-"
    r"[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$"
)
_MARKDOWN_IMAGE_RE = re.compile(
    r"""!\[[^\]]*\]\(\s*(?P<target><[^>\n]+>|[^\s)]+)"""
    r"""(?:\s+(?:"[^"]*"|'[^']*'|\([^)]*\)))?\s*\)""",
    re.DOTALL,
)
_SOURCE_ASSET_FIELDS = (
    "artifact_id",
    "artifact_kind",
    "format",
    "media_type",
    "relative_path",
    "sha256",
)
_MAX_CANDIDATE_BYTES = 4 * 1024 * 1024
_MAX_BOOK_PACKAGE_JSON_BYTES = 16 * 1024 * 1024
_MAX_BOOK_PACKAGE_ASSET_BYTES = 32 * 1024 * 1024
_MAX_BOOK_PACKAGE_TOTAL_ASSET_BYTES = 128 * 1024 * 1024
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

    async def ensure_directories(
        self,
        directories: list[str],
        *,
        mode: int = 0o755,
    ) -> None: ...

    async def seal_directory_read_only(self, path: str) -> None: ...

    async def seal_file_append_only(self, path: str) -> None: ...


_MANAGED_SKILL_NAMES = ("book-to-skill",)
_STATIC_SKILL_SUFFIXES = frozenset({".css", ".html", ".json", ".md", ".py", ".toml"})
_BOOK_PACKAGE_FILES = (
    "outputs/book_package.json",
    "outputs/content_tree.json",
    "outputs/knowledge_points.json",
    "outputs/assets_manifest.json",
)
_ASSETS_MANIFEST_FORMAT = "langalpha-assets-manifest/v1"
_CONTENT_TREE_FORMAT = "langalpha-content-tree/v1"
_KNOWLEDGE_POINTS_FORMAT = "langalpha-knowledge-points/v1"
_PROJECTION_FORMATS = {
    "content_nodes": {None, BOOK_PACKAGE_FORMAT, _CONTENT_TREE_FORMAT},
    "knowledge_points": {None, BOOK_PACKAGE_FORMAT, _KNOWLEDGE_POINTS_FORMAT},
}


def _strict_json_object(content: bytes, *, label: str) -> dict[str, Any]:
    if not isinstance(content, bytes) or not content.strip():
        raise TeachingPackageStorageError(f"{label} is unavailable")
    if len(content) > _MAX_BOOK_PACKAGE_JSON_BYTES:
        raise TeachingPackageStorageError(f"{label} is too large")
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TeachingPackageStorageError(f"{label} must be UTF-8") from exc

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant: {value}")

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        decoded: dict[str, Any] = {}
        for key, value in pairs:
            if key in decoded:
                raise ValueError(f"duplicate JSON key: {key}")
            decoded[key] = value
        return decoded

    def parse_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ValueError("non-finite JSON number")
        return parsed

    try:
        decoded = json.loads(
            text,
            parse_constant=reject_constant,
            parse_float=parse_float,
            object_pairs_hook=reject_duplicate_keys,
        )
    except (json.JSONDecodeError, ValueError) as exc:
        raise TeachingPackageStorageError(f"{label} is invalid") from exc
    if not isinstance(decoded, dict):
        raise TeachingPackageStorageError(f"{label} must be a JSON object")
    return decoded


def _package_projection(
    value: Mapping[str, Any],
    *,
    package: Mapping[str, Any],
    key: str,
) -> list[Any]:
    projected = value.get(key)
    if not isinstance(projected, list):
        raise TeachingPackageStorageError(f"Managed book package {key} is invalid")
    if value.get("format") not in _PROJECTION_FORMATS[key]:
        raise TeachingPackageStorageError(f"Managed book package {key} is invalid")
    return projected


def _validate_projection(
    *,
    raw_package: Mapping[str, Any],
    normalized_package: Mapping[str, Any],
    markdown: str | None,
    markdown_by_source: Mapping[str, str] | None,
    default_source_id: str | None,
    key: str,
    value: list[Any],
) -> None:
    probe = dict(raw_package)
    probe[key] = value
    try:
        normalized, _warnings = validate_book_package(
            probe,
            markdown=markdown,
            markdown_by_source=markdown_by_source,
            default_source_id=default_source_id,
        )
    except BookPackageValidationError as exc:
        raise TeachingPackageStorageError(
            f"Managed book package {key} is invalid"
        ) from exc
    if normalized[key] != normalized_package[key]:
        raise TeachingPackageStorageError(
            f"Managed book package {key} contradicts book_package.json"
        )


async def _upload_staged_files(
    sandbox: ManagedTeachingSandbox, files: list[tuple[str, bytes]]
) -> None:
    """Write fixed staged files through PTCSandbox's public byte API."""
    for path, content in files:
        if not await sandbox.aupload_file_bytes(path, content):
            raise TeachingPackageStorageError("Could not stage managed teaching input")


async def _seal_managed_inputs(
    sandbox: ManagedTeachingSandbox,
    root: str,
) -> None:
    """Remove write permission after staging frozen inputs.

    Docker tar extraction applies directory-entry modes, so every upload below
    ``inputs/`` resets that directory to the provider's default. Seal it only
    after all input files for the job have been staged.
    """
    inputs_root = f"{root}/inputs"
    await sandbox.ensure_directories([inputs_root], mode=0o555)
    await sandbox.seal_directory_read_only(inputs_root)


async def stage_managed_teaching_skills(
    job_id: str,
    sandbox: ManagedTeachingSandbox,
    *,
    skill_names: tuple[str, ...] = _MANAGED_SKILL_NAMES,
    expected_skill_sha256: str | None = None,
    expected_schema_sha256: str | None = None,
) -> None:
    """Stage selected skills plus the service-authored progress append helper."""
    root = managed_job_root(job_id)
    from ptc_agent.config.agent import host_skill_dirs

    files: list[tuple[str, bytes]] = []
    more_to_skills_files: dict[str, bytes] = {}
    for skill_name in skill_names:
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
                raise TeachingPackageStorageError(
                    "Managed teaching skill is unavailable"
                ) from exc
            relative_path = source.relative_to(source_root).as_posix()
            files.append(
                (f"{root}/.agents/skills/{skill_name}/{relative_path}", content)
            )
            if skill_name == "more-to-skills":
                more_to_skills_files[relative_path] = content
    if expected_skill_sha256 is not None or expected_schema_sha256 is not None:
        skill_content = more_to_skills_files.get("SKILL.md")
        schema_content = more_to_skills_files.get("schemas/book-structure.schema.json")
        if (
            skill_content is None
            or schema_content is None
            or expected_skill_sha256 is None
            or expected_schema_sha256 is None
            or hashlib.sha256(skill_content).hexdigest() != expected_skill_sha256
            or hashlib.sha256(schema_content).hexdigest() != expected_schema_sha256
        ):
            raise TeachingPackageStorageError(
                "Managed teaching skill does not match the frozen identity"
            )
    files.append((f"{root}/.langalpha/progress.jsonl", b""))
    files.append((f"{root}/.langalpha/progress.py", progress_helper_source()))
    await _upload_staged_files(sandbox, files)
    await sandbox.seal_file_append_only(f"{root}/.langalpha/progress.jsonl")


def _safe_component(value: object, fallback: str) -> str:
    normalized = _SAFE_COMPONENT_RE.sub("-", str(value).strip()).strip(".-").lower()
    return normalized[:80] or fallback


def managed_job_root(job_id: str) -> str:
    """Construct the sole sandbox namespace a managed task may use."""
    return f"/managed/textbook-job/{UUID(str(job_id))}"


def _normalized_source_asset_manifest(value: object) -> list[dict[str, str]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise TeachingPackageStorageError("Frozen source asset manifest is invalid")
    normalized: list[dict[str, str]] = []
    relative_paths: set[str] = set()
    for asset in value:
        if not isinstance(asset, Mapping):
            raise TeachingPackageStorageError("Frozen source asset is invalid")
        fields = {field: str(asset.get(field) or "") for field in _SOURCE_ASSET_FIELDS}
        relative_path = fields["relative_path"]
        if (
            not all(fields[field] for field in fields if field != "relative_path")
            or not relative_path
            or "\\" in relative_path
            or relative_path.startswith("/")
            or any(part in {"", ".", ".."} for part in relative_path.split("/"))
        ):
            raise TeachingPackageStorageError("Frozen source asset is invalid")
        if relative_path in relative_paths:
            raise TeachingPackageStorageError(
                "Frozen source asset paths must be unique"
            )
        if not _SHA256_RE.fullmatch(fields["sha256"]):
            raise TeachingPackageStorageError("Frozen source asset digest is invalid")
        relative_paths.add(relative_path)
        normalized.append(fields)
    return normalized


def _local_image_references(markdown: str) -> list[str]:
    references: list[str] = []
    for match in _MARKDOWN_IMAGE_RE.finditer(markdown):
        target = match.group("target").strip()
        if target.startswith("<") and target.endswith(">"):
            target = target[1:-1].strip()
        target = unquote(target)
        if not target or target.startswith(("#", "//")):
            continue
        if re.match(r"^(?:https?|data|blob):", target, re.IGNORECASE):
            continue
        if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target):
            raise TeachingPackageStorageError(
                "A Markdown image reference uses an unsupported scheme"
            )
        references.append(target)
    return references


def _referenced_source_assets(
    *,
    markdown: str,
    asset_manifest: list[dict[str, str]],
    position: int,
) -> tuple[list[str], list[dict[str, str]]]:
    image_assets = [
        asset for asset in asset_manifest if asset["artifact_kind"] == "embedded_image"
    ]
    by_path = {asset["relative_path"]: asset for asset in image_assets}
    by_basename: dict[str, list[dict[str, str]]] = {}
    for asset in image_assets:
        by_basename.setdefault(asset["relative_path"].rsplit("/", 1)[-1], []).append(
            asset
        )

    staged: dict[str, dict[str, str]] = {}
    for reference in _local_image_references(markdown):
        normalized = reference[2:] if reference.startswith("./") else reference
        if (
            normalized.startswith("/")
            or "\\" in normalized
            or "\x00" in normalized
            or any(part in {"", ".", ".."} for part in normalized.split("/"))
        ):
            raise TeachingPackageStorageError(
                "A referenced frozen source asset is unavailable"
            )
        asset = by_path.get(reference) or by_path.get(normalized)
        if asset is None:
            matches = by_basename.get(normalized.rsplit("/", 1)[-1], [])
            if len(matches) != 1:
                raise TeachingPackageStorageError(
                    "A referenced frozen source asset is unavailable"
                )
            asset = matches[0]
        staged_path = f"assets/{position:02d}/{asset['relative_path']}"
        staged[asset["relative_path"]] = {
            **asset,
            "path": staged_path,
        }
    return [asset["path"] for asset in staged.values()], list(staged.values())


async def hydrate_source_asset_manifests(job: Mapping[str, Any]) -> dict[str, Any]:
    """Backfill empty v2 source manifests from each frozen root snapshot manifest."""
    result = dict(job)
    sources = job.get("sources")
    if not isinstance(sources, list):
        return result
    hydrated_sources: list[Any] = []
    for source in sources:
        if not (
            isinstance(source, Mapping)
            and source.get("markdown") is not None
            and source.get("content_chapter_id") is not None
        ):
            hydrated_sources.append(source)
            continue
        hydrated = dict(source)
        if not hydrated.get("asset_manifest"):
            snapshot_prefix = hydrated.get("snapshot_prefix")
            if isinstance(snapshot_prefix, str) and snapshot_prefix:
                try:
                    prefix = validated_snapshot_prefix(snapshot_prefix)
                except TextbookSnapshotReadError as exc:
                    raise TeachingPackageStorageError(
                        "Frozen source snapshot prefix is invalid"
                    ) from exc
                manifest_bytes = await asyncio.to_thread(
                    get_bytes, f"{prefix}manifest.json"
                )
                if (
                    not isinstance(manifest_bytes, bytes)
                    or not manifest_bytes
                    or len(manifest_bytes) > _MAX_CANDIDATE_BYTES
                ):
                    raise TeachingPackageStorageError(
                        "Frozen source snapshot manifest is unavailable"
                    )
                try:
                    manifest = json.loads(manifest_bytes.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise TeachingPackageStorageError(
                        "Frozen source snapshot manifest is invalid"
                    ) from exc
                artifacts = (
                    manifest.get("artifacts") if isinstance(manifest, Mapping) else None
                )
                if (
                    not isinstance(manifest, Mapping)
                    or manifest.get("format") != _SOURCE_SNAPSHOT_FORMAT
                    or not isinstance(artifacts, list)
                ):
                    raise TeachingPackageStorageError(
                        "Frozen source snapshot manifest is invalid"
                    )
                asset_manifest: list[dict[str, str]] = []
                for artifact in artifacts:
                    entry = safe_asset_manifest_entry(artifact)
                    if entry is None:
                        raise TeachingPackageStorageError(
                            "Frozen source snapshot manifest artifact is invalid"
                        )
                    asset_manifest.append(entry)
                hydrated["asset_manifest"] = asset_manifest
            else:
                hydrated["asset_manifest"] = []
            hydrated["asset_manifest_hydrated"] = True
        hydrated_sources.append(hydrated)
    result["sources"] = hydrated_sources
    return result


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
                raise TeachingPackageStorageError("Frozen source position is invalid")
            positions.add(position)
            slug = _safe_component(source.get("slug"), "source")
            markdown = source.get("markdown")
            if not isinstance(markdown, str) or not markdown.strip():
                raise TeachingPackageStorageError("Frozen source text is invalid")
            asset_manifest = _normalized_source_asset_manifest(
                source.get("asset_manifest")
            )
            if asset_manifest or source.get("asset_manifest_hydrated"):
                asset_paths, staged_assets = _referenced_source_assets(
                    markdown=markdown,
                    asset_manifest=asset_manifest,
                    position=position,
                )
            else:
                asset_paths, staged_assets = [], []
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
                    "asset_paths": asset_paths,
                    "snapshot_prefix": source.get("snapshot_prefix"),
                    "staged_assets": staged_assets,
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
            raise TeachingPackageStorageError(
                "Frozen content chapter position is invalid"
            )
        slug = _safe_component(chapter.get("slug"), "chapter")
        markdown = chapter.get("markdown")
        if not isinstance(markdown, str) or not markdown.strip():
            raise TeachingPackageStorageError("Frozen content chapter text is invalid")
        path = f"chapters/{position:02d}-{slug}.md"
        if path in paths:
            raise TeachingPackageStorageError(
                "Frozen content chapter paths must be unique"
            )
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
    job = await hydrate_source_asset_manifests(job)
    staged = build_staged_teaching_input(job)
    frozen = staged["frozen"]
    root = managed_job_root(frozen["job_id"])
    files: list[tuple[str, bytes]] = [
        (f"{root}/inputs/manifest.json", staged["manifest_bytes"]),
        # The Docker job root is service-created. Seed the two fixed writable
        # directories through the sandbox API so later relative Bash commands
        # do not fail on its ownership boundary.
        (f"{root}/work/knowledge-skill/.keep", b""),
        (f"{root}/outputs/.keep", b""),
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
        for source in frozen["sources"]:
            snapshot_prefix = source.get("snapshot_prefix")
            for asset in source["staged_assets"]:
                try:
                    content, _snapshot_key = await read_snapshot_artifact_bytes(
                        snapshot_prefix=str(snapshot_prefix or ""),
                        relative_path=asset["relative_path"],
                        expected_sha256=asset["sha256"],
                        read_bytes=get_bytes,
                    )
                except TextbookSnapshotDigestError as exc:
                    raise TeachingPackageStorageError(
                        "A referenced frozen source asset digest does not match"
                    ) from exc
                except TextbookSnapshotReadError as exc:
                    raise TeachingPackageStorageError(
                        "A referenced frozen source asset is unavailable"
                    ) from exc
                files.append((f"{root}/inputs/{asset['path']}", content))
    else:
        files.extend(
            (f"{root}/inputs/{chapter['path']}", chapter["markdown"].encode("utf-8"))
            for chapter in frozen["chapters"]
        )
    await _upload_staged_files(sandbox, files)
    await _seal_managed_inputs(sandbox, root)
    return {key: staged[key] for key in ("manifest", "manifest_sha256", "chapters")}


async def download_structure_output(
    job_id: str, sandbox: ManagedTeachingSandbox
) -> dict[str, Any]:
    """Download the one fixed structure candidate without listing paths."""
    path = f"{managed_job_root(job_id)}/outputs/structure.json"
    content = await sandbox.adownload_file_bytes(path)
    if content is None:
        raise TeachingPackageStorageError(
            "Managed textbook structure output is unavailable"
        )
    if len(content) > _MAX_CANDIDATE_BYTES:
        raise TeachingPackageStorageError(
            "Managed textbook structure output is too large"
        )
    try:
        output = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TeachingPackageStorageError(
            "Managed textbook structure output is invalid"
        ) from exc
    if not isinstance(output, dict):
        raise TeachingPackageStorageError(
            "Managed textbook structure output is invalid"
        )
    return output


async def download_book_package_outputs(
    job_id: str,
    sandbox: ManagedTeachingSandbox,
    *,
    markdown: str | None = None,
    markdown_by_source: Mapping[str, str] | None = None,
    default_source_id: str | None = None,
) -> dict[str, Any]:
    """Download the fixed package bundle and only manifest-declared assets."""
    root = managed_job_root(job_id)
    raw_files: dict[str, bytes] = {}
    for relative_path in _BOOK_PACKAGE_FILES:
        content = await sandbox.adownload_file_bytes(f"{root}/{relative_path}")
        if not isinstance(content, bytes) or not content.strip():
            raise TeachingPackageStorageError(
                f"Managed book package output is unavailable: {relative_path}"
            )
        raw_files[relative_path] = content

    parsed = {
        relative_path: _strict_json_object(
            raw_files[relative_path],
            label=f"Managed book package output {relative_path}",
        )
        for relative_path in _BOOK_PACKAGE_FILES
    }
    package_raw = parsed["outputs/book_package.json"]
    try:
        package, warnings = validate_book_package(
            package_raw,
            markdown=markdown,
            markdown_by_source=markdown_by_source,
            default_source_id=default_source_id,
        )
    except BookPackageValidationError as exc:
        raise TeachingPackageStorageError("Managed book package is invalid") from exc

    content_tree = parsed["outputs/content_tree.json"]
    knowledge_points = parsed["outputs/knowledge_points.json"]
    _validate_projection(
        raw_package=package_raw,
        normalized_package=package,
        markdown=markdown,
        markdown_by_source=markdown_by_source,
        default_source_id=default_source_id,
        key="content_nodes",
        value=_package_projection(
            content_tree,
            package=package,
            key="content_nodes",
        ),
    )
    _validate_projection(
        raw_package=package_raw,
        normalized_package=package,
        markdown=markdown,
        markdown_by_source=markdown_by_source,
        default_source_id=default_source_id,
        key="knowledge_points",
        value=_package_projection(
            knowledge_points,
            package=package,
            key="knowledge_points",
        ),
    )

    manifest = parsed["outputs/assets_manifest.json"]
    if manifest.get("format") != _ASSETS_MANIFEST_FORMAT:
        raise TeachingPackageStorageError("Managed asset manifest format is invalid")
    manifest_assets = manifest.get("assets")
    if not isinstance(manifest_assets, list):
        raise TeachingPackageStorageError("Managed asset manifest is invalid")
    manifest_probe = dict(package_raw)
    manifest_probe["assets"] = manifest_assets
    try:
        normalized_manifest, _manifest_warnings = validate_book_package(
            manifest_probe,
            markdown=markdown,
            markdown_by_source=markdown_by_source,
            default_source_id=default_source_id,
        )
    except BookPackageValidationError as exc:
        raise TeachingPackageStorageError("Managed asset manifest is invalid") from exc
    manifest_assets_by_path = {
        str(asset["path"]): asset for asset in normalized_manifest["assets"]
    }
    if any(
        manifest_assets_by_path.get(str(asset["path"])) != asset
        for asset in package["assets"]
    ):
        raise TeachingPackageStorageError(
            "Managed asset manifest contradicts book_package.json"
        )

    asset_files: dict[str, bytes] = {}
    total_size = 0
    for asset in package["assets"]:
        relative_path = str(asset["path"])
        expected_size = asset.get("size_bytes")
        expected_sha256 = asset.get("content_sha256")
        if (
            not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size < 0
            or not isinstance(expected_sha256, str)
            or not _SHA256_RE.fullmatch(expected_sha256)
        ):
            raise TeachingPackageStorageError(
                "Managed book package asset metadata is incomplete"
            )
        content = await sandbox.adownload_file_bytes(f"{root}/{relative_path}")
        if not isinstance(content, bytes):
            raise TeachingPackageStorageError(
                f"Managed book package asset is unavailable: {relative_path}"
            )
        if len(content) > _MAX_BOOK_PACKAGE_ASSET_BYTES:
            raise TeachingPackageStorageError(
                f"Managed book package asset is too large: {relative_path}"
            )
        total_size += len(content)
        if total_size > _MAX_BOOK_PACKAGE_TOTAL_ASSET_BYTES:
            raise TeachingPackageStorageError(
                "Managed book package assets exceed the size limit"
            )
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if len(content) != expected_size or actual_sha256 != expected_sha256:
            raise TeachingPackageStorageError(
                f"Managed book package asset digest or size does not match: "
                f"{relative_path}"
            )
        asset_files[relative_path] = content
    return {
        "package": package,
        "raw_files": raw_files,
        "asset_files": asset_files,
        "warnings": warnings,
    }


async def download_book_asset_outputs(
    job_id: str,
    sandbox: ManagedTeachingSandbox,
) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Download the fixed manifest and only the Markdown files it names."""
    root = managed_job_root(job_id)
    manifest_content = await sandbox.adownload_file_bytes(
        f"{root}/outputs/chapters_manifest.json"
    )
    if not isinstance(manifest_content, bytes) or not manifest_content.strip():
        raise TeachingPackageStorageError("Managed book asset manifest is unavailable")
    try:
        candidate = json.loads(manifest_content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TeachingPackageStorageError(
            "Managed book asset manifest is invalid"
        ) from exc
    if (
        isinstance(candidate, Mapping)
        and candidate.get("format") == READING_ASSET_FORMAT
    ):
        manifest = validate_reading_asset_manifest(candidate)
        expected_files = expected_reading_asset_files(manifest)
    else:
        manifest = validate_book_asset_manifest(candidate)
        expected_files = expected_book_asset_files(manifest)
    outputs: dict[str, bytes] = {}
    for relative_path in expected_files:
        content = await sandbox.adownload_file_bytes(f"{root}/outputs/{relative_path}")
        if not isinstance(content, bytes) or not content.strip():
            raise TeachingPackageStorageError(
                f"Managed book asset is unavailable: {relative_path}"
            )
        if len(content) > _MAX_CANDIDATE_BYTES:
            raise TeachingPackageStorageError(
                f"Managed book asset is too large: {relative_path}"
            )
        outputs[relative_path] = content
    return manifest, outputs


async def stage_reading_asset_inputs(
    job: Mapping[str, Any],
    frozen_input: Mapping[str, Any],
    scopes: list[Mapping[str, Any]],
    sandbox: ManagedTeachingSandbox,
) -> dict[str, Any]:
    """Stage only the service-produced per-Reading slices for one asset job."""
    job_id = str(job.get("generation_job_id") or job.get("job_id") or "")
    if not job_id:
        raise TeachingPackageStorageError("Reading asset job is unavailable")
    built = build_reading_asset_inputs(job, frozen_input, scopes)
    root = managed_job_root(job_id)
    await _upload_staged_files(
        sandbox,
        [
            (f"{root}/{relative_path}", content)
            for relative_path, content in built["files"].items()
        ],
    )
    await _seal_managed_inputs(sandbox, root)
    return built["manifest"]


async def stage_kp_lesson_inputs(
    job: Mapping[str, Any],
    source_context: str,
    chapter_markdown: str,
    sandbox: ManagedTeachingSandbox,
) -> None:
    """Stage only the selected knowledge-point context for one lesson job."""
    if not isinstance(source_context, str) or not source_context.strip():
        raise TeachingPackageStorageError(
            "Knowledge-point lesson context is unavailable"
        )
    if not isinstance(chapter_markdown, str) or not chapter_markdown.strip():
        raise TeachingPackageStorageError(
            "Knowledge-point chapter asset is unavailable"
        )
    job_id = str(job.get("generation_job_id") or job.get("job_id") or "")
    if not job_id:
        raise TeachingPackageStorageError("Knowledge-point lesson job is unavailable")
    root = managed_job_root(job_id)
    content_node_id = str(job.get("content_node_id") or "")
    raw_source_refs = job.get("knowledge_point_source_refs")
    if raw_source_refs is None:
        raw_source_refs = job.get("source_refs")
    if raw_source_refs is None and content_node_id:
        source_refs: list[Any] = []
    elif isinstance(raw_source_refs, list):
        source_refs = raw_source_refs
    else:
        raise TeachingPackageStorageError(
            "Knowledge-point lesson source refs are unavailable"
        )
    if content_node_id:
        path_id = str(UUID(content_node_id))
        source_path = f"inputs/content-nodes/{path_id}.md"
        chapter_path = f"inputs/chapters/{path_id}-knowledge.md"
        manifest = {
            "format": "langalpha-managed-kp-lesson-input/v2",
            "source_kind": "content_node",
            "job_id": job_id,
            "knowledge_point_id": str(job["knowledge_point_id"]),
            "knowledge_point_title": str(job.get("knowledge_point_title") or ""),
            "content_node_id": path_id,
            "content_node_title": str(job.get("content_node_title") or ""),
            "auto_grading": bool(job.get("auto_grading")),
            "source_refs": source_refs,
            "source_path": source_path,
            "chapter_path": chapter_path,
        }
    else:
        if not source_refs:
            raise TeachingPackageStorageError(
                "Knowledge-point lesson source refs are unavailable"
            )
        scope_slot = str(job.get("knowledge_point_scope_slot") or "")
        if scope_slot not in {"reading_a", "reading_b"}:
            raise TeachingPackageStorageError(
                "Knowledge-point reading scope is unavailable"
            )
        source_path = f"inputs/readings/{scope_slot}.md"
        chapter_path = f"inputs/chapters/{scope_slot}-knowledge.md"
        manifest = {
            "format": "langalpha-managed-kp-lesson-input/v1",
            "source_kind": "legacy_reading",
            "job_id": job_id,
            "knowledge_point_id": str(job["knowledge_point_id"]),
            "knowledge_point_title": str(job.get("knowledge_point_title") or ""),
            "unit_title": str(job.get("unit_title") or ""),
            "auto_grading": bool(job.get("auto_grading")),
            "scope_slot": scope_slot,
            "source_refs": source_refs,
            "reading_path": source_path,
            "chapter_path": chapter_path,
        }
    files = [
        (
            f"{root}/inputs/manifest.json",
            json.dumps(
                manifest,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"),
        ),
        (f"{root}/{source_path}", source_context.encode("utf-8")),
        (f"{root}/{chapter_path}", chapter_markdown.encode("utf-8")),
        (f"{root}/outputs/.keep", b""),
    ]
    await _upload_staged_files(sandbox, files)
    await _seal_managed_inputs(sandbox, root)


async def read_content_node_asset(job: Mapping[str, Any]) -> str:
    """Read one declared generic content-node asset with integrity checks."""
    content_key = str(job.get("content_asset_key") or "")
    content_sha256 = str(job.get("content_asset_sha256") or "")
    size_bytes = job.get("content_asset_size_bytes")
    if (
        not content_key.startswith("education/")
        or ".." in content_key
        or not _SHA256_RE.fullmatch(content_sha256)
        or not isinstance(size_bytes, int)
        or isinstance(size_bytes, bool)
        or size_bytes <= 0
        or size_bytes > _MAX_BOOK_PACKAGE_ASSET_BYTES
    ):
        raise TeachingPackageStorageError(
            "Knowledge-point content node asset is unavailable"
        )
    content = await asyncio.to_thread(get_bytes, content_key)
    if (
        not isinstance(content, bytes)
        or len(content) != size_bytes
        or hashlib.sha256(content).hexdigest() != content_sha256
    ):
        raise TeachingPackageStorageError(
            "Knowledge-point content node asset is invalid"
        )
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TeachingPackageStorageError(
            "Knowledge-point content node asset is invalid"
        ) from exc


async def read_reading_asset_knowledge(
    job: Mapping[str, Any],
    scope: Mapping[str, Any],
) -> str:
    """Read the verified canonical knowledge file assigned to one Reading."""
    prefix = str(job.get("book_asset_prefix") or "")
    manifest = job.get("book_asset_manifest")
    if (
        not prefix.startswith("education/")
        or not isinstance(manifest, Mapping)
        or manifest.get("format") != READING_ASSET_FORMAT
    ):
        raise TeachingPackageStorageError(
            "Knowledge-point chapter assets are unavailable"
        )
    unit_id = str(scope.get("unit_id") or "")
    slot = str(scope.get("slot") or "")
    reading = next(
        (
            item
            for item in manifest.get("readings", [])
            if isinstance(item, Mapping)
            and str(item.get("unit_id") or "") == unit_id
            and str(item.get("slot") or "") == slot
        ),
        None,
    )
    if not isinstance(reading, Mapping):
        raise TeachingPackageStorageError(
            "Knowledge-point chapter asset is unavailable"
        )
    files = reading.get("files")
    knowledge = files.get("knowledge") if isinstance(files, Mapping) else None
    if not isinstance(knowledge, Mapping):
        raise TeachingPackageStorageError(
            "Knowledge-point chapter asset is unavailable"
        )
    relative_path = str(knowledge.get("path") or "")
    expected_size = knowledge.get("size_bytes")
    expected_sha256 = str(knowledge.get("sha256") or "")
    if (
        not relative_path
        or relative_path.startswith("/")
        or ".." in relative_path
        or not isinstance(expected_size, int)
        or len(expected_sha256) != 64
    ):
        raise TeachingPackageStorageError("Knowledge-point chapter manifest is invalid")
    content = await asyncio.to_thread(get_bytes, f"{prefix}/{relative_path}")
    if (
        not isinstance(content, bytes)
        or len(content) != expected_size
        or hashlib.sha256(content).hexdigest() != expected_sha256
    ):
        raise TeachingPackageStorageError("Knowledge-point chapter asset is invalid")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TeachingPackageStorageError(
            "Knowledge-point chapter asset is invalid"
        ) from exc


async def download_kp_lesson_outputs(
    job_id: str,
    sandbox: ManagedTeachingSandbox,
    *,
    auto_grading: bool,
) -> tuple[bytes, bytes | None]:
    """Download only lesson.md and the optional practice.json candidate."""
    root = managed_job_root(job_id)
    lesson = await sandbox.adownload_file_bytes(f"{root}/outputs/lesson.md")
    if not isinstance(lesson, bytes) or not lesson.strip():
        raise TeachingPackageStorageError(
            "Knowledge-point lesson output is unavailable"
        )
    if len(lesson) > _MAX_CANDIDATE_BYTES:
        raise TeachingPackageStorageError("Knowledge-point lesson output is too large")
    practice = await sandbox.adownload_file_bytes(f"{root}/outputs/practice.json")
    if practice is not None:
        if not isinstance(practice, bytes):
            raise TeachingPackageStorageError(
                "Knowledge-point practice output is invalid"
            )
        if len(practice) > _MAX_CANDIDATE_BYTES:
            raise TeachingPackageStorageError(
                "Knowledge-point practice output is too large"
            )
    elif auto_grading:
        raise TeachingPackageStorageError(
            "Knowledge-point practice output is unavailable"
        )
    return lesson, practice


async def _put(key: str, content: bytes, content_type: str) -> None:
    for retry_delay in (*_ARCHIVE_PUT_RETRY_DELAYS, None):
        if await asyncio.to_thread(upload_bytes, key, content, content_type):
            return
        if retry_delay is not None:
            await asyncio.sleep(retry_delay)
    raise TeachingPackageStorageError("Could not store teaching package artifact")


def _asset_content_type(path: str) -> str:
    return (
        "application/json" if path.endswith(".json") else "text/markdown; charset=utf-8"
    )


def _safe_asset_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Copy only the service-produced asset summary, not caller-controlled paths."""
    if manifest.get("format") != "langalpha-family-teaching-assets/v2":
        raise TeachingPackageStorageError("Teaching asset manifest is invalid")
    concept_index = manifest.get("concept_index")
    coverage_audit = manifest.get("coverage_audit")
    chapters = manifest.get("chapters")
    if not isinstance(concept_index, Mapping) or not isinstance(
        coverage_audit, Mapping
    ):
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


def structure_bundle_prefix(job: Mapping[str, Any]) -> str:
    """Return the private object prefix for one immutable structure candidate."""
    try:
        content_sequence = int(job["content_version_sequence"])
        structure_sequence = int(job["structure_sequence"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TeachingPackageStorageError(
            "Textbook structure version sequence is invalid"
        ) from exc
    if content_sequence <= 0 or structure_sequence <= 0:
        raise TeachingPackageStorageError(
            "Textbook structure version sequence is invalid"
        )
    return "education/{}/{}/v{}/structures/v{}".format(
        _safe_component(job.get("household_id"), "household"),
        _safe_component(job.get("slug"), "textbook"),
        content_sequence,
        structure_sequence,
    )


def book_package_bundle_prefix(job: Mapping[str, Any]) -> str:
    """Return the immutable private prefix for one raw managed package."""
    try:
        content_sequence = int(job["content_version_sequence"])
        generation_job_id = UUID(str(job["generation_job_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise TeachingPackageStorageError(
            "Managed book package version is invalid"
        ) from exc
    if content_sequence <= 0:
        raise TeachingPackageStorageError("Managed book package version is invalid")
    return "education/{}/{}/v{}/book-packages/{}".format(
        _safe_component(job.get("household_id"), "household"),
        _safe_component(job.get("slug"), "textbook"),
        content_sequence,
        generation_job_id,
    )


async def write_book_package_bundle(
    job: Mapping[str, Any],
    downloaded: Mapping[str, Any],
) -> dict[str, Any]:
    """Archive the raw package JSON and manifest-declared content assets."""
    raw_files = downloaded.get("raw_files")
    asset_files = downloaded.get("asset_files")
    package = downloaded.get("package")
    if (
        not isinstance(raw_files, Mapping)
        or not isinstance(asset_files, Mapping)
        or not isinstance(package, Mapping)
    ):
        raise TeachingPackageStorageError("Managed book package bundle is invalid")
    prefix = book_package_bundle_prefix(job)
    for relative_path, content in raw_files.items():
        if relative_path not in _BOOK_PACKAGE_FILES or not isinstance(content, bytes):
            raise TeachingPackageStorageError("Managed book package bundle is invalid")
        filename = str(relative_path).removeprefix("outputs/")
        await _put(
            f"{prefix}/{filename}",
            content,
            "application/json",
        )

    asset_content_keys: dict[str, str] = {}
    asset_manifest: list[dict[str, Any]] = []
    for asset in package.get("assets", []):
        if not isinstance(asset, Mapping):
            raise TeachingPackageStorageError("Managed book package asset is invalid")
        relative_path = str(asset.get("path") or "")
        content = asset_files.get(relative_path)
        if (
            relative_path not in asset_files
            or not isinstance(content, bytes)
            or not relative_path.startswith("outputs/")
        ):
            raise TeachingPackageStorageError("Managed book package asset is invalid")
        asset_key = f"{prefix}/assets/{relative_path.removeprefix('outputs/')}"
        await _put(asset_key, content, _asset_content_type(relative_path))
        asset_content_keys[relative_path] = asset_key
        asset_manifest.append(
            {
                "path": relative_path,
                "content_key": asset_key,
                "content_sha256": hashlib.sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
        )

    files_manifest = {
        relative_path: {
            "content_key": f"{prefix}/{str(relative_path).removeprefix('outputs/')}",
            "content_sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }
        for relative_path, content in raw_files.items()
    }
    manifest = {
        "format": "langalpha-book-package-bundle/v1",
        "generation_job_id": str(UUID(str(job["generation_job_id"]))),
        "source_revision": str(package.get("source_revision") or ""),
        "files": files_manifest,
        "assets": asset_manifest,
    }
    await _put(
        f"{prefix}/manifest.json",
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
        "application/json",
    )
    return {
        "prefix": prefix,
        "manifest": manifest,
        "asset_content_keys": asset_content_keys,
    }


def book_pipeline_checkpoint_prefix(
    job: Mapping[str, Any],
    attempt_id: str,
) -> str:
    """Return the immutable private prefix for a chapter-analysis checkpoint."""
    try:
        content_sequence = int(job["content_version_sequence"])
        generation_job_id = UUID(str(job["generation_job_id"]))
        normalized_attempt_id = UUID(str(attempt_id))
    except (KeyError, TypeError, ValueError) as exc:
        raise TeachingPackageStorageError(
            "Book pipeline checkpoint identity is invalid"
        ) from exc
    if content_sequence <= 0:
        raise TeachingPackageStorageError("Book pipeline checkpoint version is invalid")
    prefix = "education/{}/{}/v{}/book-pipeline-checkpoints/{}/{}".format(
        _safe_component(job.get("household_id"), "household"),
        _safe_component(job.get("slug"), "textbook"),
        content_sequence,
        generation_job_id,
        normalized_attempt_id,
    )
    return validate_book_pipeline_checkpoint_prefix(prefix)


def validate_book_pipeline_checkpoint_prefix(value: object) -> str:
    """Return one canonical checkpoint prefix or reject it."""
    prefix = str(value or "").strip()
    if not _CHECKPOINT_BUNDLE_PREFIX_RE.fullmatch(prefix):
        raise TeachingPackageStorageError("Book pipeline checkpoint prefix is invalid")
    return prefix


async def write_book_pipeline_checkpoint_bundle(
    job: Mapping[str, Any],
    attempt_id: str,
    sandbox: ManagedTeachingSandbox,
) -> dict[str, Any]:
    """Archive the durable package projections available after chapter analysis."""
    root = managed_job_root(str(job["generation_job_id"]))
    files: dict[str, bytes] = {}
    for relative_path in _BOOK_PACKAGE_FILES:
        content = await sandbox.adownload_file_bytes(f"{root}/{relative_path}")
        if content is None:
            continue
        if (
            not isinstance(content, bytes)
            or len(content) > _MAX_BOOK_PACKAGE_JSON_BYTES
        ):
            raise TeachingPackageStorageError(
                f"Book pipeline checkpoint file is invalid: {relative_path}"
            )
        if not content.strip():
            continue
        files[relative_path] = content

    required = {
        "outputs/book_package.json",
        "outputs/content_tree.json",
    }
    if not required.issubset(files):
        raise TeachingPackageStorageError(
            "Book pipeline checkpoint lacks chapter-analysis outputs"
        )

    prefix = book_pipeline_checkpoint_prefix(job, attempt_id)
    file_manifest: dict[str, dict[str, Any]] = {}
    for relative_path, content in files.items():
        filename = relative_path.removeprefix("outputs/")
        content_key = f"{prefix}/{filename}"
        await _put(content_key, content, "application/json")
        file_manifest[relative_path] = {
            "content_key": content_key,
            "content_sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }
    manifest = {
        "format": "langalpha-book-pipeline-checkpoint/v1",
        "generation_job_id": str(UUID(str(job["generation_job_id"]))),
        "version_id": str(job["version_id"]),
        "attempt_id": str(UUID(str(attempt_id))),
        "files": file_manifest,
    }
    await _put(
        f"{prefix}/manifest.json",
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8"),
        "application/json",
    )
    return {"prefix": prefix, "manifest": manifest}


async def stage_book_pipeline_checkpoint_bundle(
    job: Mapping[str, Any],
    sandbox: ManagedTeachingSandbox,
) -> list[str]:
    """Restore only the fixed projections named by a continuation checkpoint."""
    prefix = validate_book_pipeline_checkpoint_prefix(
        job.get("checkpoint_bundle_prefix")
    )
    root = managed_job_root(str(job["generation_job_id"]))
    manifest = _strict_json_object(
        await asyncio.to_thread(get_bytes, f"{prefix}/manifest.json") or b"",
        label="Book pipeline checkpoint manifest",
    )
    if manifest.get("format") != "langalpha-book-pipeline-checkpoint/v1":
        raise TeachingPackageStorageError(
            "Book pipeline checkpoint manifest is invalid"
        )
    manifest_attempt_id = str(manifest.get("attempt_id") or "")
    if (
        str(manifest.get("generation_job_id") or "") != str(job["generation_job_id"])
        or str(manifest.get("version_id") or "") != str(job.get("version_id") or "")
        or manifest_attempt_id != str(job.get("latest_attempt_id") or "")
    ):
        raise TeachingPackageStorageError(
            "Book pipeline checkpoint manifest ownership is invalid"
        )
    if book_pipeline_checkpoint_prefix(job, manifest_attempt_id) != prefix:
        raise TeachingPackageStorageError(
            "Book pipeline checkpoint manifest prefix is invalid"
        )
    manifest_files = manifest.get("files")
    if not isinstance(manifest_files, Mapping):
        raise TeachingPackageStorageError(
            "Book pipeline checkpoint manifest files are invalid"
        )
    if not {"outputs/book_package.json", "outputs/content_tree.json"}.issubset(
        manifest_files
    ):
        raise TeachingPackageStorageError(
            "Book pipeline checkpoint manifest is incomplete"
        )
    if not set(manifest_files).issubset(_BOOK_PACKAGE_FILES):
        raise TeachingPackageStorageError(
            "Book pipeline checkpoint manifest has undeclared keys"
        )

    validated_files: list[tuple[str, bytes]] = []
    for relative_path in _BOOK_PACKAGE_FILES:
        file_metadata = manifest_files.get(relative_path)
        if file_metadata is None:
            continue
        if not isinstance(file_metadata, Mapping):
            raise TeachingPackageStorageError(
                "Book pipeline checkpoint file metadata is invalid"
            )
        expected_key = f"{prefix}/{relative_path.removeprefix('outputs/')}"
        expected_sha256 = str(file_metadata.get("content_sha256") or "")
        expected_size = file_metadata.get("size_bytes")
        if (
            str(file_metadata.get("content_key") or "") != expected_key
            or not _SHA256_RE.fullmatch(expected_sha256)
            or not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size < 0
        ):
            raise TeachingPackageStorageError(
                "Book pipeline checkpoint file metadata is invalid"
            )
        content = await asyncio.to_thread(
            get_bytes,
            expected_key,
        )
        if content is None:
            raise TeachingPackageStorageError(
                "Book pipeline checkpoint restore is incomplete"
            )
        if (
            not isinstance(content, bytes)
            or len(content) != expected_size
            or hashlib.sha256(content).hexdigest() != expected_sha256
            or len(content) > _MAX_BOOK_PACKAGE_JSON_BYTES
        ):
            raise TeachingPackageStorageError(
                "Book pipeline checkpoint restore is invalid"
            )
        validated_files.append((relative_path, content))

    uploaded: list[str] = []
    for relative_path, content in validated_files:
        if not await sandbox.aupload_file_bytes(
            f"{root}/{relative_path}",
            content,
        ):
            raise TeachingPackageStorageError(
                "Book pipeline checkpoint could not be staged"
            )
        uploaded.append(relative_path)
    return uploaded


async def write_structure_bundle(
    job: Mapping[str, Any], structure: Mapping[str, Any]
) -> str:
    """Archive one validated structure under a service-generated key."""
    prefix = structure_bundle_prefix(job)
    content = json.dumps(
        structure,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(content) > _MAX_CANDIDATE_BYTES:
        raise TeachingPackageStorageError("Textbook structure bundle is too large")
    manifest = {
        "format": "langalpha-family-textbook-structure/v1",
        "content_version": int(job["content_version_sequence"]),
        "structure_version": int(job["structure_sequence"]),
        "structure_sha256": hashlib.sha256(content).hexdigest(),
        "size_bytes": len(content),
    }
    await _put(
        f"{prefix}/structure.json",
        content,
        "application/json",
    )
    await _put(
        f"{prefix}/manifest.json",
        json.dumps(
            manifest,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ).encode("utf-8"),
        "application/json",
    )
    await _put(
        f"{prefix}/README.md",
        "# 教材结构版本\n\n本目录由受管教材任务生成，须经家长审阅后才能用于课程加工。\n".encode(
            "utf-8"
        ),
        "text/markdown; charset=utf-8",
    )
    return prefix


async def write_book_asset_bundle(
    job: Mapping[str, Any],
    manifest: Mapping[str, Any],
    outputs: Mapping[str, bytes],
) -> tuple[str, dict[str, Any]]:
    """Archive optional chapter assets under the immutable structure bundle."""
    prefix = f"{structure_bundle_prefix(job)}/book-assets"
    if manifest.get("format") == READING_ASSET_FORMAT:
        validated = validate_reading_asset_content(manifest, outputs)
        file_entries = [
            file_entry
            for reading in validated["readings"]
            for file_entry in reading["files"].values()
        ]
    else:
        validated = validate_book_asset_content(manifest, outputs)
        file_entries = list(validated["files"])
    for entry in file_entries:
        relative_path = str(entry["path"])
        await _put(
            f"{prefix}/{relative_path}",
            outputs[relative_path],
            _asset_content_type(relative_path),
        )
    await _put(
        f"{prefix}/manifest.json",
        json.dumps(
            validated,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        ).encode("utf-8"),
        "application/json",
    )
    await _put(
        f"{prefix}/README.md",
        "# 教材知识包\n\n本目录由受管教材任务生成，可随教材结构版本一起复用。\n".encode(
            "utf-8"
        ),
        "text/markdown; charset=utf-8",
    )
    return prefix, validated


def kp_lesson_content_key(
    job: Mapping[str, Any],
    *,
    content_sha256: str,
) -> str:
    """Return the deterministic private key for one Markdown lesson revision."""
    if not _SHA256_RE.fullmatch(content_sha256):
        raise TeachingPackageStorageError("Knowledge-point lesson hash is invalid")
    try:
        content_sequence = int(job["content_version_sequence"])
        structure_sequence = int(job["structure_sequence"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TeachingPackageStorageError(
            "Knowledge-point lesson version is invalid"
        ) from exc
    if min(content_sequence, structure_sequence) <= 0:
        raise TeachingPackageStorageError("Knowledge-point lesson version is invalid")
    prefix = (
        "education/{household}/{textbook}/v{content}/structures/v{structure}"
    ).format(
        household=_safe_component(job.get("household_id"), "household"),
        textbook=_safe_component(job.get("slug"), "textbook"),
        content=content_sequence,
        structure=structure_sequence,
    )
    content_node_id = str(job.get("content_node_id") or "")
    if content_node_id:
        try:
            node_id = str(UUID(content_node_id))
            knowledge_point_id = str(UUID(str(job["knowledge_point_id"])))
        except (TypeError, ValueError) as exc:
            raise TeachingPackageStorageError(
                "Knowledge-point lesson identity is invalid"
            ) from exc
        candidate_key = str(
            job.get("candidate_key") or job.get("knowledge_point_slug") or ""
        )
        candidate_digest = hashlib.sha256(candidate_key.encode("utf-8")).hexdigest()
        return (
            f"{prefix}/content-nodes/{node_id}/knowledge-points/"
            f"{knowledge_point_id}-{candidate_digest}/lessons/"
            f"{content_sha256}/lesson.md"
        )
    try:
        unit_position = int(job["unit_position"])
        knowledge_point_position = int(job["knowledge_point_position"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TeachingPackageStorageError(
            "Knowledge-point lesson version is invalid"
        ) from exc
    if min(unit_position, knowledge_point_position) <= 0:
        raise TeachingPackageStorageError("Knowledge-point lesson version is invalid")
    return (
        f"{prefix}/units/{{unit_position:02d}}-{{unit_slug}}/knowledge-points/"
        "{knowledge_point_position:02d}-{knowledge_point_slug}/lessons/"
        "{content_sha256}/lesson.md"
    ).format(
        unit_position=unit_position,
        unit_slug=_safe_component(job.get("unit_slug"), "unit"),
        knowledge_point_position=knowledge_point_position,
        knowledge_point_slug=_safe_component(
            job.get("knowledge_point_slug"), "knowledge-point"
        ),
        content_sha256=content_sha256,
    )


async def write_kp_lesson_revision(
    job: Mapping[str, Any], content: bytes
) -> dict[str, Any]:
    """Store one immutable Markdown lesson revision."""
    if (
        not isinstance(content, bytes)
        or not content
        or len(content) > _MAX_CANDIDATE_BYTES
    ):
        raise TeachingPackageStorageError("Knowledge-point lesson content is invalid")
    try:
        content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TeachingPackageStorageError(
            "Knowledge-point lesson content must be UTF-8"
        ) from exc
    content_sha256 = hashlib.sha256(content).hexdigest()
    content_key = kp_lesson_content_key(job, content_sha256=content_sha256)
    existing = await asyncio.to_thread(get_bytes, content_key)
    if existing is not None:
        if hashlib.sha256(existing).hexdigest() != content_sha256:
            raise TeachingPackageStorageError(
                "Knowledge-point lesson object hash collision"
            )
    else:
        await _put(content_key, content, "text/markdown; charset=utf-8")
    return {
        "content_key": content_key,
        "content_sha256": content_sha256,
        "size_bytes": len(content),
    }


async def read_kp_lesson_revision(
    content_key: str,
    *,
    expected_sha256: str | None = None,
    expected_size: int | None = None,
) -> bytes:
    """Read one private Markdown lesson revision by its database key."""
    if (
        not isinstance(content_key, str)
        or not content_key.startswith("education/")
        or ".." in content_key
        or not content_key.endswith("/lesson.md")
    ):
        raise TeachingPackageStorageError("Knowledge-point lesson key is invalid")
    content = await asyncio.to_thread(get_bytes, content_key)
    if (
        not isinstance(content, bytes)
        or not content
        or len(content) > _MAX_CANDIDATE_BYTES
    ):
        raise TeachingPackageStorageError(
            "Knowledge-point lesson content is unavailable"
        )
    if expected_sha256 is not None and (
        not _SHA256_RE.fullmatch(expected_sha256)
        or hashlib.sha256(content).hexdigest() != expected_sha256
    ):
        raise TeachingPackageStorageError(
            "Knowledge-point lesson content hash mismatch"
        )
    if expected_size is not None and (
        isinstance(expected_size, bool)
        or not isinstance(expected_size, int)
        or len(content) != expected_size
    ):
        raise TeachingPackageStorageError(
            "Knowledge-point lesson content size mismatch"
        )
    return content
