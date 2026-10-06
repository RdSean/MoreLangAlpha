"""User-owned reading markers and durable parent lesson chat mappings."""

from uuid import uuid4

from psycopg.rows import dict_row

from src.server.database.pool import get_db_connection


async def list_reading_states(*, user_id: str, textbook_id: str) -> list[dict]:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """SELECT knowledge_point_id,
                    CASE WHEN asked_at IS NOT NULL THEN 'asked' ELSE 'viewed' END AS state
                    FROM education_book_reading_state
                    WHERE user_id = %s AND textbook_id = %s""",
                (user_id, textbook_id),
            )
            return [dict(row) for row in await cur.fetchall()]


async def mark_reading_state(*, user_id: str, textbook_id: str, knowledge_point_id: str, state: str) -> bool:
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """INSERT INTO education_book_reading_state
                    (user_id, textbook_id, knowledge_point_id, asked_at)
                    SELECT %s, books.textbook_id, points.knowledge_point_id,
                           CASE WHEN %s = 'asked' THEN NOW() ELSE NULL END
                    FROM education_textbooks AS books
                    JOIN education_book_knowledge_points AS points
                      ON points.structure_id = books.current_structure_id
                    WHERE books.textbook_id = %s AND points.knowledge_point_id = %s
                      AND (EXISTS (SELECT 1 FROM education_memberships AS member
                        WHERE member.household_id = books.household_id AND member.user_id = %s AND member.role = 'parent')
                        OR EXISTS (SELECT 1 FROM education_textbook_assignments AS assignment
                        WHERE assignment.textbook_id = books.textbook_id AND assignment.student_user_id = %s))
                    ON CONFLICT (user_id, textbook_id, knowledge_point_id)
                    DO UPDATE SET asked_at = COALESCE(EXCLUDED.asked_at, education_book_reading_state.asked_at)""",
                (user_id, state, textbook_id, knowledge_point_id, user_id, user_id),
            )
            return cur.rowcount > 0


async def get_study_space(*, user_id: str, textbook_id: str, knowledge_point_id: str, create: bool = False) -> dict | None:
    from src.server.database.conversation import create_thread
    from src.server.database.workspace import get_or_create_flash_workspace

    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            # Lock the book before its reading row, matching textbook deletion.
            await cur.execute(
                """SELECT points.title FROM education_textbooks AS books
                    JOIN education_book_knowledge_points AS points ON points.structure_id = books.current_structure_id
                    JOIN education_memberships AS member ON member.household_id = books.household_id
                      AND member.user_id = %s AND member.role = 'parent'
                    WHERE books.textbook_id = %s AND points.knowledge_point_id = %s
                    FOR SHARE OF books""",
                (user_id, textbook_id, knowledge_point_id),
            )
            point = await cur.fetchone()
            if point is None:
                return None
            if create:
                await cur.execute(
                    """INSERT INTO education_book_reading_state (user_id,textbook_id,knowledge_point_id)
                        VALUES (%s,%s,%s) ON CONFLICT DO NOTHING""",
                    (user_id, textbook_id, knowledge_point_id),
                )
            await cur.execute(
                """SELECT state.conversation_thread_id, threads.workspace_id
                    FROM education_book_reading_state AS state
                    LEFT JOIN conversation_threads AS threads USING (conversation_thread_id)
                    WHERE state.user_id = %s AND state.textbook_id = %s AND state.knowledge_point_id = %s
                    FOR UPDATE OF state""",
                (user_id, textbook_id, knowledge_point_id),
            )
            row = await cur.fetchone()
            if row and row["conversation_thread_id"]:
                return dict(row)
            if not create:
                return None
            workspace = await get_or_create_flash_workspace(user_id, conn=conn)
            thread_id = str(uuid4())
            await create_thread(
                conversation_thread_id=thread_id,
                workspace_id=str(workspace["workspace_id"]),
                current_status="completed", msg_type="flash", title=f"{point['title']} · 讲义问答"[:255],
                platform="education",
                metadata={"education": {"textbook_id": textbook_id, "knowledge_point_id": knowledge_point_id}},
                conn=conn,
            )
            await cur.execute(
                """UPDATE education_book_reading_state SET conversation_thread_id = %s
                    WHERE user_id = %s AND textbook_id = %s AND knowledge_point_id = %s""",
                (thread_id, user_id, textbook_id, knowledge_point_id),
            )
            return {"conversation_thread_id": thread_id, "workspace_id": workspace["workspace_id"]}
