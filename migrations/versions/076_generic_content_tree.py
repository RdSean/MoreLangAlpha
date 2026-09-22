"""Add generic content tree and asset storage.

Revision ID: 076
Revises: 075
"""

from __future__ import annotations

from migrations.textbook_ddl import execute_textbook_ddl


revision = "076_generic_content_tree"
down_revision = "075_reset_textbook_pipeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    execute_textbook_ddl(
        """
        CREATE TABLE education_content_nodes (
            node_id UUID PRIMARY KEY,
            structure_id UUID NOT NULL
                REFERENCES education_textbook_structures(structure_id)
                ON DELETE CASCADE,
            parent_node_id UUID NULL,
            node_key VARCHAR(255) NOT NULL,
            node_type VARCHAR(64) NOT NULL,
            label VARCHAR(255) NULL,
            position INTEGER NOT NULL CHECK (position > 0),
            slug VARCHAR(255) NOT NULL,
            title VARCHAR(255) NOT NULL,
            summary TEXT NOT NULL DEFAULT '',
            source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (structure_id, node_key),
            UNIQUE (structure_id, node_id),
            UNIQUE NULLS NOT DISTINCT (
                structure_id, parent_node_id, position
            ),
            FOREIGN KEY (structure_id, parent_node_id)
                REFERENCES education_content_nodes (structure_id, node_id)
                ON DELETE RESTRICT
        )
        """
    )
    execute_textbook_ddl(
        """
        CREATE TABLE education_content_assets (
            asset_id UUID PRIMARY KEY,
            structure_id UUID NOT NULL
                REFERENCES education_textbook_structures(structure_id)
                ON DELETE CASCADE,
            node_id UUID NOT NULL,
            asset_type VARCHAR(64) NOT NULL,
            content_key TEXT NOT NULL UNIQUE,
            content_sha256 VARCHAR(64) NOT NULL,
            size_bytes INTEGER NOT NULL CHECK (size_bytes >= 0),
            metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            FOREIGN KEY (structure_id, node_id)
                REFERENCES education_content_nodes (structure_id, node_id)
                ON DELETE CASCADE
        )
        """
    )
    execute_textbook_ddl(
        """
        CREATE INDEX idx_education_content_assets_structure_node
        ON education_content_assets (structure_id, node_id, asset_type)
        """
    )


def downgrade() -> None:
    execute_textbook_ddl("DROP TABLE IF EXISTS education_content_assets")
    execute_textbook_ddl("DROP TABLE IF EXISTS education_content_nodes")
