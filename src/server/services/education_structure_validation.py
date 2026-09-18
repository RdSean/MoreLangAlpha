"""Validation for untrusted managed-PTC textbook structure candidates."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any


_STRUCTURE_FORMAT = "langalpha-managed-textbook-structure/v1"
_MAX_UNITS = 500
_MAX_KNOWLEDGE_POINTS_PER_UNIT = 200
_MAX_SOURCE_REFS = 32
_MAX_TEXT_LENGTH = 30_000
_MAX_TITLE_LENGTH = 255
_SAFE_SLUG_RE = re.compile(r"[^0-9A-Za-z._-]+")
_UNIT_TYPES = frozenset({"teaching", "front_matter", "reference", "appendix"})


class TextbookStructureValidationError(ValueError):
    """A managed structure candidate cannot become a reviewable structure."""


def _require_text(
    value: object,
    *,
    field: str,
    limit: int = _MAX_TEXT_LENGTH,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TextbookStructureValidationError(
            f"{field} must be a non-empty string"
        )
    normalized = value.strip()
    if len(normalized) > limit:
        raise TextbookStructureValidationError(
            f"{field} exceeds its maximum length"
        )
    return normalized


def _safe_slug(value: object, *, field: str) -> str:
    normalized = _SAFE_SLUG_RE.sub(
        "-", _require_text(value, field=field, limit=255)
    ).strip(".-").lower()[:80]
    if not normalized:
        raise TextbookStructureValidationError(f"{field} is invalid")
    return normalized


def _require_confidence(value: object, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TextbookStructureValidationError(
            f"{field} must be a number between 0 and 1"
        )
    confidence = float(value)
    if confidence < 0 or confidence > 1:
        raise TextbookStructureValidationError(
            f"{field} must be between 0 and 1"
        )
    return confidence


def _frozen_sources(
    frozen_input: Mapping[str, Any],
) -> dict[str, str | None]:
    raw_sources = frozen_input.get("sources")
    if raw_sources is None:
        raw_sources = frozen_input.get("chapters")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise TextbookStructureValidationError(
            "Frozen input must contain sources or chapters"
        )
    sources: dict[str, str | None] = {}
    for raw_source in raw_sources:
        if not isinstance(raw_source, Mapping):
            raise TextbookStructureValidationError("Frozen source is invalid")
        source_id = str(
            raw_source.get("source_id")
            or raw_source.get("content_chapter_id")
            or ""
        ).strip()
        if not source_id:
            raise TextbookStructureValidationError(
                "Frozen source identity is invalid"
            )
        if source_id in sources:
            raise TextbookStructureValidationError(
                "Frozen source identities must be unique"
            )
        markdown = raw_source.get("markdown")
        sources[source_id] = (
            markdown if isinstance(markdown, str) and markdown else None
        )
    return sources


def _normalize_source_refs(
    value: object,
    *,
    field: str,
    sources: Mapping[str, str | None],
) -> list[dict[str, Any]]:
    if not isinstance(value, list) or not value:
        raise TextbookStructureValidationError(
            f"{field} must contain at least one source reference"
        )
    if len(value) > _MAX_SOURCE_REFS:
        raise TextbookStructureValidationError(
            f"{field} contains too many source references"
        )
    normalized: list[dict[str, Any]] = []
    for reference in value:
        if not isinstance(reference, Mapping):
            raise TextbookStructureValidationError(
                f"{field} source reference is invalid"
            )
        source_id = _require_text(
            reference.get("source_id"),
            field=f"{field} source_id",
            limit=255,
        )
        if source_id not in sources:
            raise TextbookStructureValidationError(
                f"{field} references an unknown source"
            )
        start = reference.get("start")
        end = reference.get("end")
        if (
            not isinstance(start, int)
            or isinstance(start, bool)
            or not isinstance(end, int)
            or isinstance(end, bool)
            or start < 0
            or end <= start
        ):
            raise TextbookStructureValidationError(
                f"{field} source range is invalid"
            )
        markdown = sources[source_id]
        if markdown is not None and end > len(markdown):
            raise TextbookStructureValidationError(
                f"{field} source range exceeds the frozen source"
            )
        item: dict[str, Any] = {
            "source_id": source_id,
            "start": start,
            "end": end,
        }
        quote = reference.get("quote")
        if quote is not None:
            item["quote"] = _require_text(
                quote,
                field=f"{field} quote",
                limit=500,
            )
        heading_path = reference.get("heading_path")
        if heading_path is not None:
            if (
                not isinstance(heading_path, list)
                or len(heading_path) > 8
                or any(not isinstance(item, str) for item in heading_path)
            ):
                raise TextbookStructureValidationError(
                    f"{field} heading_path is invalid"
                )
            item["heading_path"] = [
                _require_text(value, field=f"{field} heading", limit=255)
                for value in heading_path
            ]
        normalized.append(item)
    return normalized


def _normalize_knowledge_point(
    value: object,
    *,
    index: int,
    sources: Mapping[str, str | None],
    positions: set[int],
    slugs: set[str],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TextbookStructureValidationError(
            f"knowledge point {index} must be an object"
        )
    position = value.get("position")
    if (
        not isinstance(position, int)
        or isinstance(position, bool)
        or position <= 0
    ):
        raise TextbookStructureValidationError(
            f"knowledge point {index} position is invalid"
        )
    if position in positions:
        raise TextbookStructureValidationError(
            "knowledge point positions must be unique within a Unit"
        )
    positions.add(position)
    slug = _safe_slug(
        value.get("slug"), field=f"knowledge point {index} slug"
    )
    if slug in slugs:
        raise TextbookStructureValidationError(
            "knowledge point slugs must be unique within a Unit"
        )
    slugs.add(slug)
    summary = value.get("summary", "")
    if not isinstance(summary, str):
        raise TextbookStructureValidationError(
            f"knowledge point {index} summary must be a string"
        )
    return {
        "position": position,
        "slug": slug,
        "title": _require_text(
            value.get("title"),
            field=f"knowledge point {index} title",
            limit=_MAX_TITLE_LENGTH,
        ),
        "summary": summary.strip(),
        "source_refs": _normalize_source_refs(
            value.get("source_refs"),
            field=f"knowledge point {index}",
            sources=sources,
        ),
        "confidence": _require_confidence(
            value.get("confidence"),
            field=f"knowledge point {index} confidence",
        ),
        "status": "review",
    }


def _normalize_unit(
    value: object,
    *,
    index: int,
    sources: Mapping[str, str | None],
    positions: set[int],
    slugs: set[str],
) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TextbookStructureValidationError(f"Unit {index} must be an object")
    position = value.get("position")
    if (
        not isinstance(position, int)
        or isinstance(position, bool)
        or position <= 0
    ):
        raise TextbookStructureValidationError(
            f"Unit {index} position is invalid"
        )
    if position in positions:
        raise TextbookStructureValidationError("Unit positions must be unique")
    positions.add(position)
    slug = _safe_slug(value.get("slug"), field=f"Unit {index} slug")
    if slug in slugs:
        raise TextbookStructureValidationError("Unit slugs must be unique")
    slugs.add(slug)
    unit_type = value.get("unit_type")
    if unit_type not in _UNIT_TYPES:
        raise TextbookStructureValidationError(f"Unit {index} type is invalid")
    summary = value.get("summary", "")
    if not isinstance(summary, str):
        raise TextbookStructureValidationError(
            f"Unit {index} summary must be a string"
        )
    raw_knowledge_points = value.get("knowledge_points", [])
    if not isinstance(raw_knowledge_points, list):
        raise TextbookStructureValidationError(
            f"Unit {index} knowledge_points must be a list"
        )
    if len(raw_knowledge_points) > _MAX_KNOWLEDGE_POINTS_PER_UNIT:
        raise TextbookStructureValidationError(
            f"Unit {index} contains too many knowledge points"
        )
    if unit_type != "teaching" and raw_knowledge_points:
        raise TextbookStructureValidationError(
            f"non-teaching Unit {index} must not contain knowledge points"
        )
    knowledge_point_positions: set[int] = set()
    knowledge_point_slugs: set[str] = set()
    knowledge_points = [
        _normalize_knowledge_point(
            knowledge_point,
            index=knowledge_point_index,
            sources=sources,
            positions=knowledge_point_positions,
            slugs=knowledge_point_slugs,
        )
        for knowledge_point_index, knowledge_point in enumerate(
            raw_knowledge_points, start=1
        )
    ]
    return {
        "position": position,
        "slug": slug,
        "title": _require_text(
            value.get("title"),
            field=f"Unit {index} title",
            limit=_MAX_TITLE_LENGTH,
        ),
        "summary": summary.strip(),
        "unit_type": unit_type,
        "source_refs": _normalize_source_refs(
            value.get("source_refs"),
            field=f"Unit {index}",
            sources=sources,
        ),
        "confidence": _require_confidence(
            value.get("confidence"),
            field=f"Unit {index} confidence",
        ),
        "status": "review",
        "knowledge_points": knowledge_points,
    }


def validate_textbook_structure(
    candidate: object,
    frozen_input: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a safe normalized structure or reject the candidate."""
    if not isinstance(candidate, Mapping):
        raise TextbookStructureValidationError("Structure must be an object")
    if candidate.get("format") != _STRUCTURE_FORMAT:
        raise TextbookStructureValidationError("Structure format is invalid")
    raw_units = candidate.get("units")
    if not isinstance(raw_units, list) or not raw_units:
        raise TextbookStructureValidationError(
            "Structure must contain at least one Unit"
        )
    if len(raw_units) > _MAX_UNITS:
        raise TextbookStructureValidationError("Structure contains too many Units")
    sources = _frozen_sources(frozen_input)
    positions: set[int] = set()
    slugs: set[str] = set()
    units = [
        _normalize_unit(
            unit,
            index=index,
            sources=sources,
            positions=positions,
            slugs=slugs,
        )
        for index, unit in enumerate(raw_units, start=1)
    ]
    return {
        "format": _STRUCTURE_FORMAT,
        "units": sorted(units, key=lambda unit: unit["position"]),
    }
