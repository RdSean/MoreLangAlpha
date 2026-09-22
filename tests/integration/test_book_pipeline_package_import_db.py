"""Real PostgreSQL contracts for generic book-package import."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import runpy
from unittest.mock import AsyncMock
from uuid import uuid4

import psycopg
import pytest

from migrations import textbook_ddl
from src.server.database import education_textbooks
from src.server.database.conversation.threads_write import create_thread
from src.server.database.workspace import create_workspace
from src.server.services import education_book_pipeline_jobs


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "migrations"
    / "versions"
    / "079_book_pipeline_package_import.py"
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


def _test_connection(test_db_uri: str):
    @asynccontextmanager
    async def _connect():
        async with await psycopg.AsyncConnection.connect(
            test_db_uri,
            autocommit=True,
            row_factory=psycopg.rows.dict_row,
        ) as conn:
            yield conn

    return _connect


def _package() -> dict:
    return {
        "format": "langalpha-book-package/v1",
        "source_revision": "integration-revision-" + ("x" * 60),
        "content_nodes": [
            {
                "node_key": "unit-1",
                "parent_key": None,
                "node_type": "unit",
                "position": 1,
                "slug": "unit-1",
                "title": "Unit 1",
                "summary": "",
                "source_refs": [],
                "metadata": {},
            },
            {
                "node_key": "reading-a",
                "parent_key": "unit-1",
                "node_type": "reading",
                "position": 1,
                "slug": "reading-a",
                "title": "Reading A",
                "summary": "",
                "source_refs": [],
                "metadata": {},
            },
        ],
        "knowledge_points": [
            {
                "candidate_key": "reading-a-kp-1",
                "node_key": "reading-a",
                "point_type": "concept",
                "title": "Candidate",
                "summary": "",
                "source_refs": [],
                "confidence": 0.8,
                "metadata": {},
            }
        ],
        "assets": [
            {
                "node_key": "reading-a",
                "kind": "knowledge",
                "path": "outputs/reading-a.md",
                "content_sha256": "c" * 64,
                "size_bytes": 10,
                "metadata": {},
            }
        ],
    }


async def _seed_running_job(
    db_conn: psycopg.AsyncConnection,
) -> tuple[str, str, str, str]:
    parent_user_id = f"parent-{uuid4()}"
    household_id = str(uuid4())
    textbook_id = str(uuid4())
    version_id = str(uuid4())
    generation_job_id = str(uuid4())
    attempt_id = str(uuid4())
    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO users (user_id, name) VALUES (%s, %s)",
                (parent_user_id, "Package parent"),
            )
            await cur.execute(
                """
                INSERT INTO education_households (
                    household_id, name, model_owner_user_id
                ) VALUES (%s, %s, %s)
                """,
                (household_id, "Package household", parent_user_id),
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
                    "Package textbook",
                    f"package-{uuid4().hex}",
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
            name="Package workspace",
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
                (generation_job_id, version_id, "a" * 64),
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
    return parent_user_id, version_id, generation_job_id, attempt_id


async def _seed_queue_parent(
    db_conn: psycopg.AsyncConnection,
) -> tuple[str, str]:
    parent_user_id = f"parent-{uuid4()}"
    household_id = str(uuid4())
    textbook_id = str(uuid4())
    version_id = str(uuid4())
    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO users (user_id, name) VALUES (%s, %s)",
                (parent_user_id, "Queue parent"),
            )
            await cur.execute(
                """
                INSERT INTO education_households (
                    household_id, name, model_owner_user_id
                ) VALUES (%s, %s, %s)
                """,
                (household_id, "Queue household", parent_user_id),
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
                    "Queue textbook",
                    f"queue-{uuid4().hex}",
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


async def _add_running_job(
    db_conn: psycopg.AsyncConnection,
    *,
    parent_user_id: str,
    version_id: str,
) -> tuple[str, str]:
    generation_job_id = str(uuid4())
    attempt_id = str(uuid4())
    async with db_conn.transaction():
        workspace = await create_workspace(
            user_id=parent_user_id,
            name=f"Extra workspace {uuid4()}",
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
                (generation_job_id, version_id, "b" * 64),
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


async def _import_package(
    parent_user_id: str,
    generation_job_id: str,
    attempt_id: str,
    *,
    package: dict | None = None,
    prefix_suffix: str = "one",
) -> dict:
    package = package or _package()
    return await education_textbooks.complete_book_pipeline_import(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
        attempt_id=attempt_id,
        package=package,
        bundle_prefix=(
            f"education/household/textbook/v1/book-packages/{prefix_suffix}"
        ),
        bundle_manifest={"format": "langalpha-book-package-bundle/v1"},
        asset_content_keys={
            str(asset["path"]): (
                "education/household/textbook/v1/book-packages/"
                f"{prefix_suffix}/{asset['path'].removeprefix('outputs/')}"
            )
            for asset in package["assets"]
        },
    )


@pytest.mark.asyncio
async def test_package_import_persists_topology_candidates_and_completion(
    cleanup_tables,
    db_conn,
    test_db_uri,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_user_id, version_id, generation_job_id, attempt_id = await _seed_running_job(
        db_conn
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_db_connection",
        _test_connection(test_db_uri),
    )

    result = await _import_package(
        parent_user_id,
        generation_job_id,
        attempt_id,
    )

    assert result is not None
    assert result["node_count"] == 2
    assert result["knowledge_point_count"] == 1
    assert result["asset_count"] == 1
    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT node_id, node_key, parent_node_id
            FROM education_content_nodes
            WHERE structure_id = %s
            ORDER BY position
            """,
            (result["structure_id"],),
        )
        nodes = await cur.fetchall()
        by_key = {row["node_key"]: row for row in nodes}
        assert by_key["unit-1"]["parent_node_id"] is None
        assert by_key["reading-a"]["parent_node_id"] == by_key["unit-1"]["node_id"]
        await cur.execute(
            """
            SELECT content_structure_id, content_node_id, candidate_key,
                   origin, candidate_status, unit_id
            FROM education_structure_knowledge_points
            WHERE content_node_id IS NOT NULL
            """
        )
        candidate = await cur.fetchone()
        assert candidate["content_structure_id"] == result["structure_id"]
        assert candidate["content_node_id"] is not None
        assert candidate["candidate_key"] == "reading-a-kp-1"
        assert candidate["origin"] == "generated"
        assert candidate["candidate_status"] == "pending"
        assert candidate["unit_id"] is None
        await cur.execute(
            """
            SELECT status, structure_id
            FROM education_generation_jobs
            WHERE generation_job_id = %s
            """,
            (generation_job_id,),
        )
        job = await cur.fetchone()
        assert job == {
            "status": "completed",
            "structure_id": result["structure_id"],
        }
        await cur.execute(
            "SELECT COUNT(*) AS count FROM education_textbook_structures WHERE version_id = %s",
            (version_id,),
        )
        assert (await cur.fetchone())["count"] == 1


@pytest.mark.asyncio
async def test_package_import_rolls_back_all_rows_on_asset_conflict(
    cleanup_tables,
    db_conn,
    test_db_uri,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent_user_id, version_id, generation_job_id, attempt_id = await _seed_running_job(
        db_conn
    )
    monkeypatch.setattr(
        education_textbooks,
        "get_db_connection",
        _test_connection(test_db_uri),
    )
    package = _package()
    package["assets"].append(dict(package["assets"][0]))

    with pytest.raises(psycopg.errors.UniqueViolation):
        await _import_package(
            parent_user_id,
            generation_job_id,
            attempt_id,
            package=package,
        )

    async with db_conn.cursor() as cur:
        await cur.execute(
            "SELECT COUNT(*) AS count FROM education_textbook_structures WHERE version_id = %s",
            (version_id,),
        )
        assert (await cur.fetchone())["count"] == 0
        await cur.execute(
            """
            SELECT status FROM education_generation_jobs
            WHERE generation_job_id = %s
            """,
            (generation_job_id,),
        )
        assert (await cur.fetchone())["status"] == "running"


@pytest.mark.asyncio
async def test_package_import_candidate_constraints_are_enforced(
    cleanup_tables,
    db_conn,
    test_db_uri,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        parent_user_id,
        version_id,
        generation_job_id,
        attempt_id,
    ) = await _seed_running_job(db_conn)
    monkeypatch.setattr(
        education_textbooks,
        "get_db_connection",
        _test_connection(test_db_uri),
    )
    result = await _import_package(
        parent_user_id,
        generation_job_id,
        attempt_id,
    )
    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT node_id
            FROM education_content_nodes
            WHERE structure_id = %s AND node_key = 'reading-a'
            """,
            (result["structure_id"],),
        )
        node_id = (await cur.fetchone())["node_id"]
        second_structure_id = str(uuid4())
        second_node_id = str(uuid4())
        await cur.execute(
            """
            INSERT INTO education_textbook_structures (
                structure_id, version_id, sequence, status, schema_version,
                processing_profile_sha256, input_manifest_sha256,
                source_revision, created_by_user_id
            ) VALUES (
                %s, %s, 2, 'queued', 'langalpha-book-content-tree/v1',
                %s, %s, %s, %s
            )
            """,
            (
                second_structure_id,
                version_id,
                "d" * 64,
                "e" * 64,
                "second",
                parent_user_id,
            ),
        )
        await cur.execute(
            """
            INSERT INTO education_content_nodes (
                node_id, structure_id, parent_node_id, node_key, node_type,
                position, slug, title, summary, source_refs, metadata
            ) VALUES (
                %s, %s, NULL, 'second-unit', 'unit',
                1, 'second-unit', 'Second unit', '', '[]', '{}'
            )
            """,
            (second_node_id, second_structure_id),
        )

        with pytest.raises(psycopg.errors.CheckViolation):
            await cur.execute(
                """
                INSERT INTO education_structure_knowledge_points (
                    knowledge_point_id, unit_id, content_structure_id,
                    content_node_id, candidate_key, point_type, origin,
                    candidate_status,
                    position, slug, title, summary, source_refs, confidence,
                    status
                ) VALUES (
                    %s, NULL, NULL, NULL, %s, 'concept', 'generated',
                    'pending', 2, %s, 'Invalid', '', '[]', 0.5, 'review'
                )
                """,
                (str(uuid4()), "invalid-unbound", "invalid-unbound"),
            )
        with pytest.raises(psycopg.errors.UniqueViolation):
            await cur.execute(
                """
                INSERT INTO education_structure_knowledge_points (
                    knowledge_point_id, unit_id, content_structure_id,
                    content_node_id, candidate_key, point_type, origin,
                    candidate_status,
                    position, slug, title, summary, source_refs, confidence,
                    status
                ) VALUES (
                    %s, NULL, %s, %s, 'reading-a-kp-1', 'concept',
                    'generated', 'pending', 2, %s, 'Duplicate', '', '[]',
                    0.5, 'review'
                )
                """,
                (
                    str(uuid4()),
                    result["structure_id"],
                    node_id,
                    "duplicate-candidate",
                ),
            )
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            await cur.execute(
                """
                INSERT INTO education_structure_knowledge_points (
                    knowledge_point_id, unit_id, content_structure_id,
                    content_node_id, candidate_key, point_type, origin,
                    candidate_status, position, slug, title, summary,
                    source_refs, confidence, status
                ) VALUES (
                    %s, NULL, %s, %s, 'cross-structure', 'concept',
                    'generated', 'pending', 3, %s, 'Cross', '', '[]',
                    0.5, 'review'
                )
                """,
                (
                    str(uuid4()),
                    result["structure_id"],
                    second_node_id,
                    "cross-structure",
                ),
            )


@pytest.mark.asyncio
async def test_package_import_serializes_sequence_allocation(
    cleanup_tables,
    test_db_pool,
    patched_get_db_connection,
) -> None:
    async with test_db_pool.connection() as seed_conn:
        parent_user_id, version_id, first_job_id, first_attempt_id = (
            await _seed_running_job(seed_conn)
        )
        second_job_id, second_attempt_id = await _add_running_job(
            seed_conn,
            parent_user_id=parent_user_id,
            version_id=version_id,
        )

    first, second = await asyncio.gather(
        _import_package(
            parent_user_id,
            first_job_id,
            first_attempt_id,
            prefix_suffix="first",
        ),
        _import_package(
            parent_user_id,
            second_job_id,
            second_attempt_id,
            prefix_suffix="second",
        ),
    )

    assert {first["sequence"], second["sequence"]} == {1, 2}


@pytest.mark.asyncio
async def test_package_import_completes_current_attempt_not_old_completed_attempt(
    cleanup_tables,
    test_db_pool,
    patched_get_db_connection,
) -> None:
    async with test_db_pool.connection() as seed_conn:
        parent_user_id, _version_id, generation_job_id, old_attempt_id = (
            await _seed_running_job(seed_conn)
        )
        await seed_conn.execute(
            """
            UPDATE education_generation_attempts
            SET status = 'completed', completed_at = NOW()
            WHERE attempt_id = %s
            """,
            (old_attempt_id,),
        )
        workspace = await create_workspace(
            user_id=parent_user_id,
            name=f"Retry workspace {uuid4()}",
            status="running",
            conn=seed_conn,
        )
        thread = await create_thread(
            conversation_thread_id=str(uuid4()),
            workspace_id=str(workspace["workspace_id"]),
            current_status="completed",
            msg_type="ptc",
            conn=seed_conn,
        )
        new_attempt_id = str(uuid4())
        await seed_conn.execute(
            """
            INSERT INTO education_generation_attempts (
                attempt_id, generation_job_id, previous_attempt_id,
                managed_workspace_id, managed_thread_id, status
            ) VALUES (%s, %s, %s, %s, %s, 'running')
            """,
            (
                new_attempt_id,
                generation_job_id,
                old_attempt_id,
                workspace["workspace_id"],
                thread["conversation_thread_id"],
            ),
        )
        await seed_conn.execute(
            """
            UPDATE education_generation_jobs
            SET latest_attempt_id = %s, status = 'running'
            WHERE generation_job_id = %s
            """,
            (new_attempt_id, generation_job_id),
        )

    result = await _import_package(
        parent_user_id,
        generation_job_id,
        new_attempt_id,
    )

    assert result["job_status"] == "completed"
    async with test_db_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT attempt_id, status
                FROM education_generation_attempts
                WHERE generation_job_id = %s
                ORDER BY started_at
                """,
                (generation_job_id,),
            )
            attempts = {
                str(row["attempt_id"]): row["status"]
                for row in await cur.fetchall()
            }
    assert attempts == {
        old_attempt_id: "completed",
        new_attempt_id: "completed",
    }


@pytest.mark.asyncio
async def test_queue_and_launch_has_one_winner_and_reuses_same_job(
    cleanup_tables,
    test_db_pool,
    patched_get_db_connection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with test_db_pool.connection() as seed_conn:
        parent_user_id, version_id = await _seed_queue_parent(seed_conn)

    resource_calls = {"workspace": 0, "thread": 0, "executor": 0}
    original_workspace = education_book_pipeline_jobs._create_book_pipeline_workspace
    original_thread = education_book_pipeline_jobs._create_book_pipeline_thread

    async def counted_workspace(**kwargs):
        resource_calls["workspace"] += 1
        return await original_workspace(**kwargs)

    async def counted_thread(**kwargs):
        resource_calls["thread"] += 1
        return await original_thread(**kwargs)

    session = type("Session", (), {"sandbox": object()})()
    graph = object()

    class FakeWorkspaceManager:
        async def provision_managed_textbook_session(self, **_kwargs):
            return session

    class FakeRunCoordinator:
        async def start_run(self, **kwargs):
            async with patched_get_db_connection() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        INSERT INTO conversation_responses (
                            conversation_response_id, conversation_thread_id,
                            turn_index, status, created_at
                        ) VALUES (%s, %s, 1, 'in_progress', NOW())
                        """,
                        (kwargs["run_id"], kwargs["thread_id"]),
                    )
            return type(
                "RunHandle",
                (),
                {
                    "run_id": kwargs["run_id"],
                    "turn_index": 1,
                    "guard": object(),
                    "checkpointer": object(),
                },
            )()

    class FakeExecutor:
        async def start_run(self, **_kwargs):
            resource_calls["executor"] += 1

    class FakeRunSSEProducer:
        def __init__(self, **_kwargs):
            pass

        async def stream_workflow(self, **_kwargs):
            if False:
                yield "unused"

    async def fake_build_graph(**_kwargs):
        return graph, {"messages": []}, {"configurable": {}}

    async def fake_resolve_config(**_kwargs):
        return object()

    async def fake_get_input(**_kwargs):
        return {"sources": [{"source_id": "source-1", "markdown": "# Unit\n"}]}

    async def fake_hydrate(frozen):
        return frozen

    async def fake_stage_skills(*_args, **_kwargs):
        return None

    async def fake_stage_inputs(*_args, **_kwargs):
        return None

    def fake_recursion_limit():
        return 50

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "_create_book_pipeline_workspace",
        counted_workspace,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "_create_book_pipeline_thread",
        counted_thread,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "resolve_managed_education_agent_config",
        fake_resolve_config,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs.WorkspaceManager,
        "get_instance",
        classmethod(lambda cls: FakeWorkspaceManager()),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_teaching_input_for_parent",
        fake_get_input,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "hydrate_source_asset_manifests",
        fake_hydrate,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "stage_managed_teaching_skills",
        fake_stage_skills,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "stage_teaching_inputs",
        fake_stage_inputs,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "build_managed_education_graph",
        fake_build_graph,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs.RunCoordinator,
        "get_instance",
        classmethod(lambda cls: FakeRunCoordinator()),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs.LocalRunExecutor,
        "get_instance",
        classmethod(lambda cls: FakeExecutor()),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "RunSSEProducer",
        FakeRunSSEProducer,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_ptc_recursion_limit",
        fake_recursion_limit,
    )

    first, second = await asyncio.gather(
        education_book_pipeline_jobs.queue_and_launch_book_pipeline_for_parent(
            parent_user_id=parent_user_id,
            content_version_id=version_id,
        ),
        education_book_pipeline_jobs.queue_and_launch_book_pipeline_for_parent(
            parent_user_id=parent_user_id,
            content_version_id=version_id,
        ),
    )

    assert first["generation_job_id"] == second["generation_job_id"]
    assert {first["status"], second["status"]} <= {"preparing", "running"}
    assert "running" in {first["status"], second["status"]}
    assert {first["reused_existing_job"], second["reused_existing_job"]} == {
        False,
        True,
    }
    assert resource_calls == {"workspace": 1, "thread": 1, "executor": 1}
    async with test_db_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT COUNT(*) AS attempts
                FROM education_generation_attempts
                WHERE generation_job_id = %s
                """,
                (first["generation_job_id"],),
            )
            assert (await cur.fetchone())["attempts"] == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_stage", ["read", "hydrate"])
async def test_preparing_failure_settles_attempt_and_allows_new_job(
    cleanup_tables,
    test_db_pool,
    patched_get_db_connection,
    monkeypatch: pytest.MonkeyPatch,
    failed_stage: str,
) -> None:
    async with test_db_pool.connection() as seed_conn:
        parent_user_id, version_id = await _seed_queue_parent(seed_conn)

    session = type("Session", (), {"sandbox": object()})()

    class FakeWorkspaceManager:
        async def provision_managed_textbook_session(self, **_kwargs):
            return session

    async def fake_get_input(**_kwargs):
        if failed_stage == "read":
            raise RuntimeError("read failed")
        return {"sources": [{"source_id": "source-1", "markdown": "# Unit\n"}]}

    async def fake_hydrate(_frozen):
        raise RuntimeError("hydrate failed")

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "resolve_managed_education_agent_config",
        AsyncMock(return_value=object()),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs.WorkspaceManager,
        "get_instance",
        classmethod(lambda cls: FakeWorkspaceManager()),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_teaching_input_for_parent",
        fake_get_input,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "hydrate_source_asset_manifests",
        fake_hydrate,
    )

    queued = await education_textbooks.queue_book_pipeline_job(
        parent_user_id=parent_user_id,
        content_version_id=version_id,
        processing_profile_sha256="a" * 64,
    )
    assert queued is not None
    with pytest.raises(RuntimeError, match=failed_stage):
        await education_book_pipeline_jobs.launch_book_pipeline_generation(
            parent_user_id=parent_user_id,
            generation_job_id=str(queued["generation_job_id"]),
        )

    async with test_db_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT jobs.status AS job_status,
                       attempts.status AS attempt_status
                FROM education_generation_jobs AS jobs
                JOIN education_generation_attempts AS attempts
                  ON attempts.attempt_id = jobs.latest_attempt_id
                WHERE jobs.generation_job_id = %s
                """,
                (queued["generation_job_id"],),
            )
            assert await cur.fetchone() == {
                "job_status": "failed",
                "attempt_status": "failed",
            }

    replacement = await education_textbooks.queue_book_pipeline_job(
        parent_user_id=parent_user_id,
        content_version_id=version_id,
        processing_profile_sha256="b" * 64,
    )
    assert replacement is not None
    assert replacement["generation_job_id"] != queued["generation_job_id"]
    assert replacement["status"] == "queued"


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_stage", ["workspace", "thread", "attempt"])
async def test_pre_attempt_launch_failure_closes_claim_and_allows_new_job(
    cleanup_tables,
    test_db_pool,
    patched_get_db_connection,
    monkeypatch: pytest.MonkeyPatch,
    failed_stage: str,
) -> None:
    async with test_db_pool.connection() as seed_conn:
        parent_user_id, version_id = await _seed_queue_parent(seed_conn)

    original_workspace = education_book_pipeline_jobs._create_book_pipeline_workspace
    original_thread = education_book_pipeline_jobs._create_book_pipeline_thread

    async def workspace(**kwargs):
        if failed_stage == "workspace":
            raise RuntimeError("workspace failed")
        return await original_workspace(**kwargs)

    async def thread(**kwargs):
        if failed_stage == "thread":
            raise RuntimeError("thread failed")
        return await original_thread(**kwargs)

    async def claim_attempt(**_kwargs):
        if failed_stage == "attempt":
            return None
        raise AssertionError("runtime must not proceed past resource creation")

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "_create_book_pipeline_workspace",
        workspace,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "_create_book_pipeline_thread",
        thread,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "claim_generation_job",
        claim_attempt,
    )

    queued = await education_textbooks.queue_book_pipeline_job(
        parent_user_id=parent_user_id,
        content_version_id=version_id,
        processing_profile_sha256="a" * 64,
    )
    assert queued is not None
    with pytest.raises((RuntimeError, education_book_pipeline_jobs.TextbookTransitionError)):
        await education_book_pipeline_jobs.launch_book_pipeline_generation(
            parent_user_id=parent_user_id,
            generation_job_id=str(queued["generation_job_id"]),
        )

    async with test_db_pool.connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT status, error_code, latest_attempt_id
                FROM education_generation_jobs
                WHERE generation_job_id = %s
                """,
                (queued["generation_job_id"],),
            )
            failed = await cur.fetchone()
            assert failed["status"] == "failed"
            assert failed["error_code"] == "managed_book_pipeline_start_failed"
            assert failed["latest_attempt_id"] is None
            await cur.execute(
                """
                SELECT COUNT(*) AS active
                FROM education_generation_jobs
                WHERE version_id = %s
                  AND scope = 'book_pipeline'
                  AND status IN (
                      'queued', 'preparing', 'running', 'validating',
                      'awaiting_review'
                  )
                """,
                (version_id,),
            )
            assert (await cur.fetchone())["active"] == 0

    replacement = await education_textbooks.queue_book_pipeline_job(
        parent_user_id=parent_user_id,
        content_version_id=version_id,
        processing_profile_sha256="b" * 64,
    )
    assert replacement is not None
    assert replacement["generation_job_id"] != queued["generation_job_id"]
    assert replacement["status"] == "queued"


@pytest.mark.asyncio
async def test_079_downgrade_fails_closed_while_package_data_exists(
    cleanup_tables,
    db_conn,
    test_db_uri,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        parent_user_id,
        _version_id,
        generation_job_id,
        attempt_id,
    ) = await _seed_running_job(db_conn)
    monkeypatch.setattr(
        education_textbooks,
        "get_db_connection",
        _test_connection(test_db_uri),
    )
    result = await _import_package(
        parent_user_id,
        generation_job_id,
        attempt_id,
    )
    migration = runpy.run_path(str(MIGRATION_PATH))
    operations = _RecordingOperations()
    monkeypatch.setattr(textbook_ddl, "op", operations)
    migration["downgrade"]()

    with pytest.raises(psycopg.errors.RaiseException, match="cannot downgrade 079"):
        async with db_conn.transaction():
            async with db_conn.cursor() as cur:
                await cur.execute(operations.bind.statements[0])

    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT COUNT(*) AS count
            FROM education_content_nodes
            WHERE structure_id = %s
            """,
            (result["structure_id"],),
        )
        assert (await cur.fetchone())["count"] == 2


@pytest.mark.asyncio
async def test_079_downgrade_succeeds_without_generic_package_data(
    cleanup_tables,
    test_db_uri: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    migration = runpy.run_path(str(MIGRATION_PATH))
    operations = _RecordingOperations()
    monkeypatch.setattr(textbook_ddl, "op", operations)
    migration["downgrade"]()

    conn = await psycopg.AsyncConnection.connect(
        test_db_uri,
        autocommit=False,
        row_factory=psycopg.rows.dict_row,
    )
    try:
        with pytest.raises(_RollbackMigration):
            async with conn.transaction():
                for statement in operations.bind.statements:
                    await conn.execute(statement)
                async with conn.cursor() as cur:
                    await cur.execute(
                        """
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = current_schema()
                          AND table_name = 'education_structure_knowledge_points'
                          AND column_name = 'content_structure_id'
                        """
                    )
                    assert await cur.fetchone() is None
                raise _RollbackMigration

        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = 'education_structure_knowledge_points'
                  AND column_name = 'content_structure_id'
                """
            )
            assert (await cur.fetchone())["column_name"] == "content_structure_id"
    finally:
        await conn.close()
