"""Strict import contract for service-managed more-to-skills structures."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from jsonschema.validators import validator_for


_SKILL_ROOT = (
    Path(__file__).resolve().parents[3]
    / "plugins"
    / "langalpha_local"
    / "skills"
    / "more-to-skills"
)
_SKILL_PATH = _SKILL_ROOT / "SKILL.md"
_SCHEMA_PATH = _SKILL_ROOT / "schemas" / "book-structure.schema.json"
_SUPPORTED_SCHEMA_MAJOR = 2
_MORE_TO_SKILLS_VERSION = "2.1.0"


class BookStructureValidationError(ValueError):
    """Raised when a managed structure cannot be imported safely."""


@dataclass(frozen=True, slots=True)
class TrustedBookSource:
    """Service-owned source coordinates that replace model-provided metadata."""

    path: str
    filename: str
    format: str
    total_lines: int
    anchor_mode: str
    line_offset: int | None = None
    source_total_lines: int | None = None
    workdir_text: str | None = None
    page_label: str | None = None

    def as_structure_source(self) -> dict[str, object]:
        source: dict[str, object] = {
            "path": self.path,
            "filename": self.filename,
            "format": self.format,
            "total_lines": self.total_lines,
            "anchor_mode": self.anchor_mode,
        }
        optional = {
            "line_offset": self.line_offset,
            "source_total_lines": self.source_total_lines,
            "workdir_text": self.workdir_text,
            "page_label": self.page_label,
        }
        source.update(
            {key: value for key, value in optional.items() if value is not None}
        )
        return source


@dataclass(frozen=True, slots=True)
class ParsedBookStructure:
    """Validated semantic JSON plus database-ready knowledge-point projections."""

    document: dict[str, Any]
    knowledge_points: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MoreToSkillsIdentity:
    """Content identity persisted with each managed textbook job."""

    version: str
    skill_sha256: str
    schema_sha256: str


def get_more_to_skills_identity() -> MoreToSkillsIdentity:
    """Return digests for the repository-owned instructions and schema."""

    return MoreToSkillsIdentity(
        version=_MORE_TO_SKILLS_VERSION,
        skill_sha256=hashlib.sha256(_SKILL_PATH.read_bytes()).hexdigest(),
        schema_sha256=hashlib.sha256(_SCHEMA_PATH.read_bytes()).hexdigest(),
    )


def _reject_constant(value: str) -> None:
    raise BookStructureValidationError(f"non-standard JSON constant: {value}")


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BookStructureValidationError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _decode_json(raw_json: str | bytes) -> dict[str, Any]:
    try:
        payload = json.loads(
            raw_json,
            parse_constant=_reject_constant,
            object_pairs_hook=_reject_duplicate_keys,
        )
    except BookStructureValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        raise BookStructureValidationError("structure is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise BookStructureValidationError("$: structure must be an object")
    return payload


def _json_path(parts: Collection[object]) -> str:
    path = "$"
    for part in parts:
        if isinstance(part, int):
            path += f"[{part}]"
        elif isinstance(part, str) and part.replace("_", "a").isalnum():
            path += f".{part}"
        else:
            path += f"[{json.dumps(part, ensure_ascii=True)}]"
    return path


def _validate_schema(document: dict[str, Any]) -> None:
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator_type = validator_for(schema)
    validator_type.check_schema(schema)
    errors = sorted(
        validator_type(schema).iter_errors(document),
        key=lambda error: (list(error.absolute_path), error.message),
    )
    if errors:
        error = errors[0]
        raise BookStructureValidationError(
            f"{_json_path(error.absolute_path)}: {error.message}"
        )


def _validate_schema_version(document: Mapping[str, Any]) -> None:
    value = document.get("schema_version")
    if not isinstance(value, str):
        raise BookStructureValidationError("$.schema_version: must be a string")
    try:
        major = int(value.split(".", 1)[0])
    except ValueError as exc:
        raise BookStructureValidationError(
            "$.schema_version: must use MAJOR.MINOR.PATCH"
        ) from exc
    if major != _SUPPORTED_SCHEMA_MAJOR:
        raise BookStructureValidationError(
            f"$.schema_version: unsupported schema major {major}"
        )


def _validate_finite_numbers(value: object, *, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise BookStructureValidationError(f"{path}: number must be finite")
    if isinstance(value, dict):
        for key, child in value.items():
            _validate_finite_numbers(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _validate_finite_numbers(child, path=f"{path}[{index}]")


def _validate_output_path(path: str, *, allowed: frozenset[str], where: str) -> None:
    candidate = PurePosixPath(path)
    if (
        "\\" in path
        or candidate.is_absolute()
        or not candidate.parts
        or any(part in {"", ".", ".."} for part in candidate.parts)
    ):
        raise BookStructureValidationError(f"{where}: output path is invalid")
    normalized = candidate.as_posix()
    if normalized not in allowed:
        raise BookStructureValidationError(
            f"{where}: material is missing from controlled outputs"
        )


def _validate_trusted_source(source: TrustedBookSource) -> None:
    if source.anchor_mode == "source_lines" and source.line_offset is None:
        raise BookStructureValidationError(
            "trusted_source.line_offset: required for source_lines"
        )
    if source.anchor_mode == "workdir_lines" and not source.workdir_text:
        raise BookStructureValidationError(
            "trusted_source.workdir_text: required for workdir_lines"
        )


def _validate_anchor(
    anchor: Mapping[str, Any], *, total_lines: int, where: str
) -> None:
    start = anchor["start_line"]
    end = anchor["end_line"]
    if start > end:
        raise BookStructureValidationError(f"{where}: start_line exceeds end_line")
    if end > total_lines:
        raise BookStructureValidationError(
            f"{where}.end_line: exceeds trusted source line count"
        )


def _validate_nodes(
    nodes: list[dict[str, Any]],
    *,
    total_lines: int,
    allowed_outputs: frozenset[str],
) -> set[str]:
    node_ids: set[str] = set()
    stack = [(node, f"$.nodes[{index}]") for index, node in enumerate(nodes)]
    while stack:
        node, where = stack.pop()
        node_id = node["id"]
        if node_id in node_ids:
            raise BookStructureValidationError(
                f"{where}.id: duplicate node id {node_id}"
            )
        node_ids.add(node_id)
        _validate_anchor(
            node["anchor"], total_lines=total_lines, where=f"{where}.anchor"
        )
        content_file = node.get("content_file")
        if content_file is not None:
            _validate_output_path(
                content_file,
                allowed=allowed_outputs,
                where=f"{where}.content_file",
            )
            raise BookStructureValidationError(
                f"{where}.content_file: node-level content_file is not supported; "
                "attach managed materials to knowledge_points"
            )
        children = node.get("children", [])
        stack.extend(
            (child, f"{where}.children[{index}]")
            for index, child in enumerate(children)
        )
    return node_ids


def _project_knowledge_points(
    document: dict[str, Any],
    *,
    node_ids: set[str],
    total_lines: int,
    allowed_outputs: frozenset[str],
) -> tuple[dict[str, Any], ...]:
    projections: list[dict[str, Any]] = []
    skill_kp_ids: set[str] = set()
    for index, knowledge_point in enumerate(document.get("knowledge_points", [])):
        where = f"$.knowledge_points[{index}]"
        skill_kp_id = knowledge_point["id"]
        if skill_kp_id in skill_kp_ids:
            raise BookStructureValidationError(
                f"{where}.id: duplicate knowledge point id {skill_kp_id}"
            )
        skill_kp_ids.add(skill_kp_id)
        anchor = knowledge_point["anchor"]
        _validate_anchor(anchor, total_lines=total_lines, where=f"{where}.anchor")
        unit_id = knowledge_point.get("unit")
        if unit_id is not None and unit_id not in node_ids:
            raise BookStructureValidationError(
                f"{where}.unit: unknown node id {unit_id}"
            )
        referenced_nodes = tuple(knowledge_point.get("nodes", []))
        missing_nodes = [
            node_id for node_id in referenced_nodes if node_id not in node_ids
        ]
        if missing_nodes:
            raise BookStructureValidationError(
                f"{where}.nodes: unknown node id {missing_nodes[0]}"
            )
        content_file = knowledge_point.get("content_file")
        if content_file is not None:
            _validate_output_path(
                content_file,
                allowed=allowed_outputs,
                where=f"{where}.content_file",
            )
        projections.append(
            {
                "skill_kp_id": skill_kp_id,
                "position": index + 1,
                "title": knowledge_point["title"],
                "unit_skill_node_id": unit_id,
                "node_skill_ids": referenced_nodes,
                "start_line": anchor["start_line"],
                "end_line": anchor["end_line"],
                "raw": knowledge_point,
            }
        )
    return tuple(projections)


def _validate_coverage(document: Mapping[str, Any], *, total_lines: int) -> None:
    coverage = document["coverage"]
    for bucket in ("excluded", "omitted"):
        for index, entry in enumerate(coverage.get(bucket, [])):
            anchor = entry.get("anchor")
            if anchor is not None:
                _validate_anchor(
                    anchor,
                    total_lines=total_lines,
                    where=f"$.coverage.{bucket}[{index}].anchor",
                )


def parse_book_structure(
    *,
    trusted_source: TrustedBookSource,
    raw_json: str | bytes,
    allowed_output_paths: Collection[str],
) -> ParsedBookStructure:
    """Parse a more-to-skills structure using only service-owned coordinates."""

    _validate_trusted_source(trusted_source)
    document = copy.deepcopy(_decode_json(raw_json))
    _validate_schema_version(document)
    document["source"] = trusted_source.as_structure_source()
    _validate_finite_numbers(document)
    _validate_schema(document)

    allowed_outputs = frozenset(allowed_output_paths)
    node_ids = _validate_nodes(
        document["nodes"],
        total_lines=trusted_source.total_lines,
        allowed_outputs=allowed_outputs,
    )
    knowledge_points = _project_knowledge_points(
        document,
        node_ids=node_ids,
        total_lines=trusted_source.total_lines,
        allowed_outputs=allowed_outputs,
    )
    _validate_coverage(document, total_lines=trusted_source.total_lines)
    warnings = () if knowledge_points else ("knowledge_points_empty",)
    return ParsedBookStructure(
        document=document,
        knowledge_points=knowledge_points,
        warnings=warnings,
    )


def project_material_content_files(
    document: Mapping[str, Any],
    content_files_by_skill_kp_id: Mapping[str, str],
) -> dict[str, Any]:
    """Overlay current material pointers without mutating stored semantics."""

    projected = copy.deepcopy(dict(document))
    stack = list(projected.get("nodes") or [])
    while stack:
        node = stack.pop()
        if not isinstance(node, dict):
            continue
        node.pop("content_file", None)
        stack.extend(node.get("children") or [])
    for knowledge_point in projected.get("knowledge_points") or []:
        if not isinstance(knowledge_point, dict):
            continue
        skill_kp_id = knowledge_point.get("id")
        current = content_files_by_skill_kp_id.get(str(skill_kp_id))
        if current is None:
            knowledge_point.pop("content_file", None)
        else:
            knowledge_point["content_file"] = current
    return projected


async def get_projected_current_structure(
    *,
    textbook_id: str,
) -> dict[str, Any] | None:
    """Load current semantics and derive API material paths from DB pointers."""

    from src.server.database.education_books import get_current_structure

    result = await get_current_structure(textbook_id=textbook_id)
    if result is None:
        return None
    points = result["knowledge_points"]
    content_files = {
        str(point["skill_kp_id"]): f"materials/{point['knowledge_point_id']}.md"
        for point in points
        if point["content_key"] is not None
    }
    result["structure_json"] = project_material_content_files(
        result["structure_json"], content_files
    )
    return result
