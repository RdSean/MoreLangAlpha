"""Persist semantic progress events for managed education generation jobs.

Revision ID: 080
Revises: 079
"""

from __future__ import annotations

from migrations.textbook_ddl import execute_textbook_ddl


revision = "080_education_job_progress"
down_revision = "079_book_pipeline_package_import"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_attempts
        ADD CONSTRAINT uq_education_generation_attempts_job_attempt
        UNIQUE (generation_job_id, attempt_id)
        """
    )
    execute_textbook_ddl(
        """
        CREATE TABLE education_generation_progress_events (
            event_id BIGSERIAL PRIMARY KEY,
            generation_job_id UUID NOT NULL
                CONSTRAINT fk_education_generation_progress_job
                REFERENCES education_generation_jobs(generation_job_id)
                ON DELETE CASCADE,
            attempt_id UUID NOT NULL,
            run_id UUID NULL,
            sequence BIGINT NOT NULL,
            event_key TEXT NOT NULL,
            stage VARCHAR(64) NOT NULL,
            substage VARCHAR(64) NULL,
            status VARCHAR(24) NOT NULL,
            label TEXT NOT NULL,
            detail TEXT NULL,
            node_key TEXT NULL,
            current_value INTEGER NULL,
            total_value INTEGER NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT fk_education_generation_progress_attempt_ownership
            FOREIGN KEY (generation_job_id, attempt_id)
            REFERENCES education_generation_attempts(generation_job_id, attempt_id)
            ON DELETE CASCADE
        )
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_progress_events
        ADD CONSTRAINT uq_education_generation_progress_attempt_sequence
        UNIQUE (attempt_id, sequence)
        """
    )
    execute_textbook_ddl(
        """
        CREATE INDEX idx_education_generation_progress_job_attempt_sequence
        ON education_generation_progress_events (
            generation_job_id, attempt_id, sequence
        )
        """
    )


def downgrade() -> None:
    execute_textbook_ddl("DROP TABLE IF EXISTS education_generation_progress_events")
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_attempts
        DROP CONSTRAINT IF EXISTS uq_education_generation_attempts_job_attempt
        """
    )
