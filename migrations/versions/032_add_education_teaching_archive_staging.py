"""Persist validated teaching candidates while private archive storage recovers.

Revision ID: 032
Revises: 031
"""

from alembic import op


revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE education_teaching_archive_staging (
            attempt_id UUID PRIMARY KEY
                REFERENCES education_teaching_attempts(attempt_id) ON DELETE RESTRICT,
            job_id UUID NOT NULL
                REFERENCES education_teaching_jobs(job_id) ON DELETE RESTRICT,
            root_run_id UUID NOT NULL
                REFERENCES conversation_responses(conversation_response_id) ON DELETE RESTRICT,
            validated_assets JSONB NOT NULL,
            output_bundle BYTEA NOT NULL,
            output_bundle_sha256 VARCHAR(64) NOT NULL
                CHECK (output_bundle_sha256 ~ '^[0-9a-f]{64}$'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE INDEX idx_education_teaching_archive_staging_job_attempt
        ON education_teaching_archive_staging (job_id, attempt_id)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_education_teaching_archive_staging_job_attempt")
    op.execute("DROP TABLE IF EXISTS education_teaching_archive_staging")
