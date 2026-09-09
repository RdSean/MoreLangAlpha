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


def test_local_project_skills_remain_after_bundle_migration(
    bundle_root: Path, tmp_path: Path
) -> None:
    _write_bundle(bundle_root)
    project_skills = tmp_path / "local-skills"
    project_skills.mkdir()

    sources = SkillsConfig(project_skills_dir=str(project_skills)).local_skill_dirs_with_sandbox()

    assert str(bundle_root / "demo" / "skills") in [source for source, _ in sources]
    assert str(project_skills.resolve()) in [source for source, _ in sources]
