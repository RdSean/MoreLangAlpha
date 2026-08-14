"""Persist safe v2 textbook teaching-asset manifests and milestones.

Revision ID: 031
Revises: 030
"""

from alembic import op


revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE education_teaching_packages "
        "ADD COLUMN asset_manifest JSONB NOT NULL DEFAULT '{}'::jsonb"
    )
    op.execute(
        "ALTER TABLE education_teaching_events "
        "ADD COLUMN asset_kind VARCHAR(32)"
    )
    op.execute(
        "ALTER TABLE education_teaching_events "
        "ADD CONSTRAINT education_teaching_events_asset_kind_check "
        "CHECK (asset_kind IS NULL OR asset_kind IN ('knowledge', 'toolkit', 'practice', 'teaching'))"
    )
    op.execute("ALTER TABLE education_teaching_events DROP CONSTRAINT IF EXISTS education_teaching_events_phase_check")
    op.execute(
        "ALTER TABLE education_teaching_events "
        "ADD CONSTRAINT education_teaching_events_phase_check "
        "CHECK (phase IN ("
        "'queued', 'preparing', 'building_skill', 'generating_teaching', 'validating', "
        "'review', 'failed', 'cancelled', 'planning', 'chapter_mapping', "
        "'concept_linking', 'coverage_audit', 'practice_build', 'teaching_build', "
        "'bundle_assembling', 'validating_bundle'"
        "))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE education_teaching_events DROP CONSTRAINT IF EXISTS education_teaching_events_phase_check")
    op.execute(
        "ALTER TABLE education_teaching_events "
        "ADD CONSTRAINT education_teaching_events_phase_check "
        "CHECK (phase IN ('queued', 'preparing', 'building_skill', 'generating_teaching', "
        "'validating', 'review', 'failed', 'cancelled'))"
    )
    op.execute(
        "ALTER TABLE education_teaching_events "
        "DROP CONSTRAINT IF EXISTS education_teaching_events_asset_kind_check"
    )
    op.execute("ALTER TABLE education_teaching_events DROP COLUMN IF EXISTS asset_kind")
    op.execute("ALTER TABLE education_teaching_packages DROP COLUMN IF EXISTS asset_manifest")
