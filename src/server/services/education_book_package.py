"""Deterministic validation for managed book-to-skill packages."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
from pathlib import PurePosixPath
import re
from typing import Any

BOOK_PACKAGE_FORMAT = "langalpha-book-package/v1"
MAX_BOOK_PACKAGE_BYTES = 16 * 1024 * 1024
MAX_FROZEN_MARKDOWN_BYTES = 64 * 1024 * 1024
MAX_CONTENT_NODES = 5_000
MAX_KNOWLEDGE_POINTS = 50_000
MAX_CONTENT_ASSETS = 5_000
MAX_SOURCE_REFS_PER_ITEM = 64
MAX_KNOWLEDGE_POINTS_PER_NODE = 200
MAX_TEXT_LENGTH = 30_000
MAX_TITLE_LENGTH = 255
MAX_LABEL_LENGTH = 255
MAX_KEY_LENGTH = 255
POSTGRES_INTEGER_MAX = 2_147_483_647

_COMMON_NODE_TYPES = frozenset(
    {
        "part",
        "unit",
        "chapter",
        "section",
        "reading",
        "lesson",
        "video",
        "exercise",
        "appendix",
        "reference",
        "other",
    }
)
_POINT_TYPES = frozenset(
    {
        "concept",
        "vocabulary",
        "reading_skill",
        "critical_thinking",
        "procedure",
        "problem_solving",
        "theme",
        "case",
        "other",
    }
)
_SAFE_SLUG_RE = re.compile(r"[^0-9A-Za-z._-]+")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_LINE_BREAK_RE = re.compile(r"\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]")
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x1f\x7f]")
_ASSET_EXTENSIONS = frozenset(
    {".md", ".json", ".txt", ".csv", ".png", ".jpg", ".jpeg", ".webp", ".svg"}
)


class BookPackageValidationError(ValueError):
    """A managed book package violates the integrity or safety contract."""


class _LineIndex:
    """Precomputed line-start offsets for one frozen Markdown document."""

    def __init__(self, markdown: str, requested_lines: set[int]) -> None:
        self._line_starts: dict[int, int] = {}
        if 1 in requested_lines:
            self._line_starts[1] = 0
        break_count = 0
        last_break_end = 0
        for break_count, match in enumerate(
            _LINE_BREAK_RE.finditer(markdown),
            start=1,
        ):
            line_number = break_count + 1
            if line_number in requested_lines:
                self._line_starts[line_number] = match.end()
            last_break_end = match.end()
        line_count = break_count + (
            1 if markdown and last_break_end != len(markdown) else 0
        )
        self._max_line_index = line_count + 1
        if self._max_line_index in requested_lines:
            self._line_starts[self._max_line_index] = len(markdown)

    def offsets(
        self,
        *,
        line_start: object,
        line_end: object,
        label: str,
    ) -> tuple[int, int]:
        if (
            not _is_int(line_start)
            or not _is_int(line_end)
            or line_start < 1
            or line_end <= line_start
            or line_end > self._max_line_index
            or line_start not in self._line_starts
            or line_end not in self._line_starts
        ):
            raise BookPackageValidationError(f"{label} line range is invalid")
        start = self._line_starts[line_start]
        end = self._line_starts[line_end]
        if end <= start:
            raise BookPackageValidationError(f"{label} line range is invalid")
        return start, end


def _build_line_index(
    markdown: str,
    requested_lines: set[int],
) -> _LineIndex:
    return _LineIndex(markdown, requested_lines)


def _collect_line_requests(package: Mapping[str, Any]) -> set[int]:
    requested: set[int] = set()
    for collection_name in ("content_nodes", "knowledge_points"):
        collection = package.get(collection_name)
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, Mapping):
                continue
            references = item.get("source_refs")
            if not isinstance(references, list):
                continue
            for reference in references:
                if not isinstance(reference, Mapping):
                    continue
                if "char_start" in reference or "char_end" in reference:
                    continue
                if "line_start" not in reference or "line_end" not in reference:
                    continue
                for field in ("line_start", "line_end"):
                    line_number = reference.get(field)
                    if _is_int(line_number) and line_number > 0:
                        requested.add(line_number)
    return requested


def _warn(warnings: list[str], warning: str) -> None:
    if warning not in warnings:
        warnings.append(warning)


def _open_type(value: object, *, label: str) -> str:
    normalized = _text(value, label=label, limit=64, required=True).lower()
    if _CONTROL_CHAR_RE.search(normalized):
        raise BookPackageValidationError(f"{label} must not contain control characters")
    return normalized


def _require_mapping(value: object, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BookPackageValidationError(f"{label} must be an object")
    return value


def _require_list(value: object, *, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise BookPackageValidationError(f"{label} must be a list")
    return value


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _text(
    value: object,
    *,
    label: str,
    limit: int,
    required: bool = False,
) -> str:
    if value is None:
        normalized = ""
    elif isinstance(value, str):
        normalized = value.strip()
    else:
        raise BookPackageValidationError(f"{label} must be a string")
    if required and not normalized:
        raise BookPackageValidationError(f"{label} must not be empty")
    if len(normalized) > limit:
        raise BookPackageValidationError(f"{label} exceeds the size limit")
    return normalized


def _key(value: object, *, label: str) -> str:
    normalized = _text(value, label=label, limit=MAX_KEY_LENGTH, required=True)
    if "\x00" in normalized:
        raise BookPackageValidationError(f"{label} contains a NUL byte")
    return normalized


def _slug(value: object, *, fallback: str) -> str:
    raw = str(value or "").strip()
    normalized = _SAFE_SLUG_RE.sub("-", raw).strip(".-").lower()
    return normalized[:255] or fallback


def _safe_asset_path(value: object) -> str:
    if not isinstance(value, str):
        raise BookPackageValidationError("asset path must be a string")
    if any(ord(character) < 32 for character in value):
        raise BookPackageValidationError(
            "asset path must stay inside the managed output root"
        )
    raw = value.strip()
    components = raw.split("/")
    if (
        not raw
        or "\\" in raw
        or raw.startswith("/")
        or any(component in {"", ".", ".."} for component in components)
    ):
        raise BookPackageValidationError(
            "asset path must stay inside the managed output root"
        )
    path = PurePosixPath(raw)
    if (
        path.is_absolute()
        or not path.parts
        or path.parts[0] != "outputs"
        or not path.name
        or path.suffix.casefold() not in _ASSET_EXTENSIONS
    ):
        raise BookPackageValidationError(
            "asset path must stay inside the managed output root"
        )
    return path.as_posix()


def _contains_nul(value: object) -> bool:
    if isinstance(value, str):
        return "\x00" in value
    if isinstance(value, Mapping):
        return any(
            _contains_nul(key) or _contains_nul(item) for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_nul(item) for item in value)
    return False


def _ensure_utf8_size(
    value: object,
    *,
    label: str,
    limit: int,
    allow_nan: bool = True,
    reject_nul: bool = False,
) -> None:
    if reject_nul and _contains_nul(value):
        raise BookPackageValidationError(f"{label} contains a NUL byte")
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=allow_nan,
        ).encode("utf-8")
    except UnicodeEncodeError as exc:
        raise BookPackageValidationError(f"{label} must be valid UTF-8") from exc
    except (TypeError, ValueError) as exc:
        raise BookPackageValidationError(f"{label} must be JSON-compatible") from exc
    if len(encoded) > limit:
        raise BookPackageValidationError(f"{label} exceeds the size limit")


def _ensure_utf8_bytes(
    value: str,
    *,
    label: str,
    limit: int,
) -> None:
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise BookPackageValidationError(f"{label} must be valid UTF-8") from exc
    if len(encoded) > limit:
        raise BookPackageValidationError(f"{label} exceeds the size limit")


def _offset_ref(
    *,
    markdown: str,
    start: int,
    end: int,
    label: str,
    source_id: object = None,
    line_range: tuple[int, int] | None = None,
) -> dict[str, Any]:
    if (
        not _is_int(start)
        or not _is_int(end)
        or start < 0
        or end <= start
        or end > len(markdown)
    ):
        raise BookPackageValidationError(
            f"{label} source reference is outside frozen Markdown"
        )
    normalized: dict[str, Any] = {
        "start": start,
        "end": end,
        "quote": markdown[start:end],
        "resolution_status": "resolved",
    }
    if source_id is not None:
        normalized["source_id"] = _text(
            source_id,
            label=f"{label} source_id",
            limit=MAX_KEY_LENGTH,
        )
    if line_range is not None:
        normalized["line_start"] = line_range[0]
        normalized["line_end"] = line_range[1]
    return normalized


def _normalize_source_ref(
    raw_reference: object,
    *,
    markdown: str,
    label: str,
    warnings: list[str],
    line_index: _LineIndex | None,
) -> dict[str, Any]:
    if not isinstance(raw_reference, Mapping):
        raise BookPackageValidationError(
            f"{label} source reference must be an object containing a range"
        )
    reference = _require_mapping(raw_reference, label=label)
    source_id = reference.get("source_id")

    has_any_char = "char_start" in reference or "char_end" in reference
    has_any_line = "line_start" in reference or "line_end" in reference
    if has_any_char and has_any_line:
        raise BookPackageValidationError(
            f"{label} source reference must use exactly one range family"
        )
    has_char_range = "char_start" in reference and "char_end" in reference
    has_line_range = "line_start" in reference and "line_end" in reference
    if has_char_range and not has_any_line:
        return _offset_ref(
            markdown=markdown,
            start=reference.get("char_start"),
            end=reference.get("char_end"),
            label=f"{label} char range",
            source_id=source_id,
        )
    if has_line_range and not has_any_char:
        line_start = reference.get("line_start")
        line_end = reference.get("line_end")
        active_line_index = line_index or _build_line_index(
            markdown,
            {
                line_number
                for line_number in (line_start, line_end)
                if _is_int(line_number) and line_number > 0
            },
        )
        start, end = active_line_index.offsets(
            line_start=line_start,
            line_end=line_end,
            label=f"{label} line range",
        )
        return _offset_ref(
            markdown=markdown,
            start=start,
            end=end,
            label=f"{label} line range",
            source_id=source_id,
            line_range=(line_start, line_end),
        )
    raise BookPackageValidationError(
        f"{label} source reference must contain exactly one complete char or line range"
    )


def _normalize_source_refs(
    value: object,
    *,
    markdown: str,
    label: str,
    warnings: list[str],
    line_index: _LineIndex | None,
) -> list[dict[str, Any]]:
    if value is None:
        _warn(warnings, "source_refs_missing")
        return []
    references = _require_list(value, label=f"{label} source_refs")
    if not references:
        _warn(warnings, "source_refs_missing")
    if len(references) > MAX_SOURCE_REFS_PER_ITEM:
        raise BookPackageValidationError(f"{label} has too many source refs")
    return [
        _normalize_source_ref(
            reference,
            markdown=markdown,
            label=f"{label} source_refs[{index}]",
            warnings=warnings,
            line_index=line_index,
        )
        for index, reference in enumerate(references)
    ]


def _source_span(source_refs: list[dict[str, Any]]) -> tuple[int, int] | None:
    starts = [
        reference["start"]
        for reference in source_refs
        if _is_int(reference.get("start"))
    ]
    ends = [
        reference["end"] for reference in source_refs if _is_int(reference.get("end"))
    ]
    if not starts or not ends:
        return None
    return min(starts), max(ends)


def _validate_hierarchy(
    nodes: list[dict[str, Any]],
    *,
    warnings: list[str],
) -> None:
    by_key = {node["node_key"]: node for node in nodes}
    for node in nodes:
        parent_key = node["parent_key"]
        if parent_key is not None and parent_key not in by_key:
            raise BookPackageValidationError(
                f"content node {node['node_key']} references a missing parent"
            )
        seen: set[str] = {node["node_key"]}
        ancestor = parent_key
        while ancestor is not None:
            if ancestor in seen:
                raise BookPackageValidationError(
                    "content node parent references must not contain a cycle"
                )
            seen.add(ancestor)
            ancestor = by_key[ancestor]["parent_key"]

    sibling_positions: set[tuple[str | None, int]] = set()
    for node in nodes:
        sibling_key = (node["parent_key"], node["position"])
        if sibling_key in sibling_positions:
            raise BookPackageValidationError(
                "sibling content node positions must be unique"
            )
        sibling_positions.add(sibling_key)

    if not any(node["parent_key"] is not None for node in nodes):
        _warn(warnings, "no_child_nodes")
    if not any(node["node_type"] == "reading" for node in nodes):
        _warn(warnings, "no_reading_nodes")

    sibling_spans: dict[str | None, list[tuple[int, int]]] = {}
    for node in nodes:
        span = _source_span(node["source_refs"])
        if span is not None:
            sibling_spans.setdefault(node["parent_key"], []).append(span)
    for spans in sibling_spans.values():
        spans.sort()
        for previous, current in zip(spans, spans[1:]):
            if current[0] <= previous[1]:
                _warn(warnings, "sibling_source_spans_overlap")
                break


def _normalize_nodes(
    value: object,
    *,
    markdown: str,
    warnings: list[str],
    line_index: _LineIndex | None,
) -> list[dict[str, Any]]:
    raw_nodes = _require_list(value, label="content_nodes")
    if len(raw_nodes) > MAX_CONTENT_NODES:
        raise BookPackageValidationError("content_nodes exceeds the size limit")
    nodes: list[dict[str, Any]] = []
    used_keys: set[str] = set()
    explicit_sibling_positions: dict[str | None, set[int]] = {}
    node_contexts: list[tuple[int, Mapping[str, Any], str, str | None]] = []
    for index, raw_node in enumerate(raw_nodes, start=1):
        node = _require_mapping(raw_node, label=f"content_nodes[{index - 1}]")
        node_key = _key(node.get("node_key"), label="node_key")
        if node_key in used_keys:
            raise BookPackageValidationError("node keys must be unique")
        used_keys.add(node_key)
        parent_value = node.get("parent_key")
        parent_key = (
            _key(parent_value, label="parent_key") if parent_value is not None else None
        )
        position = node.get("position")
        if position is not None:
            if not _is_int(position) or position < 1 or position > POSTGRES_INTEGER_MAX:
                raise BookPackageValidationError(
                    "node position must be a positive PostgreSQL INTEGER"
                )
            explicit_sibling_positions.setdefault(parent_key, set()).add(position)
        node_contexts.append((index, node, node_key, parent_key))

    assigned_sibling_positions = {
        parent_key: set(positions)
        for parent_key, positions in explicit_sibling_positions.items()
    }
    for index, node, node_key, parent_key in node_contexts:
        node_type = _open_type(node.get("node_type"), label="node_type")
        if node_type not in _COMMON_NODE_TYPES:
            _warn(warnings, "unknown_node_type")
        title = _text(
            node.get("title"),
            label="node title",
            limit=MAX_TITLE_LENGTH,
        )
        if not title:
            title = node_key
            _warn(warnings, "node_title_missing")
        raw_label = node.get("label")
        label = (
            _text(
                raw_label,
                label="node label",
                limit=MAX_LABEL_LENGTH,
            )
            if raw_label is not None
            else None
        )
        position = node.get("position")
        if position is None:
            sibling_positions = assigned_sibling_positions.setdefault(
                parent_key,
                set(),
            )
            position = 1
            while position in sibling_positions:
                position += 1
            sibling_positions.add(position)
            _warn(warnings, "node_position_defaulted")
        summary = _text(
            node.get("summary"),
            label="node summary",
            limit=MAX_TEXT_LENGTH,
        )
        if not summary:
            _warn(warnings, "node_summary_missing")
        metadata = node.get("metadata", {})
        if not isinstance(metadata, Mapping):
            metadata = {}
            _warn(warnings, "node_metadata_invalid")
        nodes.append(
            {
                "node_key": node_key,
                "parent_key": parent_key,
                "node_type": node_type,
                "label": label,
                "position": position,
                "slug": _slug(
                    node.get("slug") or node_key,
                    fallback=f"node-{index}",
                ),
                "title": title,
                "summary": summary,
                "source_refs": _normalize_source_refs(
                    node.get("source_refs"),
                    markdown=markdown,
                    label=f"node {node_key}",
                    warnings=warnings,
                    line_index=line_index,
                ),
                "metadata": dict(metadata),
            }
        )
    _validate_hierarchy(nodes, warnings=warnings)
    return nodes


def _point_confidence(
    value: object,
    *,
    warnings: list[str],
) -> float:
    if value is None:
        _warn(warnings, "knowledge_point_confidence_missing")
        return 1.0
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _warn(warnings, "knowledge_point_confidence_defaulted")
        return 1.0
    try:
        numeric = float(value)
    except OverflowError:
        _warn(warnings, "knowledge_point_confidence_defaulted")
        return 1.0
    if not math.isfinite(numeric):
        _warn(warnings, "knowledge_point_confidence_defaulted")
        return 1.0
    if numeric < 0 or numeric > 1:
        _warn(warnings, "knowledge_point_confidence_clamped")
        return min(1.0, max(0.0, numeric))
    return numeric


def _normalize_knowledge_points(
    value: object,
    *,
    nodes: list[dict[str, Any]],
    markdown: str,
    warnings: list[str],
    line_index: _LineIndex | None,
) -> list[dict[str, Any]]:
    raw_points = _require_list(value, label="knowledge_points")
    if len(raw_points) > MAX_KNOWLEDGE_POINTS:
        raise BookPackageValidationError("knowledge_points exceeds the size limit")
    nodes_by_key = {node["node_key"]: node for node in nodes}
    points: list[dict[str, Any]] = []
    used_keys: set[str] = set()
    for index, raw_point in enumerate(raw_points):
        point = _require_mapping(
            raw_point,
            label=f"knowledge_points[{index}]",
        )
        candidate_key = _key(
            point.get("candidate_key"),
            label="candidate_key",
        )
        if candidate_key in used_keys:
            raise BookPackageValidationError("candidate keys must be unique")
        used_keys.add(candidate_key)
        node_key = _key(point.get("node_key"), label="knowledge point node_key")
        node = nodes_by_key.get(node_key)
        if node is None:
            raise BookPackageValidationError(
                "knowledge point must reference a real content node"
            )
        source_refs = _normalize_source_refs(
            point.get("source_refs"),
            markdown=markdown,
            label=f"knowledge point {candidate_key}",
            warnings=warnings,
            line_index=line_index,
        )
        node_ranges = [
            (reference["start"], reference["end"]) for reference in node["source_refs"]
        ]
        if source_refs and not node_ranges:
            raise BookPackageValidationError(
                "knowledge point source refs require a node source ref"
            )
        if any(
            not any(
                reference["start"] >= node_start and reference["end"] <= node_end
                for node_start, node_end in node_ranges
            )
            for reference in source_refs
        ):
            raise BookPackageValidationError(
                "knowledge point source refs must stay inside its node span "
                "and one node source ref"
            )
        point_type = _open_type(point.get("point_type"), label="point_type")
        if point_type not in _POINT_TYPES:
            _warn(warnings, "unknown_point_type")
        title = _text(
            point.get("title"),
            label="knowledge point title",
            limit=MAX_TITLE_LENGTH,
        )
        if not title:
            title = candidate_key
            _warn(warnings, "knowledge_point_title_missing")
        summary = _text(
            point.get("summary"),
            label="knowledge point summary",
            limit=MAX_TEXT_LENGTH,
        )
        if not summary:
            _warn(warnings, "knowledge_point_summary_missing")
        metadata = point.get("metadata", {})
        if not isinstance(metadata, Mapping):
            metadata = {}
            _warn(warnings, "knowledge_point_metadata_invalid")
        points.append(
            {
                "candidate_key": candidate_key,
                "node_key": node_key,
                "point_type": point_type,
                "title": title,
                "summary": summary,
                "source_refs": source_refs,
                "confidence": _point_confidence(
                    point.get("confidence"),
                    warnings=warnings,
                ),
                "metadata": dict(metadata),
            }
        )
    if not points:
        _warn(warnings, "no_knowledge_points")
    return points


def _normalize_assets(
    value: object,
    *,
    nodes: list[dict[str, Any]],
    warnings: list[str],
) -> list[dict[str, Any]]:
    raw_assets = _require_list(value, label="assets")
    if len(raw_assets) > MAX_CONTENT_ASSETS:
        raise BookPackageValidationError("assets exceeds the size limit")
    nodes_by_key = {node["node_key"]: node for node in nodes}
    assets: list[dict[str, Any]] = []
    used_paths: set[str] = set()
    for index, raw_asset in enumerate(raw_assets):
        asset = _require_mapping(raw_asset, label=f"assets[{index}]")
        node_key = _key(asset.get("node_key"), label="asset node_key")
        if node_key not in nodes_by_key:
            raise BookPackageValidationError("asset must reference a real content node")
        kind = _text(
            asset.get("kind", asset.get("asset_type")),
            label="asset kind",
            limit=64,
            required=True,
        )
        path = _safe_asset_path(asset.get("path"))
        if path in used_paths:
            raise BookPackageValidationError("asset paths must be unique")
        used_paths.add(path)
        normalized: dict[str, Any] = {
            "node_key": node_key,
            "kind": kind,
            "path": path,
        }
        content_sha256 = asset.get("content_sha256")
        if content_sha256 is not None:
            normalized_sha256 = _text(
                content_sha256,
                label="asset content_sha256",
                limit=64,
                required=True,
            ).lower()
            if not _SHA256_RE.fullmatch(normalized_sha256):
                raise BookPackageValidationError(
                    "asset content_sha256 must be a SHA-256 digest"
                )
            normalized["content_sha256"] = normalized_sha256
        size_bytes = asset.get("size_bytes")
        if size_bytes is not None:
            if (
                not _is_int(size_bytes)
                or size_bytes < 0
                or size_bytes > POSTGRES_INTEGER_MAX
            ):
                raise BookPackageValidationError(
                    "asset size_bytes must be a non-negative PostgreSQL INTEGER"
                )
            normalized["size_bytes"] = size_bytes
        metadata = asset.get("metadata", {})
        if not isinstance(metadata, Mapping):
            metadata = {}
            _warn(warnings, "asset_metadata_invalid")
        normalized["metadata"] = dict(metadata)
        assets.append(normalized)

    nodes_with_assets = {asset["node_key"] for asset in assets}
    if any(node["node_key"] not in nodes_with_assets for node in nodes):
        _warn(warnings, "node_assets_missing")
    return assets


def _warn_point_density(
    nodes: list[dict[str, Any]],
    points: list[dict[str, Any]],
    warnings: list[str],
) -> None:
    counts = {node["node_key"]: 0 for node in nodes}
    for point in points:
        counts[point["node_key"]] += 1
    if points and any(count == 0 for count in counts.values()):
        _warn(warnings, "node_knowledge_points_missing")
    if any(count > MAX_KNOWLEDGE_POINTS_PER_NODE for count in counts.values()):
        _warn(warnings, "node_too_many_knowledge_points")


def validate_book_package(
    candidate: object,
    *,
    markdown: str,
) -> tuple[dict[str, Any], list[str]]:
    """Normalize a managed package while enforcing only integrity limits.

    Non-standard textbook shapes remain valid. Structural oddities are
    returned as warnings so review can decide how to handle them.
    """
    if not isinstance(markdown, str):
        raise BookPackageValidationError("frozen Markdown must be a string")
    _ensure_utf8_bytes(
        markdown,
        label="frozen Markdown",
        limit=MAX_FROZEN_MARKDOWN_BYTES,
    )
    _ensure_utf8_size(
        candidate,
        label="book package",
        limit=MAX_BOOK_PACKAGE_BYTES,
    )
    package = _require_mapping(candidate, label="book package")
    if package.get("format") != BOOK_PACKAGE_FORMAT:
        raise BookPackageValidationError("book package format is invalid")
    source_revision = _text(
        package.get("source_revision"),
        label="source_revision",
        limit=MAX_KEY_LENGTH,
        required=True,
    )

    warnings: list[str] = []
    line_requests = _collect_line_requests(package)
    line_index = _build_line_index(markdown, line_requests) if line_requests else None
    nodes = _normalize_nodes(
        package.get("content_nodes"),
        markdown=markdown,
        warnings=warnings,
        line_index=line_index,
    )
    points = _normalize_knowledge_points(
        package.get("knowledge_points"),
        nodes=nodes,
        markdown=markdown,
        warnings=warnings,
        line_index=line_index,
    )
    assets = _normalize_assets(
        package.get("assets"),
        nodes=nodes,
        warnings=warnings,
    )
    _warn_point_density(nodes, points, warnings)
    normalized = {
        "format": BOOK_PACKAGE_FORMAT,
        "source_revision": source_revision,
        "content_nodes": nodes,
        "knowledge_points": points,
        "assets": assets,
    }
    _ensure_utf8_size(
        normalized,
        label="normalized book package",
        limit=MAX_BOOK_PACKAGE_BYTES,
        allow_nan=False,
        reject_nul=True,
    )
    return normalized, warnings
