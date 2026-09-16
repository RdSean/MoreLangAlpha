"""Replace the broad compatibility prefix check with explicit safe shapes.

Revision ID: 064
Revises: 063
"""

from __future__ import annotations

from alembic import op


revision = "064_textbook_source_prefix_constraint"
down_revision = "063_textbook_artifact_source_prefix"
branch_labels = None
depends_on = None


_HOUSEHOLD = r"[0-9A-Za-z][0-9A-Za-z.-]*"
_SLUG = r"[0-9A-Za-z][0-9A-Za-z._-]*"
_UUID = (
    r"[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}"
)
_COMPATIBILITY_REGEX = (
    r"^(?:"
    rf"education/{_HOUSEHOLD}/{_SLUG}/v[1-9][0-9]*/"
    r"source-bundles/[0-9]{2,}/"
    rf"|education/{_HOUSEHOLD}/{_SLUG}/{_UUID}/"
    r"source-bundles/[0-9]{2,}/"
    rf"|education/{_HOUSEHOLD}/{_SLUG}/source-bundles/"
    rf"{_UUID}/[0-9]{{2,}}/"
    r")$"
)
_DOWNGRADE_REGEX = _COMPATIBILITY_REGEX


def _replace_constraint(*, regex: str) -> None:
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
            AND snapshot_prefix ~ '{regex}'
        )
        """
    )


def upgrade() -> None:
    _replace_constraint(regex=_COMPATIBILITY_REGEX)


def downgrade() -> None:
    # Reapplying the exact upgrade set avoids rejecting rows that the upgrade
    # accepted while removing the broad 063 branch.
    _replace_constraint(regex=_DOWNGRADE_REGEX)
