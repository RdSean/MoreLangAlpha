from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "055_tool_denylist.py"
)


def test_tool_denylist_follows_local_jsonb_merge_head() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "055_tool_denylist"
    assert migration["down_revision"] == "054_jsonb_deep_merge"


def test_tool_denylist_keeps_expand_contract_policy_columns() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS tool_denylist JSONB" in source
    # The local 046 port predates remote 036, so 055 must provide this
    # compatibility prerequisite before replacing the policy constraint.
    assert "ADD COLUMN IF NOT EXISTS policy_required BOOLEAN" in source
    assert "sandbox_egress_grants_policy_present" in source
    assert "tool_denylist IS NULL" in source
    assert "tool_allowlist IS NULL" in source


def test_tool_denylist_downgrade_fails_closed_before_drop() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    set_allowlist = source.index("SET tool_allowlist = '[]'::jsonb")
    drop_denylist = source.index("DROP COLUMN IF EXISTS tool_denylist")
    assert set_allowlist < drop_denylist
    assert "policy_required = true" in source


def test_tool_denylist_bumps_workspace_mcp_versions() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "mcp_config_version = ws.mcp_config_version + 1" in source
    assert "user_mcp_oauth_connections" in source
