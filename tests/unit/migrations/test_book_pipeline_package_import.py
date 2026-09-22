from __future__ import annotations

from pathlib import Path
import runpy


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "079_book_pipeline_package_import.py"
)


def test_package_import_migration_follows_idempotency() -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))

    assert migration["revision"] == "079_book_pipeline_package_import"
    assert migration["down_revision"] == "078_book_pipeline_idempotency"


def test_package_import_migration_adds_candidate_contract() -> None:
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    normalized = " ".join(source.split())

    assert (
        "ALTER TABLE education_structure_knowledge_points "
        "ALTER COLUMN unit_id DROP NOT NULL"
    ) in normalized
    for column in (
        "content_node_id UUID",
        "content_structure_id UUID",
        "candidate_key VARCHAR(255)",
        "point_type VARCHAR(64) NOT NULL DEFAULT 'concept'",
        "origin VARCHAR(24) NOT NULL DEFAULT 'manual'",
        "candidate_status VARCHAR(24) NOT NULL DEFAULT 'pending'",
    ):
        assert column in normalized
    assert (
        "FOREIGN KEY (content_structure_id, content_node_id) "
        "REFERENCES education_content_nodes(structure_id, node_id)"
    ) in normalized
    assert "origin IN ('manual', 'generated')" in normalized
    assert "candidate_status IN (" in normalized
    for candidate_status in (
        "'pending'",
        "'accepted'",
        "'rejected'",
        "'merged'",
        "'split'",
    ):
        assert candidate_status in normalized
    assert "origin <> 'generated' OR (" in normalized
    assert (
        "content_structure_id IS NOT NULL "
        "AND content_node_id IS NOT NULL "
        "AND candidate_key IS NOT NULL"
    ) in normalized
    assert ("content_node_id IS NOT NULL OR unit_id IS NOT NULL") in normalized
    assert (
        "UNIQUE INDEX uq_education_structure_kp_candidate_node_key "
        "ON education_structure_knowledge_points "
        "(content_node_id, candidate_key)"
    ) in normalized


def test_package_import_migration_allows_completed_structure_link_and_fails_closed() -> (
    None
):
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    normalized = " ".join(source.split())

    assert ("DROP CONSTRAINT IF EXISTS education_generation_jobs_check") in normalized
    assert ("scope = 'book_pipeline' AND knowledge_point_id IS NULL") in normalized
    assert "cannot downgrade 079 while generic book package data exists" in normalized
    assert "origin <> 'manual'" in normalized
    assert "scope = 'book_pipeline' AND structure_id IS NOT NULL" in normalized
    assert "ALTER COLUMN unit_id SET NOT NULL" in normalized
    assert ("ALTER COLUMN source_revision TYPE VARCHAR(255)") in normalized
    assert "char_length(source_revision) > 64" in normalized
