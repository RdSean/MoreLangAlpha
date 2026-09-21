"""Add authoritative reading scopes from the canonical book-to-skill run.

Revision ID: 073
Revises: 072
"""

from __future__ import annotations

from migrations.textbook_ddl import execute_textbook_ddl


revision = "073_textbook_scopes"
down_revision = "072_structure_validation_warnings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_textbook_ddl(
        """
        CREATE TABLE education_textbook_scopes (
            scope_id UUID PRIMARY KEY,
            structure_id UUID NOT NULL
                REFERENCES education_textbook_structures(structure_id)
                ON DELETE CASCADE,
            unit_id UUID NOT NULL
                REFERENCES education_structure_units(unit_id)
                ON DELETE CASCADE,
            slot VARCHAR(16) NOT NULL CHECK (
                slot IN ('reading_a', 'reading_b')
            ),
            title TEXT NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            reading_skill TEXT NOT NULL DEFAULT '',
            vocabulary_building TEXT NOT NULL DEFAULT '',
            critical_thinking TEXT NOT NULL DEFAULT '',
            source_id TEXT NOT NULL,
            line_start INTEGER NOT NULL CHECK (line_start > 0),
            line_end INTEGER NOT NULL CHECK (line_end > line_start),
            char_start INTEGER NOT NULL CHECK (char_start >= 0),
            char_end INTEGER NOT NULL CHECK (char_end > char_start),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (unit_id, slot)
        )
        """
    )
    execute_textbook_ddl(
        """
        CREATE INDEX idx_education_textbook_scopes_structure
        ON education_textbook_scopes (structure_id, unit_id, line_start)
        """
    )


def downgrade() -> None:
    execute_textbook_ddl("DROP TABLE IF EXISTS education_textbook_scopes")
