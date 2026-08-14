"""Explicit execution limits for service-owned managed PTC runs."""

from dataclasses import dataclass
import re
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class ManagedExecutionPolicy:
    """Limits a managed agent to a service-defined capability envelope."""

    allowed_skill_names: frozenset[str]
    filesystem_root: str
    enable_mcp: bool = False
    enable_web: bool = False
    enable_vault: bool = False
    enable_preview: bool = False
    allow_subagents: bool = False


def education_teaching_policy(job_id: str) -> ManagedExecutionPolicy:
    """Return the fixed policy for one staged family-textbook job."""
    normalized_job_id = str(UUID(job_id))
    return ManagedExecutionPolicy(
        allowed_skill_names=frozenset({"book-to-skill", "the-knowledge-guy"}),
        filesystem_root=f"/managed/textbook-job/{normalized_job_id}",
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
        candidate.relative_to(root)
    except ValueError:
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
    if command == "sha256sum inputs/manifest.json":
        return None
    if not re.fullmatch(
        r"(?:cat|mkdir -p|printf|echo|test -[def]) [0-9A-Za-z._/{}:,= -]+",
        command,
    ):
        return "ERROR: command is not allowed in a managed textbook run"
    return None
