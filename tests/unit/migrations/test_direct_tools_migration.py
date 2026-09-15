from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3] / "migrations" / "versions" / "059_direct_tools.py"
)


def test_direct_tools_follows_workspace_file_blobs() -> None:
    """Upstream's 040 lands after the renumbered blob migration."""
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "059_direct_tools"
    assert migration["down_revision"] == "058_workspace_file_blobs"


def test_direct_tools_records_the_bound_set_and_forces_a_resolve() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "ADD COLUMN tool_direct_only JSONB" in source
    # Every workspace with a connection has to recompute the bound set.
    assert "mcp_config_version = ws.mcp_config_version + 1" in source
    assert "DROP COLUMN IF EXISTS tool_direct_only" in source
