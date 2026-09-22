"""Migration contract for durable book-pipeline continuation bundles."""

from __future__ import annotations

from pathlib import Path
import runpy

from migrations import textbook_ddl


MIGRATION_PATH = (
    Path(__file__).parents[3]
    / "migrations"
    / "versions"
    / "081_book_pipeline_checkpoint.py"
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


def _statements(monkeypatch, function_name: str) -> list[str]:
    namespace = runpy.run_path(str(MIGRATION_PATH))
    operations = _RecordingOperations()
    monkeypatch.setattr(textbook_ddl, "op", operations)
    namespace[function_name]()
    return operations.bind.statements


def test_checkpoint_migration_follows_progress_and_adds_safe_prefix(
    monkeypatch,
) -> None:
    namespace = runpy.run_path(str(MIGRATION_PATH))
    assert namespace["revision"] == "081_book_pipeline_checkpoint"
    assert namespace["down_revision"] == "080_education_job_progress"

    upgrade = "\n".join(_statements(monkeypatch, "upgrade"))

    assert "checkpoint_bundle_prefix TEXT NULL" in upgrade
    assert "education/%" in upgrade
    assert "checkpoint_bundle_prefix NOT LIKE '%%..%%'" in upgrade
    assert "status <> 'awaiting_review'" in upgrade
    assert "btrim(checkpoint_bundle_prefix) <> ''" in upgrade
    assert "checkpoint_bundle_prefix IS NOT NULL" in upgrade


def test_checkpoint_migration_downgrade_guards_then_removes_new_contract(
    monkeypatch,
) -> None:
    downgrade = "\n".join(_statements(monkeypatch, "downgrade"))

    assert "DROP CONSTRAINT" in downgrade
    assert "checkpoint_bundle_prefix IS NOT NULL" in downgrade
    assert "RAISE EXCEPTION" in downgrade
    assert "DROP COLUMN" in downgrade
    assert "education_generation_jobs" in downgrade
