from __future__ import annotations

from pathlib import Path
import runpy

import pytest


MIGRATIONS = (
    Path(__file__).parents[3] / "migrations" / "versions"
)


class _RecordingBind:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def exec_driver_sql(self, statement: str) -> None:
        self.statements.append(statement)


class _RejectingOperations:
    def __init__(self) -> None:
        self.bind = _RecordingBind()

    def execute(self, *_args, **_kwargs) -> None:
        raise AssertionError("DDL must bypass SQLAlchemy bind parsing")

    def get_bind(self) -> _RecordingBind:
        return self.bind


def _run_migration_ddl(
    filename: str,
    function_name: str,
) -> list[str]:
    migration = runpy.run_path(str(MIGRATIONS / filename))
    function = migration[function_name]
    operations = _RejectingOperations()
    original_operations = function.__globals__["op"]
    function.__globals__["op"] = operations
    try:
        function()
    finally:
        function.__globals__["op"] = original_operations
    return operations.bind.statements


@pytest.mark.parametrize(
    ("filename", "function_name"),
    [
        ("062_add_textbook_artifact_sources.py", "upgrade"),
        ("062_add_textbook_artifact_sources.py", "downgrade"),
        ("063_align_textbook_artifact_source_prefix.py", "upgrade"),
        ("063_align_textbook_artifact_source_prefix.py", "downgrade"),
        ("064_strengthen_textbook_source_prefix_constraint.py", "upgrade"),
        ("064_strengthen_textbook_source_prefix_constraint.py", "downgrade"),
        ("065_add_textbook_source_asset_manifest.py", "upgrade"),
        ("065_add_textbook_source_asset_manifest.py", "downgrade"),
    ],
)
def test_textbook_migration_ddl_uses_raw_driver_execution(
    filename: str, function_name: str
) -> None:
    statements = _run_migration_ddl(filename, function_name)

    assert statements
    assert all(statement.strip() for statement in statements)


@pytest.mark.parametrize(
    "filename",
    [
        "063_align_textbook_artifact_source_prefix.py",
        "064_strengthen_textbook_source_prefix_constraint.py",
    ],
)
@pytest.mark.parametrize("function_name", ["upgrade", "downgrade"])
def test_textbook_prefix_constraint_ddl_preserves_regex_unchanged(
    filename: str, function_name: str
) -> None:
    statements = _run_migration_ddl(filename, function_name)

    constraint = statements[-1]
    assert "(?:" in constraint
    assert "education/" in constraint
    assert "%(" not in constraint


def test_prefix_upgrade_expands_alembic_version_before_long_revision() -> None:
    statements = _run_migration_ddl(
        "063_align_textbook_artifact_source_prefix.py",
        "upgrade",
    )

    assert statements[0] == (
        "ALTER TABLE alembic_version "
        "ALTER COLUMN version_num TYPE VARCHAR(255)"
    )
