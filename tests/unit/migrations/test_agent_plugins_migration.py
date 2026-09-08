from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "049_agent_plugins.py"
)


def test_agent_plugins_migration_follows_builtin_disables() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "049_agent_plugins"
    assert migration["down_revision"] == "048_builtin_mcp_disables"


def test_agent_plugins_schema_declares_ownership_and_restricts_deletion() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS user_plugins" in source
    for field in (
        "name VARCHAR(64) NOT NULL",
        "source_type VARCHAR(8) NOT NULL",
        "manifest JSONB NOT NULL",
        "mcp_document JSONB NULL",
        "content_hash TEXT NOT NULL",
        "enabled BOOLEAN NOT NULL DEFAULT TRUE",
    ):
        assert field in source

    assert "ADD COLUMN IF NOT EXISTS plugin_id UUID NULL" in source
    assert "ADD COLUMN IF NOT EXISTS plugin_server_key TEXT NULL" in source
    assert "FOREIGN KEY (user_id, plugin_id)" in source
    assert "ON DELETE RESTRICT" in source

