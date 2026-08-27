"""Contracts for the default family homework Skill."""

import re
from pathlib import Path

import yaml

from ptc_agent.agent.middleware.skills.registry import (
    SKILL_REGISTRY,
    get_skill_registry,
)


SKILL_NAME = "family-homework"
REPO_ROOT = Path(__file__).resolve().parents[4]


def test_family_homework_is_registered_for_both_agent_modes():
    skill = SKILL_REGISTRY[SKILL_NAME]
    assert skill.tools[0].name == "education_create_homework"
    assert skill.skill_md_path == f"skills/{SKILL_NAME}/SKILL.md"
    assert skill.exposure == "both"
    assert SKILL_NAME in get_skill_registry("ptc")
    assert SKILL_NAME in get_skill_registry("flash")


def test_family_homework_skill_frontmatter_matches_registry():
    skill = SKILL_REGISTRY[SKILL_NAME]
    text = (REPO_ROOT / skill.skill_md_path).read_text(encoding="utf-8")
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    assert match
    frontmatter = yaml.safe_load(match.group(1))
    assert frontmatter["name"] == SKILL_NAME
    assert frontmatter["description"] == skill.description


def test_family_homework_skill_requires_tool_and_text_only_boundary():
    text = (REPO_ROOT / SKILL_REGISTRY[SKILL_NAME].skill_md_path).read_text(encoding="utf-8")
    assert "education_create_homework" in text
    assert "Do not claim" in text
    assert "text instructions only" in text
    assert "images, PDFs" in text
    assert "multiple children" in text
    assert "语文 `chinese`" in text
    assert "校内作业 `schoolwork`" in text
