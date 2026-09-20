"""Remove legacy teaching packages and chapter learning state.

Revision ID: 071
Revises: 070
"""

from __future__ import annotations

from migrations.textbook_ddl import execute_textbook_ddl


revision = "071_remove_legacy_teaching_packages"
down_revision = "070_book_asset_jobs"
branch_labels = None
depends_on = None


def _drop(table_name: str) -> None:
    execute_textbook_ddl(f"DROP TABLE IF EXISTS {table_name}")


def upgrade() -> None:
    execute_textbook_ddl(
        """
        DELETE FROM education_learning_answers
        WHERE assignment_id IN (
            SELECT assignments.assignment_id
            FROM education_textbook_assignments AS assignments
            JOIN education_textbook_publications AS publications
              ON publications.publication_id = assignments.publication_id
            WHERE publications.structure_id IS NULL
        )
        """
    )
    execute_textbook_ddl(
        """
        DELETE FROM education_learning_progress
        WHERE assignment_id IN (
            SELECT assignments.assignment_id
            FROM education_textbook_assignments AS assignments
            JOIN education_textbook_publications AS publications
              ON publications.publication_id = assignments.publication_id
            WHERE publications.structure_id IS NULL
        )
        """
    )
    execute_textbook_ddl(
        """
        DELETE FROM education_learning_kp_progress
        WHERE assignment_id IN (
            SELECT assignments.assignment_id
            FROM education_textbook_assignments AS assignments
            JOIN education_textbook_publications AS publications
              ON publications.publication_id = assignments.publication_id
            WHERE publications.structure_id IS NULL
        )
        """
    )
    execute_textbook_ddl(
        """
        DELETE FROM education_learning_items
        WHERE assignment_id IN (
            SELECT assignments.assignment_id
            FROM education_textbook_assignments AS assignments
            JOIN education_textbook_publications AS publications
              ON publications.publication_id = assignments.publication_id
            WHERE publications.structure_id IS NULL
        )
        """
    )
    execute_textbook_ddl(
        """
        DELETE FROM education_learning_spaces
        WHERE assignment_id IN (
            SELECT assignments.assignment_id
            FROM education_textbook_assignments AS assignments
            JOIN education_textbook_publications AS publications
              ON publications.publication_id = assignments.publication_id
            WHERE publications.structure_id IS NULL
        )
        """
    )
    execute_textbook_ddl(
        """
        DELETE FROM education_textbook_assignments
        WHERE publication_id IN (
            SELECT publication_id
            FROM education_textbook_publications
            WHERE structure_id IS NULL
        )
        """
    )
    execute_textbook_ddl(
        "DELETE FROM education_textbook_publications WHERE structure_id IS NULL"
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_textbook_publications
        DROP CONSTRAINT IF EXISTS education_textbook_publications_target_check
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_textbook_publications
        DROP COLUMN IF EXISTS teaching_package_id
        """
    )
    execute_textbook_ddl(
        """
        ALTER TABLE education_textbook_publications
        ALTER COLUMN structure_id SET NOT NULL
        """
    )

    _drop("education_teaching_archive_staging")
    _drop("education_teaching_events")
    execute_textbook_ddl(
        """
        ALTER TABLE education_teaching_jobs
        DROP CONSTRAINT IF EXISTS fk_education_teaching_jobs_latest_attempt
        """
    )
    _drop("education_teaching_attempts")
    _drop("education_teaching_jobs")
    _drop("education_learning_answers")
    _drop("education_teaching_package_questions")
    _drop("education_teaching_package_chapters")
    _drop("education_teaching_packages")
    _drop("education_chapter_questions")
    _drop("education_learning_progress")
    _drop("education_textbook_sources")

    execute_textbook_ddl(
        """
        ALTER TABLE education_textbook_chapters
        DROP COLUMN IF EXISTS teaching_material,
        DROP COLUMN IF EXISTS teaching_material_key
        """
    )


def downgrade() -> None:
    execute_textbook_ddl(
        """
        ALTER TABLE education_textbook_chapters
        ADD COLUMN IF NOT EXISTS teaching_material TEXT,
        ADD COLUMN IF NOT EXISTS teaching_material_key TEXT
        """
    )
    # Schema recreation is intentionally not attempted: this revision removes
    # incompatible historical data and is not reversible in-place.
