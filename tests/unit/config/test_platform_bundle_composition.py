"""Platform bundles participate in runtime MCP and Skills configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ptc_agent.config import plugins as bundles
from ptc_agent.config.agent import SkillsConfig
from ptc_agent.config.utils import create_mcp_config


def _write_bundle(root: Path) -> None:
    bundle = root / "demo"
    bundle.mkdir(parents=True)
    (bundle / "plugin.json").write_text(
        json.dumps(
            {
                "name": "demo",
                "extensions": {
                    "ai.langalpha": {
                        "servers": {
                            "demo-server": {
                                "description": "Demo server",
                                "instruction": "Use for tests",
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    (bundle / "mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "demo-server": {
                        "type": "stdio",
                        "command": "uv",
                        "args": ["run", "python", "plugins/demo/server.py"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    skill = bundle / "skills" / "demo-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: demo-skill\n---\n", encoding="utf-8")


@pytest.fixture
def bundle_root(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    root = tmp_path / "plugins"
    root.mkdir()
    monkeypatch.setattr(bundles, "BUNDLES_DIR", root)
    return root


def test_bundled_server_is_composed_before_operator_config(bundle_root: Path) -> None:
    _write_bundle(bundle_root)

    config = create_mcp_config(
        {
            "tool_discovery_enabled": True,
            "servers": [{"name": "operator", "command": "operator-mcp"}],
        }
    )

    assert [server.name for server in config.servers] == ["demo-server", "operator"]
    assert config.servers[0].description == "Demo server"
    assert config.servers[0].source == "builtin"


def test_skill_sources_are_the_bundles_then_the_operator_directory(
    bundle_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The chain is bundles first, the operator's own directory last.

    This deployment used to keep a cwd-relative ``skills/`` on top of the
    bundles. Its own skills now travel as the ``langalpha_local`` bundle, so
    nothing resolves against the working directory: a server started from
    anywhere finds the same set, and an operator can still override a shipped
    name by dropping it into ``user_skills_dir`` (later sources win).
    """
    _write_bundle(bundle_root)
    user_skills = tmp_path / "user-skills"
    user_skills.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    sources = SkillsConfig(user_skills_dir=str(user_skills)).local_skill_dirs_with_sandbox()
    resolved = [source for source, _ in sources]

    assert str(bundle_root / "demo" / "skills") in resolved
    assert str(user_skills) in resolved
    assert resolved[-1] == str(user_skills)
    # Nothing in the chain is derived from where the process happens to run.
    assert not any(str(elsewhere) in source for source in resolved)
