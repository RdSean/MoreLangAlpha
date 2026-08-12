"""Add versioned family textbook learning records.

Revision ID: 028
Revises: 027
"""

from alembic import op


revision = "028"
down_revision = "027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE education_textbooks (
            textbook_id UUID PRIMARY KEY,
            household_id UUID NOT NULL REFERENCES education_households(household_id) ON DELETE CASCADE,
            title VARCHAR(255) NOT NULL,
            slug VARCHAR(255) NOT NULL,
            created_by_user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (household_id, slug)
        )
    """)
    op.execute("""
        CREATE TABLE education_textbook_versions (
            version_id UUID PRIMARY KEY,
            textbook_id UUID NOT NULL REFERENCES education_textbooks(textbook_id) ON DELETE RESTRICT,
            sequence INTEGER NOT NULL CHECK (sequence > 0),
            status VARCHAR(24) NOT NULL CHECK (status IN ('draft', 'processing', 'review', 'published', 'failed')),
            extractor_name VARCHAR(64),
            extractor_version VARCHAR(64),
            bundle_prefix TEXT,
            processing_error TEXT,
            created_by_user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            reviewed_at TIMESTAMPTZ,
            published_at TIMESTAMPTZ,
            UNIQUE (textbook_id, sequence)
        )
    """)
    op.execute("""
        CREATE TABLE education_textbook_sources (
            version_id UUID NOT NULL REFERENCES education_textbook_versions(version_id) ON DELETE CASCADE,
            asset_id UUID NOT NULL REFERENCES education_assets(asset_id) ON DELETE RESTRICT,
            position INTEGER NOT NULL CHECK (position > 0),
            PRIMARY KEY (version_id, asset_id),
            UNIQUE (version_id, position)
        )
    """)
    op.execute("""
        CREATE TABLE education_processing_jobs (
            job_id UUID PRIMARY KEY,
            version_id UUID NOT NULL UNIQUE REFERENCES education_textbook_versions(version_id) ON DELETE RESTRICT,
            status VARCHAR(24) NOT NULL CHECK (status IN ('queued', 'processing', 'completed', 'failed')),
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
            error_message TEXT,
            claimed_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE education_textbook_chapters (
            chapter_id UUID PRIMARY KEY,
            version_id UUID NOT NULL REFERENCES education_textbook_versions(version_id) ON DELETE RESTRICT,
            position INTEGER NOT NULL CHECK (position > 0),
            slug VARCHAR(255) NOT NULL,
            title VARCHAR(255) NOT NULL,
            page_start INTEGER,
            page_end INTEGER,
            markdown TEXT NOT NULL,
            teaching_material TEXT NOT NULL,
            markdown_key TEXT NOT NULL,
            teaching_material_key TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (version_id, position),
            UNIQUE (version_id, slug)
        )
    """)
    op.execute("""
        CREATE TABLE education_chapter_questions (
            question_id UUID PRIMARY KEY,
            chapter_id UUID NOT NULL REFERENCES education_textbook_chapters(chapter_id) ON DELETE RESTRICT,
            position INTEGER NOT NULL CHECK (position > 0),
            prompt TEXT NOT NULL,
            options JSONB NOT NULL,
            correct_option VARCHAR(32) NOT NULL,
            explanation TEXT NOT NULL,
            knowledge_point TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (chapter_id, position)
        )
    """)
    op.execute("""
        CREATE TABLE education_textbook_publications (
            publication_id UUID PRIMARY KEY,
            version_id UUID NOT NULL UNIQUE REFERENCES education_textbook_versions(version_id) ON DELETE RESTRICT,
            published_by_user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE education_textbook_assignments (
            assignment_id UUID PRIMARY KEY,
            publication_id UUID NOT NULL REFERENCES education_textbook_publications(publication_id) ON DELETE RESTRICT,
            student_user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
            assigned_by_user_id VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (publication_id, student_user_id)
        )
    """)
    op.execute("""
        CREATE TABLE education_learning_progress (
            assignment_id UUID NOT NULL REFERENCES education_textbook_assignments(assignment_id) ON DELETE CASCADE,
            chapter_id UUID NOT NULL REFERENCES education_textbook_chapters(chapter_id) ON DELETE RESTRICT,
            status VARCHAR(24) NOT NULL CHECK (status IN ('not_started', 'learning', 'read', 'check_completed', 'review_recommended')),
            last_read_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (assignment_id, chapter_id)
        )
    """)
    op.execute("""
        CREATE TABLE education_learning_answers (
            answer_id UUID PRIMARY KEY,
            assignment_id UUID NOT NULL REFERENCES education_textbook_assignments(assignment_id) ON DELETE RESTRICT,
            question_id UUID NOT NULL REFERENCES education_chapter_questions(question_id) ON DELETE RESTRICT,
            selected_option VARCHAR(32) NOT NULL,
            is_correct BOOLEAN NOT NULL,
            answered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (assignment_id, question_id)
        )
    """)
    op.execute(
        "CREATE INDEX idx_education_textbooks_household_created ON education_textbooks (household_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_education_textbook_versions_textbook_sequence ON education_textbook_versions (textbook_id, sequence DESC)"
    )
    op.execute(
        "CREATE INDEX idx_education_textbook_assignments_student ON education_textbook_assignments (student_user_id, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX idx_education_processing_jobs_status_created ON education_processing_jobs (status, created_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE education_learning_answers")
    op.execute("DROP TABLE education_learning_progress")
    op.execute("DROP TABLE education_textbook_assignments")
    op.execute("DROP TABLE education_textbook_publications")
    op.execute("DROP TABLE education_chapter_questions")
    op.execute("DROP TABLE education_textbook_chapters")
    op.execute("DROP TABLE education_processing_jobs")
    op.execute("DROP TABLE education_textbook_sources")
    op.execute("DROP TABLE education_textbook_versions")
    op.execute("DROP TABLE education_textbooks")
