from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "060_restore_finance_schema.py"
)


def test_restore_finance_schema_follows_direct_tools() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "060_restore_finance_schema"
    assert migration["down_revision"] == "059_direct_tools"


def test_restore_finance_schema_recreates_what_001_dropped() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS risk_preference JSONB" in source
    assert "ADD COLUMN IF NOT EXISTS investment_preference JSONB" in source
    for table in ("watchlists", "watchlist_items", "user_portfolios", "market_insights"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in source
    # 005 and 007 already ran here as empty stubs, so their effects are folded in.
    assert "idx_market_insights_user_generating" in source
    assert "user_id VARCHAR(255)" in source
    # The reader that made this mandatory reads the new columns every turn.
    assert "user_preferences" in source


def test_restore_finance_schema_downgrade_refuses_to_delete_data() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "still holds data" in source
    assert "LOCK TABLE" in source
