"""Validate and normalize canonical book-to-skill reading scopes.

The canonical skill reports Unit and Reading boundaries as 1-based line ranges
into the frozen Markdown. This module is the single gate that turns those
ranges into the character offsets the rest of the pipeline uses, and it rejects
any structure whose ranges cannot be trusted. Nothing downstream may re-derive
a range.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from src.server.services.education_structure_validation import (
    TextbookStructureValidationError,
)


STRUCTURE_FORMAT_V2 = "langalpha-managed-textbook-structure/v2"
READING_SLOTS = ("reading_a", "reading_b")


class ScopeValidationError(TextbookStructureValidationError):
    """A reading scope cannot be trusted and must go back for review."""


def _require_int(value: Any, *, field: str, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ScopeValidationError(f"{where}.{field} must be an integer")
    return value


def _validate_range(
    item: Mapping[str, Any], *, where: str, line_count: int
) -> tuple[int, int]:
    start = _require_int(item.get("line_start"), field="line_start", where=where)
    end = _require_int(item.get("line_end"), field="line_end", where=where)
    if start < 1:
        raise ScopeValidationError(f"{where}.line_start must be 1 or greater")
    if end <= start:
        raise ScopeValidationError(f"{where}.line_end must be greater than line_start")
    if end > line_count + 1:
        raise ScopeValidationError(
            f"{where}.line_end {end} is past the end of a {line_count}-line source"
        )
    return start, end


def line_offsets(markdown: str) -> list[int]:
    """Return the character offset at the start of each 1-based line."""
    offsets = [0]
    for index, character in enumerate(markdown):
        if character == "\n":
            offsets.append(index + 1)
    return offsets


def _char_span(offsets: Sequence[int], markdown_len: int, start: int, end: int) -> tuple[int, int]:
    """Translate a 1-based, half-open line range into a character span."""
    first = offsets[min(start, len(offsets)) - 1]
    last = offsets[end - 1] if end - 1 < len(offsets) else markdown_len
    return first, last


def validate_structure_scopes(
    payload: Mapping[str, Any],
    *,
    markdown: str,
    source_id: str = "",
) -> list[dict[str, Any]]:
    """Return one normalized scope per reading, or raise ScopeValidationError."""
    if not isinstance(payload, Mapping):
        raise ScopeValidationError("Structure payload must be an object")
    if payload.get("format") != STRUCTURE_FORMAT_V2:
        raise ScopeValidationError(
            f"Structure format must be {STRUCTURE_FORMAT_V2}"
        )
    units = payload.get("units")
    if not isinstance(units, list) or not units:
        raise ScopeValidationError("Structure must contain at least one unit")

    offsets = line_offsets(markdown)
    line_count = len(offsets)
    markdown_len = len(markdown)
    scopes: list[dict[str, Any]] = []
    previous_unit_end = 0
    for unit_index, unit in enumerate(units):
        where = f"units[{unit_index}]"
        if not isinstance(unit, Mapping):
            raise ScopeValidationError(f"{where} must be an object")
        unit_start, unit_end = _validate_range(
            unit, where=where, line_count=line_count
        )
        if unit_start < previous_unit_end:
            raise ScopeValidationError(f"{where} overlaps the previous unit")
        previous_unit_end = unit_end
        readings = unit.get("readings")
        if not isinstance(readings, list):
            raise ScopeValidationError(f"{where}.readings must be a list")
        previous_reading_end = 0
        seen_slots: set[str] = set()
        for reading_index, reading in enumerate(readings):
            reading_where = f"{where}.readings[{reading_index}]"
            if not isinstance(reading, Mapping):
                raise ScopeValidationError(f"{reading_where} must be an object")
            slot = str(reading.get("slot") or "")
            if slot not in READING_SLOTS:
                raise ScopeValidationError(
                    f"{reading_where}.slot must be one of {READING_SLOTS}"
                )
            if slot in seen_slots:
                raise ScopeValidationError(
                    f"{where} repeats slot {slot}"
                )
            seen_slots.add(slot)
            title = str(reading.get("title") or "").strip()
            if not title:
                raise ScopeValidationError(f"{reading_where}.title must not be empty")
            start, end = _validate_range(
                reading, where=reading_where, line_count=line_count
            )
            if start < unit_start or end > unit_end:
                raise ScopeValidationError(
                    f"{reading_where} escapes its unit range "
                    f"[{unit_start}, {unit_end})"
                )
            if start < previous_reading_end:
                raise ScopeValidationError(
                    f"{reading_where} overlaps the previous reading"
                )
            previous_reading_end = end
            char_start, char_end = _char_span(offsets, markdown_len, start, end)
            if char_end <= char_start:
                raise ScopeValidationError(
                    f"{reading_where} resolves to an empty source span"
                )
            scopes.append(
                {
                    "unit_index": unit_index,
                    "slot": slot,
                    "title": title,
                    "line_start": start,
                    "line_end": end,
                    "char_start": char_start,
                    "char_end": char_end,
                    "summary": str(reading.get("summary") or ""),
                    "source_id": source_id,
                    "reading_skill": str(reading.get("reading_skill") or ""),
                    "vocabulary_building": str(
                        reading.get("vocabulary_building") or ""
                    ),
                    "critical_thinking": str(
                        reading.get("critical_thinking") or ""
                    ),
                }
            )
    return scopes
