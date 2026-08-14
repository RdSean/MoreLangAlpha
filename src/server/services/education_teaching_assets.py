"""Validate the complete, fixed-path asset bundle from a managed textbook run."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.server.services.education_teaching_validation import (
    TeachingPackageValidationError,
    _frozen_chapters,
    validate_teaching_package,
)


_ASSET_FORMAT = "langalpha-family-teaching-assets/v2"
_CONCEPT_INDEX_FORMAT = "langalpha-managed-concept-index/v1"
_COVERAGE_AUDIT_FORMAT = "langalpha-managed-coverage-audit/v1"
_CHAPTER_KNOWLEDGE_FORMAT = "langalpha-managed-chapter-knowledge/v1"
_CHAPTER_PRACTICE_FORMAT = "langalpha-managed-chapter-practice/v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SAFE_SLUG_RE = re.compile(r"[^0-9A-Za-z._-]+")
_CHAPTER_ASSET_KINDS = ("knowledge", "toolkit", "practice", "teaching")


class TeachingAssetValidationError(ValueError):
    """An untrusted managed asset bundle violates the frozen output contract."""


@dataclass(frozen=True)
class ChapterAssetPaths:
    knowledge: str
    toolkit: str
    practice: str


@dataclass(frozen=True)
class TeachingAssetPaths:
    concept_index: str
    coverage_audit: str
    teaching_package: str
    _chapters: Mapping[str, ChapterAssetPaths]

    def for_chapter(self, content_chapter_id: str) -> ChapterAssetPaths:
        try:
            return self._chapters[content_chapter_id]
        except KeyError as exc:
            raise TeachingAssetValidationError("Unknown frozen chapter asset path") from exc

    @property
    def all_paths(self) -> frozenset[str]:
        paths = {self.concept_index, self.coverage_audit, self.teaching_package}
        for chapter in self._chapters.values():
            paths.update((chapter.knowledge, chapter.toolkit, chapter.practice))
        return frozenset(paths)


def _require_string(value: object, *, field: str, limit: int = 30_000) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TeachingAssetValidationError(f"{field} must be a non-empty string")
    if len(value) > limit:
        raise TeachingAssetValidationError(f"{field} exceeds its maximum length")
    return value.strip()


def _require_string_list(value: object, *, field: str) -> list[str]:
    if not isinstance(value, list) or not value or len(value) > 128:
        raise TeachingAssetValidationError(f"{field} must be a non-empty bounded list")
    normalized = [_require_string(item, field=field, limit=500) for item in value]
    if len(normalized) != len(set(normalized)):
        raise TeachingAssetValidationError(f"{field} must not contain duplicates")
    return normalized


def _safe_slug(value: object) -> str:
    slug = _SAFE_SLUG_RE.sub("-", str(value).strip()).strip(".-").lower()[:80]
    if not slug:
        raise TeachingAssetValidationError("Frozen chapter slug is invalid")
    return slug


def expected_teaching_asset_paths(frozen_input: Mapping[str, Any]) -> TeachingAssetPaths:
    """Derive every allowed output path from frozen service-owned chapter data."""
    try:
        frozen = _frozen_chapters(frozen_input)
    except TeachingPackageValidationError as exc:
        raise TeachingAssetValidationError(str(exc)) from exc

    chapter_paths: dict[str, ChapterAssetPaths] = {}
    positions: set[int] = set()
    output_paths: set[str] = set()
    for chapter_id, chapter in frozen.items():
        position = chapter.get("position")
        if not isinstance(position, int) or isinstance(position, bool) or position <= 0:
            raise TeachingAssetValidationError("Frozen chapter position is invalid")
        if position in positions:
            raise TeachingAssetValidationError("Frozen chapter positions must be unique")
        positions.add(position)
        prefix = f"outputs/chapters/{position:02d}-{_safe_slug(chapter.get('slug'))}"
        paths = ChapterAssetPaths(
            knowledge=f"{prefix}-knowledge.json",
            toolkit=f"{prefix}-toolkit.md",
            practice=f"{prefix}-practice.json",
        )
        if any(path in output_paths for path in (paths.knowledge, paths.toolkit, paths.practice)):
            raise TeachingAssetValidationError("Frozen chapter output paths must be unique")
        output_paths.update((paths.knowledge, paths.toolkit, paths.practice))
        chapter_paths[chapter_id] = paths
    return TeachingAssetPaths(
        concept_index="outputs/knowledge/concept-index.json",
        coverage_audit="outputs/knowledge/coverage-audit.json",
        teaching_package="outputs/teaching-package.json",
        _chapters=chapter_paths,
    )


def _decode_json(outputs: Mapping[str, bytes], path: str) -> Mapping[str, Any]:
    content = outputs[path]
    if not isinstance(content, bytes):
        raise TeachingAssetValidationError("Managed asset content must be bytes")
    try:
        decoded = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TeachingAssetValidationError("Managed JSON asset is invalid") from exc
    if not isinstance(decoded, Mapping):
        raise TeachingAssetValidationError("Managed JSON asset must be an object")
    return decoded


def _require_chapter_identity(
    asset: Mapping[str, Any], chapter_id: str, chapter: Mapping[str, Any], *, kind: str
) -> None:
    if str(asset.get("content_chapter_id", "")) != chapter_id:
        raise TeachingAssetValidationError(f"{kind} asset does not match its frozen chapter")
    if str(asset.get("content_sha256", "")) != str(chapter["content_sha256"]):
        raise TeachingAssetValidationError(f"{kind} asset hash does not match frozen content")


def _validate_knowledge_asset(
    asset: Mapping[str, Any], chapter_id: str, chapter: Mapping[str, Any]
) -> dict[str, Any]:
    if asset.get("format") != _CHAPTER_KNOWLEDGE_FORMAT:
        raise TeachingAssetValidationError("Knowledge asset format is invalid")
    _require_chapter_identity(asset, chapter_id, chapter, kind="Knowledge")
    knowledge_points = _require_string_list(asset.get("knowledge_points"), field="knowledge points")
    raw_concepts = asset.get("concepts")
    if not isinstance(raw_concepts, list) or not raw_concepts or len(raw_concepts) > 128:
        raise TeachingAssetValidationError("Knowledge concepts must be a non-empty bounded list")
    concepts: dict[str, str] = {}
    for item in raw_concepts:
        if not isinstance(item, Mapping):
            raise TeachingAssetValidationError("Knowledge concept is invalid")
        concept_id = _require_string(item.get("concept_id"), field="concept id", limit=160)
        name = _require_string(item.get("name"), field="concept name", limit=500)
        if concept_id in concepts or name not in knowledge_points:
            raise TeachingAssetValidationError("Knowledge concept must uniquely match a knowledge point")
        evidence = item.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise TeachingAssetValidationError("Knowledge concept requires evidence")
        for locator in evidence:
            if not isinstance(locator, Mapping):
                raise TeachingAssetValidationError("Knowledge evidence is invalid")
            start, end = locator.get("start"), locator.get("end")
            if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end <= start:
                raise TeachingAssetValidationError("Knowledge evidence range is invalid")
        concepts[concept_id] = name
    if set(concepts.values()) != set(knowledge_points):
        raise TeachingAssetValidationError("Knowledge concepts must cover every knowledge point")
    relations = asset.get("relations")
    if not isinstance(relations, list) or len(relations) > 256:
        raise TeachingAssetValidationError("Knowledge relations must be a bounded list")
    for relation in relations:
        if not isinstance(relation, Mapping):
            raise TeachingAssetValidationError("Knowledge relation is invalid")
        if relation.get("from_concept_id") not in concepts or relation.get("to_concept_id") not in concepts:
            raise TeachingAssetValidationError("Knowledge relation references an unknown concept")
    prerequisites = asset.get("prerequisite_concept_ids")
    if not isinstance(prerequisites, list) or len(prerequisites) > 128:
        raise TeachingAssetValidationError("Knowledge prerequisites must be a bounded list")
    if len(prerequisites) != len(set(prerequisites)) or not all(isinstance(item, str) and item for item in prerequisites):
        raise TeachingAssetValidationError("Knowledge prerequisites are invalid")
    return {"knowledge_points": knowledge_points, "concepts": concepts}


def _validate_practice_asset(
    asset: Mapping[str, Any], chapter_id: str, chapter: Mapping[str, Any], knowledge: Mapping[str, Any]
) -> None:
    if asset.get("format") != _CHAPTER_PRACTICE_FORMAT:
        raise TeachingAssetValidationError("Practice asset format is invalid")
    _require_chapter_identity(asset, chapter_id, chapter, kind="Practice")
    questions = asset.get("questions")
    if not isinstance(questions, list) or not questions or len(questions) > 48:
        raise TeachingAssetValidationError("Practice questions must be a non-empty bounded list")
    positions: set[int] = set()
    concept_ids = set(knowledge["concepts"])
    knowledge_points = set(knowledge["knowledge_points"])
    for question in questions:
        if not isinstance(question, Mapping):
            raise TeachingAssetValidationError("Practice question is invalid")
        position = question.get("position")
        if not isinstance(position, int) or isinstance(position, bool) or position <= 0 or position in positions:
            raise TeachingAssetValidationError("Practice question positions are invalid")
        positions.add(position)
        if question.get("concept_id") not in concept_ids:
            raise TeachingAssetValidationError("Practice question references an unknown concept")
        if question.get("knowledge_point") not in knowledge_points:
            raise TeachingAssetValidationError("Practice question knowledge point is invalid")


def _validate_concept_index(
    asset: Mapping[str, Any], frozen: Mapping[str, Mapping[str, Any]], concepts: Mapping[str, tuple[str, str]]
) -> None:
    if asset.get("format") != _CONCEPT_INDEX_FORMAT:
        raise TeachingAssetValidationError("Concept index format is invalid")
    raw_concepts = asset.get("concepts")
    if not isinstance(raw_concepts, list) or len(raw_concepts) != len(concepts):
        raise TeachingAssetValidationError("Concept index must cover every verified concept exactly once")
    indexed: set[str] = set()
    for item in raw_concepts:
        if not isinstance(item, Mapping):
            raise TeachingAssetValidationError("Concept index item is invalid")
        concept_id = item.get("concept_id")
        if concept_id not in concepts or concept_id in indexed:
            raise TeachingAssetValidationError("Concept index references an unknown concept")
        indexed.add(concept_id)
        if item.get("name") != concepts[concept_id][1]:
            raise TeachingAssetValidationError("Concept index concept name is inconsistent")
        chapter_ids = item.get("content_chapter_ids")
        if not isinstance(chapter_ids, list) or not chapter_ids or set(chapter_ids) - set(frozen):
            raise TeachingAssetValidationError("Concept index references an unknown chapter")
        if concepts[concept_id][0] not in chapter_ids:
            raise TeachingAssetValidationError("Concept index omits its source chapter")
    relations = asset.get("relations")
    if not isinstance(relations, list) or len(relations) > 256:
        raise TeachingAssetValidationError("Concept index relations must be a bounded list")
    for relation in relations:
        if not isinstance(relation, Mapping) or relation.get("from_concept_id") not in indexed or relation.get("to_concept_id") not in indexed:
            raise TeachingAssetValidationError("Concept index relation references an unknown concept")


def _validate_coverage_audit(asset: Mapping[str, Any], frozen: Mapping[str, Mapping[str, Any]]) -> None:
    if asset.get("format") != _COVERAGE_AUDIT_FORMAT:
        raise TeachingAssetValidationError("Coverage audit format is invalid")
    chapters = asset.get("chapters")
    if not isinstance(chapters, list) or len(chapters) != len(frozen):
        raise TeachingAssetValidationError("Coverage audit must contain every frozen chapter")
    seen: set[str] = set()
    for item in chapters:
        if not isinstance(item, Mapping):
            raise TeachingAssetValidationError("Coverage audit chapter is invalid")
        chapter_id = str(item.get("content_chapter_id", ""))
        if chapter_id not in frozen or chapter_id in seen:
            raise TeachingAssetValidationError("Coverage audit references an unknown chapter")
        seen.add(chapter_id)
        if item.get("content_sha256") != frozen[chapter_id]["content_sha256"]:
            raise TeachingAssetValidationError("Coverage audit hash does not match frozen content")
        if item.get("status") != "complete" or item.get("missing") != []:
            raise TeachingAssetValidationError("Coverage audit is not complete")
        asset_kinds = item.get("asset_kinds")
        if not isinstance(asset_kinds, list) or set(asset_kinds) != set(_CHAPTER_ASSET_KINDS) or len(asset_kinds) != len(_CHAPTER_ASSET_KINDS):
            raise TeachingAssetValidationError("Coverage audit asset kinds are invalid")


def validate_teaching_assets(outputs: Mapping[str, bytes], frozen_input: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a complete v2 candidate and return only a safe archive manifest."""
    paths = expected_teaching_asset_paths(frozen_input)
    actual_paths = set(outputs)
    missing = paths.all_paths - actual_paths
    unknown = actual_paths - paths.all_paths
    if missing:
        raise TeachingAssetValidationError("Managed teaching bundle is missing required assets")
    if unknown:
        raise TeachingAssetValidationError("Managed teaching bundle contains an unknown asset")
    try:
        frozen = _frozen_chapters(frozen_input)
    except TeachingPackageValidationError as exc:
        raise TeachingAssetValidationError(str(exc)) from exc

    chapter_records: list[dict[str, Any]] = []
    concepts: dict[str, tuple[str, str]] = {}
    chapter_knowledge: dict[str, dict[str, Any]] = {}
    for chapter_id, chapter in frozen.items():
        chapter_paths = paths.for_chapter(chapter_id)
        knowledge_asset = _decode_json(outputs, chapter_paths.knowledge)
        knowledge = _validate_knowledge_asset(knowledge_asset, chapter_id, chapter)
        for concept_id, name in knowledge["concepts"].items():
            if concept_id in concepts:
                raise TeachingAssetValidationError("Knowledge concept ids must be unique across the bundle")
            concepts[concept_id] = (chapter_id, name)
        chapter_knowledge[chapter_id] = knowledge
        practice_asset = _decode_json(outputs, chapter_paths.practice)
        _validate_practice_asset(practice_asset, chapter_id, chapter, knowledge)
        toolkit = outputs[chapter_paths.toolkit]
        if not isinstance(toolkit, bytes):
            raise TeachingAssetValidationError("Toolkit asset content must be bytes")
        _require_string(toolkit.decode("utf-8"), field="Toolkit asset")
        assets = []
        for kind, path in (("knowledge", chapter_paths.knowledge), ("toolkit", chapter_paths.toolkit), ("practice", chapter_paths.practice)):
            content = outputs[path]
            assets.append({"kind": kind, "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
        chapter_records.append(
            {
                "content_chapter_id": chapter_id,
                "content_sha256": chapter["content_sha256"],
                "assets": assets,
                "coverage_status": "complete",
                "concept_count": len(knowledge["concepts"]),
            }
        )

    concept_index = _decode_json(outputs, paths.concept_index)
    _validate_concept_index(concept_index, frozen, concepts)
    coverage_audit = _decode_json(outputs, paths.coverage_audit)
    _validate_coverage_audit(coverage_audit, frozen)
    package_candidate = _decode_json(outputs, paths.teaching_package)
    try:
        package = validate_teaching_package(package_candidate, frozen_input)
    except TeachingPackageValidationError as exc:
        raise TeachingAssetValidationError(str(exc)) from exc
    for chapter in package["chapters"]:
        knowledge = chapter_knowledge[chapter["content_chapter_id"]]
        if set(chapter["knowledge_points"]) != set(knowledge["knowledge_points"]):
            raise TeachingAssetValidationError("Teaching package knowledge points do not match chapter knowledge")

    return {
        "format": _ASSET_FORMAT,
        "concept_index": {
            "sha256": hashlib.sha256(outputs[paths.concept_index]).hexdigest(),
            "size_bytes": len(outputs[paths.concept_index]),
            "concept_count": len(concepts),
        },
        "coverage_audit": {
            "sha256": hashlib.sha256(outputs[paths.coverage_audit]).hexdigest(),
            "size_bytes": len(outputs[paths.coverage_audit]),
            "status": "complete",
        },
        "chapters": chapter_records,
        "teaching_package": package,
    }
