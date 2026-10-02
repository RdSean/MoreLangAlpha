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


NATIVE_BOOK_SKILLS = ("more-to-skills",)
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

    more_to_skills = (LOCAL_BUNDLE / "more-to-skills/SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "more-to-skills" in more_to_skills
    assert "SKILL.md" in more_to_skills
