from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest
import psycopg
from alembic import command
from alembic.config import Config
from psycopg.errors import ForeignKeyViolation


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

TABLES = {
    "document_datasets",
    "documents",
    "document_dataset_items",
    "document_tags",
    "document_tag_assignments",
    "document_inspections",
    "document_parse_jobs",
    "document_artifacts",
}

ENTITY_IDS = {
    "document_datasets": "dataset_id",
    "documents": "document_id",
    "document_tags": "tag_id",
    "document_inspections": "inspection_id",
    "document_parse_jobs": "job_id",
    "document_artifacts": "artifact_id",
}


async def _run_alembic(test_db_uri: str, revision: str, *, downgrade: bool) -> None:
    project_root = Path(__file__).resolve().parents[2]
    alembic_cfg = Config(str(project_root / "alembic.ini"))
    alembic_cfg.set_main_option(
        "script_location",
        str(project_root / "migrations"),
    )
    alembic_cfg.set_main_option(
        "sqlalchemy.url",
        test_db_uri.replace("postgresql://", "postgresql+psycopg://", 1),
    )
    operation = command.downgrade if downgrade else command.upgrade
    await asyncio.to_thread(operation, alembic_cfg, revision)


async def test_document_library_schema_and_repeatable_jobs(cleanup_tables, db_conn) -> None:
    owner_id = f"owner-{uuid4()}"

    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_name = ANY(%s)
            """,
            (list(TABLES),),
        )
        assert {row["table_name"] for row in await cur.fetchall()} == TABLES

        await cur.execute(
            "INSERT INTO users (user_id, name) VALUES (%s, %s)",
            (owner_id, "Document owner"),
        )
        await cur.execute(
            """
            INSERT INTO documents (
                document_id, owner_user_id, original_filename, media_type,
                document_format, source_storage_key, source_size_bytes, source_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "doc-A1b2C3d4E5f6",
                owner_id,
                "source.pdf",
                "application/pdf",
                "pdf",
                "documents/doc-A1b2C3d4E5f6/source",
                128,
                "a" * 64,
            ),
        )
        await cur.execute(
            """
            INSERT INTO document_inspections (
                inspection_id, document_id, inspector_id, inspector_name,
                inspector_version, status, detected_format, classification
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "ins-A1b2C3d4E5f6",
                "doc-A1b2C3d4E5f6",
                "pdf-inspector",
                "PDF Inspector",
                "1.17.0",
                "completed",
                "pdf",
                "text_based",
            ),
        )
        await cur.executemany(
            """
            INSERT INTO document_parse_jobs (
                job_id, document_id, inspection_id, parser_id,
                parser_name, parser_version, request_mode
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    "job-A1b2C3d4E5f6",
                    "doc-A1b2C3d4E5f6",
                    "ins-A1b2C3d4E5f6",
                    "anydoc-local",
                    "AnyDoc Local",
                    "0.2.4",
                    "async",
                ),
                (
                    "job-G7h8I9j0K1l2",
                    "doc-A1b2C3d4E5f6",
                    "ins-A1b2C3d4E5f6",
                    "anydoc-local",
                    "AnyDoc Local",
                    "0.2.4",
                    "async",
                ),
            ],
        )
        await cur.execute(
            "SELECT count(*) AS count FROM document_parse_jobs WHERE parser_id = %s",
            ("anydoc-local",),
        )
        assert (await cur.fetchone())["count"] == 2

        await cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'document_artifacts'
            """
        )
        artifact_columns = {row["column_name"] for row in await cur.fetchall()}
        assert {
            "artifact_kind",
            "format",
            "media_type",
            "schema_name",
            "schema_version",
            "relative_path",
            "storage_key",
            "locator",
            "metadata",
            "producer_job_id",
        } <= artifact_columns
        assert {"size_bytes", "sha256", "revision"}.isdisjoint(artifact_columns)


async def test_document_library_constraints_columns_and_indexes(
    cleanup_tables,
    db_conn,
) -> None:
    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT table_name, column_name, data_type, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = ANY(%s)
            """,
            (list(TABLES),),
        )
        columns = {
            (row["table_name"], row["column_name"]): row
            for row in await cur.fetchall()
        }

        for table, id_column in ENTITY_IDS.items():
            id_definition = columns[(table, id_column)]
            assert id_definition["data_type"] == "character varying"
            assert id_definition["character_maximum_length"] == 16

        owner_columns = {
            table
            for table in TABLES
            if (table, "owner_user_id") in columns
        }
        assert owner_columns == {
            "document_datasets",
            "documents",
            "document_dataset_items",
            "document_tags",
            "document_tag_assignments",
        }

        required_job_columns = {
            "status",
            "stage",
            "percentage",
            "status_version",
            "lease_expires_at",
            "attempt_count",
            "cancellation_requested_at",
            "parser_id",
            "parser_name",
            "parser_version",
            "parser_options",
            "primary_artifact_id",
        }
        assert required_job_columns <= {
            column
            for table, column in columns
            if table == "document_parse_jobs"
        }

        await cur.execute(
            """
            SELECT cls.relname AS table_name,
                   att.attname AS column_name
            FROM pg_constraint con
            JOIN pg_class cls ON cls.oid = con.conrelid
            JOIN unnest(con.conkey) WITH ORDINALITY AS key(attnum, ordinality)
              ON TRUE
            JOIN pg_attribute att
              ON att.attrelid = cls.oid AND att.attnum = key.attnum
            WHERE con.contype = 'p' AND cls.relname = ANY(%s)
            """,
            (list(ENTITY_IDS),),
        )
        primary_keys = {
            (row["table_name"], row["column_name"])
            for row in await cur.fetchall()
        }
        assert primary_keys == set(ENTITY_IDS.items())

        await cur.execute(
            """
            SELECT cls.relname AS table_name, pg_get_constraintdef(con.oid) AS definition
            FROM pg_constraint con
            JOIN pg_class cls ON cls.oid = con.conrelid
            WHERE con.contype = 'c' AND cls.relname = ANY(%s)
            """,
            (list(TABLES),),
        )
        check_definitions = {}
        for row in await cur.fetchall():
            check_definitions.setdefault(row["table_name"], []).append(
                row["definition"]
            )

        for table, prefix in {
            "document_datasets": "dts",
            "documents": "doc",
            "document_tags": "tag",
            "document_inspections": "ins",
            "document_parse_jobs": "job",
            "document_artifacts": "art",
        }.items():
            assert any(
                f"^{prefix}-[0-9A-Za-z]{{12}}$" in definition
                for definition in check_definitions[table]
            )

        document_checks = " ".join(check_definitions["documents"])
        job_checks = " ".join(check_definitions["document_parse_jobs"])
        artifact_checks = " ".join(check_definitions["document_artifacts"])
        assert "source_size_bytes >= 0" in document_checks
        assert "percentage >= 0" in job_checks
        assert "percentage <= 100" in job_checks
        for status in ("queued", "running", "completed", "failed", "cancelled"):
            assert status in job_checks
        for kind in (
            "primary_document",
            "embedded_image",
            "structured_data",
            "manifest",
        ):
            assert kind in artifact_checks

        await cur.execute(
            """
            SELECT source.relname AS source_table, target.relname AS target_table
            FROM pg_constraint con
            JOIN pg_class source ON source.oid = con.conrelid
            JOIN pg_class target ON target.oid = con.confrelid
            WHERE con.contype = 'f' AND source.relname = ANY(%s)
            """,
            (["document_inspections", "document_parse_jobs", "document_artifacts"],),
        )
        foreign_key_edges = {
            (row["source_table"], row["target_table"])
            for row in await cur.fetchall()
        }
        assert {
            ("document_inspections", "documents"),
            ("document_parse_jobs", "document_inspections"),
            ("document_artifacts", "document_parse_jobs"),
        } <= foreign_key_edges

        await cur.execute(
            """
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public' AND tablename = ANY(%s)
            """,
            (list(TABLES),),
        )
        index_names = {row["indexname"] for row in await cur.fetchall()}
        assert {
            "idx_document_datasets_owner_updated",
            "idx_documents_owner_updated",
            "idx_documents_owner_format",
            "idx_document_tags_owner_name",
            "idx_document_dataset_items_document",
            "idx_document_tag_assignments_document",
            "idx_document_inspections_document_created",
            "idx_document_inspections_classification",
            "idx_document_parse_jobs_document_created",
            "idx_document_parse_jobs_claimable",
            "idx_document_artifacts_document_created",
            "idx_document_artifacts_job_kind",
        } <= index_names


async def test_dataset_membership_cannot_cross_owners(cleanup_tables, db_conn) -> None:
    owner_id = f"owner-{uuid4()}"
    other_id = f"other-{uuid4()}"

    async with db_conn.cursor() as cur:
        await cur.executemany(
            "INSERT INTO users (user_id, name) VALUES (%s, %s)",
            [(owner_id, "Owner"), (other_id, "Other")],
        )
        await cur.execute(
            """
            INSERT INTO document_datasets (dataset_id, owner_user_id, name)
            VALUES (%s, %s, %s)
            """,
            ("dts-A1b2C3d4E5f6", owner_id, "Owner dataset"),
        )
        await cur.execute(
            """
            INSERT INTO documents (
                document_id, owner_user_id, original_filename, media_type,
                document_format, source_storage_key, source_size_bytes, source_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "doc-G7h8I9j0K1l2",
                other_id,
                "other.pdf",
                "application/pdf",
                "pdf",
                "documents/doc-G7h8I9j0K1l2/source",
                64,
                "b" * 64,
            ),
        )
        await cur.execute(
            """
            INSERT INTO document_tags (tag_id, owner_user_id, name, normalized_name)
            VALUES (%s, %s, %s, %s)
            """,
            ("tag-A1b2C3d4E5f6", owner_id, "Owner tag", "owner tag"),
        )

    with pytest.raises(ForeignKeyViolation):
        async with db_conn.transaction():
            async with db_conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO document_dataset_items
                        (dataset_id, document_id, owner_user_id)
                    VALUES (%s, %s, %s)
                    """,
                    ("dts-A1b2C3d4E5f6", "doc-G7h8I9j0K1l2", owner_id),
                )

    with pytest.raises(ForeignKeyViolation):
        async with db_conn.transaction():
            async with db_conn.cursor() as cur:
                await cur.execute(
                    """
                    INSERT INTO document_tag_assignments
                        (tag_id, document_id, owner_user_id)
                    VALUES (%s, %s, %s)
                    """,
                    ("tag-A1b2C3d4E5f6", "doc-G7h8I9j0K1l2", owner_id),
                )


async def test_zero_byte_source_is_valid(cleanup_tables, db_conn) -> None:
    owner_id = f"owner-{uuid4()}"

    async with db_conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO users (user_id, name) VALUES (%s, %s)",
            (owner_id, "Empty source owner"),
        )
        await cur.execute(
            """
            INSERT INTO documents (
                document_id, owner_user_id, original_filename, media_type,
                document_format, source_storage_key, source_size_bytes, source_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "doc-M3n4O5p6Q7r8",
                owner_id,
                "empty.pdf",
                "application/pdf",
                "pdf",
                "documents/doc-M3n4O5p6Q7r8/source",
                0,
                "c" * 64,
            ),
        )


async def test_primary_artifact_must_belong_to_the_same_job(
    cleanup_tables,
    db_conn,
) -> None:
    owner_id = f"owner-{uuid4()}"

    async with db_conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO users (user_id, name) VALUES (%s, %s)",
            (owner_id, "Artifact owner"),
        )
        await cur.execute(
            """
            INSERT INTO documents (
                document_id, owner_user_id, original_filename, media_type,
                document_format, source_storage_key, source_size_bytes, source_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "doc-M3n4O5p6Q7r8",
                owner_id,
                "source.pdf",
                "application/pdf",
                "pdf",
                "documents/doc-M3n4O5p6Q7r8/source",
                128,
                "d" * 64,
            ),
        )
        await cur.execute(
            """
            INSERT INTO document_inspections (
                inspection_id, document_id, inspector_id, inspector_name,
                status, detected_format, classification
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "ins-M3n4O5p6Q7r8",
                "doc-M3n4O5p6Q7r8",
                "pdf-inspector",
                "PDF Inspector",
                "completed",
                "pdf",
                "text_based",
            ),
        )
        await cur.executemany(
            """
            INSERT INTO document_parse_jobs (
                job_id, document_id, inspection_id, parser_id,
                parser_name, request_mode
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            [
                (
                    "job-M3n4O5p6Q7r8",
                    "doc-M3n4O5p6Q7r8",
                    "ins-M3n4O5p6Q7r8",
                    "anydoc-local",
                    "AnyDoc Local",
                    "async",
                ),
                (
                    "job-S9t0U1v2W3x4",
                    "doc-M3n4O5p6Q7r8",
                    "ins-M3n4O5p6Q7r8",
                    "legacy-pdf-text",
                    "Legacy PDF Text",
                    "async",
                ),
            ],
        )
        await cur.execute(
            """
            INSERT INTO document_artifacts (
                artifact_id, document_id, producer_job_id, artifact_kind,
                format, media_type, relative_path, storage_key
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "art-M3n4O5p6Q7r8",
                "doc-M3n4O5p6Q7r8",
                "job-M3n4O5p6Q7r8",
                "primary_document",
                "gfm",
                "text/markdown",
                "document.md",
                "documents/doc-M3n4O5p6Q7r8/artifacts/job-M3n4O5p6Q7r8/document.md",
            ),
        )

    with pytest.raises(ForeignKeyViolation):
        async with db_conn.transaction():
            async with db_conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE document_parse_jobs
                    SET primary_artifact_id = %s
                    WHERE job_id = %s
                    """,
                    ("art-M3n4O5p6Q7r8", "job-S9t0U1v2W3x4"),
                )


async def test_user_delete_cannot_orphan_document_source(
    cleanup_tables,
    db_conn,
) -> None:
    owner_id = f"owner-{uuid4()}"

    async with db_conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO users (user_id, name) VALUES (%s, %s)",
            (owner_id, "Source owner"),
        )
        await cur.execute(
            """
            INSERT INTO documents (
                document_id, owner_user_id, original_filename, media_type,
                document_format, source_storage_key, source_size_bytes, source_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                "doc-Y5z6A7b8C9d0",
                owner_id,
                "source.pdf",
                "application/pdf",
                "pdf",
                "documents/doc-Y5z6A7b8C9d0/source",
                128,
                "e" * 64,
            ),
        )

    with pytest.raises(ForeignKeyViolation):
        async with db_conn.transaction():
            async with db_conn.cursor() as cur:
                await cur.execute("DELETE FROM users WHERE user_id = %s", (owner_id,))


async def test_revision_045_downgrades_to_044_and_reupgrades(
    test_db_pool,
    test_db_uri,
) -> None:
    del test_db_pool

    try:
        await _run_alembic(test_db_uri, "044", downgrade=True)
        async with await psycopg.AsyncConnection.connect(test_db_uri) as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT version_num FROM alembic_version")
                assert (await cur.fetchone())[0] == "044"
                await cur.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public' AND table_name = ANY(%s)
                    """,
                    (list(TABLES),),
                )
                assert await cur.fetchall() == []
    finally:
        await _run_alembic(test_db_uri, "head", downgrade=False)
