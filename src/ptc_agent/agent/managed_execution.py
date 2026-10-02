"""Explicit execution limits for service-owned managed PTC runs."""

from collections.abc import Mapping
from dataclasses import dataclass
import json
import math
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID


_MAX_MANAGED_WRITE_BYTES = 32 * 1024 * 1024


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
    enable_mcp: bool = False
    enable_web: bool = False
    enable_vault: bool = False
    enable_code_execution: bool = False
    enable_bash: bool = True
    enable_preview: bool = False
    enable_widgets: bool = False
    enable_progress_reporting: bool = False
    allow_subagents: bool = False


def education_book_policy(execution_id: str) -> ManagedExecutionPolicy:
    """Return the sole policy for one isolated textbook item execution."""
    normalized_execution_id = str(UUID(execution_id))
    return ManagedExecutionPolicy(
        allowed_skill_names=frozenset({"more-to-skills"}),
        filesystem_root=f"/managed/textbook-job/{normalized_execution_id}",
        enable_web=True,
        enable_code_execution=True,
        enable_bash=True,
        enable_preview=True,
        enable_widgets=True,
        enable_progress_reporting=True,
        allow_subagents=False,
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
    managed.sandbox.docker.dev_mode = False
    managed.sandbox.docker.host_work_dir = None
    managed.sandbox.docker.volumes = []
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


def _validate_managed_textbook_path(
    path: str,
    policy: ManagedExecutionPolicy,
) -> tuple[PurePosixPath | None, str | None]:
    """Validate the managed write zone while preserving the raw path for safety checks."""
    if (
        not isinstance(path, str)
        or _contains_c0_control(path)
        or "\\" in path
        or ".." in path.split("/")
    ):
        return None, "managed teaching candidate path is not allowed"

    candidate_path = PurePosixPath(path)
    root = PurePosixPath(policy.filesystem_root)
    if not candidate_path.is_absolute():
        candidate_path = root / candidate_path
    try:
        relative = candidate_path.relative_to(root)
    except ValueError:
        return None, "managed teaching candidate path is not allowed"
    if len(relative.parts) < 2 or relative.parts[0] not in {"work", "outputs"}:
        return None, "managed teaching candidate path is not allowed"
    return relative, None


def validate_managed_textbook_edit(
    path: str,
    policy: ManagedExecutionPolicy,
) -> str | None:
    """Enforce the managed write-zone boundary for an in-place edit."""
    _relative, error = _validate_managed_textbook_path(path, policy)
    return error


def validate_managed_textbook_write(
    path: str, content: str, policy: ManagedExecutionPolicy
) -> str | None:
    """Enforce managed write-zone and content safety before disk access."""
    relative, error = _validate_managed_textbook_path(path, policy)
    if error is not None:
        return error
    assert relative is not None
    if not isinstance(content, str):
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
