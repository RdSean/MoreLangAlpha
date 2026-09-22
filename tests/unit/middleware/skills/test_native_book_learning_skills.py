"""Contract tests for the project-native book learning skills."""

from pathlib import Path

import pytest

from ptc_agent.agent.middleware.skills.registry import (
    SKILL_REGISTRY,
    get_command_to_skill_map,
    get_sandbox_skill_names,
    get_skill,
    get_skill_registry,
    list_skills,
)
from ptc_agent.config.agent import SkillsConfig


NATIVE_BOOK_SKILLS = ("book-to-skill",)
REPO_ROOT = Path(__file__).resolve().parents[4]
#: This deployment's own skills travel as a bundle, so the host sources are
#: the bundles followed by the operator's directory.
LOCAL_BUNDLE = REPO_ROOT / "plugins/langalpha_local/skills"


@pytest.mark.parametrize("name", NATIVE_BOOK_SKILLS)
def test_native_book_learning_skills_are_ptc_only_registry_entries(name):
    """Book ingestion and routing need the PTC filesystem and sandbox surface."""
    skill = SKILL_REGISTRY[name]

    assert skill.name == name
    assert skill.tools == []
    assert skill.skill_md_path == f"skills/{name}/SKILL.md"
    assert skill.exposure == "ptc"
    assert skill.command == name
    assert name in get_sandbox_skill_names()
    assert name in get_skill_registry("ptc")
    assert name not in get_skill_registry("flash")
    assert get_skill(name, mode="ptc") is skill
    assert get_skill(name, mode="flash") is None
    assert name in {entry["name"] for entry in list_skills("ptc")}
    assert get_command_to_skill_map("ptc")[name] == name


def test_native_book_learning_skill_uses_the_sandbox_skills_runtime_root():
    """PTC commands resolve generated knowledge from the sandbox sync destination."""
    sources = SkillsConfig().local_skill_dirs_with_sandbox()
    sandbox_dirs = {sandbox for _, sandbox in sources}

    assert sandbox_dirs == {"/home/workspace/.agents/skills"}
    assert str(LOCAL_BUNDLE) in [source for source, _ in sources]

    book_to_skill = (LOCAL_BUNDLE / "book-to-skill/SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "book-to-skill" in book_to_skill
    assert "SKILL.md" in book_to_skill


def test_book_to_skill_managed_overlay_declares_full_pipeline_contract():
    """The managed adapter must stay aligned with the service package contract."""
    overlay = (LOCAL_BUNDLE / "book-to-skill/reference/langalpha-managed.md").read_text(
        encoding="utf-8"
    )

    assert "Steps 0-9" in overlay
    assert "outputs/book_package.json" in overlay
    assert "outputs/content_tree.json" in overlay
    assert "outputs/knowledge_points.json" in overlay
    assert "outputs/assets_manifest.json" in overlay
    assert ".langalpha/progress.jsonl" in overlay
    assert "char_start" in overlay and "char_end" in overlay
    assert "line_start" in overlay and "line_end" in overlay
    assert "quote" in overlay and "not used for locating" in overlay
    assert "Reading" in overlay and "not required" in overlay
    assert "network" in overlay and "MCP" in overlay


def test_book_to_skill_managed_overlay_dispatches_callers_mode():
    """Full-pipeline rules must not overwrite the legacy analyze pass."""
    overlay = (LOCAL_BUNDLE / "book-to-skill/reference/langalpha-managed.md").read_text(
        encoding="utf-8"
    )

    assert "mode=analyze-pass" in overlay
    assert "Steps 0-3" in overlay
    assert "outputs/structure.json" in overlay
    assert "langalpha-managed-textbook-structure/v2" in overlay
    assert "mode=full-pipeline" in overlay
    assert "Steps 0-9" in overlay
    assert "mode dispatch" in overlay.lower()


def test_book_to_skill_analyze_mode_keeps_the_v2_structure_schema():
    overlay = (LOCAL_BUNDLE / "book-to-skill/reference/langalpha-managed.md").read_text(
        encoding="utf-8"
    )

    assert "mode=analyze-pass" in overlay
    assert "Steps 0-3" in overlay
    assert "outputs/structure.json" in overlay
    assert "langalpha-managed-textbook-structure/v2" in overlay
    for field in (
        '"units"',
        '"readings"',
        '"slot"',
        '"title"',
        '"summary"',
        '"line_start"',
        '"line_end"',
    ):
        assert field in overlay
    assert "reading_a" in overlay
    assert "reading_b" in overlay
    assert "boundary" in overlay.lower()


def test_book_to_skill_managed_overlay_declares_progress_contract():
    overlay = (LOCAL_BUNDLE / "book-to-skill/reference/langalpha-managed.md").read_text(
        encoding="utf-8"
    )

    assert "queued | running | completed | failed | skipped" in overlay
    assert "event_key" in overlay
    assert "stage" in overlay
    assert "status" in overlay
    assert "model reasoning" in overlay
    assert "raw tool arguments" in overlay
    assert "credentials" in overlay
    assert "raw book passages" in overlay
