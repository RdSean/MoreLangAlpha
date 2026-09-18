"""Persist immutable knowledge-point lesson revisions and publication freezes.

Revision ID: 067
Revises: 066
"""

from __future__ import annotations

from migrations.textbook_ddl import execute_textbook_ddl


revision = "067_kp_lessons"
down_revision = "066_textbook_structure_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_textbook_ddl(
        """
        CREATE TABLE education_kp_lessons (
            lesson_id UUID PRIMARY KEY,
            knowledge_point_id UUID NOT NULL UNIQUE
                REFERENCES education_structure_knowledge_points(knowledge_point_id)
                ON DELETE RESTRICT,
            status VARCHAR(24) NOT NULL CHECK (
                status IN (
                    'draft', 'generating', 'review', 'approved',
                    'failed', 'cancelled'
                )
            ),
            latest_revision_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            reviewed_at TIMESTAMPTZ
        )
        """
    )
    execute_textbook_ddl(
        """
        CREATE TABLE education_kp_lesson_revisions (
            revision_id UUID PRIMARY KEY,
            lesson_id UUID NOT NULL
                REFERENCES education_kp_lessons(lesson_id)
                ON DELETE RESTRICT,
            revision INTEGER NOT NULL CHECK (revision > 0),
            format VARCHAR(24) NOT NULL DEFAULT 'markdown'
                CHECK (format = 'markdown'),
            content_key TEXT NOT NULL UNIQUE,
            content_sha256 VARCHAR(64) NOT NULL,
            size_bytes INTEGER NOT NULL CHECK (size_bytes > 0),
            processing_profile_sha256 VARCHAR(64) NOT NULL,
            generation_job_id UUID
                REFERENCES education_generation_jobs(generation_job_id)
                ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (lesson_id, revision)
        )
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_kp_lessons
        ADD CONSTRAINT fk_education_kp_lessons_latest_revision
        FOREIGN KEY (latest_revision_id)
        REFERENCES education_kp_lesson_revisions(revision_id)
        ON DELETE RESTRICT
        DEFERRABLE INITIALLY DEFERRED
        """
    )
    execute_textbook_ddl(
        """
        CREATE TABLE education_publication_kp_lessons (
            publication_id UUID NOT NULL
                REFERENCES education_textbook_publications(publication_id)
                ON DELETE RESTRICT,
            knowledge_point_id UUID NOT NULL
                REFERENCES education_structure_knowledge_points(knowledge_point_id)
                ON DELETE RESTRICT,
            lesson_revision_id UUID NOT NULL
                REFERENCES education_kp_lesson_revisions(revision_id)
                ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (publication_id, knowledge_point_id)
        )
        """
    )
    execute_textbook_ddl(
        """
        CREATE INDEX idx_education_kp_lessons_status
        ON education_kp_lessons (status, created_at)
        """
    )
    execute_textbook_ddl(
        """
        CREATE INDEX idx_education_kp_lesson_revisions_lesson
        ON education_kp_lesson_revisions (lesson_id, revision DESC)
        """
    )
    execute_textbook_ddl(
        """
        CREATE INDEX idx_education_publication_kp_lessons_revision
        ON education_publication_kp_lessons (lesson_revision_id)
        """
    )


def downgrade() -> None:
    execute_textbook_ddl(
        "DROP TABLE IF EXISTS education_publication_kp_lessons"
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_kp_lessons
        DROP CONSTRAINT IF EXISTS fk_education_kp_lessons_latest_revision
        """
    )
    execute_textbook_ddl(
        "DROP TABLE IF EXISTS education_kp_lesson_revisions"
    )
    execute_textbook_ddl("DROP TABLE IF EXISTS education_kp_lessons")
