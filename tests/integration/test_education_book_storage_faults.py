"""Opt-in local transport faults; never stop shared PostgreSQL or MinIO."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from urllib.parse import urlsplit

import boto3
from botocore.config import Config
import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
import pytest

from tests.integration.test_education_assets_minio import _require_local_minio
from tests.integration.test_education_book_jobs_db import _seed_claimed_material_job


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@asynccontextmanager
async def _put_response_proxy(endpoint: str, *, interrupt_body: bool):
    upstream = urlsplit(endpoint)
    assert upstream.scheme == "http"
    assert upstream.hostname in {"localhost", "127.0.0.1"}
    receipts = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_PUT(self):
            length = int(self.headers["Content-Length"])
            if interrupt_body:
                self.rfile.read(min(length, 32))
                receipts.append({"interrupted": True})
                self.close_connection = True
                return
            body = self.rfile.read(length)
            connection = HTTPConnection(upstream.hostname, upstream.port, timeout=5)
            try:
                connection.request(
                    "PUT", self.path, body=body, headers=dict(self.headers)
                )
                response = connection.getresponse()
                response.read()
                receipts.append({"status": response.status, "size": len(body)})
            finally:
                connection.close()
            # MinIO accepted the PUT, but the caller receives no HTTP response.
            self.close_connection = True

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", receipts
    finally:
        await asyncio.to_thread(server.shutdown)
        server.server_close()
        await asyncio.to_thread(thread.join, 5)


@asynccontextmanager
async def _commit_response_proxy(test_db_uri: str):
    config = conninfo_to_dict(test_db_uri)
    assert config["dbname"] == "langalpha_test"
    assert config["host"] in {"localhost", "127.0.0.1"}
    receipts = []
    handlers = set()

    async def handle(reader, writer):
        task = asyncio.current_task()
        handlers.add(task)
        upstream_writer = None
        pumps = []
        try:
            upstream_reader, upstream_writer = await asyncio.open_connection(
                config["host"], int(config.get("port", 5432))
            )

            async def forward_requests():
                while data := await reader.read(65536):
                    upstream_writer.write(data)
                    await upstream_writer.drain()

            async def forward_responses():
                while True:
                    header = await upstream_reader.readexactly(5)
                    body = await upstream_reader.readexactly(
                        int.from_bytes(header[1:], "big") - 4
                    )
                    if header[:1] == b"C" and body == b"COMMIT\x00":
                        receipts.append("COMMIT CommandComplete discarded")
                        return
                    writer.write(header + body)
                    await writer.drain()

            pumps = [
                asyncio.create_task(forward_requests()),
                asyncio.create_task(forward_responses()),
            ]
            await asyncio.wait(pumps, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for pump in pumps:
                pump.cancel()
            await asyncio.gather(*pumps, return_exceptions=True)
            writer.close()
            if upstream_writer is not None:
                upstream_writer.close()
                await upstream_writer.wait_closed()
            await writer.wait_closed()
            handlers.discard(task)

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    proxy_uri = make_conninfo(
        test_db_uri,
        host="127.0.0.1",
        port=server.sockets[0].getsockname()[1],
        sslmode="disable",
    )
    try:
        yield proxy_uri, receipts
    finally:
        server.close()
        await server.wait_closed()
        for task in tuple(handlers):
            task.cancel()
        await asyncio.gather(*tuple(handlers), return_exceptions=True)


async def _item_state(connection_factory, item_id):
    async with connection_factory() as conn, conn.cursor() as cur:
        await cur.execute(
            """SELECT i.status,i.attempt,i.candidate_objects,i.result_snapshot,
                (SELECT count(*) FROM education_book_materials m
                 WHERE m.source_item_id=i.item_id) AS material_count,
                (SELECT count(*) FROM education_book_activity_events e
                 WHERE e.job_id=i.job_id
                 AND e.metadata->>'budget_class'='terminal') AS terminal_events
                FROM education_book_job_items i WHERE i.item_id=%s""",
            (item_id,),
        )
        return await cur.fetchone()


@pytest.mark.parametrize("interrupt_body", [True, False])
async def test_real_minio_put_disconnect_keeps_attempt_uncommitted_then_recovers(
    patched_get_db_connection, seed_user, monkeypatch, interrupt_body
):
    _require_local_minio()
    from src.server.services import education_book_storage as storage
    from src.utils.storage import s3_compatible as s3

    _, _, item = await _seed_claimed_material_job(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
        include_supplementary=False,
    )
    normal_client = s3._get_client()
    markdown = b"# Durable transport lesson\n" + b"Source text.\n" * 50000
    keys = []
    try:
        async with _put_response_proxy(
            s3.StorageConfig.ENDPOINT_URL, interrupt_body=interrupt_body
        ) as (endpoint, receipts):
            fault_client = boto3.client(
                "s3",
                aws_access_key_id=s3.StorageConfig.ACCESS_KEY_ID,
                aws_secret_access_key=s3.StorageConfig.SECRET_ACCESS_KEY,
                region_name=s3.StorageConfig.REGION,
                endpoint_url=endpoint,
                config=Config(
                    signature_version="s3v4",
                    s3={"addressing_style": "path"},
                    retries={"total_max_attempts": 1},
                    connect_timeout=3,
                    read_timeout=3,
                ),
            )
            monkeypatch.setattr(s3, "_CLIENT", fault_client)
            try:
                with pytest.raises(
                    storage.BookStorageError, match="could not be stored"
                ):
                    await storage.store_material(
                        item_id=item["item_id"],
                        attempt_token=item["attempt_token"],
                        markdown=markdown,
                        generation_params={"depth": "lesson"},
                    )
            finally:
                monkeypatch.setattr(s3, "_CLIENT", normal_client)
                fault_client.close()
        failed = await _item_state(patched_get_db_connection, item["item_id"])
        keys = failed["candidate_objects"]
        assert len(keys) == 1
        assert failed["status"] == "running"
        assert failed["material_count"] == failed["terminal_events"] == 0
        assert failed["result_snapshot"] is None
        if interrupt_body:
            assert receipts == [{"interrupted": True}]
            assert await storage._read(keys[0]) is None
        else:
            assert receipts == [{"status": 200, "size": len(markdown)}]
            assert await storage._read(keys[0]) == markdown
        committed = await storage.store_material(
            item_id=item["item_id"],
            attempt_token=item["attempt_token"],
            markdown=markdown,
            generation_params={"depth": "lesson"},
        )
        settled = await _item_state(patched_get_db_connection, item["item_id"])
        assert settled["status"] == "succeeded"
        assert settled["material_count"] == settled["attempt"] == 1
        assert settled["terminal_events"] == 2
        assert committed["generation"] == 1
        assert committed["content_key"] == keys[0]
        assert (
            await storage.cleanup_book_item_candidates(
                item_id=item["item_id"], attempt_token=item["attempt_token"]
            )
            == 1
        )
        assert await storage._read(keys[0]) == markdown
    finally:
        for key in keys:
            assert key.startswith(f"education/{item['household_id']}/textbooks/")
            assert await storage._delete(key)


async def test_real_postgres_commit_ack_loss_does_not_repeat_material_generation(
    patched_get_db_connection, seed_user, test_db_uri, monkeypatch
):
    _require_local_minio()
    from src.server.database import education_book_jobs as jobs
    from src.server.services import education_book_storage as storage

    _, _, item = await _seed_claimed_material_job(
        patched_get_db_connection,
        parent_user_id=seed_user["user_id"],
        include_supplementary=False,
    )
    keys = []
    try:
        async with _commit_response_proxy(test_db_uri) as (proxy_uri, receipts):

            @asynccontextmanager
            async def proxy_connection():
                async with await psycopg.AsyncConnection.connect(
                    proxy_uri, autocommit=True, row_factory=dict_row
                ) as conn:
                    yield conn

            async def finalize_through_proxy(**kwargs):
                with monkeypatch.context() as patch:
                    patch.setattr(jobs, "get_db_connection", proxy_connection)
                    return await jobs.finalize_material(**kwargs)

            with monkeypatch.context() as patch:
                patch.setattr(storage, "finalize_material", finalize_through_proxy)
                with pytest.raises(psycopg.OperationalError):
                    await storage.store_material(
                        item_id=item["item_id"],
                        attempt_token=item["attempt_token"],
                        markdown=b"# Committed despite lost ACK\n",
                        generation_params={"depth": "lesson"},
                    )
            assert receipts == ["COMMIT CommandComplete discarded"]
        settled = await _item_state(patched_get_db_connection, item["item_id"])
        keys = settled["candidate_objects"]
        assert settled["status"] == "succeeded"
        assert settled["material_count"] == settled["attempt"] == 1
        assert settled["terminal_events"] == 2
        snapshot = settled["result_snapshot"]
        repeated = await jobs.finalize_material(
            item_id=item["item_id"],
            attempt_token=item["attempt_token"],
            content_key=snapshot["content_key"],
            content_sha256=snapshot["content_sha256"],
            size_bytes=snapshot["size_bytes"],
            generation_params={"depth": "lesson"},
        )
        assert repeated == snapshot
        assert await _item_state(patched_get_db_connection, item["item_id"]) == settled
        assert all(
            row["item_id"] != item["item_id"]
            for row in await jobs.list_book_items_for_recovery()
        )
        assert (
            await storage.cleanup_book_item_candidates(
                item_id=item["item_id"], attempt_token=item["attempt_token"]
            )
            == 1
        )
        assert (
            await storage._read(snapshot["content_key"])
            == b"# Committed despite lost ACK\n"
        )
    finally:
        for key in keys:
            assert key.startswith(f"education/{item['household_id']}/textbooks/")
            assert await storage._delete(key)
