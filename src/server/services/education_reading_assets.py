"""Input and output contracts for canonical per-Reading asset generation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import PurePosixPath
from typing import Any


READING_ASSET_FORMAT = "langalpha-managed-reading-assets/v2"
MAX_READING_ASSET_FILES = 1_000
MAX_READING_ASSET_BYTES = 4 * 1024 * 1024
_SAFE_COMPONENT_RE = re.compile(r"[^0-9A-Za-z._-]+")
_OUTPUT_NAMES = ("knowledge.md", "glossary.md", "cheatsheet.md")


class ReadingAssetValidationError(ValueError):
    """A per-Reading asset bundle violates the managed output contract."""


def _safe_component(value: object, *, fallback: str) -> str:
    normalized = _SAFE_COMPONENT_RE.sub("-", str(value or "")).strip(".-_")
    return normalized[:80] or fallback


def _safe_output_path(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReadingAssetValidationError("Reading asset path must be non-empty")
    path = PurePosixPath(value.strip())
    if (
        path.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
        or not path.as_posix().endswith(".md")
    ):
        raise ReadingAssetValidationError("Reading asset path is invalid")
    return path.as_posix()


def _reading_output_paths(
    *, unit_position: int, unit_slug: str, slot: str
) -> dict[str, str]:
    prefix = f"readings/{unit_position:02d}-{unit_slug}/{slot}"
    return {name.removesuffix(".md"): f"{prefix}/{name}" for name in _OUTPUT_NAMES}


def build_reading_asset_inputs(
    job: Mapping[str, Any],
    frozen_input: Mapping[str, Any],
    scopes: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Build deterministic per-Reading slices and their output allow-list."""
    raw_units = job.get("units")
    if not isinstance(raw_units, list):
        raise ReadingAssetValidationError("Structure Units are unavailable")
    units_by_id = {
        str(unit.get("unit_id") or ""): unit
        for unit in raw_units
        if isinstance(unit, Mapping)
    }
    raw_sources = frozen_input.get("sources")
    if not isinstance(raw_sources, list):
        raise ReadingAssetValidationError("Frozen textbook sources are unavailable")
    sources_by_id = {
        str(source.get("source_id") or source.get("content_chapter_id") or ""): source
        for source in raw_sources
        if isinstance(source, Mapping)
    }

    files: dict[str, bytes] = {}
    readings: list[dict[str, Any]] = []
    for scope in sorted(
        scopes,
        key=lambda item: (int(item.get("line_start") or 0), str(item.get("slot") or "")),
    ):
        unit_id = str(scope.get("unit_id") or "")
        unit = units_by_id.get(unit_id)
        if not isinstance(unit, Mapping):
            raise ReadingAssetValidationError("Reading scope Unit is unavailable")
        unit_position = int(unit.get("position") or 0)
        unit_slug = _safe_component(
            unit.get("slug") or unit.get("title"),
            fallback=f"unit-{unit_position or 1}",
        )
        slot = str(scope.get("slot") or "")
        if slot not in {"reading_a", "reading_b"}:
            raise ReadingAssetValidationError("Reading scope slot is invalid")
        source = sources_by_id.get(str(scope.get("source_id") or ""))
        markdown = source.get("markdown") if isinstance(source, Mapping) else None
        if not isinstance(markdown, str):
            raise ReadingAssetValidationError("Reading source Markdown is unavailable")
        start = max(0, min(int(scope["char_start"]), len(markdown)))
        end = max(start, min(int(scope["char_end"]), len(markdown)))
        if end <= start:
            raise ReadingAssetValidationError("Reading source slice is empty")

        input_path = f"inputs/readings/{unit_position:02d}-{unit_slug}/{slot}.md"
        outputs = _reading_output_paths(
            unit_position=unit_position,
            unit_slug=unit_slug,
            slot=slot,
        )
        files[input_path] = markdown[start:end].encode("utf-8")
        readings.append(
            {
                "unit_id": unit_id,
                "unit_position": unit_position,
                "unit_slug": unit_slug,
                "slot": slot,
                "title": str(scope.get("title") or slot),
                "source_id": str(scope.get("source_id") or ""),
                "line_start": int(scope["line_start"]),
                "line_end": int(scope["line_end"]),
                "char_start": start,
                "char_end": end,
                "input_path": input_path,
                "outputs": outputs,
            }
        )
    if not readings:
        raise ReadingAssetValidationError("Structure has no verified Reading scopes")

    manifest = {
        "format": READING_ASSET_FORMAT,
        "readings": readings,
    }
    files["inputs/readings_manifest.json"] = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return {"format": READING_ASSET_FORMAT, "manifest": manifest, "files": files}


def validate_reading_asset_manifest(candidate: object) -> dict[str, Any]:
    """Validate and normalize the model-produced per-Reading output manifest."""
    if not isinstance(candidate, Mapping):
        raise ReadingAssetValidationError("Reading asset manifest must be an object")
    if candidate.get("format") != READING_ASSET_FORMAT:
        raise ReadingAssetValidationError("Reading asset manifest format is invalid")
    raw_readings = candidate.get("readings")
    if not isinstance(raw_readings, list) or not raw_readings:
        raise ReadingAssetValidationError("Reading asset manifest has no readings")
    readings: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_readings:
        if not isinstance(raw, Mapping):
            raise ReadingAssetValidationError("Reading asset entry is invalid")
        unit_id = str(raw.get("unit_id") or "")
        slot = str(raw.get("slot") or "")
        if not unit_id or slot not in {"reading_a", "reading_b"}:
            raise ReadingAssetValidationError("Reading asset identity is invalid")
        identity = (unit_id, slot)
        if identity in seen:
            raise ReadingAssetValidationError("Reading asset identity is duplicated")
        seen.add(identity)
        raw_outputs = raw.get("outputs")
        if not isinstance(raw_outputs, Mapping):
            raise ReadingAssetValidationError("Reading asset outputs are invalid")
        outputs = {
            name: _safe_output_path(raw_outputs.get(name))
            for name in ("knowledge", "glossary", "cheatsheet")
        }
        readings.append(
            {
                "unit_id": unit_id,
                "slot": slot,
                "title": str(raw.get("title") or slot),
                "outputs": outputs,
            }
        )
    expected_files = {
        path
        for reading in readings
        for path in reading["outputs"].values()
    }
    if len(expected_files) > MAX_READING_ASSET_FILES:
        raise ReadingAssetValidationError("Reading asset manifest is too large")
    return {"format": READING_ASSET_FORMAT, "readings": readings}


def expected_reading_asset_files(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    return tuple(
        path
        for reading in manifest.get("readings", [])
        if isinstance(reading, Mapping)
        for path in reading.get("outputs", {}).values()
    )


def validate_reading_asset_content(
    manifest: Mapping[str, Any],
    outputs: Mapping[str, bytes],
) -> dict[str, Any]:
    """Attach hashes to the fixed Markdown output set."""
    validated_readings: list[dict[str, Any]] = []
    for reading in manifest.get("readings", []):
        if not isinstance(reading, Mapping):
            raise ReadingAssetValidationError("Reading asset entry is invalid")
        files: dict[str, dict[str, Any]] = {}
        for name, relative_path in reading["outputs"].items():
            content = outputs.get(relative_path)
            if not isinstance(content, bytes) or not content.strip():
                raise ReadingAssetValidationError(
                    f"Reading asset file is missing: {relative_path}"
                )
            if len(content) > MAX_READING_ASSET_BYTES:
                raise ReadingAssetValidationError(
                    f"Reading asset file is too large: {relative_path}"
                )
            files[name] = {
                "path": relative_path,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        validated_readings.append(
            {
                **{key: reading[key] for key in ("unit_id", "slot", "title")},
                "files": files,
            }
        )
    return {
        "format": READING_ASSET_FORMAT,
        "readings": validated_readings,
    }
