from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "046_mcp_platform_core.py"
)


def test_mcp_platform_core_follows_local_document_library_head() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "046_mcp_platform_core"
    assert migration["down_revision"] == "045"


def test_mcp_platform_core_declares_new_remote_platform_tables() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for table in (
        "user_vault_secrets",
        "user_mcp_oauth_connections",
        "user_mcp_tool_schemas",
        "sandbox_egress_grants",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in source

    assert "ALTER TABLE user_mcp_servers" in source
    assert "ADD COLUMN IF NOT EXISTS enabled" in source

