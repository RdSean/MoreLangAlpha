from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "053_model_preference.py"
)


def test_model_preference_follows_in_flight_credits() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "053_model_preference"
    assert migration["down_revision"] == "052_in_flight_credits"


def test_model_preference_moves_only_model_keys() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "ADD COLUMN IF NOT EXISTS model_preference JSONB NOT NULL DEFAULT '{}'::jsonb" in source
    assert "jsonb_object_agg" in source
    assert "jsonb_exists_any" in source
    assert "feature_overrides" not in source.split("MOVED_KEYS", 1)[1].split(")", 1)[0]
    assert "DROP COLUMN IF EXISTS model_preference" in source

