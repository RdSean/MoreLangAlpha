"""Migration contract for unified managed book-pipeline jobs."""

from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3] / "migrations" / "versions" / "077_book_pipeline_jobs.py"
)


def test_book_pipeline_migration_follows_generic_content_tree() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "077_book_pipeline_jobs"
    assert migration["down_revision"] == "076_generic_content_tree"


def test_book_pipeline_migration_expands_scope_status_and_checkpoint() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "book_pipeline" in source
    assert "awaiting_review" in source
    assert "pause_after_chapter_analysis BOOLEAN NOT NULL DEFAULT FALSE" in source
    assert "education_generation_jobs_awaiting_review_check" in source
    assert "status <> 'awaiting_review'" in source
    assert "scope = 'book_pipeline'" in source
    assert "scope IN ('structure', 'assets', 'lesson', 'book_pipeline')" in source
    assert (
        "scope = 'book_pipeline'" in source
        and "structure_id IS NULL" in source
        and "knowledge_point_id IS NULL" in source
    )


def test_book_pipeline_migration_downgrade_only_removes_its_contract() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    downgrade = source.split("def downgrade() -> None:", maxsplit=1)[1]

    assert "DROP COLUMN IF EXISTS pause_after_chapter_analysis" in downgrade
    assert (
        "DROP CONSTRAINT IF EXISTS education_generation_jobs_awaiting_review_check"
        in downgrade
    )
    assert (
        "DROP CONSTRAINT IF EXISTS education_generation_jobs_status_check" in downgrade
    )
    assert "scope IN ('structure', 'assets', 'lesson')" in downgrade
    assert "DROP TABLE" not in downgrade
