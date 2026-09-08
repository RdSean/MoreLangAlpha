from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "054_jsonb_deep_merge.py"
)


def test_jsonb_deep_merge_follows_model_preference() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "054_jsonb_deep_merge"
    assert migration["down_revision"] == "053_model_preference"


def test_jsonb_deep_merge_declares_recursive_null_delete_function() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "CREATE OR REPLACE FUNCTION jsonb_deep_merge(a jsonb, b jsonb)" in source
    assert "LANGUAGE plpgsql" in source
    assert "jsonb_object_keys(b)" in source
    assert "merged := merged - k" in source
    assert "jsonb_deep_merge(" in source
    assert "DROP FUNCTION IF EXISTS jsonb_deep_merge(jsonb, jsonb)" in source

