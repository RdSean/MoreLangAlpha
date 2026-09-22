"""Add unified managed book-to-skill pipeline jobs.

Revision ID: 077
Revises: 076
"""

from __future__ import annotations

from migrations.textbook_ddl import execute_textbook_ddl


revision = "077_book_pipeline_jobs"
down_revision = "076_generic_content_tree"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        ADD COLUMN pause_after_chapter_analysis BOOLEAN NOT NULL DEFAULT FALSE
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        DROP CONSTRAINT IF EXISTS education_generation_jobs_awaiting_review_check
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        ADD CONSTRAINT education_generation_jobs_awaiting_review_check
        CHECK (
            status <> 'awaiting_review'
            OR (
                scope = 'book_pipeline'
                AND pause_after_chapter_analysis IS TRUE
            )
        )
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        DROP CONSTRAINT IF EXISTS education_generation_jobs_status_check
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        ADD CONSTRAINT education_generation_jobs_status_check
        CHECK (
            status IN (
                'queued', 'preparing', 'running', 'validating',
                'awaiting_review', 'completed', 'failed', 'cancelled'
            )
        )
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        DROP CONSTRAINT IF EXISTS education_generation_jobs_scope_check
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        ADD CONSTRAINT education_generation_jobs_scope_check
        CHECK (scope IN ('structure', 'assets', 'lesson', 'book_pipeline'))
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        DROP CONSTRAINT IF EXISTS education_generation_jobs_check
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        ADD CONSTRAINT education_generation_jobs_check
        CHECK (
            (
                scope IN ('structure', 'assets')
                AND structure_id IS NOT NULL
                AND knowledge_point_id IS NULL
            )
            OR
            (
                scope = 'lesson'
                AND structure_id IS NULL
                AND knowledge_point_id IS NOT NULL
            )
            OR
            (
                scope = 'book_pipeline'
                AND structure_id IS NULL
                AND knowledge_point_id IS NULL
            )
        )
        """
    )


def downgrade() -> None:
    # Fail closed when unified jobs exist. Restoring the legacy constraints
    # intentionally aborts instead of deleting or rewriting book_pipeline rows.
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        DROP CONSTRAINT IF EXISTS education_generation_jobs_awaiting_review_check
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        DROP CONSTRAINT IF EXISTS education_generation_jobs_status_check
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        ADD CONSTRAINT education_generation_jobs_status_check
        CHECK (
            status IN (
                'queued', 'preparing', 'running', 'validating',
                'completed', 'failed', 'cancelled'
            )
        )
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        DROP CONSTRAINT IF EXISTS education_generation_jobs_scope_check
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        ADD CONSTRAINT education_generation_jobs_scope_check
        CHECK (scope IN ('structure', 'assets', 'lesson'))
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        DROP CONSTRAINT IF EXISTS education_generation_jobs_check
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        ADD CONSTRAINT education_generation_jobs_check
        CHECK (
            (
                scope IN ('structure', 'assets')
                AND structure_id IS NOT NULL
                AND knowledge_point_id IS NULL
            )
            OR
            (
                scope = 'lesson'
                AND structure_id IS NULL
                AND knowledge_point_id IS NOT NULL
            )
        )
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        DROP COLUMN IF EXISTS pause_after_chapter_analysis
        """
    )
