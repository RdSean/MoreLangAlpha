"""Store the immutable continuation bundle for a book-pipeline checkpoint.

Revision ID: 081
Revises: 080
"""

from __future__ import annotations

from migrations.textbook_ddl import execute_textbook_ddl


revision = "081_book_pipeline_checkpoint"
down_revision = "080_education_job_progress"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        ADD COLUMN checkpoint_bundle_prefix TEXT NULL
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        ADD CONSTRAINT ck_education_generation_jobs_checkpoint_prefix
        CHECK (
            (
                checkpoint_bundle_prefix IS NULL
                OR (
                    btrim(checkpoint_bundle_prefix) <> ''
                    AND checkpoint_bundle_prefix LIKE 'education/%%'
                    AND checkpoint_bundle_prefix NOT LIKE '%%..%%'
                )
            )
            AND (
                status <> 'awaiting_review'
                OR (
                    checkpoint_bundle_prefix IS NOT NULL
                    AND btrim(checkpoint_bundle_prefix) <> ''
                )
            )
        )
        """
    )


def downgrade() -> None:
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        DROP CONSTRAINT IF EXISTS ck_education_generation_jobs_checkpoint_prefix
        """
    )
    execute_textbook_ddl(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM education_generation_jobs
                WHERE checkpoint_bundle_prefix IS NOT NULL
            ) THEN
                RAISE EXCEPTION
                    'cannot downgrade 081 while checkpoint data exists';
            END IF;
        END
        $$
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        DROP COLUMN IF EXISTS checkpoint_bundle_prefix
        """
    )
