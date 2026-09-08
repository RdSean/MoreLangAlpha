from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "047_user_skills.py"
)


def test_user_skills_migration_follows_mcp_platform_core() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "047_user_skills"
    assert migration["down_revision"] == "046_mcp_platform_core"


def test_user_skills_schema_has_scope_archive_and_disable_contract() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for field in (
        "workspace_id UUID NULL",
        "command VARCHAR(64) NULL",
        "plugin_id UUID NULL",
        "content_hash VARCHAR(71) NOT NULL",
        "archive_key TEXT NULL",
        "archive_blob BYTEA NULL",
        "CONSTRAINT user_skills_archive_present CHECK",
    ):
        assert field in source

    for index in (
        "uq_user_skills_user_name",
        "uq_user_skills_workspace_name",
        "uq_user_skills_user_command",
        "uq_user_skills_workspace_command",
    ):
        assert index in source

    assert "CREATE TABLE IF NOT EXISTS workspace_skill_disables" in source

