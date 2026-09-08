from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "051_account_disable_kind.py"
)


def test_account_disable_kind_follows_plugin_owned_secrets() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "051_account_disable_kind"
    assert migration["down_revision"] == "050_plugin_owned_secrets"


def test_account_disable_kind_preserves_servers_and_adds_bundle_scope() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS kind VARCHAR(16) NOT NULL DEFAULT 'server'" in source
    assert "CHECK (kind IN ('server', 'bundle'))" in source
    assert "DROP CONSTRAINT IF EXISTS user_mcp_builtin_disables_pkey" in source
    assert "PRIMARY KEY (user_id, kind, name)" in source
    assert "DELETE FROM user_mcp_builtin_disables WHERE kind <> 'server'" in source
