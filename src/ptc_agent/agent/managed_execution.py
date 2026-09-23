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


_MAX_MANAGED_WRITE_BYTES = 32 * 1024 * 1024
TEXTBOOK_PURPOSES = frozenset(
    {"teaching", "structure", "lesson", "assets", "book_pipeline"}
)


def managed_textbook_directories(root: str) -> tuple[str, ...]:
    """Return the sole writable directory layout for a managed textbook job."""
    from ptc_agent.core.sandbox.ptc_sandbox import PTCSandbox

    return PTCSandbox.managed_textbook_directories(root)


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


def _contains_c0_control(value: str) -> bool:
    return any(ord(character) < 32 for character in value)


@dataclass(frozen=True)
class ManagedExecutionPolicy:
    """Limits a managed agent to a service-defined capability envelope."""

    allowed_skill_names: frozenset[str]
    filesystem_root: str
    purpose: str = "teaching"
    enable_mcp: bool = False
    enable_web: bool = False
    enable_vault: bool = False
    enable_code_execution: bool = False
    enable_bash: bool = True
    enable_preview: bool = False
    enable_widgets: bool = False
    allow_subagents: bool = False


def education_teaching_policy(job_id: str) -> ManagedExecutionPolicy:
    """Return the fixed policy for one staged family-textbook job."""
    normalized_job_id = str(UUID(job_id))
    return ManagedExecutionPolicy(
        allowed_skill_names=frozenset({"book-to-skill"}),
        filesystem_root=f"/managed/textbook-job/{normalized_job_id}",
        enable_web=True,
        enable_code_execution=True,
        enable_bash=True,
        enable_preview=True,
        enable_widgets=True,
        allow_subagents=True,
    )


def education_structure_policy(job_id: str) -> ManagedExecutionPolicy:
    """Return the fixed policy for one reviewable textbook-structure job."""
    normalized_job_id = str(UUID(job_id))
    return ManagedExecutionPolicy(
        allowed_skill_names=frozenset({"book-to-skill"}),
        filesystem_root=f"/managed/textbook-job/{normalized_job_id}",
        purpose="structure",
        enable_web=True,
        enable_code_execution=True,
        enable_bash=True,
        enable_preview=True,
        enable_widgets=True,
        allow_subagents=True,
    )


def education_lesson_policy(job_id: str) -> ManagedExecutionPolicy:
    """Return the fixed policy for one knowledge-point lesson job."""
    normalized_job_id = str(UUID(job_id))
    return ManagedExecutionPolicy(
        allowed_skill_names=frozenset({"book-to-skill"}),
        filesystem_root=f"/managed/textbook-job/{normalized_job_id}",
        purpose="lesson",
        enable_web=True,
        enable_code_execution=True,
        enable_bash=True,
        enable_preview=True,
        enable_widgets=True,
        allow_subagents=True,
    )


def education_book_asset_policy(job_id: str) -> ManagedExecutionPolicy:
    """Return the fixed policy for optional book-to-skill chapter assets."""
    normalized_job_id = str(UUID(job_id))
    return ManagedExecutionPolicy(
        allowed_skill_names=frozenset({"book-to-skill"}),
        filesystem_root=f"/managed/textbook-job/{normalized_job_id}",
        purpose="assets",
        enable_web=True,
        enable_code_execution=True,
        enable_bash=True,
        enable_preview=True,
        enable_widgets=True,
        allow_subagents=True,
    )


def education_book_pipeline_policy(job_id: str) -> ManagedExecutionPolicy:
    """Return the fixed policy for the unified book processing pipeline."""
    normalized_job_id = str(UUID(job_id))
    return ManagedExecutionPolicy(
        allowed_skill_names=frozenset({"book-to-skill"}),
        filesystem_root=f"/managed/textbook-job/{normalized_job_id}",
        purpose="book_pipeline",
        enable_web=True,
        enable_code_execution=True,
        enable_bash=True,
        enable_preview=True,
        enable_widgets=True,
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
    """Enforce managed write-zone and path safety before disk access."""
    candidate_path = PurePosixPath(path)
    root = PurePosixPath(policy.filesystem_root)
    if not candidate_path.is_absolute():
        return "managed teaching candidate path is not allowed"
    try:
        relative = candidate_path.relative_to(root)
    except ValueError:
        return "managed teaching candidate path is not allowed"
    if (
        _contains_c0_control(path)
        or "\\" in path
        or ".." in path.split("/")
        or not isinstance(content, str)
    ):
        return "managed teaching candidate path is not allowed"
    if relative == PurePosixPath(".langalpha/progress.jsonl"):
        return (
            "managed progress stream is append-only through the staged helper; "
            "use python .langalpha/progress.py"
        )
    if not relative.parts or relative.parts[0] not in {"work", "outputs"}:
        return "managed teaching candidate path is not allowed"
    try:
        encoded = content.encode("utf-8")
    except UnicodeEncodeError:
        return "managed textbook content must be valid UTF-8"
    if len(encoded) > _MAX_MANAGED_WRITE_BYTES:
        return "managed textbook content is too large"
    if relative.suffix.lower() == ".json":
        try:
            _strict_json_loads(content)
        except ValueError:
            return "managed JSON content must be valid JSON before writing"
    return None
