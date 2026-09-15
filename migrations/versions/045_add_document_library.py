"""Add the user-private document library and durable parse jobs.

Revision ID: 045
Revises: 044
Create Date: 2026-09-05
"""

from alembic import op


revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE document_datasets (
            dataset_id VARCHAR(16) PRIMARY KEY
                CHECK (dataset_id ~ '^dts-[0-9A-Za-z]{12}$'),
            owner_user_id VARCHAR(255) NOT NULL
                REFERENCES users(user_id) ON DELETE CASCADE,
            name VARCHAR(120) NOT NULL CHECK (length(btrim(name)) > 0),
            description TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (dataset_id, owner_user_id)
        )
    """)
    op.execute("""
        CREATE INDEX idx_document_datasets_owner_updated
        ON document_datasets (owner_user_id, updated_at DESC, dataset_id)
    """)

    op.execute("""
        CREATE TABLE documents (
            document_id VARCHAR(16) PRIMARY KEY
                CHECK (document_id ~ '^doc-[0-9A-Za-z]{12}$'),
            owner_user_id VARCHAR(255) NOT NULL
                REFERENCES users(user_id) ON DELETE RESTRICT,
            original_filename VARCHAR(255) NOT NULL
                CHECK (length(btrim(original_filename)) > 0),
            media_type VARCHAR(127) NOT NULL,
            document_format VARCHAR(32) NOT NULL,
            source_storage_key TEXT NOT NULL UNIQUE
                CHECK (source_storage_key LIKE 'documents/%/source'),
            source_size_bytes BIGINT NOT NULL CHECK (source_size_bytes >= 0),
            source_sha256 VARCHAR(64) NOT NULL
                CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (document_id, owner_user_id)
        )
    """)
    op.execute("""
        CREATE INDEX idx_documents_owner_updated
        ON documents (owner_user_id, updated_at DESC, document_id)
    """)
    op.execute("""
        CREATE INDEX idx_documents_owner_format
        ON documents (owner_user_id, document_format, updated_at DESC)
    """)

    op.execute("""
        CREATE TABLE document_dataset_items (
            dataset_id VARCHAR(16) NOT NULL,
            document_id VARCHAR(16) NOT NULL,
            owner_user_id VARCHAR(255) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (dataset_id, document_id),
            FOREIGN KEY (dataset_id, owner_user_id)
                REFERENCES document_datasets(dataset_id, owner_user_id)
                ON DELETE CASCADE,
            FOREIGN KEY (document_id, owner_user_id)
                REFERENCES documents(document_id, owner_user_id)
                ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE INDEX idx_document_dataset_items_document
        ON document_dataset_items (document_id, dataset_id)
    """)

    op.execute("""
        CREATE TABLE document_tags (
            tag_id VARCHAR(16) PRIMARY KEY
                CHECK (tag_id ~ '^tag-[0-9A-Za-z]{12}$'),
            owner_user_id VARCHAR(255) NOT NULL
                REFERENCES users(user_id) ON DELETE CASCADE,
            name VARCHAR(80) NOT NULL CHECK (length(btrim(name)) > 0),
            normalized_name VARCHAR(80) NOT NULL
                CHECK (length(normalized_name) > 0),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (owner_user_id, normalized_name),
            UNIQUE (tag_id, owner_user_id)
        )
    """)
    op.execute("""
        CREATE INDEX idx_document_tags_owner_name
        ON document_tags (owner_user_id, normalized_name, tag_id)
    """)

    op.execute("""
        CREATE TABLE document_tag_assignments (
            tag_id VARCHAR(16) NOT NULL,
            document_id VARCHAR(16) NOT NULL,
            owner_user_id VARCHAR(255) NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (tag_id, document_id),
            FOREIGN KEY (tag_id, owner_user_id)
                REFERENCES document_tags(tag_id, owner_user_id)
                ON DELETE CASCADE,
            FOREIGN KEY (document_id, owner_user_id)
                REFERENCES documents(document_id, owner_user_id)
                ON DELETE CASCADE
        )
    """)
    op.execute("""
        CREATE INDEX idx_document_tag_assignments_document
        ON document_tag_assignments (document_id, tag_id)
    """)

    op.execute("""
        CREATE TABLE document_inspections (
            inspection_id VARCHAR(16) PRIMARY KEY
                CHECK (inspection_id ~ '^ins-[0-9A-Za-z]{12}$'),
            document_id VARCHAR(16) NOT NULL
                REFERENCES documents(document_id) ON DELETE CASCADE,
            inspector_id VARCHAR(100) NOT NULL,
            inspector_name VARCHAR(160) NOT NULL,
            inspector_version VARCHAR(64),
            status VARCHAR(16) NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'completed', 'failed')),
            detected_format VARCHAR(32),
            classification VARCHAR(32)
                CHECK (classification IS NULL OR classification IN (
                    'text_based', 'mixed', 'scanned', 'image_based', 'unknown'
                )),
            summary JSONB NOT NULL DEFAULT '{}'::jsonb,
            details JSONB NOT NULL DEFAULT '{}'::jsonb,
            error_code VARCHAR(64),
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            UNIQUE (document_id, inspection_id)
        )
    """)
    op.execute("""
        CREATE INDEX idx_document_inspections_document_created
        ON document_inspections (document_id, created_at DESC, inspection_id)
    """)
    op.execute("""
        CREATE INDEX idx_document_inspections_classification
        ON document_inspections (classification, created_at DESC)
        WHERE status = 'completed'
    """)

    op.execute("""
        CREATE TABLE document_parse_jobs (
            job_id VARCHAR(16) PRIMARY KEY
                CHECK (job_id ~ '^job-[0-9A-Za-z]{12}$'),
            document_id VARCHAR(16) NOT NULL,
            inspection_id VARCHAR(16) NOT NULL,
            parser_id VARCHAR(100) NOT NULL,
            parser_name VARCHAR(160) NOT NULL,
            parser_version VARCHAR(64),
            parser_options JSONB NOT NULL DEFAULT '{}'::jsonb,
            request_mode VARCHAR(8) NOT NULL
                CHECK (request_mode IN ('sync', 'async')),
            status VARCHAR(16) NOT NULL DEFAULT 'queued'
                CHECK (status IN (
                    'queued', 'running', 'completed', 'failed', 'cancelled'
                )),
            stage VARCHAR(16) NOT NULL DEFAULT 'queued'
                CHECK (stage IN (
                    'queued', 'preparing', 'parsing', 'storing',
                    'completed', 'failed', 'cancelled'
                )),
            percentage INTEGER NOT NULL DEFAULT 0
                CHECK (percentage BETWEEN 0 AND 100),
            status_version BIGINT NOT NULL DEFAULT 0 CHECK (status_version >= 0),
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
            claimed_by VARCHAR(255),
            lease_expires_at TIMESTAMPTZ,
            cancellation_requested_at TIMESTAMPTZ,
            error_code VARCHAR(64),
            error_message TEXT,
            primary_artifact_id VARCHAR(16),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (document_id, inspection_id)
                REFERENCES document_inspections(document_id, inspection_id)
                ON DELETE CASCADE,
            UNIQUE (job_id, document_id)
        )
    """)
    op.execute("""
        CREATE INDEX idx_document_parse_jobs_document_created
        ON document_parse_jobs (document_id, created_at DESC, job_id)
    """)
    op.execute("""
        CREATE INDEX idx_document_parse_jobs_claimable
        ON document_parse_jobs (status, lease_expires_at, created_at, job_id)
        WHERE status IN ('queued', 'running')
    """)

    op.execute(r"""
        CREATE TABLE document_artifacts (
            artifact_id VARCHAR(16) PRIMARY KEY
                CHECK (artifact_id ~ '^art-[0-9A-Za-z]{12}$'),
            document_id VARCHAR(16) NOT NULL,
            producer_job_id VARCHAR(16) NOT NULL,
            artifact_kind VARCHAR(32) NOT NULL
                CHECK (artifact_kind IN (
                    'primary_document', 'embedded_image',
                    'structured_data', 'manifest'
                )),
            format VARCHAR(64) NOT NULL,
            media_type VARCHAR(127) NOT NULL,
            schema_name VARCHAR(160),
            schema_version VARCHAR(64),
            relative_path TEXT NOT NULL
                CHECK (length(relative_path) > 0)
                CHECK (relative_path !~ '(^/|(^|/)\.\.(/|$))'),
            storage_key TEXT NOT NULL UNIQUE
                CHECK (storage_key LIKE 'documents/%/artifacts/%'),
            locator JSONB,
            metadata JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (producer_job_id, document_id)
                REFERENCES document_parse_jobs(job_id, document_id)
                ON DELETE CASCADE,
            UNIQUE (artifact_id, producer_job_id),
            UNIQUE (producer_job_id, relative_path)
        )
    """)
    op.execute("""
        CREATE INDEX idx_document_artifacts_document_created
        ON document_artifacts (document_id, created_at DESC, artifact_id)
    """)
    op.execute("""
        CREATE INDEX idx_document_artifacts_job_kind
        ON document_artifacts (producer_job_id, artifact_kind, artifact_id)
    """)
    op.execute("""
        ALTER TABLE document_parse_jobs
        ADD CONSTRAINT fk_document_parse_jobs_primary_artifact
        FOREIGN KEY (primary_artifact_id, job_id)
        REFERENCES document_artifacts(artifact_id, producer_job_id)
        ON DELETE SET NULL (primary_artifact_id)
    """)

    for table in (
        "document_datasets",
        "documents",
        "document_tags",
        "document_inspections",
        "document_parse_jobs",
        "document_artifacts",
    ):
        op.execute(f"""
            CREATE TRIGGER trg_{table}_updated_at
                BEFORE UPDATE ON {table}
                FOR EACH ROW
                EXECUTE FUNCTION update_updated_at_column()
        """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE document_parse_jobs
        DROP CONSTRAINT IF EXISTS fk_document_parse_jobs_primary_artifact
    """)
    op.execute("DROP TABLE IF EXISTS document_artifacts")
    op.execute("DROP TABLE IF EXISTS document_parse_jobs")
    op.execute("DROP TABLE IF EXISTS document_inspections")
    op.execute("DROP TABLE IF EXISTS document_tag_assignments")
    op.execute("DROP TABLE IF EXISTS document_tags")
    op.execute("DROP TABLE IF EXISTS document_dataset_items")
    op.execute("DROP TABLE IF EXISTS documents")
    op.execute("DROP TABLE IF EXISTS document_datasets")
