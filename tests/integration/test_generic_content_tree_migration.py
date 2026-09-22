from __future__ import annotations

from pathlib import Path
import runpy
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from migrations import textbook_ddl
from src.server.database.pool import get_db_connection_string


MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "migrations"
    / "versions"
    / "076_generic_content_tree.py"
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


def _migration_statements(
    monkeypatch: pytest.MonkeyPatch,
    *,
    function_name: str,
) -> list[str]:
    migration = runpy.run_path(str(MIGRATION_PATH))
    operations = _RecordingOperations()
    monkeypatch.setattr(textbook_ddl, "op", operations)
    migration[function_name]()
    return operations.bind.statements


@pytest.mark.integration
@pytest.mark.asyncio
async def test_root_sibling_positions_reject_null_duplicates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements = _migration_statements(monkeypatch, function_name="upgrade")
    schema_name = f"test_content_tree_{uuid4().hex}"

    async with await psycopg.AsyncConnection.connect(
        get_db_connection_string(),
        autocommit=False,
    ) as conn:
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
                )
                await cur.execute(
                    sql.SQL("SET LOCAL search_path TO {}").format(
                        sql.Identifier(schema_name)
                    )
                )
                await cur.execute(
                    """
                    CREATE TABLE education_textbook_structures (
                        structure_id UUID PRIMARY KEY
                    )
                    """
                )
                for statement in statements:
                    await cur.execute(statement)

                structure_id = uuid4()
                await cur.execute(
                    """
                    INSERT INTO education_textbook_structures (structure_id)
                    VALUES (%s)
                    """,
                    (structure_id,),
                )
                await cur.execute(
                    """
                    INSERT INTO education_content_nodes (
                        node_id, structure_id, parent_node_id, node_key,
                        node_type, position, slug, title
                    ) VALUES (%s, %s, NULL, 'root-a', 'unit', 1, 'root-a', 'A')
                    """,
                    (uuid4(), structure_id),
                )
                with pytest.raises(psycopg.errors.UniqueViolation):
                    await cur.execute(
                        """
                        INSERT INTO education_content_nodes (
                            node_id, structure_id, parent_node_id, node_key,
                            node_type, position, slug, title
                        ) VALUES (
                            %s, %s, NULL, 'root-b', 'unit', 1, 'root-b', 'B'
                        )
                        """,
                        (uuid4(), structure_id),
                    )
        finally:
            await conn.rollback()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cross_structure_parent_and_asset_references_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements = _migration_statements(monkeypatch, function_name="upgrade")
    schema_name = f"test_content_tree_{uuid4().hex}"

    async with await psycopg.AsyncConnection.connect(
        get_db_connection_string(),
        autocommit=False,
    ) as conn:
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
                )
                await cur.execute(
                    sql.SQL("SET LOCAL search_path TO {}").format(
                        sql.Identifier(schema_name)
                    )
                )
                await cur.execute(
                    """
                    CREATE TABLE education_textbook_structures (
                        structure_id UUID PRIMARY KEY
                    )
                    """
                )
                for statement in statements:
                    await cur.execute(statement)

                structure_a = uuid4()
                structure_b = uuid4()
                node_b = uuid4()
                await cur.execute(
                    """
                    INSERT INTO education_textbook_structures (structure_id)
                    VALUES (%s), (%s)
                    """,
                    (structure_a, structure_b),
                )
                await cur.execute(
                    """
                    INSERT INTO education_content_nodes (
                        node_id, structure_id, parent_node_id, node_key,
                        node_type, position, slug, title
                    ) VALUES (%s, %s, NULL, 'root-b', 'unit', 1, 'root-b', 'B')
                    """,
                    (node_b, structure_b),
                )

                with pytest.raises(psycopg.errors.ForeignKeyViolation):
                    async with conn.transaction():
                        await cur.execute(
                            """
                            INSERT INTO education_content_nodes (
                                node_id, structure_id, parent_node_id, node_key,
                                node_type, position, slug, title
                            ) VALUES (
                                %s, %s, %s, 'child-a', 'section', 1,
                                'child-a', 'Child A'
                            )
                            """,
                            (uuid4(), structure_a, node_b),
                        )

                with pytest.raises(psycopg.errors.ForeignKeyViolation):
                    async with conn.transaction():
                        await cur.execute(
                            """
                            INSERT INTO education_content_assets (
                                asset_id, structure_id, node_id, asset_type,
                                content_key, content_sha256, size_bytes
                            ) VALUES (%s, %s, %s, 'knowledge', %s, %s, 1)
                            """,
                            (
                                uuid4(),
                                structure_a,
                                node_b,
                                "assets/cross.md",
                                "a" * 64,
                            ),
                        )
        finally:
            await conn.rollback()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_migration_downgrade_removes_generic_tables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upgrade_statements = _migration_statements(
        monkeypatch,
        function_name="upgrade",
    )
    downgrade_statements = _migration_statements(
        monkeypatch,
        function_name="downgrade",
    )
    schema_name = f"test_content_tree_{uuid4().hex}"

    async with await psycopg.AsyncConnection.connect(
        get_db_connection_string(),
        autocommit=False,
    ) as conn:
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
                )
                await cur.execute(
                    sql.SQL("SET LOCAL search_path TO {}").format(
                        sql.Identifier(schema_name)
                    )
                )
                await cur.execute(
                    """
                    CREATE TABLE education_textbook_structures (
                        structure_id UUID PRIMARY KEY
                    )
                    """
                )
                for statement in upgrade_statements:
                    await cur.execute(statement)
                for statement in downgrade_statements:
                    await cur.execute(statement)

                await cur.execute(
                    """
                    SELECT to_regclass('education_content_nodes'),
                           to_regclass('education_content_assets')
                    """
                )
                assert await cur.fetchone() == (None, None)
        finally:
            await conn.rollback()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_structure_cascade_and_parent_restrict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    statements = _migration_statements(monkeypatch, function_name="upgrade")
    schema_name = f"test_content_tree_{uuid4().hex}"

    async with await psycopg.AsyncConnection.connect(
        get_db_connection_string(),
        autocommit=False,
    ) as conn:
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
                )
                await cur.execute(
                    sql.SQL("SET LOCAL search_path TO {}").format(
                        sql.Identifier(schema_name)
                    )
                )
                await cur.execute(
                    """
                    CREATE TABLE education_textbook_structures (
                        structure_id UUID PRIMARY KEY
                    )
                    """
                )
                for statement in statements:
                    await cur.execute(statement)

                structure_id = uuid4()
                parent_id = uuid4()
                child_id = uuid4()
                await cur.execute(
                    """
                    INSERT INTO education_textbook_structures (structure_id)
                    VALUES (%s)
                    """,
                    (structure_id,),
                )
                await cur.execute(
                    """
                    INSERT INTO education_content_nodes (
                        node_id, structure_id, parent_node_id, node_key,
                        node_type, position, slug, title
                    ) VALUES
                        (%s, %s, NULL, 'parent', 'unit', 1, 'parent', 'Parent'),
                        (%s, %s, %s, 'child', 'section', 1, 'child', 'Child')
                    """,
                    (parent_id, structure_id, child_id, structure_id, parent_id),
                )
                await cur.execute(
                    """
                    INSERT INTO education_content_assets (
                        asset_id, structure_id, node_id, asset_type,
                        content_key, content_sha256, size_bytes
                    ) VALUES (%s, %s, %s, 'knowledge', %s, %s, 1)
                    """,
                    (uuid4(), structure_id, child_id, "assets/child.md", "b" * 64),
                )

                with pytest.raises(psycopg.errors.ForeignKeyViolation):
                    async with conn.transaction():
                        await cur.execute(
                            "DELETE FROM education_content_nodes WHERE node_id = %s",
                            (parent_id,),
                        )

                await cur.execute(
                    "DELETE FROM education_textbook_structures WHERE structure_id = %s",
                    (structure_id,),
                )
                await cur.execute(
                    """
                    SELECT
                        (SELECT COUNT(*) FROM education_content_nodes),
                        (SELECT COUNT(*) FROM education_content_assets)
                    """
                )
                assert await cur.fetchone() == (0, 0)
        finally:
            await conn.rollback()
