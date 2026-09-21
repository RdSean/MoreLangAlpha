"""Tolerant normalization for untrusted textbook structure candidates."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any

from src.server.services.education_source_refs import (
    SourceReferenceResolutionError,
    resolve_source_ref,
)


_STRUCTURE_FORMAT = "langalpha-managed-textbook-structure/v1"
_MAX_UNITS = 500
_MAX_KNOWLEDGE_POINTS_PER_UNIT = 200
_MAX_SOURCE_REFS = 32
_MAX_TEXT_LENGTH = 30_000
_MAX_TITLE_LENGTH = 255
_SAFE_SLUG_RE = re.compile(r"[^0-9A-Za-z._-]+")
_UNIT_TYPES = frozenset({"teaching", "front_matter", "reference", "appendix"})


class TextbookStructureValidationError(ValueError):
    """A textbook structure cannot be represented as usable review content."""


def _text(
    value: object,
    *,
    fallback: str = "",
    limit: int = _MAX_TEXT_LENGTH,
) -> str:
    if value is None:
        return fallback
    normalized = str(value).strip()
    if not normalized:
        return fallback
    return normalized[:limit]


def _slug(value: object, *, fallback: str) -> str:
    normalized = _SAFE_SLUG_RE.sub("-", str(value or "").strip()).strip(".-").lower()
    return normalized[:80] or fallback


def _unique_slug(
    value: object,
    *,
    fallback: str,
    used: set[str],
    warning_code: str,
    warnings: list[str],
) -> str:
    base = _slug(value, fallback=fallback)
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base[:74]}-{suffix}"
        suffix += 1
    if candidate != base:
        warnings.append(warning_code)
    used.add(candidate)
    return candidate


def _confidence(
    value: object,
    *,
    default: float,
    field: str,
    warnings: list[str],
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        warnings.append(f"{field}_defaulted")
        return default
    numeric = float(value)
    if numeric < 0 or numeric > 1:
        warnings.append(f"{field}_clamped")
        return min(1.0, max(0.0, numeric))
    return numeric


def _frozen_sources(
    frozen_input: Mapping[str, Any],
) -> tuple[dict[str, str], set[str]]:
    raw_sources = frozen_input.get("sources")
    if raw_sources is None:
        raw_sources = frozen_input.get("chapters")
    if not isinstance(raw_sources, list) or not raw_sources:
        raise TextbookStructureValidationError(
            "Frozen input must contain sources or chapters"
        )
    markdown_by_source: dict[str, str] = {}
    known_source_ids: set[str] = set()
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
        if source_id in known_source_ids:
            raise TextbookStructureValidationError(
                "Frozen source identities must be unique"
            )
        known_source_ids.add(source_id)
        markdown = raw_source.get("markdown")
        if isinstance(markdown, str):
            markdown_by_source[source_id] = markdown
    return markdown_by_source, known_source_ids


def _legacy_quote(reference: Mapping[str, Any], markdown_by_source: Mapping[str, str]) -> str:
    source_id = str(reference.get("source_id") or "")
    markdown = markdown_by_source.get(source_id)
    start = reference.get("start")
    end = reference.get("end")
    if (
        not markdown
        or not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 0
        or end <= start
        or end > len(markdown)
    ):
        return ""
    return markdown[start:end]


def _normalize_source_refs(
    value: object,
    *,
    markdown_by_source: Mapping[str, str],
    warning_prefix: str,
    warnings: list[str],
) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        warnings.append(f"{warning_prefix}_source_refs_invalid")
        return []
    normalized: list[dict[str, Any]] = []
    for raw_reference in value[:_MAX_SOURCE_REFS]:
        if not isinstance(raw_reference, Mapping):
            warnings.append(f"{warning_prefix}_source_ref_skipped")
            continue
        source_id = str(raw_reference.get("source_id") or "").strip() or None
        quote = _text(raw_reference.get("quote"), limit=2_000)
        if not quote:
            quote = _legacy_quote(raw_reference, markdown_by_source)
            if quote:
                warnings.append("legacy_source_offsets_recovered")
        if not quote:
            warnings.append(f"{warning_prefix}_source_ref_skipped")
            continue
        try:
            resolved = resolve_source_ref(
                sources=markdown_by_source,
                source_id=source_id,
                quote=quote,
            )
        except SourceReferenceResolutionError:
            warnings.append(f"{warning_prefix}_source_ref_skipped")
            continue
        warnings.extend(resolved.pop("warnings", []))
        heading_path = raw_reference.get("heading_path")
        if isinstance(heading_path, list):
            resolved["heading_path"] = [
                _text(item, limit=255)
                for item in heading_path[:8]
                if isinstance(item, str) and _text(item)
            ]
        normalized.append(resolved)
    if len(value) > _MAX_SOURCE_REFS:
        warnings.append(f"{warning_prefix}_source_refs_truncated")
    return normalized


def _normalize_knowledge_point(
    value: object,
    *,
    index: int,
    markdown_by_source: Mapping[str, str],
    used_slugs: set[str],
    warnings: list[str],
) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        warnings.append("knowledge_point_skipped_invalid")
        return None
    title = _text(
        value.get("title"),
        fallback=f"Knowledge point {index}",
        limit=_MAX_TITLE_LENGTH,
    )
    if title == f"Knowledge point {index}":
        warnings.append("knowledge_point_title_defaulted")
    source_refs = _normalize_source_refs(
        value.get("source_refs"),
        markdown_by_source=markdown_by_source,
        warning_prefix="knowledge_point",
        warnings=warnings,
    )
    if not source_refs:
        warnings.append("knowledge_point_source_refs_missing")
    return {
        "position": index,
        "slug": _unique_slug(
            value.get("slug") or title,
            fallback=f"kp-{index:02d}",
            used=used_slugs,
            warning_code="knowledge_point_slug_deduplicated",
            warnings=warnings,
        ),
        "title": title,
        "summary": _text(value.get("summary"), limit=_MAX_TEXT_LENGTH),
        "scope_slot": (
            str(value.get("scope_slot"))
            if value.get("scope_slot") in {"reading_a", "reading_b"}
            else None
        ),
        "source_refs": source_refs,
        "confidence": _confidence(
            value.get("confidence"),
            default=1.0,
            field="knowledge_point_confidence",
            warnings=warnings,
        ),
        "status": "review",
    }


def _normalize_unit(
    value: object,
    *,
    index: int,
    markdown_by_source: Mapping[str, str],
    used_slugs: set[str],
    warnings: list[str],
) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        warnings.append("unit_skipped_invalid")
        return None
    title = _text(
        value.get("title"),
        fallback=f"Unit {index}",
        limit=_MAX_TITLE_LENGTH,
    )
    if title == f"Unit {index}":
        warnings.append("unit_title_defaulted")
    raw_knowledge_points = value.get("knowledge_points", [])
    if not isinstance(raw_knowledge_points, list):
        warnings.append("unit_knowledge_points_invalid")
        raw_knowledge_points = []
    unit_type = value.get("unit_type")
    if unit_type not in _UNIT_TYPES:
        unit_type = "teaching"
        warnings.append("unit_type_defaulted")
    if unit_type != "teaching" and raw_knowledge_points:
        unit_type = "teaching"
        warnings.append("unit_type_promoted")
    source_refs = _normalize_source_refs(
        value.get("source_refs"),
        markdown_by_source=markdown_by_source,
        warning_prefix="unit",
        warnings=warnings,
    )
    if not source_refs:
        warnings.append("unit_source_refs_missing")
    knowledge_point_slugs: set[str] = set()
    knowledge_points: list[dict[str, Any]] = []
    for knowledge_point_index, knowledge_point in enumerate(
        raw_knowledge_points[:_MAX_KNOWLEDGE_POINTS_PER_UNIT],
        start=1,
    ):
        normalized = _normalize_knowledge_point(
            knowledge_point,
            index=knowledge_point_index,
            markdown_by_source=markdown_by_source,
            used_slugs=knowledge_point_slugs,
            warnings=warnings,
        )
        if normalized is not None:
            knowledge_points.append(normalized)
    if len(raw_knowledge_points) > _MAX_KNOWLEDGE_POINTS_PER_UNIT:
        warnings.append("unit_knowledge_points_truncated")
    return {
        "position": index,
        "slug": _unique_slug(
            value.get("slug") or title,
            fallback=f"unit-{index:02d}",
            used=used_slugs,
            warning_code="unit_slug_deduplicated",
            warnings=warnings,
        ),
        "title": title,
        "summary": _text(value.get("summary"), limit=_MAX_TEXT_LENGTH),
        "unit_type": unit_type,
        "source_refs": source_refs,
        "confidence": _confidence(
            value.get("confidence"),
            default=1.0,
            field="unit_confidence",
            warnings=warnings,
        ),
        "status": "review",
        "knowledge_points": knowledge_points,
    }


def validate_textbook_structure(
    candidate: object,
    frozen_input: Mapping[str, Any],
) -> dict[str, Any]:
    """Normalize a book-to-skill structure into safe review content."""
    if not isinstance(candidate, Mapping):
        raise TextbookStructureValidationError("Structure must be an object")
    if candidate.get("format") != _STRUCTURE_FORMAT:
        raise TextbookStructureValidationError("Structure format is invalid")
    raw_units = candidate.get("units")
    if not isinstance(raw_units, list) or not raw_units:
        raise TextbookStructureValidationError(
            "Structure must contain at least one Unit"
        )
    markdown_by_source, _ = _frozen_sources(frozen_input)
    warnings: list[str] = []
    unit_slugs: set[str] = set()
    units: list[dict[str, Any]] = []
    for unit_index, raw_unit in enumerate(raw_units[:_MAX_UNITS], start=1):
        normalized = _normalize_unit(
            raw_unit,
            index=unit_index,
            markdown_by_source=markdown_by_source,
            used_slugs=unit_slugs,
            warnings=warnings,
        )
        if normalized is not None:
            units.append(normalized)
    if len(raw_units) > _MAX_UNITS:
        warnings.append("structure_units_truncated")
    if not units:
        raise TextbookStructureValidationError(
            "Structure has no usable Units"
        )
    return {
        "format": _STRUCTURE_FORMAT,
        "units": units,
        "warnings": warnings,
    }


def normalize_v2_units(
    payload: Mapping[str, Any],
    *,
    warnings: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Turn a v2 reading-scope payload into units for the review projection.

    Knowledge points are intentionally absent: the canonical skill declares
    Reading boundaries, and the parent adds or edits knowledge points inside
    those boundaries during structure review.
    """
    collected = warnings if warnings is not None else []
    units: list[dict[str, Any]] = []
    unit_slugs: set[str] = set()
    for index, raw_unit in enumerate(payload.get("units", []), start=1):
        if not isinstance(raw_unit, Mapping):
            collected.append("unit_skipped_invalid")
            continue
        number = raw_unit.get("unit")
        theme = _text(
            raw_unit.get("theme"),
            fallback=f"Unit {index}",
            limit=_MAX_TITLE_LENGTH,
        )
        title = (
            f"Unit {number}: {theme}"
            if isinstance(number, int) and not isinstance(number, bool)
            else theme
        )
        units.append(
            {
                "position": index,
                "slug": _unique_slug(
                    title,
                    fallback=f"unit-{index}",
                    used=unit_slugs,
                    warning_code="unit_slug_deduplicated",
                    warnings=collected,
                ),
                "title": title,
                "summary": str(raw_unit.get("summary") or ""),
                "unit_type": "teaching",
                "source_refs": [],
                "confidence": 1.0,
                "status": "review",
                "knowledge_points": [],
            }
        )
    if not units:
        raise TextbookStructureValidationError("Structure has no usable Units")
    return units
