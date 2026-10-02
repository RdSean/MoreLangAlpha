"""Replace the legacy textbook pipeline with the more-to-skills model.

Revision ID: 082
Revises: 081
"""

from __future__ import annotations

from migrations.textbook_ddl import execute_textbook_ddl


revision = "082_more_to_skills_textbooks"
down_revision = "081_book_pipeline_checkpoint"
branch_labels = None
depends_on = None


def _execute(sql: str) -> None:
    execute_textbook_ddl(sql)


def _rename_retained_tables() -> None:
    for table in (
        "education_learning_spaces",
        "education_learning_items",
        "education_learning_kp_progress",
        "education_textbook_assignments",
        "education_textbooks",
    ):
        _execute(f"ALTER TABLE {table} RENAME TO {table}_legacy_082")


def _drop_legacy_tables() -> None:
    # Remove children before parents. The five retained names were renamed so
    # their old foreign keys continue to point at the legacy graph while it is
    # dismantled.
    for table in (
        "education_learning_spaces_legacy_082",
        "education_learning_items_legacy_082",
        "education_learning_kp_progress_legacy_082",
        "education_textbook_assignments_legacy_082",
        "education_publication_kp_lessons",
    ):
        _execute(f"DROP TABLE IF EXISTS {table}")

    _execute(
        """
        ALTER TABLE education_kp_lessons
        DROP CONSTRAINT IF EXISTS fk_education_kp_lessons_latest_revision
        """
    )
    _execute("DROP TABLE IF EXISTS education_kp_lesson_revisions")
    _execute("DROP TABLE IF EXISTS education_kp_lessons")

    _execute(
        """
        ALTER TABLE education_generation_jobs
        DROP CONSTRAINT IF EXISTS fk_education_generation_jobs_latest_attempt
        """
    )
    for table in (
        "education_generation_progress_events",
        "education_generation_attempts",
        "education_generation_jobs",
        "education_textbook_scopes",
        "education_content_assets",
        "education_structure_knowledge_points",
        "education_structure_units",
        "education_content_nodes",
        "education_textbook_publications",
        "education_textbook_structures",
        "education_processing_profiles",
        "education_textbook_chapters",
        "education_processing_jobs",
        "education_textbook_artifact_sources",
        "education_textbook_versions",
        "education_textbooks_legacy_082",
    ):
        _execute(f"DROP TABLE IF EXISTS {table}")


def _create_textbooks() -> None:
    _execute(
        """
        CREATE TABLE education_textbooks (
            textbook_id UUID PRIMARY KEY,
            household_id UUID NOT NULL
                REFERENCES education_households(household_id) ON DELETE CASCADE,
            title VARCHAR(240) NOT NULL CHECK (length(btrim(title)) > 0),
            slug VARCHAR(255) NOT NULL CHECK (length(btrim(slug)) > 0),
            source_document_id VARCHAR(128) NOT NULL,
            source_parse_job_id VARCHAR(128) NOT NULL,
            source_primary_artifact_id VARCHAR(128) NOT NULL,
            source_filename VARCHAR(255) NOT NULL,
            source_media_type VARCHAR(127) NOT NULL,
            source_format VARCHAR(32) NOT NULL,
            source_parser_id VARCHAR(100) NOT NULL,
            source_parser_name VARCHAR(160) NOT NULL,
            source_parser_version VARCHAR(64),
            source_parse_completed_at TIMESTAMPTZ NOT NULL,
            source_content_sha256 VARCHAR(64) NOT NULL
                CHECK (source_content_sha256 ~ '^[0-9a-f]{64}$'),
            source_size_bytes BIGINT NOT NULL CHECK (source_size_bytes >= 0),
            source_snapshot_prefix TEXT NOT NULL CHECK (
                source_snapshot_prefix = 'education/' || household_id::text
                    || '/textbooks/' || textbook_id::text || '/source/'
            ),
            source_markdown_key TEXT NOT NULL UNIQUE CHECK (
                source_markdown_key LIKE source_snapshot_prefix || '%%'
                AND source_markdown_key NOT LIKE '%%..%%'
            ),
            source_blocks_key TEXT CHECK (
                source_blocks_key IS NULL OR (
                    source_blocks_key LIKE source_snapshot_prefix || '%%'
                    AND source_blocks_key NOT LIKE '%%..%%'
                )
            ),
            source_report_key TEXT CHECK (
                source_report_key IS NULL OR (
                    source_report_key LIKE source_snapshot_prefix || '%%'
                    AND source_report_key NOT LIKE '%%..%%'
                )
            ),
            source_asset_manifest JSONB NOT NULL DEFAULT '[]'::jsonb,
            source_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
            current_structure_id UUID NULL,
            created_by_user_id VARCHAR(255) NOT NULL
                REFERENCES users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (household_id, slug),
            UNIQUE (household_id, source_parse_job_id, source_primary_artifact_id)
        )
        """
    )
    _execute(
        """
        CREATE INDEX idx_education_textbooks_household_updated
        ON education_textbooks (household_id, updated_at DESC, textbook_id)
        """
    )


def _create_structures_and_knowledge_points() -> None:
    _execute(
        """
        CREATE TABLE education_book_structures (
            structure_id UUID PRIMARY KEY,
            textbook_id UUID NOT NULL
                REFERENCES education_textbooks(textbook_id) ON DELETE CASCADE,
            status VARCHAR(24) NOT NULL DEFAULT 'ready'
                CHECK (status IN ('ready', 'superseded')),
            schema_version VARCHAR(64) NOT NULL,
            more_to_skills_version VARCHAR(64) NOT NULL,
            skill_sha256 VARCHAR(64) NOT NULL
                CHECK (skill_sha256 ~ '^[0-9a-f]{64}$'),
            schema_sha256 VARCHAR(64) NOT NULL
                CHECK (schema_sha256 ~ '^[0-9a-f]{64}$'),
            source_content_sha256 VARCHAR(64) NOT NULL
                CHECK (source_content_sha256 ~ '^[0-9a-f]{64}$'),
            structure_json JSONB NOT NULL,
            validation_warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_by_job_id UUID NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (textbook_id, structure_id)
        )
        """
    )
    _execute(
        """
        CREATE INDEX idx_education_book_structures_textbook_created
        ON education_book_structures (textbook_id, created_at DESC, structure_id)
        """
    )
    _execute(
        """
        ALTER TABLE education_textbooks
        ADD CONSTRAINT fk_education_textbooks_current_structure
        FOREIGN KEY (textbook_id, current_structure_id)
        REFERENCES education_book_structures(textbook_id, structure_id)
        ON DELETE RESTRICT DEFERRABLE INITIALLY DEFERRED
        """
    )
    _execute(
        """
        CREATE TABLE education_book_knowledge_points (
            knowledge_point_id UUID PRIMARY KEY,
            textbook_id UUID NOT NULL,
            structure_id UUID NOT NULL,
            skill_kp_id VARCHAR(64) NOT NULL,
            position INTEGER NOT NULL CHECK (position > 0),
            title TEXT NOT NULL CHECK (length(btrim(title)) > 0),
            unit_skill_node_id VARCHAR(255),
            node_skill_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            start_line INTEGER NOT NULL CHECK (start_line > 0),
            end_line INTEGER NOT NULL CHECK (end_line >= start_line),
            knowledge_point_json JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (textbook_id, structure_id)
                REFERENCES education_book_structures(textbook_id, structure_id)
                ON DELETE CASCADE,
            UNIQUE (textbook_id, knowledge_point_id),
            UNIQUE (structure_id, skill_kp_id),
            UNIQUE (structure_id, position)
        )
        """
    )
    _execute(
        """
        CREATE INDEX idx_education_book_kps_structure_position
        ON education_book_knowledge_points (structure_id, position)
        """
    )


def _create_jobs_and_materials() -> None:
    _execute(
        """
        CREATE TABLE education_book_jobs (
            job_id UUID PRIMARY KEY,
            textbook_id UUID NOT NULL
                REFERENCES education_textbooks(textbook_id) ON DELETE CASCADE,
            kind VARCHAR(24) NOT NULL CHECK (kind IN ('structure', 'materials')),
            status VARCHAR(32) NOT NULL CHECK (
                status IN (
                    'queued', 'running', 'succeeded', 'partially_succeeded',
                    'failed', 'cancelled'
                )
            ),
            idempotency_key VARCHAR(160) NOT NULL,
            target_knowledge_point_ids JSONB NOT NULL DEFAULT '[]'::jsonb,
            depth VARCHAR(24) CHECK (depth IN ('summary', 'lesson', 'deep')),
            requirements TEXT CHECK (
                requirements IS NULL OR char_length(requirements) <= 8000
            ),
            replace_existing BOOLEAN NOT NULL DEFAULT FALSE,
            include_supplementary BOOLEAN NOT NULL DEFAULT FALSE,
            follow_up_request JSONB,
            more_to_skills_version VARCHAR(64) NOT NULL,
            skill_sha256 VARCHAR(64) NOT NULL
                CHECK (skill_sha256 ~ '^[0-9a-f]{64}$'),
            schema_sha256 VARCHAR(64) NOT NULL
                CHECK (schema_sha256 ~ '^[0-9a-f]{64}$'),
            requested_by_user_id VARCHAR(255) NOT NULL
                REFERENCES users(user_id) ON DELETE RESTRICT,
            total_items INTEGER NOT NULL DEFAULT 0 CHECK (total_items >= 0),
            succeeded_items INTEGER NOT NULL DEFAULT 0 CHECK (succeeded_items >= 0),
            failed_items INTEGER NOT NULL DEFAULT 0 CHECK (failed_items >= 0),
            cancelled_items INTEGER NOT NULL DEFAULT 0 CHECK (cancelled_items >= 0),
            not_run_items INTEGER NOT NULL DEFAULT 0 CHECK (not_run_items >= 0),
            high_water_seq BIGINT NOT NULL DEFAULT 0 CHECK (high_water_seq >= 0),
            activity_status VARCHAR(24) NOT NULL DEFAULT 'available'
                CHECK (activity_status IN ('available', 'unavailable')),
            safe_error TEXT,
            cancel_requested_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (textbook_id, idempotency_key),
            CHECK (
                (kind = 'structure' AND depth IS NULL)
                OR (kind = 'materials' AND depth IS NOT NULL)
            )
        )
        """
    )
    _execute(
        """
        CREATE UNIQUE INDEX uq_education_book_jobs_one_active
        ON education_book_jobs (textbook_id)
        WHERE status IN ('queued', 'running')
        """
    )
    _execute(
        """
        CREATE INDEX idx_education_book_jobs_status_created
        ON education_book_jobs (status, created_at, job_id)
        """
    )
    _execute(
        """
        CREATE TABLE education_book_job_items (
            item_id UUID PRIMARY KEY,
            job_id UUID NOT NULL
                REFERENCES education_book_jobs(job_id) ON DELETE CASCADE,
            position INTEGER NOT NULL CHECK (position > 0),
            kind VARCHAR(24) NOT NULL
                CHECK (kind IN ('structure', 'material', 'supplementary')),
            knowledge_point_id UUID NULL
                REFERENCES education_book_knowledge_points(knowledge_point_id)
                ON DELETE RESTRICT,
            status VARCHAR(24) NOT NULL CHECK (
                status IN (
                    'queued', 'running', 'succeeded', 'failed',
                    'cancelled', 'not_run'
                )
            ),
            attempt INTEGER NOT NULL DEFAULT 0 CHECK (attempt >= 0),
            attempt_token UUID,
            execution_id UUID,
            managed_workspace_id UUID
                REFERENCES workspaces(workspace_id) ON DELETE RESTRICT,
            managed_thread_id UUID
                REFERENCES conversation_threads(conversation_thread_id)
                ON DELETE RESTRICT,
            run_id UUID
                REFERENCES conversation_responses(conversation_response_id)
                ON DELETE RESTRICT,
            lease_owner VARCHAR(255),
            lease_expires_at TIMESTAMPTZ,
            candidate_objects JSONB NOT NULL DEFAULT '[]'::jsonb,
            result_snapshot JSONB,
            safe_error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            started_at TIMESTAMPTZ,
            finished_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (job_id, position),
            UNIQUE (job_id, item_id),
            CHECK (
                (kind = 'material' AND knowledge_point_id IS NOT NULL)
                OR (kind <> 'material' AND knowledge_point_id IS NULL)
            )
        )
        """
    )
    _execute(
        """
        CREATE UNIQUE INDEX uq_education_book_job_items_kp
        ON education_book_job_items (job_id, knowledge_point_id)
        WHERE knowledge_point_id IS NOT NULL
        """
    )
    _execute(
        """
        CREATE INDEX idx_education_book_job_items_claim
        ON education_book_job_items (status, lease_expires_at, created_at, item_id)
        """
    )
    _execute(
        """
        CREATE TABLE education_book_materials (
            material_id UUID PRIMARY KEY,
            knowledge_point_id UUID NOT NULL UNIQUE
                REFERENCES education_book_knowledge_points(knowledge_point_id)
                ON DELETE CASCADE,
            generation INTEGER NOT NULL DEFAULT 1 CHECK (generation > 0),
            content_key TEXT NOT NULL UNIQUE
                CHECK (
                    content_key LIKE 'education/%%'
                    AND content_key NOT LIKE '%%..%%'
                ),
            content_sha256 VARCHAR(64) NOT NULL
                CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
            size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
            format VARCHAR(24) NOT NULL DEFAULT 'markdown'
                CHECK (format = 'markdown'),
            depth VARCHAR(24) NOT NULL
                CHECK (depth IN ('summary', 'lesson', 'deep')),
            requirements TEXT,
            generation_params JSONB NOT NULL DEFAULT '{}'::jsonb,
            source_job_id UUID NOT NULL
                REFERENCES education_book_jobs(job_id) ON DELETE RESTRICT,
            source_item_id UUID
                REFERENCES education_book_job_items(item_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (source_job_id, source_item_id)
                REFERENCES education_book_job_items(job_id, item_id)
                ON DELETE RESTRICT
        )
        """
    )
    _execute(
        """
        CREATE TABLE education_book_activity_events (
            event_id BIGSERIAL PRIMARY KEY,
            job_id UUID NOT NULL
                REFERENCES education_book_jobs(job_id) ON DELETE CASCADE,
            seq BIGINT NOT NULL CHECK (seq > 0),
            dedupe_key VARCHAR(255) NOT NULL,
            item_id UUID,
            kind VARCHAR(64) NOT NULL,
            status VARCHAR(32) NOT NULL,
            message VARCHAR(512) NOT NULL,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (job_id, item_id)
                REFERENCES education_book_job_items(job_id, item_id)
                ON DELETE CASCADE,
            UNIQUE (job_id, seq),
            UNIQUE (job_id, dedupe_key)
        )
        """
    )
    _execute(
        """
        CREATE INDEX idx_education_book_activity_job_seq
        ON education_book_activity_events (job_id, seq)
        """
    )


def _create_learning_tables() -> None:
    _execute(
        """
        CREATE TABLE education_textbook_assignments (
            assignment_id UUID PRIMARY KEY,
            textbook_id UUID NOT NULL
                REFERENCES education_textbooks(textbook_id) ON DELETE CASCADE,
            student_user_id VARCHAR(255) NOT NULL
                REFERENCES users(user_id) ON DELETE RESTRICT,
            assigned_by_user_id VARCHAR(255) NOT NULL
                REFERENCES users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (textbook_id, student_user_id),
            UNIQUE (assignment_id, textbook_id)
        )
        """
    )
    _execute(
        """
        CREATE INDEX idx_education_textbook_assignments_student
        ON education_textbook_assignments (student_user_id, created_at DESC)
        """
    )
    _execute(
        """
        CREATE TABLE education_learning_kp_progress (
            assignment_id UUID NOT NULL,
            textbook_id UUID NOT NULL,
            knowledge_point_id UUID NOT NULL,
            status VARCHAR(24) NOT NULL CHECK (
                status IN ('not_started', 'learning', 'read', 'review_recommended')
            ),
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (assignment_id, knowledge_point_id),
            FOREIGN KEY (assignment_id, textbook_id)
                REFERENCES education_textbook_assignments(assignment_id, textbook_id)
                ON DELETE CASCADE,
            FOREIGN KEY (textbook_id, knowledge_point_id)
                REFERENCES education_book_knowledge_points(
                    textbook_id, knowledge_point_id
                ) ON DELETE CASCADE
        )
        """
    )
    _execute(
        """
        CREATE TABLE education_learning_items (
            item_id UUID PRIMARY KEY,
            assignment_id UUID NOT NULL,
            textbook_id UUID NOT NULL,
            skill_node_id VARCHAR(255),
            knowledge_point_id UUID,
            kind VARCHAR(24) NOT NULL
                CHECK (kind IN ('question', 'highlight', 'note', 'summary')),
            content TEXT NOT NULL,
            source_anchor JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (knowledge_point_id IS NOT NULL OR skill_node_id IS NOT NULL),
            FOREIGN KEY (assignment_id, textbook_id)
                REFERENCES education_textbook_assignments(assignment_id, textbook_id)
                ON DELETE CASCADE,
            FOREIGN KEY (textbook_id, knowledge_point_id)
                REFERENCES education_book_knowledge_points(
                    textbook_id, knowledge_point_id
                ) ON DELETE CASCADE
        )
        """
    )
    _execute(
        """
        CREATE INDEX idx_education_learning_items_assignment
        ON education_learning_items (
            assignment_id, skill_node_id, knowledge_point_id, created_at
        )
        """
    )
    _execute(
        """
        CREATE TABLE education_learning_spaces (
            assignment_id UUID PRIMARY KEY
                REFERENCES education_textbook_assignments(assignment_id)
                ON DELETE RESTRICT,
            workspace_id UUID NOT NULL
                REFERENCES workspaces(workspace_id) ON DELETE RESTRICT,
            conversation_thread_id UUID NOT NULL UNIQUE
                REFERENCES conversation_threads(conversation_thread_id)
                ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def upgrade() -> None:
    _rename_retained_tables()
    _drop_legacy_tables()
    _create_textbooks()
    _create_structures_and_knowledge_points()
    _create_jobs_and_materials()
    _create_learning_tables()


def downgrade() -> None:
    raise RuntimeError(
        "082_more_to_skills_textbooks is irreversible because it removes "
        "legacy textbook and learning data"
    )
