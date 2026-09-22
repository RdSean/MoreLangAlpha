"""Explicit execution limits for service-owned managed PTC runs."""

from collections.abc import Mapping
from dataclasses import dataclass
import json
import math
import re
import shlex
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID


_BOOK_PIPELINE_JSON_OBJECTS = frozenset(
    {
        PurePosixPath("outputs/book_package.json"),
        PurePosixPath("outputs/content_tree.json"),
        PurePosixPath("outputs/knowledge_points.json"),
        PurePosixPath("outputs/assets_manifest.json"),
    }
)
_BOOK_PIPELINE_CANONICAL_FILES = frozenset(
    {
        PurePosixPath("outputs/book-skill/SKILL.md"),
        PurePosixPath("outputs/book-skill/glossary.md"),
        PurePosixPath("outputs/book-skill/patterns.md"),
        PurePosixPath("outputs/book-skill/cheatsheet.md"),
    }
)
_BOOK_PIPELINE_ASSET_EXTENSIONS = frozenset(
    {".md", ".json", ".txt", ".png", ".jpg", ".jpeg", ".webp", ".svg", ".csv"}
)
class _StrictJsonError(ValueError):
    """A JSON value is valid syntax but violates the managed subset."""


def _reject_json_constant(value: str) -> None:
    raise _StrictJsonError(f"non-standard JSON constant: {value}")


def _reject_duplicate_json_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    decoded: dict[str, Any] = {}
    for key, value in pairs:
        if key in decoded:
            raise _StrictJsonError(f"duplicate JSON key: {key}")
        decoded[key] = value
    return decoded


def _parse_json_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise _StrictJsonError("non-finite JSON number")
    return parsed


def _contains_non_finite_number(value: Any) -> bool:
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, Mapping):
        return any(_contains_non_finite_number(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_non_finite_number(item) for item in value)
    return False


def _strict_json_loads(value: str) -> Any:
    decoded = json.loads(
        value,
        parse_constant=_reject_json_constant,
        parse_float=_parse_json_float,
        object_pairs_hook=_reject_duplicate_json_keys,
    )
    if _contains_non_finite_number(decoded):
        raise _StrictJsonError("non-finite JSON number")
    return decoded


def _validate_strict_json_object(
    content: str,
    *,
    invalid_message: str,
    object_message: str,
) -> str | None:
    try:
        decoded = _strict_json_loads(content)
    except ValueError:
        return invalid_message
    if not isinstance(decoded, dict):
        return object_message
    return None


def _contains_c0_control(value: str) -> bool:
    return any(ord(character) < 32 for character in value)


def _validate_progress_jsonl(content: str) -> str | None:
    from src.server.services.education_generation_progress import (
        ProgressEventValidationError,
        parse_progress_json_line,
    )

    for line in content.splitlines():
        if not line.strip():
            continue
        try:
            parse_progress_json_line(line)
        except ProgressEventValidationError:
            return "managed progress line violates the semantic progress contract"
    return None


@dataclass(frozen=True)
class ManagedExecutionPolicy:
    """Limits a managed agent to a service-defined capability envelope."""

    allowed_skill_names: frozenset[str]
    filesystem_root: str
    purpose: str = "teaching"
    enable_mcp: bool = False
    enable_web: bool = False
    enable_vault: bool = False
    enable_preview: bool = False
    allow_subagents: bool = False


def education_teaching_policy(job_id: str) -> ManagedExecutionPolicy:
    """Return the fixed policy for one staged family-textbook job."""
    normalized_job_id = str(UUID(job_id))
    return ManagedExecutionPolicy(
        allowed_skill_names=frozenset({"book-to-skill"}),
        filesystem_root=f"/managed/textbook-job/{normalized_job_id}",
        allow_subagents=True,
    )


def education_structure_policy(job_id: str) -> ManagedExecutionPolicy:
    """Return the fixed policy for one reviewable textbook-structure job."""
    normalized_job_id = str(UUID(job_id))
    return ManagedExecutionPolicy(
        allowed_skill_names=frozenset({"book-to-skill"}),
        filesystem_root=f"/managed/textbook-job/{normalized_job_id}",
        purpose="structure",
        allow_subagents=True,
    )


def education_lesson_policy(job_id: str) -> ManagedExecutionPolicy:
    """Return the fixed policy for one knowledge-point lesson job."""
    normalized_job_id = str(UUID(job_id))
    return ManagedExecutionPolicy(
        allowed_skill_names=frozenset({"book-to-skill"}),
        filesystem_root=f"/managed/textbook-job/{normalized_job_id}",
        purpose="lesson",
        allow_subagents=True,
    )


def education_book_asset_policy(job_id: str) -> ManagedExecutionPolicy:
    """Return the fixed policy for optional book-to-skill chapter assets."""
    normalized_job_id = str(UUID(job_id))
    return ManagedExecutionPolicy(
        allowed_skill_names=frozenset({"book-to-skill"}),
        filesystem_root=f"/managed/textbook-job/{normalized_job_id}",
        purpose="assets",
        allow_subagents=True,
    )


def education_book_pipeline_policy(job_id: str) -> ManagedExecutionPolicy:
    """Return the fixed policy for the unified book processing pipeline."""
    normalized_job_id = str(UUID(job_id))
    return ManagedExecutionPolicy(
        allowed_skill_names=frozenset({"book-to-skill"}),
        filesystem_root=f"/managed/textbook-job/{normalized_job_id}",
        purpose="book_pipeline",
        allow_subagents=True,
    )


def managed_core_config(core_config: Any, policy: ManagedExecutionPolicy) -> Any:
    """Clone and strip a CoreConfig for a service-owned managed run.

    The policy root is a first-class filesystem-tool boundary. The caller must
    still use a confined command runtime for Bash; a working directory alone
    cannot stop shell path escapes.
    """
    managed = core_config.model_copy(deep=True)
    managed.filesystem.working_directory = policy.filesystem_root
    managed.filesystem.allowed_directories = [policy.filesystem_root]
    managed.filesystem.denied_directories = []
    managed.mcp.servers = []
    managed.sandbox.platform_secrets = ()
    return managed


def managed_skill_root(policy: ManagedExecutionPolicy) -> str:
    """Return the only in-sandbox skill catalog visible to a managed run."""
    return f"{policy.filesystem_root}/.agents/skills"


def validate_managed_path(path: str, policy: ManagedExecutionPolicy) -> str | None:
    """Reject paths that are not contained by the immutable managed root."""
    candidate = PurePosixPath(path)
    root = PurePosixPath(policy.filesystem_root)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        relative = candidate.relative_to(root)
    except ValueError:
        return "ERROR: path reaches outside the managed textbook job root"
    if _contains_c0_control(path) or "\\" in path or ".." in relative.parts:
        return "ERROR: path reaches outside the managed textbook job root"
    return None


def validate_managed_bash_command(
    command: str, policy: ManagedExecutionPolicy
) -> str | None:
    """Reject shell syntax that can escape the fixed managed-job root.

    The managed Skills use a deliberately small Bash grammar. Command
    substitution, absolute paths, parent traversal and shell chaining are
    excluded so the model cannot turn the Bash tool into an ambient filesystem
    escape hatch. This check complements the provider's sandbox isolation; it
    is not presented as a complete shell sandbox.
    """
    forbidden = ("..", "$", "`", ";", "&&", "||", "|", "<", ">", "\\")
    if re.search(r"(?:^|\s)/", command) or any(token in command for token in forbidden):
        return "ERROR: command reaches outside the managed textbook job root"
    if _contains_c0_control(command):
        return "ERROR: command is not allowed in a managed textbook run"
    helper = re.fullmatch(
        r"(?:python|python3) \.langalpha/progress\.py(?: (?P<event>.+))?",
        command,
    )
    if helper is not None:
        try:
            tokens = shlex.split(command)
        except ValueError:
            return "ERROR: managed progress helper command is invalid"
        if len(tokens) == 2:
            return None
        if len(tokens) != 3:
            return "ERROR: managed progress helper accepts one JSON object"
        try:
            decoded = _strict_json_loads(tokens[2])
        except ValueError:
            return "ERROR: managed progress helper requires one JSON object"
        if not isinstance(decoded, dict):
            return "ERROR: managed progress helper requires one JSON object"
        return None
    if command == "sha256sum inputs/manifest.json":
        return None
    if not re.fullmatch(
        r"(?:cat|mkdir -p|printf|echo|test -[def]) [0-9A-Za-z._/{}:,= -]+",
        command,
    ):
        return "ERROR: command is not allowed in a managed textbook run"
    return None


def validate_managed_textbook_write(
    path: str, content: str, policy: ManagedExecutionPolicy
) -> str | None:
    """Restrict writes to v2 candidate paths before they reach sandbox disk."""
    candidate_path = PurePosixPath(path)
    root = PurePosixPath(policy.filesystem_root)
    try:
        relative = candidate_path.relative_to(root)
    except ValueError:
        return "managed teaching candidate path is not allowed"
    if _contains_c0_control(path) or "\\" in path or ".." in relative.parts:
        return "managed teaching candidate path is not allowed"
    if relative == PurePosixPath(".langalpha/progress.jsonl"):
        return (
            "managed progress stream is append-only through the staged helper; "
            "use python .langalpha/progress.py"
        )
    if policy.purpose == "book_pipeline":
        if relative in _BOOK_PIPELINE_JSON_OBJECTS:
            return _validate_strict_json_object(
                content,
                invalid_message="managed book package must be valid JSON before writing",
                object_message="managed book package must be a JSON object",
            )
        if relative in _BOOK_PIPELINE_CANONICAL_FILES:
            return None
        if (
            len(relative.parts) >= 4
            and relative.parts[:3] == ("outputs", "book-skill", "chapters")
            and relative.suffix == ".md"
        ):
            return None
        if (
            len(relative.parts) >= 2
            and relative.parts[0] == "outputs"
            and relative.suffix in _BOOK_PIPELINE_ASSET_EXTENSIONS
        ):
            # Two-layer contract: this write policy enforces root containment,
            # allowed paths/extensions and package JSON shape. The import stage
            # separately downloads only paths explicitly declared in
            # outputs/assets_manifest.json; undeclared outputs are never
            # imported.
            if relative.suffix == ".json":
                return _validate_strict_json_object(
                    content,
                    invalid_message=(
                        "managed JSON content asset must be valid JSON before writing"
                    ),
                    object_message="managed JSON content asset must be a JSON object",
                )
            return None
        return "managed teaching candidate path is not allowed"
    if policy.purpose == "structure":
        if relative != PurePosixPath("outputs/structure.json"):
            return "managed teaching candidate path is not allowed"
        return _validate_strict_json_object(
            content,
            invalid_message="managed teaching candidate must be valid JSON before writing",
            object_message="managed teaching candidate must be a JSON object",
        )
    if policy.purpose == "lesson":
        if relative == PurePosixPath("outputs/lesson.md"):
            if not content.strip():
                return "managed lesson Markdown must not be empty"
            return None
        if relative == PurePosixPath("outputs/practice.json"):
            return _validate_strict_json_object(
                content,
                invalid_message=(
                    "managed lesson practice must be valid JSON before writing"
                ),
                object_message="managed lesson practice must be a JSON object",
            )
        return "managed teaching candidate path is not allowed"
    if policy.purpose == "assets":
        if relative == PurePosixPath("outputs/chapters_manifest.json"):
            return _validate_strict_json_object(
                content,
                invalid_message="managed book asset manifest must be valid JSON",
                object_message="managed book asset manifest must be a JSON object",
            )
        if relative.as_posix() in {
            "outputs/glossary.md",
            "outputs/patterns.md",
            "outputs/cheatsheet.md",
            "outputs/nutshell.md",
        }:
            return None if content.strip() else "managed book asset must not be empty"
        if re.fullmatch(
            r"outputs/chapters/[0-9A-Za-z][0-9A-Za-z._-]*\.md",
            relative.as_posix(),
        ):
            return None if content.strip() else "managed book asset must not be empty"
        return "managed teaching candidate path is not allowed"
    allowed_json = {
        PurePosixPath("outputs/knowledge/concept-index.json"),
        PurePosixPath("outputs/knowledge/coverage-audit.json"),
        PurePosixPath("outputs/teaching-package.json"),
    }
    chapter_json = re.fullmatch(
        r"outputs/chapters/[0-9]{2,}-[0-9A-Za-z._-]+-(?:knowledge|practice)\.json",
        relative.as_posix(),
    )
    chapter_toolkit = re.fullmatch(
        r"outputs/chapters/[0-9]{2,}-[0-9A-Za-z._-]+-toolkit\.md", relative.as_posix()
    )
    if relative not in allowed_json and not chapter_json and not chapter_toolkit:
        return "managed teaching candidate path is not allowed"
    if chapter_toolkit:
        return None
    strict_error = _validate_strict_json_object(
        content,
        invalid_message="managed teaching candidate must be valid JSON before writing",
        object_message="managed teaching candidate must be a JSON object",
    )
    if strict_error is not None:
        return strict_error
    decoded = _strict_json_loads(content)
    if relative != PurePosixPath("outputs/teaching-package.json"):
        return None
    chapters = decoded.get("chapters")
    if not isinstance(chapters, list):
        return None
    for chapter in chapters:
        if not isinstance(chapter, Mapping):
            continue
        knowledge_points = chapter.get("knowledge_points")
        questions = chapter.get("questions")
        if not isinstance(knowledge_points, list) or not isinstance(questions, list):
            continue
        normalized_points = {
            value.strip()
            for value in knowledge_points
            if isinstance(value, str) and value.strip()
        }
        for question in questions:
            if not isinstance(question, Mapping):
                continue
            knowledge_point = question.get("knowledge_point")
            if (
                isinstance(knowledge_point, str)
                and knowledge_point.strip()
                and knowledge_point.strip() not in normalized_points
            ):
                return (
                    "each question knowledge point must exactly match a chapter "
                    "knowledge_points value"
                )
    return None
