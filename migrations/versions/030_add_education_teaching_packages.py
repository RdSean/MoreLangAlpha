"""Add immutable teaching packages for extracted textbook content.

Revision ID: 030
Revises: 029
"""

from alembic import op


revision = "030"
down_revision = "029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE education_teaching_packages (
            teaching_package_id UUID PRIMARY KEY,
            content_version_id UUID NOT NULL
                REFERENCES education_textbook_versions(version_id) ON DELETE RESTRICT,
            sequence INTEGER NOT NULL CHECK (sequence > 0),
            status VARCHAR(32) NOT NULL CHECK (status IN (
                'queued', 'preparing', 'building_skill', 'generating_teaching',
                'validating', 'review', 'failed', 'cancelled'
            )),
            audience VARCHAR(64) NOT NULL DEFAULT 'zh-CN-students',
            input_manifest_sha256 VARCHAR(64) NOT NULL,
            book_to_skill_sha256 VARCHAR(64) NOT NULL,
            knowledge_guy_sha256 VARCHAR(64) NOT NULL,
            adapter_prompt_sha256 VARCHAR(64) NOT NULL,
            bundle_prefix TEXT,
            error_code VARCHAR(64),
            error_message TEXT,
            created_by_user_id VARCHAR(255) NOT NULL
                REFERENCES users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            reviewed_at TIMESTAMPTZ,
            UNIQUE (content_version_id, sequence)
        )
    """)
    op.execute("""
        CREATE TABLE education_teaching_jobs (
            job_id UUID PRIMARY KEY,
            teaching_package_id UUID NOT NULL UNIQUE
                REFERENCES education_teaching_packages(teaching_package_id) ON DELETE RESTRICT,
            status VARCHAR(32) NOT NULL CHECK (status IN (
                'queued', 'preparing', 'running', 'validating',
                'completed', 'failed', 'cancelled'
            )),
            attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
            latest_attempt_id UUID,
            error_code VARCHAR(64),
            error_message TEXT,
            cancel_requested_at TIMESTAMPTZ,
            claimed_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE education_teaching_attempts (
            attempt_id UUID PRIMARY KEY,
            job_id UUID NOT NULL
                REFERENCES education_teaching_jobs(job_id) ON DELETE RESTRICT,
            previous_attempt_id UUID
                REFERENCES education_teaching_attempts(attempt_id) ON DELETE RESTRICT,
            managed_workspace_id UUID NOT NULL
                REFERENCES workspaces(workspace_id) ON DELETE RESTRICT,
            managed_thread_id UUID NOT NULL UNIQUE
                REFERENCES conversation_threads(conversation_thread_id) ON DELETE RESTRICT,
            root_run_id UUID UNIQUE
                REFERENCES conversation_responses(conversation_response_id) ON DELETE RESTRICT,
            status VARCHAR(32) NOT NULL CHECK (status IN (
                'preparing', 'running', 'completed', 'failed', 'cancelled', 'worker_lost'
            )),
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            heartbeat_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            error_code VARCHAR(64),
            error_message TEXT
        )
    """)
    # PostgreSQL considers NULL values distinct in a unique constraint.  These
    # partial indexes therefore make both the first attempt and every retry
    # edge truly single-writer.
    op.execute("""
        CREATE UNIQUE INDEX uq_education_teaching_attempts_first_attempt
        ON education_teaching_attempts (job_id)
        WHERE previous_attempt_id IS NULL
    """)
    op.execute("""
        CREATE UNIQUE INDEX uq_education_teaching_attempts_retry_edge
        ON education_teaching_attempts (previous_attempt_id)
        WHERE previous_attempt_id IS NOT NULL
    """)
    op.execute("""
        ALTER TABLE education_teaching_jobs
        ADD CONSTRAINT fk_education_teaching_jobs_latest_attempt
        FOREIGN KEY (latest_attempt_id)
        REFERENCES education_teaching_attempts(attempt_id)
        ON DELETE SET NULL
        DEFERRABLE INITIALLY DEFERRED
    """)
    op.execute("""
        CREATE TABLE education_teaching_events (
            event_id UUID PRIMARY KEY,
            attempt_id UUID NOT NULL
                REFERENCES education_teaching_attempts(attempt_id) ON DELETE RESTRICT,
            sequence INTEGER NOT NULL CHECK (sequence > 0),
            phase VARCHAR(32) NOT NULL CHECK (phase IN (
                'queued', 'preparing', 'building_skill', 'generating_teaching',
                'validating', 'review', 'failed', 'cancelled'
            )),
            chapter_id UUID REFERENCES education_textbook_chapters(chapter_id) ON DELETE RESTRICT,
            summary TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (attempt_id, sequence)
        )
    """)
    op.execute("""
        CREATE TABLE education_teaching_package_chapters (
            package_chapter_id UUID PRIMARY KEY,
            teaching_package_id UUID NOT NULL
                REFERENCES education_teaching_packages(teaching_package_id) ON DELETE RESTRICT,
            content_chapter_id UUID NOT NULL
                REFERENCES education_textbook_chapters(chapter_id) ON DELETE RESTRICT,
            position INTEGER NOT NULL CHECK (position > 0),
            learning_objectives JSONB NOT NULL DEFAULT '[]'::jsonb,
            knowledge_points JSONB NOT NULL DEFAULT '[]'::jsonb,
            key_difficulties JSONB NOT NULL DEFAULT '[]'::jsonb,
            prerequisites JSONB NOT NULL DEFAULT '[]'::jsonb,
            teaching_material TEXT NOT NULL,
            teaching_material_key TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (teaching_package_id, content_chapter_id),
            UNIQUE (teaching_package_id, position)
        )
    """)
    op.execute("""
        CREATE TABLE education_teaching_package_questions (
            question_id UUID PRIMARY KEY,
            package_chapter_id UUID NOT NULL
                REFERENCES education_teaching_package_chapters(package_chapter_id) ON DELETE RESTRICT,
            position INTEGER NOT NULL CHECK (position > 0),
            prompt TEXT NOT NULL,
            options JSONB NOT NULL,
            correct_option VARCHAR(32) NOT NULL,
            explanation TEXT NOT NULL,
            knowledge_point TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (package_chapter_id, position)
        )
    """)

    # Preserve all existing reviewable/published textbook material as immutable
    # legacy packages before publications start freezing a package reference.
    op.execute("""
        INSERT INTO education_teaching_packages (
            teaching_package_id, content_version_id, sequence, status, audience,
            input_manifest_sha256, book_to_skill_sha256, knowledge_guy_sha256,
            adapter_prompt_sha256, bundle_prefix, created_by_user_id, created_at,
            reviewed_at
        )
        SELECT gen_random_uuid(), versions.version_id, 1, 'review', 'legacy-local-v1',
               repeat('0', 64), repeat('0', 64), repeat('0', 64), repeat('0', 64),
               versions.bundle_prefix, versions.created_by_user_id, versions.created_at,
               COALESCE(versions.reviewed_at, versions.published_at, versions.created_at)
        FROM education_textbook_versions AS versions
        WHERE EXISTS (
            SELECT 1 FROM education_textbook_chapters AS chapters
            WHERE chapters.version_id = versions.version_id
        )
    """)
    op.execute("""
        INSERT INTO education_teaching_package_chapters (
            package_chapter_id, teaching_package_id, content_chapter_id, position,
            learning_objectives, knowledge_points, key_difficulties, prerequisites,
            teaching_material, teaching_material_key, created_at
        )
        SELECT chapters.chapter_id, packages.teaching_package_id, chapters.chapter_id,
               chapters.position, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb,
               chapters.teaching_material, chapters.teaching_material_key, chapters.created_at
        FROM education_textbook_chapters AS chapters
        JOIN education_teaching_packages AS packages
          ON packages.content_version_id = chapters.version_id
         AND packages.audience = 'legacy-local-v1'
    """)
    op.execute("""
        INSERT INTO education_teaching_package_questions (
            question_id, package_chapter_id, position, prompt, options,
            correct_option, explanation, knowledge_point, created_at
        )
        SELECT questions.question_id, chapters.package_chapter_id, questions.position,
               questions.prompt, questions.options, questions.correct_option,
               questions.explanation, questions.knowledge_point, questions.created_at
        FROM education_chapter_questions AS questions
        JOIN education_teaching_package_chapters AS chapters
          ON chapters.content_chapter_id = questions.chapter_id
    """)
    # Legacy package questions retain their original UUIDs, preserving every
    # historical answer while changing future learning queries to the package.
    op.execute("""
        ALTER TABLE education_learning_answers
        DROP CONSTRAINT IF EXISTS education_learning_answers_question_id_fkey
    """)
    op.execute("""
        ALTER TABLE education_learning_answers
        ADD CONSTRAINT fk_education_learning_answers_teaching_question
        FOREIGN KEY (question_id)
        REFERENCES education_teaching_package_questions(question_id) ON DELETE RESTRICT
    """)

    op.execute("""
        ALTER TABLE education_textbook_publications
        ADD COLUMN teaching_package_id UUID
    """)
    op.execute("""
        UPDATE education_textbook_publications AS publications
        SET teaching_package_id = packages.teaching_package_id
        FROM education_teaching_packages AS packages
        WHERE packages.content_version_id = publications.version_id
          AND packages.audience = 'legacy-local-v1'
    """)
    op.execute("""
        ALTER TABLE education_textbook_publications
        ALTER COLUMN teaching_package_id SET NOT NULL
    """)
    op.execute("""
        ALTER TABLE education_textbook_publications
        ADD CONSTRAINT fk_education_textbook_publications_teaching_package
        FOREIGN KEY (teaching_package_id)
        REFERENCES education_teaching_packages(teaching_package_id) ON DELETE RESTRICT
    """)

    # Content extraction no longer owns teaching material.  Existing values
    # remain intact for the legacy package backfill above.
    op.execute("""
        ALTER TABLE education_textbook_chapters
        ALTER COLUMN teaching_material DROP NOT NULL,
        ALTER COLUMN teaching_material_key DROP NOT NULL
    """)

    op.execute("""
        CREATE INDEX idx_education_teaching_packages_content_status
        ON education_teaching_packages (content_version_id, status, sequence DESC)
    """)
    op.execute("""
        CREATE INDEX idx_education_teaching_jobs_status_created
        ON education_teaching_jobs (status, created_at)
    """)
    op.execute("""
        CREATE INDEX idx_education_teaching_attempts_job_started
        ON education_teaching_attempts (job_id, started_at DESC)
    """)
    op.execute("""
        CREATE INDEX idx_education_teaching_events_attempt_sequence
        ON education_teaching_events (attempt_id, sequence)
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE education_learning_answers
        DROP CONSTRAINT IF EXISTS fk_education_learning_answers_teaching_question
    """)
    op.execute("""
        ALTER TABLE education_learning_answers
        ADD CONSTRAINT education_learning_answers_question_id_fkey
        FOREIGN KEY (question_id)
        REFERENCES education_chapter_questions(question_id) ON DELETE RESTRICT
    """)
    op.execute("""
        ALTER TABLE education_textbook_chapters
        ALTER COLUMN teaching_material SET NOT NULL,
        ALTER COLUMN teaching_material_key SET NOT NULL
    """)
    op.execute(
        "ALTER TABLE education_textbook_publications "
        "DROP CONSTRAINT IF EXISTS fk_education_textbook_publications_teaching_package"
    )
    op.execute(
        "ALTER TABLE education_textbook_publications "
        "DROP COLUMN IF EXISTS teaching_package_id"
    )
    op.execute("DROP TABLE education_teaching_package_questions")
    op.execute("DROP TABLE education_teaching_package_chapters")
    op.execute("DROP TABLE education_teaching_events")
    op.execute(
        "ALTER TABLE education_teaching_jobs "
        "DROP CONSTRAINT IF EXISTS fk_education_teaching_jobs_latest_attempt"
    )
    op.execute("DROP INDEX IF EXISTS uq_education_teaching_attempts_retry_edge")
    op.execute("DROP INDEX IF EXISTS uq_education_teaching_attempts_first_attempt")
    op.execute("DROP TABLE education_teaching_attempts")
    op.execute("DROP TABLE education_teaching_jobs")
    op.execute("DROP TABLE education_teaching_packages")
