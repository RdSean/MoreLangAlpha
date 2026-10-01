"""Migration contract for the more-to-skills textbook data model."""

from __future__ import annotations

from pathlib import Path
import inspect
import runpy

from migrations import textbook_ddl


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "082_more_to_skills_textbooks.py"
)


class _RecordingBind:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def exec_driver_sql(self, statement: str) -> None:
        self.statements.append(statement)


class _RecordingContext:
    as_sql = False


class _RecordingOperations:
    def __init__(self) -> None:
        self.bind = _RecordingBind()

    def get_context(self) -> _RecordingContext:
        return _RecordingContext()

    def get_bind(self) -> _RecordingBind:
        return self.bind


def _migration() -> dict[str, object]:
    return runpy.run_path(str(MIGRATION_PATH))


def _upgrade_sql(monkeypatch) -> str:
    migration = _migration()
    operations = _RecordingOperations()
    monkeypatch.setattr(textbook_ddl, "op", operations)
    migration["upgrade"]()
    return " ".join("\n".join(operations.bind.statements).split())


def test_migration_follows_checkpoint_head() -> None:
    migration = _migration()

    assert migration["revision"] == "082_more_to_skills_textbooks"
    assert migration["down_revision"] == "081_book_pipeline_checkpoint"


def test_migration_replaces_old_pipeline_with_six_book_tables(monkeypatch) -> None:
    sql = _upgrade_sql(monkeypatch)

    for table in (
        "education_book_structures",
        "education_book_knowledge_points",
        "education_book_materials",
        "education_book_jobs",
        "education_book_job_items",
        "education_book_activity_events",
    ):
        assert f"CREATE TABLE {table}" in sql

    for table in (
        "education_generation_progress_events",
        "education_generation_attempts",
        "education_generation_jobs",
        "education_publication_kp_lessons",
        "education_kp_lesson_revisions",
        "education_kp_lessons",
        "education_textbook_scopes",
        "education_content_assets",
        "education_content_nodes",
        "education_structure_knowledge_points",
        "education_structure_units",
        "education_textbook_publications",
        "education_processing_profiles",
        "education_textbook_structures",
        "education_textbook_chapters",
        "education_processing_jobs",
        "education_textbook_artifact_sources",
        "education_textbook_versions",
    ):
        assert f"DROP TABLE IF EXISTS {table}" in sql


def test_migration_rebuilds_textbook_and_learning_references(monkeypatch) -> None:
    sql = _upgrade_sql(monkeypatch)

    assert (
        "ALTER TABLE education_textbooks RENAME TO education_textbooks_legacy_082"
        in sql
    )
    assert "CREATE TABLE education_textbooks" in sql
    assert "source_parse_job_id VARCHAR(128) NOT NULL" in sql
    assert "source_primary_artifact_id VARCHAR(128) NOT NULL" in sql
    assert "current_structure_id UUID NULL" in sql
    assert (
        "UNIQUE (household_id, source_parse_job_id, source_primary_artifact_id)" in sql
    )
    assert "FOREIGN KEY (textbook_id, current_structure_id)" in sql
    assert "REFERENCES education_book_structures(textbook_id, structure_id)" in sql

    assert (
        "ALTER TABLE education_textbook_assignments RENAME TO education_textbook_assignments_legacy_082"
        in sql
    )
    assert "CREATE TABLE education_textbook_assignments" in sql
    assert "textbook_id UUID NOT NULL" in sql
    assert "UNIQUE (textbook_id, student_user_id)" in sql

    assert (
        "ALTER TABLE education_learning_kp_progress RENAME TO education_learning_kp_progress_legacy_082"
        in sql
    )
    assert (
        "REFERENCES education_book_knowledge_points( textbook_id, knowledge_point_id )"
        in sql
    )
    assert (
        "ALTER TABLE education_learning_items RENAME TO education_learning_items_legacy_082"
        in sql
    )
    assert "skill_node_id VARCHAR(255)" in sql
    assert "FOREIGN KEY (assignment_id, textbook_id)" in sql
    assert "FOREIGN KEY (textbook_id, knowledge_point_id)" in sql
    assert (
        "ALTER TABLE education_learning_spaces RENAME TO education_learning_spaces_legacy_082"
        in sql
    )


def test_migration_enforces_job_fencing_and_material_cas(monkeypatch) -> None:
    sql = _upgrade_sql(monkeypatch)

    assert (
        "CREATE UNIQUE INDEX uq_education_book_jobs_one_active "
        "ON education_book_jobs (textbook_id) "
        "WHERE status IN ('queued', 'running')"
    ) in sql
    assert "UNIQUE (textbook_id, idempotency_key)" in sql
    assert "UNIQUE (job_id, position)" in sql
    assert "UNIQUE (job_id, item_id)" in sql
    assert "FOREIGN KEY (source_job_id, source_item_id)" in sql
    assert "REFERENCES education_book_job_items(job_id, item_id)" in sql
    assert "attempt_token UUID" in sql
    assert "candidate_objects JSONB NOT NULL DEFAULT '[]'::jsonb" in sql
    assert "result_snapshot JSONB" in sql
    assert "generation INTEGER NOT NULL DEFAULT 1" in sql
    assert "content_key LIKE 'education/%%'" in sql
    assert "content_key NOT LIKE '%%..%%'" in sql
    assert "UNIQUE (job_id, dedupe_key)" in sql
    assert "FOREIGN KEY (job_id, item_id)" in sql


def test_material_job_creation_uses_atomic_idempotency_insert() -> None:
    from src.server.database.education_book_jobs import create_materials_job

    source = " ".join(inspect.getsource(create_materials_job).split())

    assert (
        "ON CONFLICT (textbook_id, idempotency_key) DO NOTHING RETURNING job_id"
        in source
    )


def test_downgrade_is_explicitly_irreversible() -> None:
    migration = _migration()

    try:
        migration["downgrade"]()
    except RuntimeError as exc:
        assert "irreversible" in str(exc).lower()
    else:
        raise AssertionError("destructive textbook migration must not downgrade")
