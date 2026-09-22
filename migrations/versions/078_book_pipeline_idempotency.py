"""Persist book-pipeline briefs and request idempotency keys.

Revision ID: 078
Revises: 077
"""

from __future__ import annotations

from migrations.textbook_ddl import execute_textbook_ddl


revision = "078_book_pipeline_idempotency"
down_revision = "077_book_pipeline_jobs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        ADD COLUMN request_id UUID NULL
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        ADD COLUMN processing_brief TEXT NOT NULL DEFAULT ''
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        ADD CONSTRAINT education_generation_jobs_processing_brief_length_check
        CHECK (char_length(processing_brief) <= 4000)
        """
    )
    execute_textbook_ddl(
        """
        CREATE UNIQUE INDEX uq_education_generation_jobs_version_request_id
        ON education_generation_jobs (version_id, request_id)
        WHERE request_id IS NOT NULL
        """
    )


def downgrade() -> None:
    execute_textbook_ddl(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM education_generation_jobs
                WHERE request_id IS NOT NULL OR processing_brief <> ''
            ) THEN
                RAISE EXCEPTION
                    'cannot downgrade 078 while book pipeline idempotency data exists';
            END IF;
        END
        $$
        """
    )
    execute_textbook_ddl(
        """
        DROP INDEX IF EXISTS uq_education_generation_jobs_version_request_id
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        DROP CONSTRAINT IF EXISTS education_generation_jobs_processing_brief_length_check
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        DROP COLUMN IF EXISTS request_id
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        DROP COLUMN IF EXISTS processing_brief
        """
    )
