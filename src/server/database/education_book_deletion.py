"""Atomic, household-scoped deletion and durable object cleanup leases."""

import asyncio
from contextlib import asynccontextmanager
from uuid import UUID, uuid4

from psycopg import AsyncConnection
from psycopg.rows import dict_row

from src.server.database.pool import get_db_connection, get_db_connection_string
from src.server.database.conversation import delete_thread
from src.server.services.writer_guard import thread_key
from src.server.database.session_lock import await_settled


@asynccontextmanager
async def book_item_storage_guard(*, item_id: UUID, preparation: bool = False):
    """Pin only a session lock, not a transaction, across external uploads."""
    # Do not pin an app-pool slot while storage helpers borrow from that pool.
    async with await AsyncConnection.connect(
        get_db_connection_string(), autocommit=True, prepare_threshold=0
    ) as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.textbook_id FROM education_book_jobs AS jobs
                JOIN education_book_job_items AS items ON items.job_id = jobs.job_id
                WHERE items.item_id = %s
            """,
                (item_id,),
            )
            row = await cur.fetchone()
            if row is None:
                raise LookupError("Textbook storage item was not found")
            key = f"education-book-storage:{row['textbook_id']}"
        try:
            if preparation:
                await await_settled(
                    asyncio.ensure_future(
                        conn.execute(
                            "SELECT pg_advisory_lock(hashtextextended('book-source-capacity', 0))"
                        )
                    )
                )
            await await_settled(
                asyncio.ensure_future(
                    conn.execute(
                        "SELECT pg_advisory_lock_shared(hashtextextended(%s, 0))",
                        (key,),
                    )
                )
            )
            yield
        finally:

            async def release():
                try:
                    await conn.execute(
                        "SELECT pg_advisory_unlock_shared(hashtextextended(%s, 0))",
                        (key,),
                    )
                except BaseException:
                    await conn.close()
                    raise

            await await_settled(asyncio.ensure_future(release()))


@asynccontextmanager
async def book_candidate_cleanup_guard(*, textbook_id: UUID):
    """Skip cleanup while any process still owns storage IO for this textbook."""
    async with await AsyncConnection.connect(
        get_db_connection_string(), autocommit=True, prepare_threshold=0
    ) as conn:
        key = f"education-book-storage:{textbook_id}"
        row = await (
            await conn.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s,0))", (key,)
            )
        ).fetchone()
        if not row[0]:
            yield False
            return
        try:
            yield True
        finally:
            await await_settled(
                asyncio.ensure_future(
                    conn.execute(
                        "SELECT pg_advisory_unlock(hashtextextended(%s,0))", (key,)
                    )
                )
            )


async def delete_textbook_for_parent(
    *, parent_user_id: str, textbook_id: UUID
) -> list[dict]:
    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT books.textbook_id, books.household_id
                FROM education_textbooks AS books
                JOIN education_memberships AS members
                  ON members.household_id = books.household_id
                 AND members.user_id = %s AND members.role = 'parent'
                WHERE books.textbook_id = %s
                FOR UPDATE OF books NOWAIT
            """,
                (parent_user_id, textbook_id),
            )
            book = await cur.fetchone()
            if book is None:
                raise LookupError("教材不存在")
            await cur.execute(
                "SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 0)) AS locked",
                (f"education-book-storage:{book['textbook_id']}",),
            )
            if not (await cur.fetchone())["locked"]:
                raise ValueError("教材产物仍在提交中，请等待结束后删除")
            # Fence retries/claims before checking business and runtime liveness.
            await cur.execute(
                """
                SELECT job_id FROM education_book_jobs
                WHERE textbook_id = %s ORDER BY job_id FOR UPDATE NOWAIT
            """,
                (textbook_id,),
            )
            await cur.fetchall()
            await cur.execute(
                """
                SELECT 1 FROM education_book_jobs AS jobs
                LEFT JOIN education_book_job_items AS items ON items.job_id = jobs.job_id
                LEFT JOIN conversation_responses AS runs ON runs.conversation_response_id = items.run_id
                WHERE jobs.textbook_id = %s AND (
                    jobs.status IN ('queued', 'running')
                    OR items.status IN ('queued', 'running')
                    OR runs.status = 'in_progress'
                ) LIMIT 1
            """,
                (textbook_id,),
            )
            if await cur.fetchone():
                raise ValueError("教材有进行中的加工任务，请先取消并等待结束")
            await cur.execute(
                """
                SELECT assignment_id FROM education_textbook_assignments
                WHERE textbook_id = %s ORDER BY assignment_id FOR UPDATE
            """,
                (textbook_id,),
            )
            await cur.fetchall()
            await cur.execute(
                """
                SELECT threads.conversation_thread_id, threads.workspace_id,
                       workspaces.user_id
                FROM conversation_threads AS threads
                JOIN workspaces USING (workspace_id)
                WHERE threads.platform = 'education' AND (
                  threads.metadata #>> '{education,textbook_id}' = %s::text
                  OR EXISTS (SELECT 1 FROM education_learning_spaces AS spaces
                    JOIN education_textbook_assignments AS assignments USING (assignment_id)
                    WHERE spaces.conversation_thread_id = threads.conversation_thread_id
                      AND assignments.textbook_id = %s))
                ORDER BY threads.conversation_thread_id
                FOR UPDATE OF threads NOWAIT
            """,
                (textbook_id, textbook_id),
            )
            threads = [dict(row) for row in await cur.fetchall()]
            for thread in threads:
                thread_id = str(thread["conversation_thread_id"])
                # Same keyspace as the existing exclusive thread mutation fence.
                await cur.execute(
                    "SELECT pg_try_advisory_xact_lock(%s) AS locked",
                    (thread_key(thread_id),),
                )
                if not (await cur.fetchone())["locked"]:
                    raise ValueError("学生学习对话仍在处理中，请等待结束后删除")
                await cur.execute(
                    """
                    SELECT 1 FROM conversation_responses
                    WHERE conversation_thread_id = %s AND status = 'in_progress'
                    UNION ALL
                    SELECT 1 FROM subagent_runs
                    WHERE thread_id = %s AND status = 'in_progress'
                    LIMIT 1
                """,
                    (thread_id, thread_id),
                )
                if await cur.fetchone():
                    raise ValueError("学生学习对话仍在处理中，请等待结束后删除")
            await cur.execute(
                """
                DELETE FROM education_learning_spaces WHERE assignment_id IN (
                    SELECT assignment_id FROM education_textbook_assignments WHERE textbook_id = %s
                )
            """,
                (textbook_id,),
            )
            for thread in threads:
                await delete_thread(str(thread["conversation_thread_id"]), conn=conn)
            await cur.execute(
                """
                DELETE FROM education_book_materials WHERE knowledge_point_id IN (
                    SELECT knowledge_point_id FROM education_book_knowledge_points WHERE textbook_id = %s
                )
            """,
                (textbook_id,),
            )
            await cur.execute(
                "DELETE FROM education_book_jobs WHERE textbook_id = %s", (textbook_id,)
            )
            await cur.execute(
                "UPDATE education_textbooks SET current_structure_id = NULL WHERE textbook_id = %s",
                (textbook_id,),
            )
            await cur.execute(
                "DELETE FROM education_textbooks WHERE textbook_id = %s", (textbook_id,)
            )
            await cur.execute(
                """
                INSERT INTO education_book_deletion_cleanup (textbook_id, household_id)
                VALUES (%s, %s)
            """,
                (textbook_id, book["household_id"]),
            )
    return threads


async def claim_textbook_cleanup() -> dict | None:
    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE education_book_deletion_cleanup SET lease_token = %s,
                    next_attempt_at = NOW() + INTERVAL '10 minutes', attempts = attempts + 1
                WHERE textbook_id = (
                    SELECT textbook_id FROM education_book_deletion_cleanup
                    WHERE next_attempt_at <= NOW()
                    ORDER BY next_attempt_at, textbook_id
                    FOR UPDATE SKIP LOCKED LIMIT 1
                ) RETURNING *
            """,
                (uuid4(),),
            )
            row = await cur.fetchone()
            return dict(row) if row else None


async def finish_textbook_cleanup(
    *, textbook_id: UUID, lease_token: UUID, succeeded: bool
) -> None:
    async with get_db_connection() as conn:
        if succeeded:
            await conn.execute(
                "DELETE FROM education_book_deletion_cleanup WHERE textbook_id = %s AND lease_token = %s",
                (textbook_id, lease_token),
            )
        else:
            await conn.execute(
                """
                UPDATE education_book_deletion_cleanup
                SET lease_token = NULL, next_attempt_at = NOW() + INTERVAL '1 minute'
                WHERE textbook_id = %s AND lease_token = %s
            """,
                (textbook_id, lease_token),
            )
