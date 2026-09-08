from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "050_plugin_owned_secrets.py"
)


def test_plugin_owned_secrets_follows_agent_plugins() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "050_plugin_owned_secrets"
    assert migration["down_revision"] == "049_agent_plugins"


def test_plugin_owned_secrets_uses_nullable_set_null_ownership() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS plugin_id UUID NULL" in source
    assert "FOREIGN KEY (user_id, plugin_id)" in source
    assert "ON DELETE SET NULL (plugin_id)" in source
    assert "idx_user_vault_secrets_plugin" in source

