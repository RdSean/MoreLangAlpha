"""Student authorization and learning persistence for current book structures."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.server.database.pool import get_db_connection


async def assign_textbook(
    *, textbook_id: str, student_user_id: str, assigned_by_user_id: str
) -> dict[str, Any]:
    """Grant one student access when both users belong to the book household."""

    assignment_id = uuid4()
    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO education_textbook_assignments (
                    assignment_id, textbook_id, student_user_id,
                    assigned_by_user_id
                )
                SELECT %s, textbooks.textbook_id, student.user_id, parent.user_id
                FROM education_textbooks AS textbooks
                JOIN education_memberships AS parent
                  ON parent.household_id = textbooks.household_id
                 AND parent.user_id = %s AND parent.role = 'parent'
                JOIN education_memberships AS student
                  ON student.household_id = textbooks.household_id
                 AND student.user_id = %s AND student.role = 'student'
                WHERE textbooks.textbook_id = %s
                ON CONFLICT (textbook_id, student_user_id)
                DO UPDATE SET assigned_by_user_id = EXCLUDED.assigned_by_user_id
                RETURNING *
                """,
                (
                    assignment_id,
                    assigned_by_user_id,
                    student_user_id,
                    textbook_id,
                ),
            )
            row = await cur.fetchone()
            if row is None:
                raise PermissionError(
                    "Student and parent must share the book household"
                )
            return dict(row)


async def revoke_textbook(
    *, textbook_id: str, student_user_id: str, parent_user_id: str
) -> bool:
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                DELETE FROM education_textbook_assignments AS assignments
                USING education_textbooks AS textbooks,
                      education_memberships AS memberships
                WHERE assignments.textbook_id = textbooks.textbook_id
                  AND textbooks.household_id = memberships.household_id
                  AND memberships.user_id = %s AND memberships.role = 'parent'
                  AND assignments.textbook_id = %s
                  AND assignments.student_user_id = %s
                """,
                (parent_user_id, textbook_id, student_user_id),
            )
            return cur.rowcount > 0


async def get_student_assignment(
    *, textbook_id: str, student_user_id: str
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT assignments.*, textbooks.current_structure_id
                FROM education_textbook_assignments AS assignments
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = assignments.textbook_id
                WHERE assignments.textbook_id = %s
                  AND assignments.student_user_id = %s
                """,
                (textbook_id, student_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def upsert_learning_item(
    *,
    assignment_id: str,
    kind: str,
    content: str,
    skill_node_id: str | None = None,
    knowledge_point_id: str | None = None,
    source_anchor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    item_id = uuid4()
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO education_learning_items (
                    item_id, assignment_id, textbook_id, skill_node_id,
                    knowledge_point_id, kind, content, source_anchor
                )
                SELECT %s, assignments.assignment_id, assignments.textbook_id,
                       %s, %s, %s, %s, %s
                FROM education_textbook_assignments AS assignments
                LEFT JOIN education_book_knowledge_points AS points
                  ON points.knowledge_point_id = %s
                 AND points.textbook_id = assignments.textbook_id
                WHERE assignments.assignment_id = %s
                  AND (%s::uuid IS NULL OR points.knowledge_point_id IS NOT NULL)
                RETURNING *
                """,
                (
                    item_id,
                    skill_node_id,
                    knowledge_point_id,
                    kind,
                    content,
                    Jsonb(source_anchor) if source_anchor is not None else None,
                    knowledge_point_id,
                    assignment_id,
                    knowledge_point_id,
                ),
            )
            row = await cur.fetchone()
            if row is None:
                raise ValueError("Knowledge point must belong to the assigned textbook")
            return dict(row)
