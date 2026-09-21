"""Reset the pre-canonical textbook pipeline data.

Revision ID: 075
Revises: 074
"""

from __future__ import annotations

from migrations.textbook_ddl import execute_textbook_ddl


revision = "075_reset_textbook_pipeline"
down_revision = "074_kp_reading_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The dependency graph already has the scope-aware shape. Clearing the
    # textbook root is safer than replaying dozens of destructive table DDLs,
    # while CASCADE removes every version, structure, lesson, assignment and
    # progress row that belongs to a textbook.
    execute_textbook_ddl(
        """
        TRUNCATE TABLE education_textbooks
        RESTART IDENTITY CASCADE
        """
    )


def downgrade() -> None:
    # Data deletion is intentionally irreversible.
    pass
