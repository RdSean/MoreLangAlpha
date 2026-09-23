"""Real PostgreSQL contracts for unified book-pipeline jobs."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from pathlib import Path
import runpy
from uuid import UUID, uuid4

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
import pytest

from migrations import textbook_ddl
from src.server.database.conversation import create_thread
from src.server.database import education_textbooks
from src.server.database.workspace import create_workspace


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

CHECKPOINT_PREFIX = (
    "education/household/textbook/v1/book-pipeline-checkpoints/"
    "4d0112f8-0e00-4f1f-990a-4bc1b1cc20f3/"
    "6f3f2de2-5c58-4bc2-84bc-95e97acd37f6"
)

MIGRATION_PATH = (
    Path(__file__).parents[2] / "migrations" / "versions" / "077_book_pipeline_jobs.py"
)
MIGRATION_078_PATH = (
    Path(__file__).parents[2]
    / "migrations"
    / "versions"
    / "078_book_pipeline_idempotency.py"
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


def _migration_078_statements(
    monkeypatch: pytest.MonkeyPatch,
    *,
    function_name: str,
) -> list[str]:
    migration = runpy.run_path(str(MIGRATION_078_PATH))
    operations = _RecordingOperations()
    monkeypatch.setattr(textbook_ddl, "op", operations)
    migration[function_name]()
    return operations.bind.statements


def _test_connection(test_db_uri: str):
    @asynccontextmanager
    async def _connect():
        async with await psycopg.AsyncConnection.connect(
            test_db_uri,
            autocommit=True,
            row_factory=dict_row,
        ) as conn:
            yield conn

    return _connect


async def _seed_book_pipeline_parent(
    db_conn: psycopg.AsyncConnection,
) -> tuple[str, UUID]:
    parent_user_id = f"parent-{uuid4()}"
    household_id = uuid4()
    textbook_id = uuid4()
    version_id = uuid4()
    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO users (user_id, name) VALUES (%s, %s)",
                (parent_user_id, "Book pipeline parent"),
            )
            await cur.execute(
                """
                INSERT INTO education_households (
                    household_id, name, model_owner_user_id
                ) VALUES (%s, %s, %s)
                """,
                (household_id, "Book pipeline household", parent_user_id),
            )
            await cur.execute(
                """
                INSERT INTO education_memberships (
                    household_id, user_id, role, display_name
                ) VALUES (%s, %s, 'parent', %s)
                """,
                (household_id, parent_user_id, "Parent"),
            )
            await cur.execute(
                """
                INSERT INTO education_textbooks (
                    textbook_id, household_id, title, slug, created_by_user_id
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    textbook_id,
                    household_id,
                    "Book pipeline textbook",
                    f"book-{uuid4().hex}",
                    parent_user_id,
                ),
            )
            await cur.execute(
                """
                INSERT INTO education_textbook_versions (
                    version_id, textbook_id, sequence, status, created_by_user_id
                ) VALUES (%s, %s, 1, 'review', %s)
                """,
                (version_id, textbook_id, parent_user_id),
            )
    return parent_user_id, version_id


async def _wait_for_backend_lock(
    conn: psycopg.AsyncConnection,
    *,
    backend_pid: int,
) -> None:
    for _attempt in range(100):
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT wait_event_type
                FROM pg_stat_activity
                WHERE pid = %s
                """,
                (backend_pid,),
            )
            row = await cur.fetchone()
        if row is not None and row["wait_event_type"] == "Lock":
            return
        await asyncio.sleep(0.01)
    raise AssertionError("pause did not block on the attempt row lock")


@pytest.mark.asyncio
async def test_078_schema_uniqueness_and_fail_closed_downgrade(
    test_db_uri: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    upgrade_statements = _migration_078_statements(
        monkeypatch,
        function_name="upgrade",
    )
    downgrade_statements = _migration_078_statements(
        monkeypatch,
        function_name="downgrade",
    )
    schema_name = f"test_book_pipeline_078_{uuid4().hex}"
    version_id = uuid4()
    request_id = uuid4()
    first_job_id = uuid4()

    async with await psycopg.AsyncConnection.connect(
        test_db_uri,
        autocommit=True,
        row_factory=dict_row,
    ) as conn:
        try:
            async with conn.cursor() as cur:
                await cur.execute(
                    sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
                )
                await cur.execute(
                    sql.SQL("SET search_path TO {}").format(sql.Identifier(schema_name))
                )
                await cur.execute(
                    """
                    CREATE TABLE education_generation_jobs (
                        generation_job_id UUID PRIMARY KEY,
                        version_id UUID NOT NULL,
                        scope VARCHAR(24) NOT NULL,
                        status VARCHAR(24) NOT NULL,
                        processing_profile_sha256 VARCHAR(64) NOT NULL
                    )
                    """
                )
                for statement in upgrade_statements:
                    await cur.execute(statement)

                await cur.execute(
                    """
                    SELECT column_name, column_default, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'education_generation_jobs'
                      AND column_name IN ('request_id', 'processing_brief')
                    ORDER BY column_name
                    """
                )
                assert await cur.fetchall() == [
                    {
                        "column_name": "processing_brief",
                        "column_default": "''::text",
                        "is_nullable": "NO",
                    },
                    {
                        "column_name": "request_id",
                        "column_default": None,
                        "is_nullable": "YES",
                    },
                ]
                await cur.execute(
                    """
                    SELECT indexdef
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND indexname =
                          'uq_education_generation_jobs_version_request_id'
                    """
                )
                index_definition = (await cur.fetchone())["indexdef"]
                assert "UNIQUE" in index_definition
                assert "(version_id, request_id)" in index_definition
                assert "WHERE (request_id IS NOT NULL)" in index_definition


            async with conn.transaction():
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO education_generation_jobs (
                            generation_job_id, version_id, scope, status,
                            processing_profile_sha256, request_id,
                            processing_brief
                        ) VALUES (
                            %s, %s, 'book_pipeline', 'queued', %s, NULL, %s
                        )
                        """,
                        (uuid4(), version_id, "d" * 64, "a" * 4_000),
                    )
                    with pytest.raises(psycopg.errors.CheckViolation) as exc_info:
                        async with conn.transaction():
                            await cur.execute(
                                """
                                INSERT INTO education_generation_jobs (
                                    generation_job_id, version_id, scope, status,
                                    processing_profile_sha256, request_id,
                                    processing_brief
                                ) VALUES (
                                    %s, %s, 'book_pipeline', 'queued',
                                    %s, NULL, %s
                                )
                                """,
                                (uuid4(), version_id, "e" * 64, "a" * 4_001),
                            )
                    assert (
                        exc_info.value.diag.constraint_name
                        == "education_generation_jobs_processing_brief_length_check"
                    )

            async with conn.transaction():
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO education_generation_jobs (
                            generation_job_id, version_id, scope, status,
                            processing_profile_sha256, request_id,
                            processing_brief
                        ) VALUES (
                            %s, %s, 'book_pipeline', 'queued', %s, %s, %s
                        )
                        """,
                        (
                            first_job_id,
                            version_id,
                            "a" * 64,
                            request_id,
                            "保留公式顺序。",
                        ),
                    )
                    with pytest.raises(psycopg.errors.UniqueViolation):
                        async with conn.transaction():
                            await cur.execute(
                                """
                                INSERT INTO education_generation_jobs (
                                    generation_job_id, version_id, scope, status,
                                    processing_profile_sha256, request_id,
                                    processing_brief
                                ) VALUES (
                                    %s, %s, 'book_pipeline', 'queued',
                                    %s, %s, %s
                                )
                                """,
                                (
                                    uuid4(),
                                    version_id,
                                    "b" * 64,
                                    request_id,
                                    "重复 request。",
                                ),
                            )

            async with conn.transaction():
                async with conn.cursor() as cur:
                    for _index in range(2):
                        await cur.execute(
                            """
                            INSERT INTO education_generation_jobs (
                                generation_job_id, version_id, scope, status,
                                processing_profile_sha256, request_id,
                                processing_brief
                            ) VALUES (
                                %s, %s, 'book_pipeline', 'queued', %s, NULL, ''
                            )
                            """,
                            (uuid4(), version_id, "c" * 64),
                        )

            with pytest.raises(psycopg.errors.RaiseException):
                async with conn.transaction():
                    async with conn.cursor() as cur:
                        for statement in downgrade_statements:
                            await cur.execute(statement)

            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM education_generation_jobs
                    WHERE generation_job_id = %s
                    """,
                    (first_job_id,),
                )
                assert (await cur.fetchone())["count"] == 1
                await cur.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'education_generation_jobs'
                      AND column_name IN ('request_id', 'processing_brief')
                    """
                )
                assert (await cur.fetchone())["count"] == 2
                await cur.execute("DELETE FROM education_generation_jobs")

            async with conn.transaction():
                async with conn.cursor() as cur:
                    for statement in downgrade_statements:
                        await cur.execute(statement)

            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'education_generation_jobs'
                      AND column_name IN ('request_id', 'processing_brief')
                    """
                )
                assert (await cur.fetchone())["count"] == 0
                await cur.execute(
                    """
                    SELECT to_regclass(
                        'uq_education_generation_jobs_version_request_id'
                    ) AS index_name
                    """
                )
                assert (await cur.fetchone())["index_name"] is None
        finally:
            async with conn.cursor() as cur:
                await cur.execute(
                    sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                        sql.Identifier(schema_name)
                    )
                )


@pytest.mark.asyncio
async def test_077_constraints_and_fail_closed_downgrade(
    monkeypatch: pytest.MonkeyPatch,
    test_db_uri: str,
) -> None:
    upgrade_statements = _migration_statements(
        monkeypatch,
        function_name="upgrade",
    )
    downgrade_statements = _migration_statements(
        monkeypatch,
        function_name="downgrade",
    )
    schema_name = f"test_book_pipeline_{uuid4().hex}"
    generation_job_id = uuid4()
    awaiting_job_id = uuid4()
    version_id = uuid4()

    async with await psycopg.AsyncConnection.connect(
        test_db_uri,
        autocommit=False,
        row_factory=dict_row,
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
                    CREATE TABLE education_generation_jobs (
                        generation_job_id UUID PRIMARY KEY,
                        version_id UUID NOT NULL,
                        scope VARCHAR(24) NOT NULL,
                        structure_id UUID,
                        knowledge_point_id UUID,
                        status VARCHAR(24) NOT NULL,
                        processing_profile_sha256 VARCHAR(64) NOT NULL,
                        CONSTRAINT education_generation_jobs_scope_check
                            CHECK (scope IN ('structure', 'assets', 'lesson')),
                        CONSTRAINT education_generation_jobs_status_check
                            CHECK (
                                status IN (
                                    'queued', 'preparing', 'running',
                                    'validating', 'completed', 'failed',
                                    'cancelled'
                                )
                            ),
                        CONSTRAINT education_generation_jobs_check
                            CHECK (
                                (
                                    scope IN ('structure', 'assets')
                                    AND structure_id IS NOT NULL
                                    AND knowledge_point_id IS NULL
                                )
                                OR
                                (
                                    scope = 'lesson'
                                    AND structure_id IS NULL
                                    AND knowledge_point_id IS NOT NULL
                                )
                            )
                    )
                    """
                )
                for statement in upgrade_statements:
                    await cur.execute(statement)

                await cur.execute(
                    """
                    SELECT column_default, is_nullable
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'education_generation_jobs'
                      AND column_name = 'pause_after_chapter_analysis'
                    """
                )
                column = await cur.fetchone()
                assert column is not None
                assert column["column_default"] == "false"
                assert column["is_nullable"] == "NO"

                await cur.execute(
                    """
                    INSERT INTO education_generation_jobs (
                        generation_job_id, version_id, scope, status,
                        pause_after_chapter_analysis,
                        processing_profile_sha256
                    ) VALUES
                        (%s, %s, 'book_pipeline', 'queued', FALSE, %s),
                        (%s, %s, 'book_pipeline', 'awaiting_review', TRUE, %s)
                    """,
                    (
                        generation_job_id,
                        version_id,
                        "a" * 64,
                        awaiting_job_id,
                        version_id,
                        "a" * 64,
                    ),
                )

                for scope, structure_id, knowledge_point_id, status in (
                    ("book_pipeline", uuid4(), None, "queued"),
                    ("book_pipeline", None, uuid4(), "queued"),
                    ("invalid_scope", None, None, "queued"),
                    ("book_pipeline", None, None, "awaiting_invalid"),
                    ("structure", uuid4(), None, "awaiting_review"),
                    ("book_pipeline", None, None, "awaiting_review"),
                ):
                    with pytest.raises(psycopg.errors.CheckViolation):
                        async with conn.transaction():
                            await cur.execute(
                                """
                                INSERT INTO education_generation_jobs (
                                    generation_job_id, version_id, scope,
                                    structure_id, knowledge_point_id, status,
                                    processing_profile_sha256
                                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                                """,
                                (
                                    uuid4(),
                                    version_id,
                                    scope,
                                    structure_id,
                                    knowledge_point_id,
                                    status,
                                    "b" * 64,
                                ),
                            )

                with pytest.raises(psycopg.errors.CheckViolation):
                    async with conn.transaction():
                        for statement in downgrade_statements:
                            await cur.execute(statement)

                await cur.execute(
                    """
                    SELECT COUNT(*) AS count,
                           BOOL_AND(scope = 'book_pipeline') AS all_pipeline
                    FROM education_generation_jobs
                    """
                )
                assert await cur.fetchone() == {
                    "count": 2,
                    "all_pipeline": True,
                }
                await cur.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'education_generation_jobs'
                      AND column_name = 'pause_after_chapter_analysis'
                    """
                )
                assert (await cur.fetchone())["count"] == 1

                await cur.execute(
                    """
                    DELETE FROM education_generation_jobs
                    WHERE generation_job_id = ANY(%s)
                    """,
                    ([generation_job_id, awaiting_job_id],),
                )
                async with conn.transaction():
                    for statement in downgrade_statements:
                        await cur.execute(statement)

                await cur.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'education_generation_jobs'
                      AND column_name = 'pause_after_chapter_analysis'
                    """
                )
                assert (await cur.fetchone())["count"] == 0
                await cur.execute(
                    """
                    SELECT pg_get_constraintdef(oid) AS definition
                    FROM pg_constraint
                    WHERE conrelid =
                          'education_generation_jobs'::regclass
                      AND conname = 'education_generation_jobs_scope_check'
                    """
                )
                scope_definition = (await cur.fetchone())["definition"]
                assert "book_pipeline" not in scope_definition
        finally:
            await conn.rollback()


async def _assert_downgrade_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    test_db_uri: str,
    *,
    status: str,
    pause_after_chapter_analysis: bool,
    expected_constraint: str,
) -> None:
    upgrade_statements = _migration_statements(
        monkeypatch,
        function_name="upgrade",
    )
    downgrade_statements = _migration_statements(
        monkeypatch,
        function_name="downgrade",
    )
    schema_name = f"test_book_pipeline_downgrade_{uuid4().hex}"
    generation_job_id = uuid4()
    version_id = uuid4()

    async with await psycopg.AsyncConnection.connect(
        test_db_uri,
        autocommit=False,
        row_factory=dict_row,
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
                    CREATE TABLE education_generation_jobs (
                        generation_job_id UUID PRIMARY KEY,
                        version_id UUID NOT NULL,
                        scope VARCHAR(24) NOT NULL,
                        structure_id UUID,
                        knowledge_point_id UUID,
                        status VARCHAR(24) NOT NULL,
                        processing_profile_sha256 VARCHAR(64) NOT NULL,
                        CONSTRAINT education_generation_jobs_scope_check
                            CHECK (scope IN ('structure', 'assets', 'lesson')),
                        CONSTRAINT education_generation_jobs_status_check
                            CHECK (
                                status IN (
                                    'queued', 'preparing', 'running',
                                    'validating', 'completed', 'failed',
                                    'cancelled'
                                )
                            ),
                        CONSTRAINT education_generation_jobs_check
                            CHECK (
                                (
                                    scope IN ('structure', 'assets')
                                    AND structure_id IS NOT NULL
                                    AND knowledge_point_id IS NULL
                                )
                                OR
                                (
                                    scope = 'lesson'
                                    AND structure_id IS NULL
                                    AND knowledge_point_id IS NOT NULL
                                )
                            )
                    )
                    """
                )
                for statement in upgrade_statements:
                    await cur.execute(statement)
                await cur.execute(
                    """
                    INSERT INTO education_generation_jobs (
                        generation_job_id, version_id, scope, status,
                        pause_after_chapter_analysis,
                        processing_profile_sha256
                    ) VALUES (
                        %s, %s, 'book_pipeline', %s, %s, %s
                    )
                    """,
                    (
                        generation_job_id,
                        version_id,
                        status,
                        pause_after_chapter_analysis,
                        "a" * 64,
                    ),
                )

                with pytest.raises(psycopg.errors.CheckViolation) as exc_info:
                    async with conn.transaction():
                        for statement in downgrade_statements:
                            await cur.execute(statement)
                assert exc_info.value.diag.constraint_name == expected_constraint
                await cur.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM education_generation_jobs
                    WHERE generation_job_id = %s
                    """,
                    (generation_job_id,),
                )
                assert (await cur.fetchone())["count"] == 1
        finally:
            await conn.rollback()


@pytest.mark.asyncio
async def test_077_downgrade_fails_closed_for_book_pipeline_scope(
    test_db_uri: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _assert_downgrade_fails_closed(
        monkeypatch,
        test_db_uri,
        status="queued",
        pause_after_chapter_analysis=False,
        expected_constraint="education_generation_jobs_scope_check",
    )


@pytest.mark.asyncio
async def test_077_downgrade_fails_closed_for_awaiting_review_status(
    test_db_uri: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _assert_downgrade_fails_closed(
        monkeypatch,
        test_db_uri,
        status="awaiting_review",
        pause_after_chapter_analysis=True,
        expected_constraint="education_generation_jobs_status_check",
    )


@pytest.mark.asyncio
async def test_two_connections_deduplicate_book_pipeline_queue(
    cleanup_tables,
    db_conn,
    test_db_uri: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_user_id, version_id = await _seed_book_pipeline_parent(db_conn)
    request_id = uuid4()

    monkeypatch.setattr(
        education_textbooks,
        "get_db_connection",
        _test_connection(test_db_uri),
    )

    first, second = await asyncio.gather(
        education_textbooks.queue_book_pipeline_job(
            parent_user_id=parent_user_id,
            content_version_id=str(version_id),
            processing_profile_sha256="a" * 64,
            processing_brief="保留公式顺序。",
            request_id=str(request_id),
        ),
        education_textbooks.queue_book_pipeline_job(
            parent_user_id=parent_user_id,
            content_version_id=str(version_id),
            processing_profile_sha256="b" * 64,
            processing_brief="重复提交。",
            request_id=str(request_id),
        ),
    )

    assert first is not None
    assert second is not None
    assert first["generation_job_id"] == second["generation_job_id"]
    assert {first["reused_existing_job"], second["reused_existing_job"]} == {
        False,
        True,
    }
    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT request_id, processing_brief
            FROM education_generation_jobs
            WHERE version_id = %s AND scope = 'book_pipeline'
            """,
            (version_id,),
        )
        stored_rows = await cur.fetchall()
        assert len(stored_rows) == 1
        stored = stored_rows[0]
        assert stored["request_id"] == request_id
        assert stored["processing_brief"] in {"保留公式顺序。", "重复提交。"}


@pytest.mark.asyncio
async def test_078_request_id_priority_beats_another_active_job(
    cleanup_tables,
    db_conn,
    test_db_uri: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_user_id, version_id = await _seed_book_pipeline_parent(db_conn)
    request_a = uuid4()
    request_b = uuid4()
    request_c = uuid4()
    monkeypatch.setattr(
        education_textbooks,
        "get_db_connection",
        _test_connection(test_db_uri),
    )

    job_a = await education_textbooks.queue_book_pipeline_job(
        parent_user_id=parent_user_id,
        content_version_id=str(version_id),
        processing_profile_sha256="a" * 64,
        processing_brief="任务 A。",
        request_id=str(request_a),
    )
    assert job_a is not None
    reuse_active_a = await education_textbooks.queue_book_pipeline_job(
        parent_user_id=parent_user_id,
        content_version_id=str(version_id),
        processing_profile_sha256="b" * 64,
        processing_brief="任务 B。",
        request_id=str(request_b),
    )
    assert reuse_active_a is not None
    assert reuse_active_a["generation_job_id"] == job_a["generation_job_id"]
    assert reuse_active_a["reused_existing_job"] is True

    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE education_generation_jobs
                SET status = 'completed'
                WHERE generation_job_id = %s
                """,
                (job_a["generation_job_id"],),
            )
            job_b_id = uuid4()
            await cur.execute(
                """
                INSERT INTO education_generation_jobs (
                    generation_job_id, version_id, scope, status,
                    processing_profile_sha256, request_id, processing_brief
                ) VALUES (
                    %s, %s, 'book_pipeline', 'queued', %s, %s, %s
                )
                """,
                (
                    job_b_id,
                    version_id,
                    "b" * 64,
                    request_b,
                    "任务 B。",
                ),
            )

    repeated_a = await education_textbooks.queue_book_pipeline_job(
        parent_user_id=parent_user_id,
        content_version_id=str(version_id),
        processing_profile_sha256="d" * 64,
        processing_brief="新的补充。",
        request_id=str(request_a),
    )
    reuse_active_b = await education_textbooks.queue_book_pipeline_job(
        parent_user_id=parent_user_id,
        content_version_id=str(version_id),
        processing_profile_sha256="c" * 64,
        processing_brief="任务 C。",
        request_id=str(request_c),
    )

    assert repeated_a is not None
    assert repeated_a["generation_job_id"] == job_a["generation_job_id"]
    assert repeated_a["reused_existing_job"] is True
    assert reuse_active_b is not None
    assert reuse_active_b["generation_job_id"] == job_b_id
    assert reuse_active_b["reused_existing_job"] is True


@pytest.mark.asyncio
async def test_pause_and_resume_enforce_household_acl(
    test_db_uri: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema_name = f"test_book_pipeline_acl_{uuid4().hex}"
    household_a = uuid4()
    household_b = uuid4()
    textbook_a = uuid4()
    version_a = uuid4()
    generation_job_id = uuid4()
    attempt_id = uuid4()
    parent_a = f"parent-a-{uuid4()}"
    parent_b = f"parent-b-{uuid4()}"

    async with await psycopg.AsyncConnection.connect(
        test_db_uri,
        autocommit=False,
        row_factory=dict_row,
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
                    CREATE TABLE education_memberships (
                        household_id UUID NOT NULL,
                        user_id VARCHAR(255) NOT NULL,
                        role VARCHAR(16) NOT NULL,
                        PRIMARY KEY (household_id, user_id)
                    );
                    CREATE TABLE education_textbooks (
                        textbook_id UUID PRIMARY KEY,
                        household_id UUID NOT NULL
                    );
                    CREATE TABLE education_textbook_versions (
                        version_id UUID PRIMARY KEY,
                        textbook_id UUID NOT NULL
                    );
                    CREATE TABLE education_generation_jobs (
                        generation_job_id UUID PRIMARY KEY,
                        version_id UUID NOT NULL,
                        scope VARCHAR(24) NOT NULL,
                        structure_id UUID,
                        knowledge_point_id UUID,
                        status VARCHAR(24) NOT NULL,
                        attempt_count INTEGER NOT NULL DEFAULT 0,
                        latest_attempt_id UUID,
                        pause_after_chapter_analysis BOOLEAN NOT NULL DEFAULT FALSE,
                        checkpoint_bundle_prefix TEXT,
                        processing_profile_sha256 VARCHAR(64) NOT NULL,
                        error_code VARCHAR(64),
                        error_message TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                    CREATE TABLE education_generation_attempts (
                        attempt_id UUID PRIMARY KEY,
                        generation_job_id UUID NOT NULL,
                        status VARCHAR(24) NOT NULL,
                        completed_at TIMESTAMPTZ
                    )
                    """
                )
                await cur.execute(
                    """
                    INSERT INTO education_memberships (
                        household_id, user_id, role
                    ) VALUES
                        (%s, %s, 'parent'),
                        (%s, %s, 'parent')
                    """,
                    (household_a, parent_a, household_b, parent_b),
                )
                await cur.execute(
                    """
                    INSERT INTO education_textbooks (
                        textbook_id, household_id
                    ) VALUES (%s, %s)
                    """,
                    (textbook_a, household_a),
                )
                await cur.execute(
                    """
                    INSERT INTO education_textbook_versions (
                        version_id, textbook_id
                    ) VALUES (%s, %s)
                    """,
                    (version_a, textbook_a),
                )
                await cur.execute(
                    """
                    INSERT INTO education_generation_jobs (
                        generation_job_id, version_id, scope, status,
                        attempt_count, latest_attempt_id,
                        pause_after_chapter_analysis,
                        processing_profile_sha256
                    ) VALUES (
                        %s, %s, 'book_pipeline', 'running',
                        1, %s, TRUE, %s
                    )
                    """,
                    (generation_job_id, version_a, attempt_id, "a" * 64),
                )
                await cur.execute(
                    """
                    INSERT INTO education_generation_attempts (
                        attempt_id, generation_job_id, status
                    ) VALUES (%s, %s, 'running')
                    """,
                    (attempt_id, generation_job_id),
                )

            @asynccontextmanager
            async def same_connection():
                yield conn

            monkeypatch.setattr(
                education_textbooks,
                "get_db_connection",
                same_connection,
            )

            assert (
                await education_textbooks.pause_book_pipeline_for_chapter_review(
                    parent_user_id=parent_b,
                    generation_job_id=str(generation_job_id),
                    attempt_id=str(attempt_id),
                    checkpoint_bundle_prefix=CHECKPOINT_PREFIX,
                )
                is None
            )
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT jobs.status, jobs.pause_after_chapter_analysis,
                           attempts.status AS attempt_status,
                           attempts.completed_at
                    FROM education_generation_jobs AS jobs
                    JOIN education_generation_attempts AS attempts
                      ON attempts.attempt_id = jobs.latest_attempt_id
                    WHERE jobs.generation_job_id = %s
                    """,
                    (generation_job_id,),
                )
                assert await cur.fetchone() == {
                    "status": "running",
                    "pause_after_chapter_analysis": True,
                    "attempt_status": "running",
                    "completed_at": None,
                }

            paused = await education_textbooks.pause_book_pipeline_for_chapter_review(
                parent_user_id=parent_a,
                generation_job_id=str(generation_job_id),
                attempt_id=str(attempt_id),
                checkpoint_bundle_prefix=CHECKPOINT_PREFIX,
            )
            assert paused is not None
            assert paused["status"] == "awaiting_review"
            assert paused["pause_after_chapter_analysis"] is True
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT jobs.status, jobs.pause_after_chapter_analysis,
                           attempts.status AS attempt_status,
                           attempts.completed_at
                    FROM education_generation_jobs AS jobs
                    JOIN education_generation_attempts AS attempts
                      ON attempts.attempt_id = jobs.latest_attempt_id
                    WHERE jobs.generation_job_id = %s
                    """,
                    (generation_job_id,),
                )
                paused_state = await cur.fetchone()
                assert paused_state is not None
                assert paused_state["status"] == "awaiting_review"
                assert paused_state["pause_after_chapter_analysis"] is True
                assert paused_state["attempt_status"] == "completed"
                assert paused_state["completed_at"] is not None

            assert (
                await education_textbooks.resume_book_pipeline_job(
                    parent_user_id=parent_b,
                    generation_job_id=str(generation_job_id),
                )
                is None
            )
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT status, pause_after_chapter_analysis
                    FROM education_generation_jobs
                    WHERE generation_job_id = %s
                    """,
                    (generation_job_id,),
                )
                assert await cur.fetchone() == {
                    "status": "awaiting_review",
                    "pause_after_chapter_analysis": True,
                }

            resumed = await education_textbooks.resume_book_pipeline_job(
                parent_user_id=parent_a,
                generation_job_id=str(generation_job_id),
            )
            assert resumed is not None
            assert resumed["status"] == "queued"
            assert resumed["pause_after_chapter_analysis"] is False
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    SELECT status, pause_after_chapter_analysis
                    FROM education_generation_jobs
                    WHERE generation_job_id = %s
                    """,
                    (generation_job_id,),
                )
                assert await cur.fetchone() == {
                    "status": "queued",
                    "pause_after_chapter_analysis": False,
                }
        finally:
            await conn.rollback()


@pytest.mark.asyncio
async def test_pause_uses_attempt_first_lock_order(
    test_db_uri: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    schema_name = f"test_book_pipeline_lock_{uuid4().hex}"
    household_id = uuid4()
    textbook_id = uuid4()
    version_id = uuid4()
    generation_job_id = uuid4()
    attempt_id = uuid4()
    parent_user_id = f"parent-lock-{uuid4()}"

    setup_conn = await psycopg.AsyncConnection.connect(
        test_db_uri,
        autocommit=True,
        row_factory=dict_row,
    )
    pause_conn = await psycopg.AsyncConnection.connect(
        test_db_uri,
        autocommit=False,
        row_factory=dict_row,
    )
    blocker = await psycopg.AsyncConnection.connect(
        test_db_uri,
        autocommit=False,
        row_factory=dict_row,
    )
    pause_task: asyncio.Task | None = None
    try:
        async with setup_conn.cursor() as cur:
            await cur.execute(
                sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema_name))
            )
            await cur.execute(
                sql.SQL("SET search_path TO {}").format(sql.Identifier(schema_name))
            )
            await cur.execute(
                """
                CREATE TABLE education_memberships (
                    household_id UUID NOT NULL,
                    user_id VARCHAR(255) NOT NULL,
                    role VARCHAR(16) NOT NULL
                );
                CREATE TABLE education_textbooks (
                    textbook_id UUID PRIMARY KEY,
                    household_id UUID NOT NULL
                );
                CREATE TABLE education_textbook_versions (
                    version_id UUID PRIMARY KEY,
                    textbook_id UUID NOT NULL
                );
                CREATE TABLE education_generation_jobs (
                    generation_job_id UUID PRIMARY KEY,
                    version_id UUID NOT NULL,
                    scope VARCHAR(24) NOT NULL,
                    structure_id UUID,
                    knowledge_point_id UUID,
                    status VARCHAR(24) NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    latest_attempt_id UUID,
                    pause_after_chapter_analysis BOOLEAN NOT NULL DEFAULT FALSE,
                    checkpoint_bundle_prefix TEXT,
                    processing_profile_sha256 VARCHAR(64) NOT NULL,
                    error_code VARCHAR(64),
                    error_message TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                );
                CREATE TABLE education_generation_attempts (
                    attempt_id UUID PRIMARY KEY,
                    generation_job_id UUID NOT NULL,
                    status VARCHAR(24) NOT NULL,
                    completed_at TIMESTAMPTZ
                )
                """
            )
            await cur.execute(
                """
                INSERT INTO education_memberships (
                    household_id, user_id, role
                ) VALUES (%s, %s, 'parent')
                """,
                (household_id, parent_user_id),
            )
            await cur.execute(
                """
                INSERT INTO education_textbooks (
                    textbook_id, household_id
                ) VALUES (%s, %s)
                """,
                (textbook_id, household_id),
            )
            await cur.execute(
                """
                INSERT INTO education_textbook_versions (
                    version_id, textbook_id
                ) VALUES (%s, %s)
                """,
                (version_id, textbook_id),
            )
            await cur.execute(
                """
                INSERT INTO education_generation_jobs (
                    generation_job_id, version_id, scope, status,
                    attempt_count, latest_attempt_id,
                    pause_after_chapter_analysis,
                    processing_profile_sha256
                ) VALUES (
                    %s, %s, 'book_pipeline', 'running',
                    1, %s, TRUE, %s
                )
                """,
                (generation_job_id, version_id, attempt_id, "a" * 64),
            )
            await cur.execute(
                """
                INSERT INTO education_generation_attempts (
                    attempt_id, generation_job_id, status
                ) VALUES (%s, %s, 'running')
                """,
                (attempt_id, generation_job_id),
            )

        for connection in (pause_conn, blocker):
            async with connection.cursor() as cur:
                await cur.execute(
                    sql.SQL("SET search_path TO {}").format(sql.Identifier(schema_name))
                )
            await connection.commit()

        @asynccontextmanager
        async def same_connection():
            yield pause_conn

        monkeypatch.setattr(
            education_textbooks,
            "get_db_connection",
            same_connection,
        )

        async with blocker.cursor() as cur:
            await cur.execute("SET statement_timeout = '500ms'")
            await cur.execute("BEGIN")
            await cur.execute(
                """
                SELECT attempt_id
                FROM education_generation_attempts
                WHERE attempt_id = %s
                FOR UPDATE
                """,
                (attempt_id,),
            )

        async with pause_conn.cursor() as cur:
            await cur.execute("SELECT pg_backend_pid() AS pid")
            pause_pid = (await cur.fetchone())["pid"]

        pause_task = asyncio.create_task(
            education_textbooks.pause_book_pipeline_for_chapter_review(
                parent_user_id=parent_user_id,
                generation_job_id=str(generation_job_id),
                attempt_id=str(attempt_id),
                checkpoint_bundle_prefix=CHECKPOINT_PREFIX,
            )
        )
        await _wait_for_backend_lock(blocker, backend_pid=pause_pid)

        # Attempt-first order leaves the job lock available while pause waits.
        async with blocker.cursor() as cur:
            await cur.execute(
                """
                SELECT generation_job_id
                FROM education_generation_jobs
                WHERE generation_job_id = %s
                FOR UPDATE
                """,
                (generation_job_id,),
            )
        await blocker.rollback()

        paused = await asyncio.wait_for(pause_task, timeout=2)
        assert paused is not None
        assert paused["status"] == "awaiting_review"
    finally:
        if pause_task is not None and not pause_task.done():
            pause_task.cancel()
            with suppress(asyncio.CancelledError):
                await pause_task
        await blocker.close()
        await pause_conn.close()
        async with setup_conn.cursor() as cur:
            await cur.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    sql.Identifier(schema_name)
                )
            )
        await setup_conn.close()


@pytest.mark.asyncio
async def test_cancel_book_pipeline_queued_is_atomic_and_parent_scoped(
    cleanup_tables,
    db_conn,
    test_db_uri: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_user_id, version_id = await _seed_book_pipeline_parent(db_conn)
    other_parent_user_id, _other_version_id = await _seed_book_pipeline_parent(db_conn)
    monkeypatch.setattr(
        education_textbooks,
        "get_db_connection",
        _test_connection(test_db_uri),
    )

    queued = await education_textbooks.queue_book_pipeline_job(
        parent_user_id=parent_user_id,
        content_version_id=str(version_id),
        processing_profile_sha256="a" * 64,
    )
    assert queued is not None
    generation_job_id = str(queued["generation_job_id"])

    assert (
        await education_textbooks.cancel_book_pipeline_without_run_for_parent(
            parent_user_id=other_parent_user_id,
            generation_job_id=generation_job_id,
        )
        is None
    )
    cancelled = await education_textbooks.cancel_book_pipeline_without_run_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    assert cancelled is not None
    assert cancelled["cancel_mode"] == "cancelled"
    assert cancelled["status"] == "cancelled"

    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT status, latest_attempt_id
            FROM education_generation_jobs
            WHERE generation_job_id = %s
            """,
            (generation_job_id,),
        )
        assert await cur.fetchone() == {
            "status": "cancelled",
            "latest_attempt_id": None,
        }


@pytest.mark.asyncio
async def test_cancel_book_pipeline_preparing_closes_attempt(
    cleanup_tables,
    db_conn,
    test_db_uri: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_user_id, version_id = await _seed_book_pipeline_parent(db_conn)
    monkeypatch.setattr(
        education_textbooks,
        "get_db_connection",
        _test_connection(test_db_uri),
    )

    queued = await education_textbooks.queue_book_pipeline_job(
        parent_user_id=parent_user_id,
        content_version_id=str(version_id),
        processing_profile_sha256="a" * 64,
    )
    assert queued is not None
    generation_job_id = str(queued["generation_job_id"])
    claimed = await education_textbooks.claim_book_pipeline_launch(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    assert claimed is not None
    workspace = await create_workspace(
        user_id=parent_user_id,
        name=f"Cancel workspace {uuid4()}",
        status="running",
        conn=db_conn,
    )
    thread = await create_thread(
        conversation_thread_id=str(uuid4()),
        workspace_id=str(workspace["workspace_id"]),
        current_status="completed",
        msg_type="ptc",
        conn=db_conn,
    )
    attempt = await education_textbooks.claim_generation_job(
        generation_job_id=generation_job_id,
        managed_workspace_id=str(workspace["workspace_id"]),
        managed_thread_id=str(thread["conversation_thread_id"]),
        expected_job_status="preparing",
    )
    assert attempt is not None
    attempt_id = str(attempt["attempt_id"])

    cancelled = await education_textbooks.cancel_book_pipeline_without_run_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    assert cancelled is not None
    assert cancelled["cancel_mode"] == "cancelled"
    assert cancelled["status"] == "cancelled"

    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT status, completed_at
            FROM education_generation_attempts
            WHERE attempt_id = %s AND generation_job_id = %s
            """,
            (attempt_id, generation_job_id),
        )
        attempt_state = await cur.fetchone()
    assert attempt_state is not None
    assert attempt_state["status"] == "cancelled"
    assert attempt_state["completed_at"] is not None


@pytest.mark.asyncio
async def test_cancel_book_pipeline_running_delegates_without_terminal_write(
    cleanup_tables,
    db_conn,
    test_db_uri: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_user_id, version_id = await _seed_book_pipeline_parent(db_conn)
    monkeypatch.setattr(
        education_textbooks,
        "get_db_connection",
        _test_connection(test_db_uri),
    )

    queued = await education_textbooks.queue_book_pipeline_job(
        parent_user_id=parent_user_id,
        content_version_id=str(version_id),
        processing_profile_sha256="a" * 64,
    )
    assert queued is not None
    generation_job_id = str(queued["generation_job_id"])
    await education_textbooks.claim_book_pipeline_launch(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    workspace = await create_workspace(
        user_id=parent_user_id,
        name=f"Running workspace {uuid4()}",
        status="running",
        conn=db_conn,
    )
    thread = await create_thread(
        conversation_thread_id=str(uuid4()),
        workspace_id=str(workspace["workspace_id"]),
        current_status="completed",
        msg_type="ptc",
        conn=db_conn,
    )
    thread_id = str(thread["conversation_thread_id"])
    attempt = await education_textbooks.claim_generation_job(
        generation_job_id=generation_job_id,
        managed_workspace_id=str(workspace["workspace_id"]),
        managed_thread_id=thread_id,
        expected_job_status="preparing",
    )
    assert attempt is not None
    run_id = str(uuid4())
    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO conversation_responses (
                    conversation_response_id, conversation_thread_id,
                    turn_index, status, created_at
                ) VALUES (%s, %s, 0, 'in_progress', NOW())
                """,
                (run_id, thread_id),
            )
    running = await education_textbooks.mark_generation_attempt_running(
        generation_job_id=generation_job_id,
        attempt_id=str(attempt["attempt_id"]),
        root_run_id=run_id,
    )
    assert running is not None

    decision = await education_textbooks.cancel_book_pipeline_without_run_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    assert decision is not None
    assert decision["cancel_mode"] == "running"
    assert str(decision["managed_thread_id"]) == thread_id
    assert str(decision["root_run_id"]) == run_id

    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT status
            FROM education_generation_jobs
            WHERE generation_job_id = %s
            """,
            (generation_job_id,),
        )
        assert (await cur.fetchone())["status"] == "running"


@pytest.mark.asyncio
async def test_textbook_detail_projects_book_pipeline_job_status(
    test_db_uri: str,
    db_conn: psycopg.AsyncConnection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_user_id, version_id = await _seed_book_pipeline_parent(db_conn)
    job_id = uuid4()
    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO education_generation_jobs (
                    generation_job_id, version_id, scope, status,
                    attempt_count, processing_profile_sha256,
                    error_code, error_message, pause_after_chapter_analysis
                ) VALUES (%s, %s, 'book_pipeline', 'failed', 1, %s, %s, %s, FALSE)
                """,
                (
                    job_id,
                    version_id,
                    "b" * 64,
                    "managed_book_pipeline_invalid",
                    "invalid package",
                ),
            )
            await cur.execute(
                """
                SELECT textbook_id
                FROM education_textbook_versions
                WHERE version_id = %s
                """,
                (version_id,),
            )
            textbook_id = (await cur.fetchone())["textbook_id"]

    monkeypatch.setattr(
        education_textbooks,
        "get_db_connection",
        _test_connection(test_db_uri),
    )
    detail = await education_textbooks.get_textbook_for_parent(
        parent_user_id=parent_user_id,
        textbook_id=str(textbook_id),
    )
    library = await education_textbooks.list_textbooks_for_parent(parent_user_id)

    assert detail is not None
    version = detail["versions"][0]
    assert version["processing_job_id"] == str(job_id)
    assert version["processing_job_scope"] == "book_pipeline"
    assert version["processing_job_status"] == "failed"
    assert version["processing_error"] == "invalid package"
    assert library[0]["latest_processing_job_id"] == str(job_id)
    assert library[0]["latest_processing_job_status"] == "failed"
    assert library[0]["latest_processing_error"] == "invalid package"
