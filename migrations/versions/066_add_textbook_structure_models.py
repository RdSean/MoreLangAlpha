"""Add reviewable textbook structures and scoped generation jobs.

Revision ID: 066
Revises: 065
"""

from __future__ import annotations

from migrations.textbook_ddl import execute_textbook_ddl


revision = "066_textbook_structure_models"
down_revision = "065_textbook_source_asset_manifest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_textbook_ddl(
        """
        CREATE TABLE education_textbook_structures (
            structure_id UUID PRIMARY KEY,
            version_id UUID NOT NULL
                REFERENCES education_textbook_versions(version_id)
                ON DELETE RESTRICT,
            sequence INTEGER NOT NULL CHECK (sequence > 0),
            status VARCHAR(24) NOT NULL CHECK (
                status IN (
                    'queued', 'running', 'review', 'accepted',
                    'failed', 'cancelled'
                )
            ),
            schema_version VARCHAR(64) NOT NULL,
            processing_profile_id UUID,
            processing_profile_sha256 VARCHAR(64) NOT NULL,
            input_manifest_sha256 VARCHAR(64) NOT NULL,
            source_revision VARCHAR(64) NOT NULL,
            bundle_prefix TEXT,
            created_by_user_id VARCHAR(255) NOT NULL
                REFERENCES users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            reviewed_at TIMESTAMPTZ,
            UNIQUE (version_id, sequence)
        )
        """
    )
    execute_textbook_ddl(
        """
        CREATE TABLE education_structure_units (
            unit_id UUID PRIMARY KEY,
            structure_id UUID NOT NULL
                REFERENCES education_textbook_structures(structure_id)
                ON DELETE RESTRICT,
            position INTEGER NOT NULL CHECK (position > 0),
            slug VARCHAR(255) NOT NULL,
            title VARCHAR(255) NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            unit_type VARCHAR(32) NOT NULL CHECK (
                unit_type IN (
                    'teaching', 'front_matter', 'reference', 'appendix'
                )
            ),
            source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
            confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
            status VARCHAR(24) NOT NULL CHECK (
                status IN ('review', 'accepted', 'blocked')
            ),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (structure_id, position),
            UNIQUE (structure_id, slug)
        )
        """
    )
    execute_textbook_ddl(
        """
        CREATE TABLE education_structure_knowledge_points (
            knowledge_point_id UUID PRIMARY KEY,
            unit_id UUID NOT NULL
                REFERENCES education_structure_units(unit_id)
                ON DELETE RESTRICT,
            position INTEGER NOT NULL CHECK (position > 0),
            slug VARCHAR(255) NOT NULL,
            title VARCHAR(255) NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
            confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
            status VARCHAR(24) NOT NULL CHECK (
                status IN ('review', 'accepted', 'blocked')
            ),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (unit_id, position),
            UNIQUE (unit_id, slug)
        )
        """
    )
    execute_textbook_ddl(
        """
        CREATE TABLE education_generation_jobs (
            generation_job_id UUID PRIMARY KEY,
            version_id UUID NOT NULL
                REFERENCES education_textbook_versions(version_id)
                ON DELETE RESTRICT,
            scope VARCHAR(24) NOT NULL CHECK (
                scope IN ('structure', 'lesson')
            ),
            structure_id UUID
                REFERENCES education_textbook_structures(structure_id)
                ON DELETE RESTRICT,
            knowledge_point_id UUID
                REFERENCES education_structure_knowledge_points(knowledge_point_id)
                ON DELETE RESTRICT,
            status VARCHAR(24) NOT NULL CHECK (
                status IN (
                    'queued', 'preparing', 'running', 'validating',
                    'completed', 'failed', 'cancelled'
                )
            ),
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
            latest_attempt_id UUID,
            auto_grading BOOLEAN NOT NULL DEFAULT FALSE,
            processing_profile_sha256 VARCHAR(64) NOT NULL,
            error_code VARCHAR(64),
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (
                (
                    scope = 'structure'
                    AND structure_id IS NOT NULL
                    AND knowledge_point_id IS NULL
                )
                OR
                (
                    scope = 'lesson'
                    AND structure_id IS NULL
                    AND knowledge_point_id IS NOT NULL
                )
            )
        )
        """
    )
    execute_textbook_ddl(
        """
        CREATE TABLE education_generation_attempts (
            attempt_id UUID PRIMARY KEY,
            generation_job_id UUID NOT NULL
                REFERENCES education_generation_jobs(generation_job_id)
                ON DELETE RESTRICT,
            previous_attempt_id UUID
                REFERENCES education_generation_attempts(attempt_id)
                ON DELETE RESTRICT,
            managed_workspace_id UUID NOT NULL
                REFERENCES workspaces(workspace_id) ON DELETE RESTRICT,
            managed_thread_id UUID NOT NULL UNIQUE
                REFERENCES conversation_threads(conversation_thread_id)
                ON DELETE RESTRICT,
            root_run_id UUID UNIQUE
                REFERENCES conversation_responses(conversation_response_id)
                ON DELETE RESTRICT,
            status VARCHAR(24) NOT NULL CHECK (
                status IN (
                    'preparing', 'running', 'completed', 'failed',
                    'cancelled', 'worker_lost'
                )
            ),
            error_code VARCHAR(64),
            error_message TEXT,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            heartbeat_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ
        )
        """
    )
    execute_textbook_ddl(
        """
        CREATE UNIQUE INDEX uq_education_generation_attempts_first_attempt
        ON education_generation_attempts (generation_job_id)
        WHERE previous_attempt_id IS NULL
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        ADD CONSTRAINT fk_education_generation_jobs_latest_attempt
        FOREIGN KEY (latest_attempt_id)
        REFERENCES education_generation_attempts(attempt_id)
        ON DELETE SET NULL
        DEFERRABLE INITIALLY DEFERRED
        """
    )
    execute_textbook_ddl(
        """
        CREATE UNIQUE INDEX uq_education_generation_attempts_retry_edge
        ON education_generation_attempts (previous_attempt_id)
        WHERE previous_attempt_id IS NOT NULL
        """
    )
    execute_textbook_ddl(
        """
        CREATE INDEX idx_education_textbook_structures_version
        ON education_textbook_structures (version_id, sequence DESC)
        """
    )
    execute_textbook_ddl(
        """
        CREATE INDEX idx_education_structure_units_structure
        ON education_structure_units (structure_id, position)
        """
    )
    execute_textbook_ddl(
        """
        CREATE INDEX idx_education_structure_knowledge_points_unit
        ON education_structure_knowledge_points (unit_id, position)
        """
    )
    execute_textbook_ddl(
        """
        CREATE INDEX idx_education_generation_jobs_status_created
        ON education_generation_jobs (status, created_at)
        """
    )
    execute_textbook_ddl(
        """
        CREATE INDEX idx_education_generation_jobs_version
        ON education_generation_jobs (version_id, created_at DESC)
        """
    )
    execute_textbook_ddl(
        """
        CREATE INDEX idx_education_generation_attempts_job_started
        ON education_generation_attempts (generation_job_id, started_at DESC)
        """
    )


def downgrade() -> None:
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        DROP CONSTRAINT IF EXISTS fk_education_generation_jobs_latest_attempt
        """
    )
    execute_textbook_ddl(
        "DROP TABLE IF EXISTS education_generation_attempts"
    )
    execute_textbook_ddl("DROP TABLE IF EXISTS education_generation_jobs")
    execute_textbook_ddl(
        "DROP TABLE IF EXISTS education_structure_knowledge_points"
    )
    execute_textbook_ddl("DROP TABLE IF EXISTS education_structure_units")
    execute_textbook_ddl("DROP TABLE IF EXISTS education_textbook_structures")
