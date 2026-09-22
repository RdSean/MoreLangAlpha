"""Migration contract for book-pipeline briefs and request idempotency."""

from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "078_book_pipeline_idempotency.py"
)


def test_book_pipeline_idempotency_migration_follows_unified_jobs() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "078_book_pipeline_idempotency"
    assert migration["down_revision"] == "077_book_pipeline_jobs"


def test_book_pipeline_idempotency_migration_persists_request_and_brief() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "ADD COLUMN request_id UUID NULL" in source
    assert "ADD COLUMN processing_brief TEXT NOT NULL DEFAULT ''" in source
    assert "char_length(processing_brief) <= 4000" in source
    assert "CREATE UNIQUE INDEX" in source
    assert "(version_id, request_id)" in source
    assert "WHERE request_id IS NOT NULL" in source


def test_book_pipeline_idempotency_migration_removes_only_its_contract() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    downgrade = source.split("def downgrade() -> None:", maxsplit=1)[1]

    assert "RAISE EXCEPTION" in downgrade
    assert "request_id IS NOT NULL" in downgrade
    assert "processing_brief <> ''" in downgrade
    assert "DROP INDEX IF EXISTS" in downgrade
    assert "DROP COLUMN IF EXISTS request_id" in downgrade
    assert "DROP COLUMN IF EXISTS processing_brief" in downgrade
    assert "DROP TABLE" not in downgrade
