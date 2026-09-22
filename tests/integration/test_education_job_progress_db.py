"""Real PostgreSQL contracts for semantic education progress events."""

from __future__ import annotations

from pathlib import Path
import runpy
from uuid import uuid4

import psycopg
import pytest

from migrations import textbook_ddl
from src.server.database.conversation.threads_write import create_thread
from src.server.database import education_textbooks
from src.server.database.education_textbooks import (
    ProgressEventPersistenceOutcome,
)
from src.server.database.workspace import create_workspace


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "migrations"
    / "versions"
    / "080_education_job_progress.py"
)
MIGRATION_081_PATH = (
    Path(__file__).parents[2]
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


class _RollbackMigration(Exception):
    pass


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


def _migration_081_statements(
    monkeypatch: pytest.MonkeyPatch,
    *,
    function_name: str,
) -> list[str]:
    migration = runpy.run_path(str(MIGRATION_081_PATH))
    operations = _RecordingOperations()
    monkeypatch.setattr(textbook_ddl, "op", operations)
    migration[function_name]()
    return operations.bind.statements


async def _seed_job(db_conn: psycopg.AsyncConnection) -> tuple[str, str]:
    parent_user_id = f"progress-parent-{uuid4()}"
    household_id = str(uuid4())
    textbook_id = str(uuid4())
    version_id = str(uuid4())
    generation_job_id = str(uuid4())
    attempt_id = str(uuid4())
    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO users (user_id, name) VALUES (%s, %s)",
                (parent_user_id, "Progress parent"),
            )
            await cur.execute(
                """
                INSERT INTO education_households (
                    household_id, name, model_owner_user_id
                ) VALUES (%s, %s, %s)
                """,
                (household_id, "Progress household", parent_user_id),
            )
            await cur.execute(
                """
                INSERT INTO education_memberships (
                    household_id, user_id, role, display_name
                ) VALUES (%s, %s, 'parent', %s)
                """,
                (household_id, parent_user_id, "Progress parent"),
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
                    "Progress textbook",
                    f"progress-{uuid4().hex}",
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
        workspace = await create_workspace(
            user_id=parent_user_id,
            name=f"Progress workspace {uuid4()}",
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
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO education_generation_jobs (
                    generation_job_id, version_id, scope, status,
                    attempt_count, processing_profile_sha256
                ) VALUES (%s, %s, 'book_pipeline', 'running', 1, %s)
                """,
                (generation_job_id, version_id, "c" * 64),
            )
            await cur.execute(
                """
                INSERT INTO education_generation_attempts (
                    attempt_id, generation_job_id, managed_workspace_id,
                    managed_thread_id, status
                ) VALUES (%s, %s, %s, %s, 'running')
                """,
                (
                    attempt_id,
                    generation_job_id,
                    workspace["workspace_id"],
                    thread["conversation_thread_id"],
                ),
            )
            await cur.execute(
                """
                UPDATE education_generation_jobs
                SET latest_attempt_id = %s
                WHERE generation_job_id = %s
                """,
                (attempt_id, generation_job_id),
            )
    return generation_job_id, attempt_id


@pytest.mark.asyncio
async def test_progress_event_ownership_constraints_and_indexes_are_enforced(
    cleanup_tables,
    db_conn: psycopg.AsyncConnection,
) -> None:
    generation_job_id, attempt_id = await _seed_job(db_conn)
    other_generation_job_id, other_attempt_id = await _seed_job(db_conn)

    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND tablename = 'education_generation_progress_events'
            ORDER BY indexname
            """
        )
        assert {row["indexname"] for row in await cur.fetchall()} == {
            "education_generation_progress_events_pkey",
            "idx_education_generation_progress_job_attempt_sequence",
            "uq_education_generation_progress_attempt_sequence",
        }
        await cur.execute(
            """
            SELECT conname, confdeltype
            FROM pg_constraint
            WHERE conrelid = 'education_generation_progress_events'::regclass
              AND contype = 'f'
            ORDER BY conname
            """
        )
        assert await cur.fetchall() == [
            {
                "conname": "fk_education_generation_progress_attempt_ownership",
                "confdeltype": "c",
            },
            {
                "conname": "fk_education_generation_progress_job",
                "confdeltype": "c",
            },
        ]

    try:
        async with db_conn.transaction():
            async with db_conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO education_generation_progress_events (
                        generation_job_id, attempt_id, sequence, event_key,
                        stage, substage, status, label, detail, node_key,
                        current_value, total_value, metadata
                    ) VALUES (
                        %s, %s, 1, 'chapter:start', 'chapter_analysis',
                        'inventory', 'running', 'Analyze chapters', 'Safe detail',
                        'unit-1', 1, 4, '{"safe":true}'::jsonb
                    )
                    """,
                    (generation_job_id, attempt_id),
                )
    except psycopg.errors.ForeignKeyViolation as exc:
        raise AssertionError("valid progress ownership was rejected") from exc

    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT event_id, sequence, metadata
            FROM education_generation_progress_events
            WHERE attempt_id = %s
            ORDER BY sequence
            """,
            (attempt_id,),
        )
        events = await cur.fetchall()
        assert len(events) == 1
        assert events[0]["metadata"] == {"safe": True}

    try:
        async with db_conn.transaction():
            async with db_conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO education_generation_progress_events (
                        generation_job_id, attempt_id, sequence, event_key,
                        stage, status, label
                    ) VALUES (
                        %s, %s, 1, 'ownership:test', 'chapter_analysis',
                        'running', 'Ownership test'
                    )
                    """,
                    (generation_job_id, other_attempt_id),
                )
    except psycopg.errors.ForeignKeyViolation as exc:
        assert (
            exc.diag.constraint_name
            == "fk_education_generation_progress_attempt_ownership"
        )
    else:
        raise AssertionError("job A with attempt B was accepted")

    assert other_generation_job_id != generation_job_id
    assert other_attempt_id != attempt_id


@pytest.mark.asyncio
async def test_progress_sequence_is_unique_while_event_key_is_append_only(
    cleanup_tables,
    db_conn: psycopg.AsyncConnection,
) -> None:
    generation_job_id, attempt_id = await _seed_job(db_conn)
    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO education_generation_progress_events (
                generation_job_id, attempt_id, sequence, event_key,
                stage, status, label
            ) VALUES (
                %s, %s, 1, 'same-logical-key', 'chapter_analysis',
                'running', 'First attempt'
            )
            """,
            (generation_job_id, attempt_id),
        )
        await cur.execute(
            """
            INSERT INTO education_generation_progress_events (
                generation_job_id, attempt_id, sequence, event_key,
                stage, status, label
            ) VALUES (
                %s, %s, 2, 'same-logical-key', 'chapter_analysis',
                'completed', 'Retried attempt'
            )
            """,
            (generation_job_id, attempt_id),
        )

    try:
        async with db_conn.transaction():
            async with db_conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO education_generation_progress_events (
                        generation_job_id, attempt_id, sequence, event_key,
                        stage, status, label
                    ) VALUES (
                        %s, %s, 2, 'different-key', 'chapter_analysis',
                        'running', 'Duplicate sequence'
                    )
                    """,
                    (generation_job_id, attempt_id),
                )
    except psycopg.errors.UniqueViolation as exc:
        assert (
            exc.diag.constraint_name
            == "uq_education_generation_progress_attempt_sequence"
        )
    else:
        raise AssertionError("attempt sequence uniqueness was not enforced")


@pytest.mark.asyncio
async def test_progress_cascades_from_attempt_and_job(
    cleanup_tables,
    db_conn: psycopg.AsyncConnection,
) -> None:
    generation_job_id, attempt_id = await _seed_job(db_conn)
    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO education_generation_progress_events (
                generation_job_id, attempt_id, sequence, event_key,
                stage, status, label
            ) VALUES (
                %s, %s, 1, 'attempt:cascade', 'chapter_analysis',
                'running', 'Attempt cascade'
            )
            """,
            (generation_job_id, attempt_id),
        )
        await cur.execute(
            "DELETE FROM education_generation_attempts WHERE attempt_id = %s",
            (attempt_id,),
        )
        await cur.execute(
            """
            SELECT COUNT(*) AS count
            FROM education_generation_progress_events
            WHERE attempt_id = %s
            """,
            (attempt_id,),
        )
        assert (await cur.fetchone())["count"] == 0

    generation_job_id, attempt_id = await _seed_job(db_conn)
    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO education_generation_progress_events (
                generation_job_id, attempt_id, sequence, event_key,
                stage, status, label
            ) VALUES (
                %s, %s, 1, 'job:cascade', 'chapter_analysis',
                'running', 'Job cascade'
            )
            """,
            (generation_job_id, attempt_id),
        )

    with pytest.raises(_RollbackMigration):
        async with db_conn.transaction():
            async with db_conn.cursor() as cur:
                await cur.execute(
                    """
                    ALTER TABLE education_generation_attempts
                    DROP CONSTRAINT education_generation_attempts_generation_job_id_fkey
                    """
                )
                await cur.execute(
                    """
                    DELETE FROM education_generation_jobs
                    WHERE generation_job_id = %s
                    """,
                    (generation_job_id,),
                )
                await cur.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM education_generation_progress_events
                    WHERE generation_job_id = %s
                    """,
                    (generation_job_id,),
                )
                assert (await cur.fetchone())["count"] == 0
                raise _RollbackMigration


@pytest.mark.asyncio
async def test_080_downgrade_removes_owned_schema_without_touching_job_tables(
    cleanup_tables,
    db_conn: psycopg.AsyncConnection,
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_db_uri = request.getfixturevalue("test_db_uri")
    generation_job_id, attempt_id = await _seed_job(db_conn)
    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO education_generation_progress_events (
                generation_job_id, attempt_id, sequence, event_key,
                stage, status, label
            ) VALUES (
                %s, %s, 1, 'downgrade:test', 'chapter_analysis',
                'running', 'Downgrade test'
            )
            """,
            (generation_job_id, attempt_id),
        )
        await cur.execute(
            """
            SELECT COUNT(*) AS count
            FROM pg_constraint
            WHERE conname = 'uq_education_generation_attempts_job_attempt'
            """
        )
        assert (await cur.fetchone())["count"] == 1

    statements = _migration_statements(monkeypatch, function_name="downgrade")
    connection = await psycopg.AsyncConnection.connect(
        test_db_uri,
        autocommit=False,
        row_factory=psycopg.rows.dict_row,
    )
    try:
        with pytest.raises(_RollbackMigration):
            async with connection.transaction():
                for statement in statements:
                    await connection.execute(statement)
                async with connection.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT to_regclass(
                            'education_generation_progress_events'
                        ) AS progress_table,
                        to_regclass('education_generation_jobs') AS jobs_table,
                        to_regclass('education_generation_attempts') AS attempts_table
                        """
                    )
                    tables = await cur.fetchone()
                    assert tables == {
                        "progress_table": None,
                        "jobs_table": "education_generation_jobs",
                        "attempts_table": "education_generation_attempts",
                    }
                    await cur.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM education_generation_jobs
                        WHERE generation_job_id = %s
                        """,
                        (generation_job_id,),
                    )
                    assert (await cur.fetchone())["count"] == 1
                    await cur.execute(
                        """
                        SELECT COUNT(*) AS count
                        FROM pg_constraint
                        WHERE conname =
                            'uq_education_generation_attempts_job_attempt'
                        """
                    )
                    assert (await cur.fetchone())["count"] == 0
                raise _RollbackMigration
    finally:
        await connection.close()

    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT to_regclass('education_generation_progress_events') AS progress_table
            """
        )
        assert (
            (await cur.fetchone())["progress_table"]
            == "education_generation_progress_events"
        )
        await cur.execute(
            """
            SELECT COUNT(*) AS count
            FROM pg_constraint
            WHERE conname = 'uq_education_generation_attempts_job_attempt'
            """
        )
        assert (await cur.fetchone())["count"] == 1


@pytest.mark.asyncio
async def test_progress_writer_is_idempotent_and_rejects_wrong_run_ownership(
    cleanup_tables,
    db_conn: psycopg.AsyncConnection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generation_job_id, attempt_id = await _seed_job(db_conn)
    other_generation_job_id, other_attempt_id = await _seed_job(db_conn)

    class _ConnectionContext:
        async def __aenter__(self):
            return db_conn

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(
        education_textbooks,
        "get_db_connection",
        lambda: _ConnectionContext(),
    )

    root_run_id = None
    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT attempts.root_run_id
            FROM education_generation_attempts AS attempts
            WHERE attempts.attempt_id = %s
            """,
            (attempt_id,),
        )
        root_run_id = (await cur.fetchone())["root_run_id"]

    running_event = {
        "event_key": "chapter:start",
        "stage": "chapter_analysis",
        "status": "running",
        "label": "Analyze",
    }
    first = await education_textbooks.persist_generation_progress_event(
        generation_job_id=generation_job_id,
        attempt_id=attempt_id,
        run_id=root_run_id,
        sequence=1,
        event=running_event,
    )
    duplicate = await education_textbooks.persist_generation_progress_event(
        generation_job_id=generation_job_id,
        attempt_id=attempt_id,
        run_id=root_run_id,
        sequence=1,
        event=running_event,
    )
    same_key_completed = await education_textbooks.persist_generation_progress_event(
        generation_job_id=generation_job_id,
        attempt_id=attempt_id,
        run_id=root_run_id,
        sequence=2,
        event={**running_event, "status": "completed", "label": "Analyzed"},
    )
    wrong_run = await education_textbooks.persist_generation_progress_event(
        generation_job_id=generation_job_id,
        attempt_id=attempt_id,
        run_id=f"00000000-0000-0000-0000-{uuid4().hex[:12]}",
        sequence=3,
        event={**running_event, "event_key": "wrong:run"},
    )
    cross_attempt = await education_textbooks.persist_generation_progress_event(
        generation_job_id=other_generation_job_id,
        attempt_id=attempt_id,
        run_id=root_run_id,
        sequence=4,
        event={**running_event, "event_key": "cross:attempt"},
    )
    sequence_mismatch = await education_textbooks.persist_generation_progress_event(
        generation_job_id=generation_job_id,
        attempt_id=attempt_id,
        run_id=root_run_id,
        sequence=1,
        event={**running_event, "status": "completed", "label": "Different"},
    )

    assert first.outcome is ProgressEventPersistenceOutcome.INSERTED
    assert duplicate.outcome is ProgressEventPersistenceOutcome.ALREADY_EXISTS
    assert duplicate.event["event_key"] == "chapter:start"
    assert same_key_completed.outcome is ProgressEventPersistenceOutcome.INSERTED
    assert wrong_run.outcome is ProgressEventPersistenceOutcome.REJECTED
    assert cross_attempt.outcome is ProgressEventPersistenceOutcome.REJECTED
    assert sequence_mismatch.outcome is ProgressEventPersistenceOutcome.REJECTED

    rows = await education_textbooks.list_generation_progress_events(
        generation_job_id=generation_job_id,
        attempt_id=attempt_id,
    )
    assert [(row["sequence"], row["event_key"], row["status"]) for row in rows] == [
        (1, "chapter:start", "running"),
        (2, "chapter:start", "completed"),
    ]
    assert other_attempt_id != attempt_id


@pytest.mark.asyncio
async def test_checkpoint_bundle_prefix_is_private_and_database_validated(
    cleanup_tables,
    db_conn: psycopg.AsyncConnection,
) -> None:
    generation_job_id, _attempt_id = await _seed_job(db_conn)

    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT is_nullable, data_type
            FROM information_schema.columns
            WHERE table_name = 'education_generation_jobs'
              AND column_name = 'checkpoint_bundle_prefix'
            """
        )
        assert await cur.fetchone() == {
            "is_nullable": "YES",
            "data_type": "text",
        }
        await cur.execute(
            """
            SELECT COUNT(*) AS count
            FROM pg_constraint
            WHERE conname =
                'ck_education_generation_jobs_checkpoint_prefix'
            """
        )
        assert (await cur.fetchone())["count"] == 1

    valid_prefix = (
        "education/household/textbook/v1/book-pipeline-checkpoints/"
        "4d0112f8-0e00-4f1f-990a-4bc1b1cc20f3/"
        "6f3f2de2-5c58-4bc2-84bc-95e97acd37f6"
    )
    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE education_generation_jobs
                SET checkpoint_bundle_prefix = %s
                WHERE generation_job_id = %s
                """,
                (valid_prefix, generation_job_id),
            )
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                SELECT checkpoint_bundle_prefix
                FROM education_generation_jobs
                WHERE generation_job_id = %s
                """,
                (generation_job_id,),
            )
            assert (await cur.fetchone())["checkpoint_bundle_prefix"] == valid_prefix

    with pytest.raises(psycopg.errors.CheckViolation):
        async with db_conn.transaction():
            async with db_conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE education_generation_jobs
                    SET checkpoint_bundle_prefix = %s
                    WHERE generation_job_id = %s
                    """,
                    ("/tmp/private", generation_job_id),
                )

    with pytest.raises(psycopg.errors.CheckViolation):
        async with db_conn.transaction():
            async with db_conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE education_generation_jobs
                    SET status = 'awaiting_review',
                        pause_after_chapter_analysis = TRUE,
                        checkpoint_bundle_prefix = NULL
                    WHERE generation_job_id = %s
                    """,
                    (generation_job_id,),
                )

    with pytest.raises(psycopg.errors.CheckViolation):
        async with db_conn.transaction():
            async with db_conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE education_generation_jobs
                    SET checkpoint_bundle_prefix = ''
                    WHERE generation_job_id = %s
                    """,
                    (generation_job_id,),
                )


@pytest.mark.asyncio
async def test_081_downgrade_fails_closed_when_checkpoint_data_exists(
    cleanup_tables,
    db_conn: psycopg.AsyncConnection,
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_db_uri = request.getfixturevalue("test_db_uri")
    generation_job_id, _attempt_id = await _seed_job(db_conn)
    checkpoint_prefix = (
        "education/household/textbook/v1/book-pipeline-checkpoints/"
        "4d0112f8-0e00-4f1f-990a-4bc1b1cc20f3/"
        "6f3f2de2-5c58-4bc2-84bc-95e97acd37f6"
    )
    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE education_generation_jobs
                SET checkpoint_bundle_prefix = %s
                WHERE generation_job_id = %s
                """,
                (checkpoint_prefix, generation_job_id),
            )

    statements = _migration_081_statements(
        monkeypatch,
        function_name="downgrade",
    )
    connection = await psycopg.AsyncConnection.connect(
        test_db_uri,
        autocommit=False,
        row_factory=psycopg.rows.dict_row,
    )
    try:
        with pytest.raises(psycopg.errors.RaiseException, match="checkpoint data"):
            async with connection.transaction():
                for statement in statements:
                    await connection.execute(statement)
    finally:
        await connection.close()

    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT checkpoint_bundle_prefix
            FROM education_generation_jobs
            WHERE generation_job_id = %s
            """,
            (generation_job_id,),
        )
        assert (await cur.fetchone())["checkpoint_bundle_prefix"] == checkpoint_prefix
        await cur.execute(
            """
            SELECT COUNT(*) AS count
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'education_generation_jobs'
              AND column_name = 'checkpoint_bundle_prefix'
            """
        )
        assert (await cur.fetchone())["count"] == 1


@pytest.mark.asyncio
async def test_081_downgrade_succeeds_without_checkpoint_data(
    cleanup_tables,
    db_conn: psycopg.AsyncConnection,
    request: pytest.FixtureRequest,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    test_db_uri = request.getfixturevalue("test_db_uri")
    await _seed_job(db_conn)
    statements = _migration_081_statements(
        monkeypatch,
        function_name="downgrade",
    )
    connection = await psycopg.AsyncConnection.connect(
        test_db_uri,
        autocommit=False,
        row_factory=psycopg.rows.dict_row,
    )
    try:
        async with connection.transaction():
            for statement in statements:
                await connection.execute(statement)
            async with connection.cursor() as cur:
                await cur.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = 'education_generation_jobs'
                      AND column_name = 'checkpoint_bundle_prefix'
                    """
                )
                assert (await cur.fetchone())["count"] == 0
            raise _RollbackMigration
    except _RollbackMigration:
        pass
    finally:
        await connection.close()

    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT COUNT(*) AS count
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'education_generation_jobs'
              AND column_name = 'checkpoint_bundle_prefix'
            """
        )
        assert (await cur.fetchone())["count"] == 1
