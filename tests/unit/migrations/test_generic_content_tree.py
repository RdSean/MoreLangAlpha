from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "076_generic_content_tree.py"
)


def test_generic_content_tree_follows_pipeline_reset() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "076_generic_content_tree"
    assert migration["down_revision"] == "075_reset_textbook_pipeline"


def test_generic_content_tree_creates_node_contract() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "CREATE TABLE education_content_nodes" in source
    for column in (
        "node_id UUID PRIMARY KEY",
        "structure_id UUID NOT NULL",
        "parent_node_id UUID",
        "node_key VARCHAR(255) NOT NULL",
        "node_type VARCHAR(64) NOT NULL",
        "label VARCHAR(255)",
        "position INTEGER NOT NULL",
        "slug VARCHAR(255) NOT NULL",
        "title VARCHAR(255) NOT NULL",
        "summary TEXT NOT NULL DEFAULT ''",
        "source_refs JSONB NOT NULL DEFAULT '[]'::jsonb",
        "metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
    ):
        assert column in source
    assert "UNIQUE (structure_id, node_key)" in source
    normalized_source = " ".join(source.split())
    assert "UNIQUE (structure_id, node_id)" in normalized_source
    assert "UNIQUE NULLS NOT DISTINCT (" in normalized_source
    assert "structure_id, parent_node_id, position" in normalized_source
    assert (
        "FOREIGN KEY (structure_id, parent_node_id) "
        "REFERENCES education_content_nodes (structure_id, node_id)"
    ) in normalized_source
    assert (
        "FOREIGN KEY (structure_id, node_id) "
        "REFERENCES education_content_nodes (structure_id, node_id)"
    ) in normalized_source
    assert "idx_education_content_nodes_structure_parent" not in source


def test_generic_content_tree_creates_asset_contract() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "CREATE TABLE education_content_assets" in source
    for column in (
        "asset_id UUID PRIMARY KEY",
        "structure_id UUID NOT NULL",
        "node_id UUID NOT NULL",
        "asset_type VARCHAR(64) NOT NULL",
        "content_key TEXT NOT NULL UNIQUE",
        "content_sha256 VARCHAR(64) NOT NULL",
        "size_bytes INTEGER NOT NULL",
        "metadata JSONB NOT NULL DEFAULT '{}'::jsonb",
    ):
        assert column in source


def test_generic_content_tree_downgrade_removes_only_new_tables() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")

    assert "DROP TABLE IF EXISTS education_content_assets" in source
    assert "DROP TABLE IF EXISTS education_content_nodes" in source
    assert "DROP TABLE IF EXISTS education_textbook_structures" not in source
