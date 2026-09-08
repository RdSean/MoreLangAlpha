from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "052_in_flight_credits.py"
)


def test_in_flight_credits_follows_account_disable_kind() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "052_in_flight_credits"
    assert migration["down_revision"] == "051_account_disable_kind"


def test_in_flight_credits_adds_ledger_columns_constraints_and_indexes() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    for table in ("conversation_responses", "subagent_runs"):
        assert table in source
        assert "in_flight_credits NUMERIC NOT NULL DEFAULT 0" in source
        assert "usage_settled_at TIMESTAMPTZ" in source
    assert "in_flight_credits_nonneg" in source

    assert "ix_responses_in_flight_by_user" in source
    assert "ix_subagent_runs_in_flight_by_user" in source
    assert "ix_subagent_runs_settled_by_parent" in source
