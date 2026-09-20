"""Persist recoverable structure validation warnings.

Revision ID: 072
Revises: 071
"""

from __future__ import annotations

from migrations.textbook_ddl import execute_textbook_ddl


revision = "072_structure_validation_warnings"
down_revision = "071_remove_legacy_teaching_packages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_textbook_ddl(
        """
        ALTER TABLE education_textbook_structures
        ADD COLUMN validation_warnings JSONB NOT NULL DEFAULT '[]'::jsonb
        """
    )


def downgrade() -> None:
    execute_textbook_ddl(
        """
        ALTER TABLE education_textbook_structures
        DROP COLUMN IF EXISTS validation_warnings
        """
    )
