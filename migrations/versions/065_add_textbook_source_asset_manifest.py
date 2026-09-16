"""Persist the safe artifact manifest for each frozen textbook source.

Revision ID: 065
Revises: 064
"""

from __future__ import annotations

from migrations.textbook_ddl import execute_textbook_ddl


revision = "065_textbook_source_asset_manifest"
down_revision = "064_textbook_source_prefix_constraint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_textbook_ddl(
        "ALTER TABLE education_textbook_artifact_sources "
        "ADD COLUMN IF NOT EXISTS asset_manifest JSONB "
        "NOT NULL DEFAULT '[]'::jsonb"
    )


def downgrade() -> None:
    execute_textbook_ddl(
        "ALTER TABLE education_textbook_artifact_sources "
        "DROP COLUMN IF EXISTS asset_manifest"
    )
