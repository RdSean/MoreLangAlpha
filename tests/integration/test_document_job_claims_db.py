from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
import psycopg
from psycopg.rows import dict_row

from src.server.database import document_jobs


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _seed_job(db_conn, *, job_id: str) -> None:
    owner_id = f"owner-{uuid4()}"
    async with db_conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO users (user_id, name) VALUES (%s, %s)",
            (owner_id, "Document owner"),
        )
        await cur.execute(
            """
            INSERT INTO documents (
                document_id, owner_user_id, original_filename, media_type,
                document_format, source_storage_key, source_size_bytes,
                source_sha256
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
                status, detected_format, classification
            ) VALUES (%s, %s, %s, %s, 'completed', 'pdf', 'text_based')
            """,
            (
                "ins-A1b2C3d4E5f6",
                "doc-A1b2C3d4E5f6",
                "pdf-inspector",
                "PDF Inspector",
            ),
        )
        await cur.execute(
            """
            INSERT INTO document_parse_jobs (
                job_id, document_id, inspection_id, parser_id,
                parser_name, request_mode
            ) VALUES (%s, %s, %s, %s, %s, 'async')
            """,
            (
                job_id,
                "doc-A1b2C3d4E5f6",
                "ins-A1b2C3d4E5f6",
                "anydoc-local",
                "AnyDoc Local",
            ),
        )


def _patch_connections(monkeypatch, test_db_uri: str) -> None:
    @asynccontextmanager
    async def use_test_connection():
        async with await psycopg.AsyncConnection.connect(
            test_db_uri,
            autocommit=True,
            row_factory=dict_row,
        ) as conn:
            yield conn

    monkeypatch.setattr(document_jobs, "get_db_connection", use_test_connection)


async def test_two_workers_cannot_claim_the_same_job(
    cleanup_tables,
    db_conn,
    test_db_uri,
    monkeypatch,
) -> None:
    await _seed_job(db_conn, job_id="job-A1b2C3d4E5f6")
    _patch_connections(monkeypatch, test_db_uri)

    claims = await asyncio.gather(
        document_jobs.claim_next_job(claimed_by="worker-a", lease_seconds=60),
        document_jobs.claim_next_job(claimed_by="worker-b", lease_seconds=60),
    )

    claimed = [row for row in claims if row is not None]
    assert len(claimed) == 1
    assert claimed[0]["job_id"] == "job-A1b2C3d4E5f6"
    assert claimed[0]["attempt_count"] == 1


async def test_expired_lease_is_reclaimed_with_a_new_attempt(
    cleanup_tables,
    db_conn,
    test_db_uri,
    monkeypatch,
) -> None:
    await _seed_job(db_conn, job_id="job-A1b2C3d4E5f6")
    _patch_connections(monkeypatch, test_db_uri)
    first = await document_jobs.claim_next_job(
        claimed_by="worker-a",
        lease_seconds=60,
    )
    assert first is not None

    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            UPDATE document_parse_jobs
            SET lease_expires_at = clock_timestamp() - INTERVAL '1 second'
            WHERE job_id = %s
            """,
            ("job-A1b2C3d4E5f6",),
        )

    second = await document_jobs.claim_next_job(
        claimed_by="worker-b",
        lease_seconds=60,
    )

    assert second is not None
    assert second["claimed_by"] == "worker-b"
    assert second["attempt_count"] == 2
    assert second["status_version"] > first["status_version"]
