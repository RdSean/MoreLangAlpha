"""Add optional book-to-skill chapter asset jobs.

Revision ID: 070
Revises: 069
"""

from __future__ import annotations

from migrations.textbook_ddl import execute_textbook_ddl


revision = "070_book_asset_jobs"
down_revision = "069_learning_items_and_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_textbook_ddl(
        """
        ALTER TABLE education_textbook_structures
        ADD COLUMN book_asset_prefix TEXT,
        ADD COLUMN book_asset_manifest JSONB NOT NULL DEFAULT '{}'::jsonb
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


def downgrade() -> None:
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
                scope = 'structure'
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
        DROP CONSTRAINT IF EXISTS education_generation_jobs_scope_check
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        ADD CONSTRAINT education_generation_jobs_scope_check
        CHECK (scope IN ('structure', 'lesson'))
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_textbook_structures
        DROP COLUMN IF EXISTS book_asset_manifest,
        DROP COLUMN IF EXISTS book_asset_prefix
        """
    )
