import pytest
from psycopg.types.json import Jsonb

from tests.integration.test_document_job_claims_db import _seed_job

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_page_count_uses_parse_jobs_bound_inspection_not_latest(
    patched_get_db_connection, seed_user
):
    from src.server.database.education_books import get_owned_parse_job

    async with patched_get_db_connection() as conn:
        await _seed_job(conn, job_id="job-A1b2C3d4E5f6")
        await conn.execute(
            "UPDATE document_inspections SET summary=%s WHERE inspection_id='ins-A1b2C3d4E5f6'",
            (Jsonb({"page_count": 24}),),
        )
        await conn.execute("""INSERT INTO document_inspections
          (inspection_id,document_id,inspector_id,inspector_name,status,summary)
          VALUES ('ins-B1b2C3d4E5f6','doc-A1b2C3d4E5f6','pdf-inspector','PDF Inspector',
                  'completed','{"page_count":999}'::jsonb)""")
        owner = await (
            await conn.execute(
                "SELECT owner_user_id FROM documents WHERE document_id='doc-A1b2C3d4E5f6'"
            )
        ).fetchone()
    row = await get_owned_parse_job(
        owner_user_id=owner["owner_user_id"], producer_job_id="job-A1b2C3d4E5f6"
    )
    assert row["page_count"] == 24
    assert (
        await get_owned_parse_job(
            owner_user_id=seed_user["user_id"], producer_job_id="job-A1b2C3d4E5f6"
        )
        is None
    )
