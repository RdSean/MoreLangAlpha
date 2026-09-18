"""Add student learning assets and versioned processing profiles.

Revision ID: 069
Revises: 068
"""

from __future__ import annotations

from migrations.textbook_ddl import execute_textbook_ddl


revision = "069_learning_items_and_profiles"
down_revision = "068_structure_publications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_textbook_ddl(
        """
        CREATE TABLE education_processing_profiles (
            profile_id UUID PRIMARY KEY,
            household_id UUID NOT NULL
                REFERENCES education_households(household_id)
                ON DELETE CASCADE,
            version_id UUID NOT NULL
                REFERENCES education_textbook_versions(version_id)
                ON DELETE RESTRICT,
            version INTEGER NOT NULL CHECK (version > 0),
            subject VARCHAR(24) NOT NULL,
            grade_band VARCHAR(24) NOT NULL,
            language VARCHAR(24) NOT NULL,
            depth VARCHAR(24) NOT NULL,
            question_types JSONB NOT NULL DEFAULT '[]'::jsonb,
            prompt_fragment TEXT NOT NULL DEFAULT '',
            allowed_skills JSONB NOT NULL DEFAULT '[]'::jsonb,
            profile_sha256 VARCHAR(64) NOT NULL,
            created_by_user_id VARCHAR(255) NOT NULL
                REFERENCES users(user_id) ON DELETE RESTRICT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (version_id, version),
            UNIQUE (profile_id, version_id)
        )
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_textbook_structures
        ADD CONSTRAINT fk_education_textbook_structures_profile
        FOREIGN KEY (processing_profile_id)
        REFERENCES education_processing_profiles(profile_id)
        ON DELETE RESTRICT
        """
    )
    execute_textbook_ddl(
        """
        CREATE TABLE education_learning_kp_progress (
            assignment_id UUID NOT NULL
                REFERENCES education_textbook_assignments(assignment_id)
                ON DELETE CASCADE,
            knowledge_point_id UUID NOT NULL
                REFERENCES education_structure_knowledge_points(knowledge_point_id)
                ON DELETE RESTRICT,
            status VARCHAR(24) NOT NULL CHECK (
                status IN (
                    'not_started', 'learning', 'read', 'review_recommended'
                )
            ),
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (assignment_id, knowledge_point_id)
        )
        """
    )
    execute_textbook_ddl(
        """
        CREATE TABLE education_learning_items (
            item_id UUID PRIMARY KEY,
            assignment_id UUID NOT NULL
                REFERENCES education_textbook_assignments(assignment_id)
                ON DELETE CASCADE,
            unit_id UUID
                REFERENCES education_structure_units(unit_id)
                ON DELETE RESTRICT,
            knowledge_point_id UUID
                REFERENCES education_structure_knowledge_points(knowledge_point_id)
                ON DELETE RESTRICT,
            kind VARCHAR(24) NOT NULL CHECK (
                kind IN ('question', 'highlight', 'note', 'summary')
            ),
            content TEXT NOT NULL,
            source_anchor JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CHECK (
                knowledge_point_id IS NOT NULL OR unit_id IS NOT NULL
            )
        )
        """
    )
    execute_textbook_ddl(
        """
        CREATE INDEX idx_education_learning_items_assignment
        ON education_learning_items (
            assignment_id, unit_id, knowledge_point_id, created_at
        )
        """
    )
    execute_textbook_ddl(
        """
        CREATE INDEX idx_education_processing_profiles_version
        ON education_processing_profiles (version_id, version DESC)
        """
    )


def downgrade() -> None:
    execute_textbook_ddl(
        """
        ALTER TABLE education_textbook_structures
        DROP CONSTRAINT IF EXISTS fk_education_textbook_structures_profile
        """
    )
    execute_textbook_ddl("DROP TABLE IF EXISTS education_learning_items")
    execute_textbook_ddl("DROP TABLE IF EXISTS education_learning_kp_progress")
    execute_textbook_ddl(
        "DROP TABLE IF EXISTS education_processing_profiles"
    )
