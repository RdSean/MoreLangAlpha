"""Explicit execution limits for service-owned managed PTC runs."""

from collections.abc import Mapping
from dataclasses import dataclass
import json
import re
from pathlib import PurePosixPath
from typing import Any
from uuid import UUID


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
        allowed_skill_names=frozenset({"book-to-skill", "the-knowledge-guy"}),
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
    if policy.purpose == "structure":
        if relative != PurePosixPath("outputs/structure.json"):
            return "managed teaching candidate path is not allowed"
        try:
            decoded = json.loads(content)
        except json.JSONDecodeError:
            return "managed teaching candidate must be valid JSON before writing"
        if not isinstance(decoded, dict):
            return "managed teaching candidate must be a JSON object"
        return None
    if policy.purpose == "lesson":
        if relative == PurePosixPath("outputs/lesson.md"):
            if not content.strip():
                return "managed lesson Markdown must not be empty"
            return None
        if relative == PurePosixPath("outputs/practice.json"):
            try:
                decoded = json.loads(content)
            except json.JSONDecodeError:
                return "managed lesson practice must be valid JSON before writing"
            if not isinstance(decoded, dict):
                return "managed lesson practice must be a JSON object"
            return None
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
    try:
        decoded = json.loads(content)
    except json.JSONDecodeError:
        return "managed teaching candidate must be valid JSON before writing"
    if not isinstance(decoded, dict):
        return "managed teaching candidate must be a JSON object"
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
