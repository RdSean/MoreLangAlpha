from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "058_workspace_file_blobs.py"
)


def test_workspace_file_blobs_follows_brokerage_capabilities() -> None:
    """The local chain owns 035-045, so upstream's 039 lands here as 058."""
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "058_workspace_file_blobs"
    assert migration["down_revision"] == "057_brokerage_capabilities"


def test_workspace_file_blobs_declares_registry_and_pointers() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS workspace_file_blobs" in source
    assert "PRIMARY KEY (user_id, sha256)" in source
    assert "ADD COLUMN IF NOT EXISTS blob_sha256 VARCHAR(64)" in source
    assert "ADD COLUMN IF NOT EXISTS kind VARCHAR(8) NOT NULL DEFAULT 'file'" in source
    assert "ADD COLUMN IF NOT EXISTS pack_sha256 VARCHAR(64)" in source
    assert "ADD COLUMN IF NOT EXISTS files_restore_incomplete_at" in source
    # The hot table takes exactly one ACCESS EXCLUSIVE window.
    assert "SET lock_timeout = '5s'" in source
    assert "autocommit_block" in source
    assert "CREATE INDEX CONCURRENTLY" in source


def test_workspace_file_blobs_downgrade_refuses_to_strand_bytes() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "backfill_workspace_file_blobs.py --reverse --apply" in source
    assert "LOCK TABLE workspace_files, workspaces IN ACCESS EXCLUSIVE MODE" in source
