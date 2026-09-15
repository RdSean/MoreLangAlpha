from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "048_builtin_mcp_disables.py"
)


def test_builtin_disable_migration_follows_user_skills() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "048_builtin_mcp_disables"
    assert migration["down_revision"] == "047_user_skills"


def test_builtin_disable_schema_is_account_scoped_and_idempotent() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS user_mcp_builtin_disables" in source
    assert "user_id VARCHAR(255) NOT NULL" in source
    assert "name VARCHAR(255) NOT NULL" in source
    assert "PRIMARY KEY (user_id, name)" in source
