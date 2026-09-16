"""Align textbook source snapshot prefixes without invalidating legacy rows.

Revision ID: 063
Revises: 062
"""

from __future__ import annotations

from alembic import op


revision = "063_textbook_artifact_source_prefix"
down_revision = "062_textbook_artifact_sources"
branch_labels = None
depends_on = None


_NEW_PREFIX = (
    r"^education/[0-9A-Za-z][0-9A-Za-z.-]*/"
    r"[0-9A-Za-z][0-9A-Za-z._-]*/source-bundles/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}/[0-9]{2,}/$"
)
_LEGACY_SEQUENCE_PREFIX = (
    r"^education/[0-9A-Za-z][0-9A-Za-z.-]*/"
    r"[0-9A-Za-z][0-9A-Za-z._-]*/v[1-9][0-9]*/"
    r"source-bundles/[0-9]{2,}/$"
)
_LEGACY_VERSION_DIRECTORY_PREFIX = (
    r"^education/[0-9A-Za-z][0-9A-Za-z.-]*/"
    r"[0-9A-Za-z][0-9A-Za-z._-]*/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}/source-bundles/[0-9]{2,}/$"
)


def upgrade() -> None:
    # Earlier revisions used an unnamed auto-generated name, then a named
    # replacement. Dropping IF EXISTS makes this safe for both histories.
    op.execute(
        "ALTER TABLE education_textbook_artifact_sources "
        "DROP CONSTRAINT IF EXISTS "
        "education_textbook_artifact_sources_snapshot_prefix_check"
    )
    op.execute(
        f"""
        ALTER TABLE education_textbook_artifact_sources
        ADD CONSTRAINT education_textbook_artifact_sources_snapshot_prefix_check
        CHECK (
            snapshot_prefix !~ '\\.\\.'
            AND (
                snapshot_prefix LIKE 'education/%'
                OR snapshot_prefix ~ '{_LEGACY_SEQUENCE_PREFIX}'
                OR snapshot_prefix ~ '{_LEGACY_VERSION_DIRECTORY_PREFIX}'
                OR snapshot_prefix ~ '{_NEW_PREFIX}'
            )
        )
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE education_textbook_artifact_sources "
        "DROP CONSTRAINT IF EXISTS "
        "education_textbook_artifact_sources_snapshot_prefix_check"
    )
    op.execute(
        f"""
        ALTER TABLE education_textbook_artifact_sources
        ADD CONSTRAINT education_textbook_artifact_sources_snapshot_prefix_check
        CHECK (
            snapshot_prefix ~ '{_NEW_PREFIX}'
            AND snapshot_prefix !~ '\\.\\.'
        )
        """
    )
