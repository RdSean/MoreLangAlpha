"""PostgreSQL contracts for the more-to-skills textbook model."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import psycopg
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
import pytest
from sqlalchemy.engine import URL

from src.server.services.education_book_structure import (
    MoreToSkillsIdentity,
    ParsedBookStructure,
    get_projected_current_structure,
)


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _seed_parent_household(db_conn, *, parent_user_id: str) -> str:
    household_id = str(uuid4())
    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO education_households (
                    household_id, name, model_owner_user_id
                ) VALUES (%s, %s, %s)
                """,
                (household_id, "Book household", parent_user_id),
            )
            await cur.execute(
                """
                INSERT INTO education_memberships (
                    household_id, user_id, role, display_name
                ) VALUES (%s, %s, 'parent', %s)
                """,
                (household_id, parent_user_id, "Parent"),
            )
    return household_id


def _source(
    *, suffix: str, household_id: str | None = None, textbook_id: str | None = None
) -> dict[str, object]:
    if (household_id is None) != (textbook_id is None):
        raise ValueError("household_id and textbook_id must be provided together")
    prefix = (
        f"education/{household_id}/textbooks/{textbook_id}/source/"
        if household_id is not None and textbook_id is not None
        else f"education/source-{suffix}/"
    )
    return {
        "document_id": f"doc-{suffix}",
        "parse_job_id": f"job-{suffix}",
        "primary_artifact_id": f"art-{suffix}",
        "filename": "book.pdf",
        "media_type": "application/pdf",
        "format": "pdf",
        "parser_id": "datalab",
        "parser_name": "Datalab",
        "parser_version": "2",
        "parse_completed_at": "2026-10-01T00:00:00+00:00",
        "content_sha256": "a" * 64,
        "size_bytes": 128,
        "snapshot_prefix": prefix,
        "markdown_key": f"{prefix}artifacts/document.md",
        "blocks_key": f"{prefix}artifacts/blocks.json",
        "report_key": f"{prefix}artifacts/report.json",
        "asset_manifest": [],
        "snapshot": {"format": "langalpha-textbook-source-snapshot/v2"},
    }


IDENTITY = MoreToSkillsIdentity(
    version="2.1.0",
    skill_sha256="b" * 64,
    schema_sha256="c" * 64,
)


def _parsed_structure(*, content_file: str | None = None) -> ParsedBookStructure:
    knowledge_point = {
        "id": "kp-syntax",
        "title": "Syntax",
        "anchor": {"start_line": 2, "end_line": 4},
        "nodes": [],
    }
    if content_file is not None:
        knowledge_point["content_file"] = content_file
    return ParsedBookStructure(
        document={
            "schema_version": "2.1.0",
            "source": {"path": "inputs/book.md"},
            "nodes": [],
            "knowledge_points": [knowledge_point],
            "coverage": {"excluded": [], "omitted": []},
        },
        knowledge_points=(
            {
                "skill_kp_id": "kp-syntax",
                "position": 1,
                "title": "Syntax",
                "unit_skill_node_id": None,
                "node_skill_ids": (),
                "start_line": 2,
                "end_line": 4,
                "raw": knowledge_point,
            },
        ),
        warnings=(),
    )


async def _create_committed_book(*, parent_user_id: str, household_id: str):
    from src.server.database.education_book_jobs import start_item_attempt
    from src.server.database.education_books import (
        commit_book_structure,
        create_textbook_with_initial_job,
    )

    textbook_id = uuid4()
    created = await create_textbook_with_initial_job(
        textbook_id=textbook_id,
        parent_user_id=parent_user_id,
        household_id=household_id,
        title="Atomic Book",
        slug=f"atomic-{uuid4().hex}",
        source=_source(
            suffix=uuid4().hex[:12],
            household_id=household_id,
            textbook_id=str(textbook_id),
        ),
        idempotency_key="initial-structure",
        identity=IDENTITY,
    )
    structure_token = uuid4()
    await start_item_attempt(item_id=created["item_id"], attempt_token=structure_token)
    imported = await commit_book_structure(
        textbook_id=created["textbook_id"],
        job_id=created["job_id"],
        item_id=created["item_id"],
        attempt_token=structure_token,
        parsed=_parsed_structure(),
        validated_identity=IDENTITY,
    )
    snapshot = await get_projected_current_structure(
        textbook_id=str(created["textbook_id"])
    )
    assert snapshot is not None
    assert snapshot["more_to_skills_version"] == IDENTITY.version
    assert snapshot["skill_sha256"] == IDENTITY.skill_sha256
    assert snapshot["schema_sha256"] == IDENTITY.schema_sha256
    return created, imported, snapshot


async def _catalog_signature(conn) -> tuple[tuple[object, ...], ...]:
    queries = (
        """
        SELECT 'column', table_name, ordinal_position, column_name,
               data_type, udt_name, is_nullable, column_default
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name LIKE 'education\\_%%' ESCAPE '\\'
        ORDER BY table_name, ordinal_position
        """,
        """
        SELECT 'constraint', rel.relname, 0, constraints.conname,
               constraints.contype::text, '', '',
               pg_get_constraintdef(constraints.oid, true)
        FROM pg_constraint AS constraints
        JOIN pg_class AS rel ON rel.oid = constraints.conrelid
        JOIN pg_namespace AS namespaces ON namespaces.oid = rel.relnamespace
        WHERE namespaces.nspname = 'public'
          AND rel.relname LIKE 'education\\_%%' ESCAPE '\\'
        ORDER BY rel.relname, constraints.conname
        """,
        """
        SELECT 'index', tablename, 0, indexname, '', '', '', indexdef
        FROM pg_indexes
        WHERE schemaname = 'public' AND tablename LIKE 'education\\_%%' ESCAPE '\\'
        ORDER BY tablename, indexname
        """,
    )
    signature: list[tuple[object, ...]] = []
    async with conn.cursor() as cur:
        for query in queries:
            await cur.execute(query)
            signature.extend(tuple(row.values()) for row in await cur.fetchall())
    return tuple(signature)


def _run_alembic(db_url: URL, revision: str) -> None:
    project_root = Path(__file__).parents[2]
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option(
        "sqlalchemy.url", db_url.render_as_string(hide_password=False)
    )
    command.upgrade(config, revision)


async def test_more_to_skills_catalog_replaces_legacy_pipeline(db_conn) -> None:
    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = current_schema()
              AND table_name LIKE 'education%'
            """
        )
        tables = {row["table_name"] for row in await cur.fetchall()}

        assert {
            "education_textbooks",
            "education_book_structures",
            "education_book_knowledge_points",
            "education_book_materials",
            "education_book_jobs",
            "education_book_job_items",
            "education_book_activity_events",
            "education_textbook_assignments",
            "education_learning_kp_progress",
            "education_learning_items",
            "education_learning_spaces",
        } <= tables
        assert (
            not {
                "education_textbook_versions",
                "education_textbook_artifact_sources",
                "education_textbook_structures",
                "education_structure_units",
                "education_structure_knowledge_points",
                "education_content_nodes",
                "education_kp_lessons",
                "education_kp_lesson_revisions",
                "education_textbook_publications",
                "education_processing_profiles",
                "education_generation_jobs",
                "education_generation_attempts",
                "education_generation_progress_events",
            }
            & tables
        )

        await cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'education_textbooks'
            """
        )
        textbook_columns = {row["column_name"] for row in await cur.fetchall()}
        assert {
            "source_parse_job_id",
            "source_primary_artifact_id",
            "source_snapshot_prefix",
            "source_markdown_key",
            "current_structure_id",
        } <= textbook_columns
        assert "version_id" not in textbook_columns

        await cur.execute(
            """
            SELECT indexdef
            FROM pg_indexes
            WHERE schemaname = current_schema()
              AND indexname = 'uq_education_book_jobs_one_active'
            """
        )
        active_index = (await cur.fetchone())["indexdef"]
        assert "UNIQUE" in active_index
        assert "(textbook_id)" in active_index
        assert "status" in active_index
        assert "queued" in active_index
        assert "running" in active_index


async def test_empty_to_head_matches_081_to_082_catalog(
    db_conn,
    test_db_uri: str,
) -> None:
    """The full-history and deployed-081 upgrade paths must converge."""

    expected = await _catalog_signature(db_conn)
    params = conninfo_to_dict(test_db_uri)
    temporary_name = f"langalpha_082_{uuid4().hex}"
    admin_params = {**params, "dbname": "postgres"}
    temp_params = {**params, "dbname": temporary_name}
    db_url = URL.create(
        "postgresql+psycopg",
        username=temp_params.get("user"),
        password=temp_params.get("password"),
        host=temp_params.get("host"),
        port=int(temp_params["port"]) if temp_params.get("port") else None,
        database=temporary_name,
        query={"sslmode": temp_params.get("sslmode", "prefer")},
    )
    async with await psycopg.AsyncConnection.connect(
        make_conninfo(**admin_params), autocommit=True
    ) as admin:
        await admin.execute(
            sql.SQL("CREATE DATABASE {}").format(sql.Identifier(temporary_name))
        )
    try:
        await asyncio.to_thread(_run_alembic, db_url, "081_book_pipeline_checkpoint")
        await asyncio.to_thread(_run_alembic, db_url, "head")
        async with await psycopg.AsyncConnection.connect(
            make_conninfo(**temp_params),
            autocommit=True,
            row_factory=dict_row,
        ) as upgraded:
            assert await _catalog_signature(upgraded) == expected
    finally:
        async with await psycopg.AsyncConnection.connect(
            make_conninfo(**admin_params), autocommit=True
        ) as admin:
            await admin.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(
                    sql.Identifier(temporary_name)
                )
            )


async def test_create_textbook_and_initial_job_is_atomic_and_source_idempotent(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_books import create_textbook_with_initial_job

    async with patched_get_db_connection() as conn:
        household_id = await _seed_parent_household(
            conn, parent_user_id=seed_user["user_id"]
        )
    textbook_id = uuid4()
    source = _source(
        suffix=uuid4().hex[:12],
        household_id=household_id,
        textbook_id=str(textbook_id),
    )

    first = await create_textbook_with_initial_job(
        textbook_id=textbook_id,
        parent_user_id=seed_user["user_id"],
        household_id=household_id,
        title="Reading Explorer",
        slug=f"reading-{uuid4().hex}",
        source=source,
        idempotency_key="create-1",
        identity=IDENTITY,
    )
    repeated = await create_textbook_with_initial_job(
        textbook_id=textbook_id,
        parent_user_id=seed_user["user_id"],
        household_id=household_id,
        title="Ignored retry title",
        slug=f"ignored-{uuid4().hex}",
        source=source,
        idempotency_key="create-network-retry",
        identity=IDENTITY,
    )

    assert repeated["textbook_id"] == first["textbook_id"]
    assert repeated["job_id"] == first["job_id"]
    assert repeated["item_id"] == first["item_id"]
    rejected_textbook_id = uuid4()
    rejected_source = _source(
        suffix=uuid4().hex[:12],
        household_id=household_id,
        textbook_id=str(rejected_textbook_id),
    )
    invalid_identity = MoreToSkillsIdentity(
        version="2.1.0",
        skill_sha256="not-a-digest",
        schema_sha256="c" * 64,
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        await create_textbook_with_initial_job(
            textbook_id=rejected_textbook_id,
            parent_user_id=seed_user["user_id"],
            household_id=household_id,
            title="Must roll back",
            slug=f"rollback-{uuid4().hex}",
            source=rejected_source,
            idempotency_key="invalid-job",
            identity=invalid_identity,
        )
    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*) AS count FROM education_textbooks WHERE household_id = %s",
                (household_id,),
            )
            assert (await cur.fetchone())["count"] == 1
            await cur.execute(
                "SELECT count(*) AS count FROM education_book_jobs WHERE textbook_id = %s",
                (first["textbook_id"],),
            )
            assert (await cur.fetchone())["count"] == 1
            await cur.execute(
                """
                SELECT count(*) AS count FROM education_textbooks
                WHERE source_parse_job_id = %s
                """,
                (rejected_source["parse_job_id"],),
            )
            assert (await cur.fetchone())["count"] == 0


async def test_source_idempotency_does_not_disclose_another_households_ids(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_books import create_textbook_with_initial_job

    outsider_id = f"outsider-{uuid4().hex}"
    async with patched_get_db_connection() as conn:
        household_id = await _seed_parent_household(
            conn, parent_user_id=seed_user["user_id"]
        )
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO users (user_id, name) VALUES (%s, %s)",
                (outsider_id, "Outsider"),
            )
    textbook_id = uuid4()
    source = _source(
        suffix=uuid4().hex[:12],
        household_id=household_id,
        textbook_id=str(textbook_id),
    )
    created = await create_textbook_with_initial_job(
        textbook_id=textbook_id,
        parent_user_id=seed_user["user_id"],
        household_id=household_id,
        title="Private Book",
        slug=f"private-{uuid4().hex}",
        source=source,
        idempotency_key="owner-create",
        identity=IDENTITY,
    )

    with pytest.raises(PermissionError):
        await create_textbook_with_initial_job(
            textbook_id=textbook_id,
            parent_user_id=outsider_id,
            household_id=household_id,
            title="Leaked Book",
            slug=f"leaked-{uuid4().hex}",
            source=source,
            idempotency_key="outsider-retry",
            identity=IDENTITY,
        )

    assert created["textbook_id"] == textbook_id


async def test_structure_import_and_material_finalization_are_atomic_and_idempotent(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_jobs import (
        create_materials_job,
        finalize_material,
        record_candidate_object,
        start_item_attempt,
    )

    async with patched_get_db_connection() as conn:
        household_id = await _seed_parent_household(
            conn, parent_user_id=seed_user["user_id"]
        )
    created, imported, snapshot = await _create_committed_book(
        parent_user_id=seed_user["user_id"], household_id=household_id
    )
    assert snapshot["structure_id"] == imported["structure_id"]
    assert snapshot["knowledge_points"][0]["skill_kp_id"] == "kp-syntax"
    knowledge_point_id = snapshot["knowledge_points"][0]["knowledge_point_id"]
    assert str(knowledge_point_id) != "kp-syntax"

    material_job = await create_materials_job(
        textbook_id=created["textbook_id"],
        requested_by_user_id=seed_user["user_id"],
        knowledge_point_ids=[knowledge_point_id],
        depth="lesson",
        requirements="Use examples",
        replace_existing=False,
        include_supplementary=False,
        idempotency_key="material-1",
        identity=IDENTITY,
    )
    material_token = uuid4()
    item_id = material_job["items"][0]["item_id"]
    await start_item_attempt(item_id=item_id, attempt_token=material_token)
    key = f"education/materials/{item_id}/{material_token}/lesson.md"
    await record_candidate_object(
        item_id=item_id,
        attempt_token=material_token,
        content_key=key,
    )
    first = await finalize_material(
        item_id=item_id,
        attempt_token=material_token,
        content_key=key,
        content_sha256="d" * 64,
        size_bytes=100,
        generation_params={"temperature": 0},
    )
    repeated = await finalize_material(
        item_id=item_id,
        attempt_token=material_token,
        content_key=key,
        content_sha256="d" * 64,
        size_bytes=100,
        generation_params={"temperature": 0},
    )
    assert repeated == first
    assert first["generation"] == 1
    assert first["depth"] == "lesson"
    assert first["requirements"] == "Use examples"
    ready_snapshot = await get_projected_current_structure(
        textbook_id=str(created["textbook_id"])
    )
    assert (
        ready_snapshot["structure_json"]["knowledge_points"][0]["content_file"]
        == f"materials/{knowledge_point_id}.md"
    )

    replacement_job = await create_materials_job(
        textbook_id=created["textbook_id"],
        requested_by_user_id=seed_user["user_id"],
        knowledge_point_ids=[knowledge_point_id],
        depth="deep",
        requirements=None,
        replace_existing=True,
        include_supplementary=False,
        idempotency_key="material-2",
        identity=IDENTITY,
    )
    replacement_item_id = replacement_job["items"][0]["item_id"]
    replacement_token = uuid4()
    await start_item_attempt(
        item_id=replacement_item_id,
        attempt_token=replacement_token,
    )
    replacement_key = (
        f"education/materials/{replacement_item_id}/{replacement_token}/lesson.md"
    )
    await record_candidate_object(
        item_id=replacement_item_id,
        attempt_token=replacement_token,
        content_key=replacement_key,
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        await finalize_material(
            item_id=replacement_item_id,
            attempt_token=replacement_token,
            content_key=replacement_key,
            content_sha256="invalid",
            size_bytes=200,
            generation_params={},
        )

    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT status, succeeded_items, high_water_seq
                FROM education_book_jobs WHERE job_id = %s
                """,
                (material_job["job_id"],),
            )
            job = await cur.fetchone()
            assert job["status"] == "succeeded"
            assert job["succeeded_items"] == 1
            assert job["high_water_seq"] == 2
            await cur.execute(
                """
                SELECT kind, status, metadata->>'budget_class' AS budget_class
                FROM education_book_activity_events
                WHERE job_id = %s ORDER BY seq
                """,
                (material_job["job_id"],),
            )
            activity = await cur.fetchall()
            assert [
                (event["kind"], event["status"], event["budget_class"])
                for event in activity
            ] == [
                ("material", "succeeded", "terminal"),
                ("job", "succeeded", "terminal"),
            ]
            await cur.execute(
                """
                SELECT materials.content_key, materials.generation,
                       items.status, items.candidate_objects
                FROM education_book_materials AS materials
                JOIN education_book_job_items AS items ON items.item_id = %s
                WHERE materials.knowledge_point_id = %s
                """,
                (replacement_item_id, knowledge_point_id),
            )
            preserved = await cur.fetchone()
            assert preserved["content_key"] == key
            assert preserved["generation"] == 1
            assert preserved["status"] == "running"
            assert preserved["candidate_objects"] == [replacement_key]

    replacement = await finalize_material(
        item_id=replacement_item_id,
        attempt_token=replacement_token,
        content_key=replacement_key,
        content_sha256="e" * 64,
        size_bytes=200,
        generation_params={"temperature": 0},
    )
    late_old_callback = await finalize_material(
        item_id=item_id,
        attempt_token=material_token,
        content_key=key,
        content_sha256="d" * 64,
        size_bytes=100,
        generation_params={"temperature": 0},
    )

    assert replacement["generation"] == 2
    assert replacement["content_key"] == replacement_key
    assert late_old_callback == first

    with pytest.raises(ValueError, match="Idempotency key conflicts"):
        await create_materials_job(
            textbook_id=created["textbook_id"],
            requested_by_user_id=seed_user["user_id"],
            knowledge_point_ids=[knowledge_point_id],
            depth="lesson",
            requirements=None,
            replace_existing=False,
            include_supplementary=False,
            idempotency_key="initial-structure",
            identity=IDENTITY,
        )
    with pytest.raises(ValueError, match="Idempotency key conflicts"):
        await create_materials_job(
            textbook_id=created["textbook_id"],
            requested_by_user_id=seed_user["user_id"],
            knowledge_point_ids=[knowledge_point_id],
            depth="deep",
            requirements="Different request",
            replace_existing=True,
            include_supplementary=False,
            idempotency_key="material-1",
            identity=IDENTITY,
        )

    newer_structure_id = uuid4()
    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO education_book_structures (
                    structure_id, textbook_id, schema_version,
                    more_to_skills_version, skill_sha256, schema_sha256,
                    source_content_sha256, structure_json
                ) VALUES (%s, %s, '2.1.0', %s, %s, %s, %s, %s)
                """,
                (
                    newer_structure_id,
                    created["textbook_id"],
                    IDENTITY.version,
                    IDENTITY.skill_sha256,
                    IDENTITY.schema_sha256,
                    "a" * 64,
                    psycopg.types.json.Jsonb(
                        {
                            "schema_version": "2.1.0",
                            "nodes": [],
                            "knowledge_points": [],
                        }
                    ),
                ),
            )
            await cur.execute(
                """
                UPDATE education_textbooks SET current_structure_id = %s
                WHERE textbook_id = %s
                """,
                (newer_structure_id, created["textbook_id"]),
            )

    late_request_retry = await create_materials_job(
        textbook_id=created["textbook_id"],
        requested_by_user_id=seed_user["user_id"],
        knowledge_point_ids=[knowledge_point_id],
        depth="lesson",
        requirements="Use examples",
        replace_existing=False,
        include_supplementary=False,
        idempotency_key="material-1",
        identity=IDENTITY,
    )
    assert late_request_retry["job_id"] == material_job["job_id"]


async def test_material_job_idempotency_is_concurrency_safe(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_jobs import create_materials_job

    async with patched_get_db_connection() as conn:
        household_id = await _seed_parent_household(
            conn, parent_user_id=seed_user["user_id"]
        )
    created, _, snapshot = await _create_committed_book(
        parent_user_id=seed_user["user_id"], household_id=household_id
    )
    knowledge_point_id = snapshot["knowledge_points"][0]["knowledge_point_id"]

    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                CREATE OR REPLACE FUNCTION test_delay_book_job_insert()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    PERFORM pg_advisory_xact_lock(820082);
                    PERFORM pg_sleep(2);
                    RETURN NEW;
                END
                $$
                """
            )
            await cur.execute(
                """
                CREATE TRIGGER test_delay_book_job_insert
                BEFORE INSERT ON education_book_jobs
                FOR EACH ROW EXECUTE FUNCTION test_delay_book_job_insert()
                """
            )

    async def create():
        return await create_materials_job(
            textbook_id=created["textbook_id"],
            requested_by_user_id=seed_user["user_id"],
            knowledge_point_ids=[knowledge_point_id],
            depth="lesson",
            requirements="Use examples",
            replace_existing=False,
            include_supplementary=False,
            idempotency_key="concurrent-request",
            identity=IDENTITY,
        )

    try:
        first, second = await asyncio.gather(create(), create())
    finally:
        async with patched_get_db_connection() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "DROP TRIGGER IF EXISTS test_delay_book_job_insert "
                    "ON education_book_jobs"
                )
                await cur.execute(
                    "DROP FUNCTION IF EXISTS test_delay_book_job_insert()"
                )

    assert first["job_id"] == second["job_id"]
    assert first["items"][0]["item_id"] == second["items"][0]["item_id"]


async def test_learning_items_reject_knowledge_points_from_another_textbook(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_learning import (
        assign_textbook,
        upsert_learning_item,
    )

    student_id = f"student-{uuid4().hex}"
    async with patched_get_db_connection() as conn:
        household_id = await _seed_parent_household(
            conn, parent_user_id=seed_user["user_id"]
        )
        async with conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO users (user_id, name) VALUES (%s, %s)",
                (student_id, "Student"),
            )
            await cur.execute(
                """
                INSERT INTO education_memberships (
                    household_id, user_id, role, display_name
                ) VALUES (%s, %s, 'student', %s)
                """,
                (household_id, student_id, "Student"),
            )
    first_book, _, _ = await _create_committed_book(
        parent_user_id=seed_user["user_id"], household_id=household_id
    )
    _, _, second_snapshot = await _create_committed_book(
        parent_user_id=seed_user["user_id"], household_id=household_id
    )
    assignment = await assign_textbook(
        textbook_id=str(first_book["textbook_id"]),
        student_user_id=student_id,
        assigned_by_user_id=seed_user["user_id"],
    )

    with pytest.raises(ValueError, match="assigned textbook"):
        await upsert_learning_item(
            assignment_id=str(assignment["assignment_id"]),
            knowledge_point_id=str(
                second_snapshot["knowledge_points"][0]["knowledge_point_id"]
            ),
            kind="note",
            content="Must not cross books",
        )


async def test_existing_structure_materials_use_the_normal_storage_flow(
    patched_get_db_connection,
    seed_user,
    monkeypatch,
) -> None:
    from src.server.database.education_book_jobs import start_item_attempt
    from src.server.database.education_books import (
        commit_book_structure,
        create_textbook_with_initial_job,
    )
    from src.server.services import education_book_storage as storage

    async with patched_get_db_connection() as conn:
        household_id = await _seed_parent_household(
            conn, parent_user_id=seed_user["user_id"]
        )
    textbook_id = uuid4()
    created = await create_textbook_with_initial_job(
        textbook_id=textbook_id,
        parent_user_id=seed_user["user_id"],
        household_id=household_id,
        title="Book With Material",
        slug=f"material-{uuid4().hex}",
        source=_source(
            suffix=uuid4().hex[:12],
            household_id=household_id,
            textbook_id=str(textbook_id),
        ),
        idempotency_key="initial-with-material",
        identity=IDENTITY,
    )
    parsed = _parsed_structure(content_file="chapters/kp-syntax.md")
    structure_token = uuid4()
    await start_item_attempt(item_id=created["item_id"], attempt_token=structure_token)
    await commit_book_structure(
        textbook_id=textbook_id,
        job_id=created["job_id"],
        item_id=created["item_id"],
        attempt_token=structure_token,
        parsed=parsed,
        validated_identity=IDENTITY,
    )
    objects: dict[str, bytes] = {}

    async def upload(key, content, _content_type, *, max_size):
        assert len(content) <= max_size
        objects[key] = content
        return True

    monkeypatch.setattr(storage, "_upload", upload)
    monkeypatch.setattr(
        storage, "_read", lambda key: asyncio.sleep(0, result=objects.get(key))
    )

    results = await storage.import_existing_structure_materials(
        textbook_id=textbook_id,
        requested_by_user_id=seed_user["user_id"],
        parsed=parsed,
        output_files={"chapters/kp-syntax.md": b"# Existing lesson\n"},
    )

    snapshot = await get_projected_current_structure(textbook_id=str(textbook_id))
    assert len(results) == 1
    assert snapshot is not None
    assert snapshot["structure_json"]["knowledge_points"][0]["content_file"].startswith(
        "materials/"
    )
    assert list(objects.values()) == [b"# Existing lesson\n"]


async def test_structure_commit_appends_after_existing_activity_events(
    patched_get_db_connection,
    seed_user,
) -> None:
    from src.server.database.education_book_jobs import start_item_attempt
    from src.server.database.education_books import (
        commit_book_structure,
        create_textbook_with_initial_job,
    )

    async with patched_get_db_connection() as conn:
        household_id = await _seed_parent_household(
            conn, parent_user_id=seed_user["user_id"]
        )
    textbook_id = uuid4()
    created = await create_textbook_with_initial_job(
        textbook_id=textbook_id,
        parent_user_id=seed_user["user_id"],
        household_id=household_id,
        title="Book With Activity",
        slug=f"activity-{uuid4().hex}",
        source=_source(
            suffix=uuid4().hex[:12],
            household_id=household_id,
            textbook_id=str(textbook_id),
        ),
        idempotency_key="activity-structure",
        identity=IDENTITY,
    )
    attempt_token = uuid4()
    await start_item_attempt(item_id=created["item_id"], attempt_token=attempt_token)
    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO education_book_activity_events (
                    job_id, seq, dedupe_key, item_id, kind, status, message
                ) VALUES (%s, 1, 'runtime-started', %s,
                          'runtime', 'running', 'Runtime started')
                """,
                (created["job_id"], created["item_id"]),
            )
            await cur.execute(
                """
                UPDATE education_book_jobs SET high_water_seq = 1
                WHERE job_id = %s
                """,
                (created["job_id"],),
            )

    mismatched_identity = MoreToSkillsIdentity(
        version=IDENTITY.version,
        skill_sha256="d" * 64,
        schema_sha256=IDENTITY.schema_sha256,
    )
    with pytest.raises(ValueError, match="identity does not match"):
        await commit_book_structure(
            textbook_id=textbook_id,
            job_id=created["job_id"],
            item_id=created["item_id"],
            attempt_token=attempt_token,
            parsed=_parsed_structure(),
            validated_identity=mismatched_identity,
        )

    await commit_book_structure(
        textbook_id=textbook_id,
        job_id=created["job_id"],
        item_id=created["item_id"],
        attempt_token=attempt_token,
        parsed=_parsed_structure(),
        validated_identity=IDENTITY,
    )

    async with patched_get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT seq, dedupe_key FROM education_book_activity_events
                WHERE job_id = %s ORDER BY seq
                """,
                (created["job_id"],),
            )
            events = await cur.fetchall()
            await cur.execute(
                """
                SELECT high_water_seq FROM education_book_jobs WHERE job_id = %s
                """,
                (created["job_id"],),
            )
            job = await cur.fetchone()
    assert [(row["seq"], row["dedupe_key"]) for row in events] == [
        (1, "runtime-started"),
        (2, "structure-committed"),
        (3, f"job-terminal:{created['job_id']}"),
    ]
    assert job["high_water_seq"] == 3
