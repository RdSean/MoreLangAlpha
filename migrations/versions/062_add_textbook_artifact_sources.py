"""Bind textbook content versions to completed library parse bundles.

Revision ID: 062
Revises: 061
"""

from __future__ import annotations

from alembic import op


revision = "062_textbook_artifact_sources"
down_revision = "061_document_usage_records"
branch_labels = None
depends_on = None


def _execute_ddl(sql: str) -> None:
    op.get_bind().exec_driver_sql(sql)


def upgrade() -> None:
    # Document, parse-job and artifact IDs are immutable provenance only. The
    # frozen source row must remain readable after those live rows are deleted.
    _execute_ddl(r"""
        CREATE TABLE education_textbook_artifact_sources (
            version_id UUID NOT NULL
                REFERENCES education_textbook_versions(version_id) ON DELETE RESTRICT,
            document_id VARCHAR(16) NOT NULL,
            producer_job_id VARCHAR(16) NOT NULL,
            primary_artifact_id VARCHAR(16) NOT NULL,
            position INTEGER NOT NULL CHECK (position > 0),
            source_filename VARCHAR(255) NOT NULL
                CHECK (length(btrim(source_filename)) > 0),
            source_media_type VARCHAR(127) NOT NULL
                CHECK (length(btrim(source_media_type)) > 0),
            source_format VARCHAR(32) NOT NULL
                CHECK (length(btrim(source_format)) > 0),
            parser_id VARCHAR(100) NOT NULL
                CHECK (length(btrim(parser_id)) > 0),
            parser_name VARCHAR(160) NOT NULL
                CHECK (length(btrim(parser_name)) > 0),
            parser_version VARCHAR(64),
            parse_completed_at TIMESTAMPTZ,
            primary_sha256 VARCHAR(64) NOT NULL
                CHECK (primary_sha256 ~ '^[0-9a-f]{64}$'),
            snapshot_prefix TEXT NOT NULL
                CHECK (
                    snapshot_prefix ~
                    '^education/[0-9A-Za-z][0-9A-Za-z.-]*/[0-9A-Za-z][0-9A-Za-z._-]*/source-bundles/[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/[0-9]{2,}/$'
                    AND snapshot_prefix !~ '\.\.'
                ),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (version_id, producer_job_id),
            UNIQUE (version_id, position)
        )
    """)
    _execute_ddl("""
        CREATE INDEX idx_education_textbook_artifact_sources_document
        ON education_textbook_artifact_sources (document_id, producer_job_id, version_id)
    """)


def downgrade() -> None:
    _execute_ddl(
        "DROP INDEX IF EXISTS idx_education_textbook_artifact_sources_document"
    )
    _execute_ddl("DROP TABLE IF EXISTS education_textbook_artifact_sources")
