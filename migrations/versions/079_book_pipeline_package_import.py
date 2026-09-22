"""Persist generic book package candidates and completed structure links.

Revision ID: 079
Revises: 078
"""

from __future__ import annotations

from migrations.textbook_ddl import execute_textbook_ddl


revision = "079_book_pipeline_package_import"
down_revision = "078_book_pipeline_idempotency"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        ALTER COLUMN unit_id DROP NOT NULL
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_textbook_structures
        ALTER COLUMN source_revision TYPE VARCHAR(255)
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        ADD COLUMN content_node_id UUID NULL
            REFERENCES education_content_nodes(node_id) ON DELETE RESTRICT
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        ADD COLUMN content_structure_id UUID NULL
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        ADD CONSTRAINT fk_education_structure_kp_content_node_structure
        FOREIGN KEY (content_structure_id, content_node_id)
        REFERENCES education_content_nodes(structure_id, node_id)
        ON DELETE RESTRICT
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        ADD COLUMN candidate_key VARCHAR(255) NULL
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        ADD COLUMN point_type VARCHAR(64) NOT NULL DEFAULT 'concept'
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        ADD COLUMN origin VARCHAR(24) NOT NULL DEFAULT 'manual'
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        ADD COLUMN candidate_status VARCHAR(24) NOT NULL DEFAULT 'pending'
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        ADD CONSTRAINT education_structure_kp_origin_check
        CHECK (origin IN ('manual', 'generated'))
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        ADD CONSTRAINT education_structure_kp_candidate_status_check
        CHECK (
            candidate_status IN (
                'pending', 'accepted', 'rejected', 'merged', 'split'
            )
        )
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        ADD CONSTRAINT education_structure_kp_binding_check
        CHECK (
            content_node_id IS NOT NULL OR unit_id IS NOT NULL
        )
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        ADD CONSTRAINT education_structure_kp_generated_binding_check
        CHECK (
            origin <> 'generated' OR (
                content_structure_id IS NOT NULL
                AND content_node_id IS NOT NULL
                AND candidate_key IS NOT NULL
            )
        )
        """
    )
    execute_textbook_ddl(
        """
        CREATE UNIQUE INDEX uq_education_structure_kp_candidate_structure_key
        ON education_structure_knowledge_points (
            content_structure_id, candidate_key
        )
        WHERE content_structure_id IS NOT NULL AND candidate_key IS NOT NULL
        """
    )
    execute_textbook_ddl(
        """
        CREATE UNIQUE INDEX uq_education_structure_kp_candidate_node_key
        ON education_structure_knowledge_points (content_node_id, candidate_key)
        WHERE content_node_id IS NOT NULL AND candidate_key IS NOT NULL
        """
    )
    execute_textbook_ddl(
        """
        CREATE INDEX idx_education_structure_knowledge_points_content_node
        ON education_structure_knowledge_points (content_node_id, position)
        WHERE content_node_id IS NOT NULL
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        DROP CONSTRAINT IF EXISTS education_generation_jobs_check
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        ADD CONSTRAINT education_generation_jobs_check
        CHECK (
            (
                scope IN ('structure', 'assets')
                AND structure_id IS NOT NULL
                AND knowledge_point_id IS NULL
            )
            OR
            (
                scope = 'lesson'
                AND structure_id IS NULL
                AND knowledge_point_id IS NOT NULL
            )
            OR
            (
                scope = 'book_pipeline'
                AND knowledge_point_id IS NULL
            )
        )
        """
    )


def downgrade() -> None:
    execute_textbook_ddl(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM education_structure_knowledge_points
                WHERE content_node_id IS NOT NULL
                   OR candidate_key IS NOT NULL
                   OR unit_id IS NULL
                   OR point_type <> 'concept'
                   OR origin <> 'manual'
                   OR candidate_status <> 'pending'
            ) THEN
                RAISE EXCEPTION
                    'cannot downgrade 079 while generic book package data exists';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM education_generation_jobs
                WHERE scope = 'book_pipeline' AND structure_id IS NOT NULL
            ) THEN
                RAISE EXCEPTION
                    'cannot downgrade 079 while completed book pipelines exist';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM education_textbook_structures
                WHERE char_length(source_revision) > 64
            ) THEN
                RAISE EXCEPTION
                    'cannot downgrade 079 while long source revisions exist';
            END IF;
        END
        $$
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        DROP CONSTRAINT IF EXISTS education_generation_jobs_check
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_generation_jobs
        ADD CONSTRAINT education_generation_jobs_check
        CHECK (
            (
                scope IN ('structure', 'assets')
                AND structure_id IS NOT NULL
                AND knowledge_point_id IS NULL
            )
            OR
            (
                scope = 'lesson'
                AND structure_id IS NULL
                AND knowledge_point_id IS NOT NULL
            )
            OR
            (
                scope = 'book_pipeline'
                AND structure_id IS NULL
                AND knowledge_point_id IS NULL
            )
        )
        """
    )
    execute_textbook_ddl(
        """
        DROP INDEX IF EXISTS uq_education_structure_kp_candidate_node_key
        """
    )
    execute_textbook_ddl(
        """
        DROP INDEX IF EXISTS uq_education_structure_kp_candidate_structure_key
        """
    )
    execute_textbook_ddl(
        """
        DROP INDEX IF EXISTS idx_education_structure_knowledge_points_content_node
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        DROP CONSTRAINT IF EXISTS education_structure_kp_generated_binding_check
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        DROP CONSTRAINT IF EXISTS fk_education_structure_kp_content_node_structure
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        DROP CONSTRAINT IF EXISTS education_structure_kp_binding_check
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        DROP CONSTRAINT IF EXISTS education_structure_kp_candidate_status_check
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        DROP CONSTRAINT IF EXISTS education_structure_kp_origin_check
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        DROP COLUMN IF EXISTS candidate_status
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        DROP COLUMN IF EXISTS origin
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        DROP COLUMN IF EXISTS point_type
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        DROP COLUMN IF EXISTS candidate_key
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        DROP COLUMN IF EXISTS content_node_id
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        DROP COLUMN IF EXISTS content_structure_id
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_structure_knowledge_points
        ALTER COLUMN unit_id SET NOT NULL
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_textbook_structures
        ALTER COLUMN source_revision TYPE VARCHAR(64)
        """
    )
