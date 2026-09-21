"""Assign each knowledge point to one authoritative Reading scope.

Revision ID: 074
Revises: 073
"""

from __future__ import annotations

from migrations.textbook_ddl import execute_textbook_ddl


revision = "074_kp_reading_scope"
down_revision = "073_textbook_scopes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        ADD COLUMN scope_slot VARCHAR(16) CHECK (
            scope_slot IN ('reading_a', 'reading_b')
        )
        """
    )


def downgrade() -> None:
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        DROP COLUMN IF EXISTS scope_slot
        """
    )
