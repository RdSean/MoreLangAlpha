"""Migration contract for persisted semantic generation progress events."""

from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "080_education_job_progress.py"
)


def test_education_job_progress_migration_follows_package_import() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "080_education_job_progress"
    assert migration["down_revision"] == "079_book_pipeline_package_import"


def test_education_job_progress_migration_defines_event_contract() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    normalized = " ".join(source.split())

    assert "CREATE TABLE education_generation_progress_events" in normalized
    for column in (
        "event_id BIGSERIAL PRIMARY KEY",
        "generation_job_id UUID NOT NULL",
        "attempt_id UUID NOT NULL",
        "run_id UUID NULL",
        "sequence BIGINT NOT NULL",
        "event_key TEXT NOT NULL",
        "stage VARCHAR(64) NOT NULL",
        "substage VARCHAR(64) NULL",
        "status VARCHAR(24) NOT NULL",
        "label TEXT NOT NULL",
        "detail TEXT NULL",
        "node_key TEXT NULL",
        "current_value INTEGER NULL",
        "total_value INTEGER NULL",
        "metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
        "created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()",
    ):
        assert column in normalized

    assert (
        "UNIQUE (attempt_id, sequence)" in normalized
        or "uq_education_generation_progress_attempt_sequence" in normalized
    )
    assert "uq_education_generation_progress_attempt_event_sequence" not in normalized
    assert (
        "REFERENCES education_generation_jobs(generation_job_id) ON DELETE CASCADE"
    ) in normalized
    assert (
        "UNIQUE (generation_job_id, attempt_id)"
    ) in normalized
    assert (
        "FOREIGN KEY (generation_job_id, attempt_id) "
        "REFERENCES education_generation_attempts(generation_job_id, attempt_id) "
        "ON DELETE CASCADE"
    ) in normalized
    assert "idx_education_generation_progress_job_attempt_sequence" in normalized


def test_education_job_progress_migration_downgrade_removes_080_owned_objects() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    downgrade = source.split("def downgrade() -> None:", maxsplit=1)[1]

    assert "DROP TABLE IF EXISTS education_generation_progress_events" in downgrade
    assert (
        "DROP CONSTRAINT IF EXISTS uq_education_generation_attempts_job_attempt"
        in downgrade
    )
