"""Retain revision continuity after removing the retired insights table.

Revision ID: 007
Revises: 006
Create Date: 2026-03-30
"""

revision: str = "007"
down_revision: str = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
