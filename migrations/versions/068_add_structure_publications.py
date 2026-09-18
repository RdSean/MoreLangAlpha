"""Allow textbook publications to freeze a structure and lesson revisions.

Revision ID: 068
Revises: 067
"""

from __future__ import annotations

from migrations.textbook_ddl import execute_textbook_ddl


revision = "068_structure_publications"
down_revision = "067_kp_lessons"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_textbook_ddl(
        """
        ALTER TABLE education_textbook_publications
        ADD COLUMN IF NOT EXISTS structure_id UUID
        REFERENCES education_textbook_structures(structure_id)
        ON DELETE RESTRICT
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_textbook_publications
        ALTER COLUMN teaching_package_id DROP NOT NULL
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_textbook_publications
        ADD CONSTRAINT education_textbook_publications_target_check
        CHECK (
            (
                teaching_package_id IS NOT NULL
                AND structure_id IS NULL
            )
            OR
            (
                teaching_package_id IS NULL
                AND structure_id IS NOT NULL
            )
        )
        """
    )


def downgrade() -> None:
    execute_textbook_ddl(
        """
        ALTER TABLE education_textbook_publications
        DROP CONSTRAINT IF EXISTS education_textbook_publications_target_check
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_textbook_publications
        DROP COLUMN IF EXISTS structure_id
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_textbook_publications
        ALTER COLUMN teaching_package_id SET NOT NULL
        """
    )
