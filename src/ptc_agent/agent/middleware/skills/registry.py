"""
Skill registry for dynamic tool loading.

This module defines the registry of available skills that can be dynamically
loaded by the agent via the load_skill mechanism. Each skill contains a set
of tools that are pre-registered but hidden until the skill is loaded.
"""

from dataclasses import dataclass
from typing import Any, Callable, Literal

from src.config.features import is_feature_enabled_system
from src.config.settings import get_workflow_orchestration_config
from src.tools.automation import AUTOMATION_TOOLS

# Type alias for agent modes that can use skills
SkillMode = Literal["ptc", "flash"]


@dataclass
class SkillDefinition:
    """Definition of a loadable skill.

    Attributes:
        name: Unique skill identifier
        description: Human-readable description of what the skill does
        tools: List of LangChain tools included in this skill
        tool_names: Names of externally-registered tools gated by this skill —
            for per-thread factory tools that can't be instantiated at import
            time (e.g. RunWorkflow). The tool object is registered by the agent
            factory; the skill only controls its visibility.
        skill_md_path: Optional path to SKILL.md with detailed instructions
        exposure: Which agent mode(s) can use this skill ("ptc", "flash", or "both")
        system_gate: Deployment kill switch for skills owned by a config section
            rather than the feature catalog — False drops the skill everywhere.
    """

    name: str
    description: str
    tools: list[Any]
    tool_names: tuple[str, ...] = ()
    skill_md_path: str | None = None
    exposure: Literal["ptc", "flash", "both", "hidden"] = "ptc"
    command: str | None = None
    # Feature-flag key (src/config/features.py) owning this skill; the skill
    # drops out of every accessor while the feature's system default is off.
    # Per-user resolution happens at agent build (SkillsMiddleware injection).
    feature: str | None = None
    system_gate: Callable[[], bool] | None = None

    def get_tool_names(self) -> list[str]:
        """Get list of tool names in this skill (including externally-registered ones)."""
        return [getattr(t, "name", str(t)) for t in self.tools] + list(self.tool_names)

    def format_tool_descriptions(self, max_desc_len: int = 200) -> str:
        """Format tool descriptions for display.

        Args:
            max_desc_len: Maximum length for each tool's description text.

        Returns:
            Formatted string with one line per tool.
        """
        lines = []
        for t in self.tools:
            name = getattr(t, "name", str(t))
            desc = getattr(t, "description", "No description")
            if len(desc) > max_desc_len:
                desc = desc[:max_desc_len] + "..."
            lines.append(f"  - **{name}**: {desc}")
        return "\n".join(lines)


def _run_workflow_enabled() -> bool:
    return get_workflow_orchestration_config().enabled


def _is_enabled(
    skill: SkillDefinition, feature_resolver: Callable[[str], bool] | None = None
) -> bool:
    """Availability gate: skills whose deployment switch or owning feature is
    off drop out of every accessor (listings, lookups, sandbox sync).

    ``feature_resolver`` defaults to the system gate — the no-user-context
    default these accessors run under. The agent build injects a per-user
    resolver (via ``get_skill_registry``) so a user's opt-in/out is honored
    when skills are assembled for that build. ``system_gate`` is a deployment
    kill switch, so no resolver overrides it.
    """
    if skill.system_gate is not None and not skill.system_gate():
        return False
    if skill.feature is None:
        return True
    resolve = feature_resolver or is_feature_enabled_system
    return resolve(skill.feature)


def _matches_mode(skill: SkillDefinition, mode: SkillMode | None) -> bool:
    """Check if a skill matches the given agent mode.

    Returns True if mode is None (no filter), skill.exposure matches,
    or skill is hidden (hidden skills match any mode for explicit lookup
    but are excluded from listings by callers).
    """
    if mode is None:
        return True
    if skill.exposure == "hidden":
        return True  # Available in all modes, excluded from listings separately
    return skill.exposure == mode or skill.exposure == "both"


# Registry of all available skills
# Skills are pre-registered at agent creation but tools are hidden until loaded
SKILL_REGISTRY: dict[str, SkillDefinition] = {
    "secretary": SkillDefinition(
        name="secretary",
        description="Manage workspaces, dispatch research, monitor running analyses",
        tools=[],
        skill_md_path="skills/secretary/SKILL.md",
        exposure="flash",
        command="secretary",
    ),
    "automation": SkillDefinition(
        name="automation",
        description="Create and manage scheduled automations (cron jobs, one-time tasks)",
        tools=AUTOMATION_TOOLS,
        skill_md_path="skills/automation/SKILL.md",
        exposure="both",
    ),
    "run-workflow": SkillDefinition(
        name="run-workflow",
        # Keep in sync with the `description:` in skills/run-workflow/SKILL.md
        # frontmatter (locked by a unit test). RunWorkflow itself is a per-thread
        # factory tool registered in agent.py, so it's gated by name here.
        description=(
            "Orchestrate parallel subagent pipelines from a JavaScript workflow "
            "script — fan out work across many items and synthesize the results, "
            "or run a saved workflow by name. "
            "Unlocks the RunWorkflow tool."
        ),
        tools=[],
        tool_names=("RunWorkflow",),
        skill_md_path="skills/run-workflow/SKILL.md",
        exposure="ptc",
        system_gate=_run_workflow_enabled,
    ),
    "pdf": SkillDefinition(
        name="pdf",
        description="PDF manipulation: extract text/tables, create, merge/split documents, and fill forms",
        tools=[],
        skill_md_path="skills/pdf/SKILL.md",
        exposure="ptc",
    ),
    "docx": SkillDefinition(
        name="docx",
        description="Word document creation, editing, tracked changes, comments, and text extraction",
        tools=[],
        skill_md_path="skills/docx/SKILL.md",
        exposure="ptc",
    ),
    "pptx": SkillDefinition(
        name="pptx",
        description="Presentation creation, editing, layouts, speaker notes, and slide manipulation",
        tools=[],
        skill_md_path="skills/pptx/SKILL.md",
        exposure="ptc",
    ),
    "xlsx": SkillDefinition(
        name="xlsx",
        description="Spreadsheet creation, editing, formulas, data analysis, and visualization",
        tools=[],
        skill_md_path="skills/xlsx/SKILL.md",
        exposure="ptc",
    ),
    "self-improve": SkillDefinition(
        name="self-improve",
        description="Report issues and propose fixes to improve your own capabilities when you encounter errors or limitations",
        tools=[],
        skill_md_path="skills/self-improve/SKILL.md",
        exposure="ptc",
        command="report-issue",
    ),
    "inline-widget": SkillDefinition(
        name="inline-widget",
        description="Inline HTML widgets: charts, dashboards, data tables rendered directly in the chat via ShowWidget",
        tools=[],
        skill_md_path="skills/inline-widget/SKILL.md",
        exposure="ptc",
    ),
    "web-scraping": SkillDefinition(
        name="web-scraping",
        description="Web scraping with Scrapling: fast HTTP, browser rendering, anti-bot bypass, CSS/XPath selectors, multi-page spiders",
        tools=[],
        skill_md_path="skills/web-scraping/SKILL.md",
        exposure="ptc",
        command="web-scraping",
    ),
    "html-report": SkillDefinition(
        name="html-report",
        description="Self-contained styled HTML reports written to results/: PDF-exportable research documents with inline data, charts, and theme-aware CSS",
        tools=[],
        skill_md_path="skills/html-report/SKILL.md",
        exposure="ptc",
        command="html-report",
    ),
}


def get_skill_registry(
    mode: SkillMode | None = None,
    *,
    feature_resolver: Callable[[str], bool] | None = None,
) -> dict[str, SkillDefinition]:
    """Get the skill registry filtered by agent mode.

    Args:
        mode: Optional agent mode filter. None applies no mode filter.
              Feature-gated skills are excluded when disabled regardless.
        feature_resolver: Optional per-user feature gate. Defaults to the
              system gate; the agent build passes the build's own
              ``feature_enabled`` so opt-in/out drops the skill for that user.

    Returns:
        Dict of skill name to SkillDefinition for matching skills
    """
    return {
        name: skill
        for name, skill in SKILL_REGISTRY.items()
        if _is_enabled(skill, feature_resolver) and _matches_mode(skill, mode)
    }


def get_sandbox_skill_names() -> set[str]:
    """Get names of skills that should be synced to sandbox.

    Returns skills with exposure "ptc" or "both" — NOT "flash" (flash-only
    skills are never accessed in sandboxes).

    Returns:
        Set of skill names for sandbox upload
    """
    return {
        name
        for name, skill in SKILL_REGISTRY.items()
        if _is_enabled(skill) and skill.exposure in ("ptc", "both")
    }


def get_skill(skill_name: str, mode: SkillMode | None = None) -> SkillDefinition | None:
    """Get a skill definition by name, optionally validating exposure mode.

    Args:
        skill_name: Name of the skill to retrieve
        mode: Optional agent mode. If provided, only returns the skill if
              its exposure matches the mode.

    Returns:
        SkillDefinition if found and mode-compatible, None otherwise
    """
    skill = SKILL_REGISTRY.get(skill_name)
    if skill is None or not _is_enabled(skill):
        return None
    if mode is not None and not _matches_mode(skill, mode):
        return None
    return skill


def get_all_skill_tools(mode: SkillMode | None = None) -> list[Any]:
    """Get all tools from registered skills, optionally filtered by mode.

    Used during agent creation to pre-register all tools with ToolNode.

    Args:
        mode: Optional agent mode filter. None returns tools from all skills.

    Returns:
        Flat list of all tools from matching skills
    """
    all_tools = []
    for skill in SKILL_REGISTRY.values():
        if _is_enabled(skill) and _matches_mode(skill, mode):
            all_tools.extend(skill.tools)
    return all_tools


def get_all_skill_tool_names(mode: SkillMode | None = None) -> set[str]:
    """Get names of all tools from registered skills, optionally filtered by mode.

    Used by middleware to identify which tools belong to skills.

    Args:
        mode: Optional agent mode filter. None returns tool names from all skills.

    Returns:
        Set of tool names
    """
    names = set()
    for skill in SKILL_REGISTRY.values():
        if _is_enabled(skill) and _matches_mode(skill, mode):
            names.update(skill.get_tool_names())
    return names


def get_command_to_skill_map(mode: SkillMode | None = None) -> dict[str, str]:
    """Map slash command names to skill names, filtered by mode.

    Returns a dict where keys are command strings (e.g. "3-statement-model")
    and values are skill names (e.g. "3-statements"). Only includes skills
    that have a non-None command field.

    Args:
        mode: Optional agent mode filter. None returns all skills with commands.

    Returns:
        Dict mapping command name to skill name
    """
    return {
        skill.command: name
        for name, skill in SKILL_REGISTRY.items()
        if skill.command and _is_enabled(skill) and _matches_mode(skill, mode)
    }


def list_skills(mode: SkillMode | None = None) -> list[dict[str, Any]]:
    """List available skills with their metadata, optionally filtered by mode.

    Hidden skills are excluded from listings (they can only be activated
    programmatically via additionalContext).

    Args:
        mode: Optional agent mode filter. None returns all non-hidden skills.

    Returns:
        List of skill info dicts with name, description, and tool count
    """
    return [
        {
            "name": skill.name,
            "description": skill.description,
            "tool_count": len(skill.get_tool_names()),
            "tools": skill.get_tool_names(),
            "command": skill.command,
        }
        for skill in SKILL_REGISTRY.values()
        if _is_enabled(skill) and _matches_mode(skill, mode) and skill.exposure != "hidden"
    ]
