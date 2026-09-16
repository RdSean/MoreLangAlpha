from __future__ import annotations

from pathlib import Path
import runpy

import pytest
from sqlalchemy import DDL
from sqlalchemy.dialects import postgresql

from migrations import textbook_ddl


MIGRATIONS = (
    Path(__file__).parents[3] / "migrations" / "versions"
)


class _RecordingBind:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def exec_driver_sql(self, statement: str) -> None:
        self.statements.append(statement)


class _RecordingContext:
    def __init__(self, *, as_sql: bool) -> None:
        self.as_sql = as_sql


class _RecordingOperations:
    def __init__(self, *, as_sql: bool) -> None:
        self.as_sql = as_sql
        self.bind = _RecordingBind()
        self.executed: list[str] = []

    def get_context(self) -> _RecordingContext:
        return _RecordingContext(as_sql=self.as_sql)

    def execute(self, statement: object) -> None:
        if not self.as_sql:
            raise AssertionError("online DDL must bypass op.execute()")
        if not isinstance(statement, DDL):
            raise AssertionError("offline DDL must use a raw DDL construct")
        self.executed.append(
            str(statement.compile(dialect=postgresql.dialect()))
        )

    def get_bind(self) -> _RecordingBind:
        if self.as_sql:
            raise AssertionError("offline DDL must not request a bind")
        return self.bind


def _run_migration_ddl(
    filename: str,
    function_name: str,
    *,
    as_sql: bool,
) -> list[str]:
    migration = runpy.run_path(str(MIGRATIONS / filename))
    function = migration[function_name]
    operations = _RecordingOperations(as_sql=as_sql)
    original_operations = textbook_ddl.op
    textbook_ddl.op = operations
    try:
        function()
    finally:
        textbook_ddl.op = original_operations
    return operations.executed if as_sql else operations.bind.statements


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
@pytest.mark.parametrize("as_sql", [False, True], ids=["online", "offline"])
def test_textbook_migration_ddl_uses_raw_driver_execution(
    filename: str, function_name: str, as_sql: bool
) -> None:
    statements = _run_migration_ddl(
        filename,
        function_name,
        as_sql=as_sql,
    )

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
@pytest.mark.parametrize("as_sql", [False, True], ids=["online", "offline"])
def test_textbook_prefix_constraint_ddl_preserves_regex_unchanged(
    filename: str, function_name: str, as_sql: bool
) -> None:
    statements = _run_migration_ddl(
        filename,
        function_name,
        as_sql=as_sql,
    )

    constraint = statements[-1]
    assert "(?:" in constraint
    assert "education/" in constraint
    assert "%(" not in constraint


def test_prefix_upgrade_expands_alembic_version_before_long_revision() -> None:
    statements = _run_migration_ddl(
        "063_align_textbook_artifact_source_prefix.py",
        "upgrade",
        as_sql=False,
    )

    assert statements[0] == (
        "ALTER TABLE alembic_version "
        "ALTER COLUMN version_num TYPE VARCHAR(255)"
    )
