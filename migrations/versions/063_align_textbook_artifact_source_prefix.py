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


def _execute_ddl(sql: str) -> None:
    op.get_bind().exec_driver_sql(sql)


def _ensure_alembic_version_capacity() -> None:
    _execute_ddl(
        "ALTER TABLE alembic_version "
        "ALTER COLUMN version_num TYPE VARCHAR(255)"
    )


def _replace_constraint(*, regex: str) -> None:
    # Earlier revisions used an unnamed auto-generated name, then a named
    # replacement. Dropping IF EXISTS makes this safe for both histories.
    _execute_ddl(
        "ALTER TABLE education_textbook_artifact_sources "
        "DROP CONSTRAINT IF EXISTS "
        "education_textbook_artifact_sources_snapshot_prefix_check"
    )
    _execute_ddl(
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
    _ensure_alembic_version_capacity()
    _replace_constraint(regex=_COMPATIBILITY_REGEX)


def downgrade() -> None:
    _replace_constraint(regex=_COMPATIBILITY_REGEX)
