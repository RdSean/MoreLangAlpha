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


def upgrade() -> None:
    op.execute("""
        CREATE TABLE education_textbook_artifact_sources (
            version_id UUID NOT NULL
                REFERENCES education_textbook_versions(version_id) ON DELETE RESTRICT,
            document_id VARCHAR(16) NOT NULL
                REFERENCES documents(document_id) ON DELETE RESTRICT,
            producer_job_id VARCHAR(16) NOT NULL,
            primary_artifact_id VARCHAR(16) NOT NULL,
            position INTEGER NOT NULL CHECK (position > 0),
            primary_sha256 VARCHAR(64) NOT NULL
                CHECK (primary_sha256 ~ '^[0-9a-f]{64}$'),
            snapshot_prefix TEXT NOT NULL
                CHECK (snapshot_prefix LIKE 'education/%'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (version_id, producer_job_id),
            UNIQUE (version_id, position),
            FOREIGN KEY (producer_job_id, document_id)
                REFERENCES document_parse_jobs(job_id, document_id)
                ON DELETE RESTRICT,
            FOREIGN KEY (primary_artifact_id, producer_job_id)
                REFERENCES document_artifacts(artifact_id, producer_job_id)
                ON DELETE RESTRICT
        )
    """)
    op.execute("""
        CREATE INDEX idx_education_textbook_artifact_sources_document
        ON education_textbook_artifact_sources (document_id, producer_job_id, version_id)
    """)


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS idx_education_textbook_artifact_sources_document"
    )
    op.execute("DROP TABLE IF EXISTS education_textbook_artifact_sources")
