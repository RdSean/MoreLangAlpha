"""Student authorization and learning persistence for current book structures."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.server.database.pool import get_db_connection


async def assign_textbook_students(
    *,
    textbook_id: str | UUID,
    student_user_ids: list[str],
    assigned_by_user_id: str,
) -> list[dict[str, Any]] | None:
    """Atomically grant one parent-selected set of household students access."""

    student_user_ids = list(dict.fromkeys(student_user_ids))
    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT textbooks.household_id
                FROM education_textbooks AS textbooks
                JOIN education_memberships AS parent
                  ON parent.household_id = textbooks.household_id
                 AND parent.user_id = %s
                 AND parent.role = 'parent'
                WHERE textbooks.textbook_id = %s
                FOR SHARE OF textbooks
                """,
                (assigned_by_user_id, textbook_id),
            )
            textbook = await cur.fetchone()
            if textbook is None:
                return None
            await cur.execute(
                """
                SELECT memberships.user_id
                FROM education_memberships AS memberships
                WHERE memberships.household_id = %s
                  AND memberships.role = 'student'
                  AND memberships.user_id = ANY(%s::text[])
                """,
                (textbook["household_id"], student_user_ids),
            )
            found = {str(row["user_id"]) for row in await cur.fetchall()}
            if found != set(student_user_ids):
                raise PermissionError(
                    "Every assigned student must belong to the book household"
                )
            assignments: list[dict[str, Any]] = []
            for student_user_id in student_user_ids:
                await cur.execute(
                    """
                    INSERT INTO education_textbook_assignments (
                        assignment_id, textbook_id, student_user_id,
                        assigned_by_user_id
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (textbook_id, student_user_id)
                    DO UPDATE SET assigned_by_user_id = EXCLUDED.assigned_by_user_id
                    RETURNING assignment_id, textbook_id, student_user_id, created_at
                    """,
                    (
                        uuid4(),
                        textbook_id,
                        student_user_id,
                        assigned_by_user_id,
                    ),
                )
                row = await cur.fetchone()
                assert row is not None
                assignments.append(dict(row))
            return assignments


async def list_textbook_assignments_for_parent(
    *, textbook_id: str | UUID, parent_user_id: str
) -> list[dict[str, Any]]:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT assignments.textbook_id, assignments.student_user_id,
                       assignments.created_at
                FROM education_textbook_assignments AS assignments
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = assignments.textbook_id
                JOIN education_memberships AS parent
                  ON parent.household_id = textbooks.household_id
                 AND parent.user_id = %s
                 AND parent.role = 'parent'
                WHERE assignments.textbook_id = %s
                ORDER BY assignments.created_at, assignments.student_user_id
                """,
                (parent_user_id, textbook_id),
            )
            return [dict(row) for row in await cur.fetchall()]


async def revoke_textbook_students(
    *,
    textbook_id: str | UUID,
    student_user_ids: list[str],
    parent_user_id: str,
) -> int | None:
    """Atomically revoke selected students, returning None outside parent scope."""

    async with get_db_connection() as conn, conn.transaction():
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT 1
                FROM education_textbooks AS textbooks
                JOIN education_memberships AS parent
                  ON parent.household_id = textbooks.household_id
                 AND parent.user_id = %s
                 AND parent.role = 'parent'
                WHERE textbooks.textbook_id = %s
                FOR SHARE OF textbooks
                """,
                (parent_user_id, textbook_id),
            )
            if await cur.fetchone() is None:
                return None
            await cur.execute(
                """
                DELETE FROM education_textbook_assignments
                WHERE textbook_id = %s
                  AND student_user_id = ANY(%s::text[])
                """,
                (textbook_id, student_user_ids),
            )
            return cur.rowcount


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


async def list_student_textbook_assignments(
    *, student_user_id: str
) -> list[dict[str, Any]]:
    """List the student's assigned books against each current structure."""

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT assignments.assignment_id, assignments.textbook_id,
                       textbooks.title AS textbook_title,
                       textbooks.current_structure_id AS structure_id,
                       assignments.created_at,
                       COALESCE((
                           SELECT COUNT(*)
                           FROM education_book_knowledge_points AS points
                           WHERE points.structure_id = textbooks.current_structure_id
                       ), 0) AS knowledge_point_count,
                       COALESCE((
                           SELECT COUNT(*)
                           FROM education_learning_kp_progress AS progress
                           JOIN education_book_knowledge_points AS points
                             ON points.textbook_id = progress.textbook_id
                            AND points.knowledge_point_id = progress.knowledge_point_id
                           WHERE progress.assignment_id = assignments.assignment_id
                             AND points.structure_id = textbooks.current_structure_id
                             AND progress.status = 'read'
                       ), 0) AS completed_knowledge_point_count
                FROM education_textbook_assignments AS assignments
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = assignments.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                 AND memberships.user_id = assignments.student_user_id
                 AND memberships.role = 'student'
                WHERE assignments.student_user_id = %s
                ORDER BY assignments.created_at DESC, assignments.assignment_id
                """,
                (student_user_id,),
            )
            return [dict(row) for row in await cur.fetchall()]


async def get_student_assignment_by_id(
    *, assignment_id: str | UUID, student_user_id: str
) -> dict[str, Any] | None:
    """Resolve a stable student assignment without exposing legacy publications."""

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT assignments.assignment_id, assignments.textbook_id,
                       textbooks.title AS textbook_title,
                       textbooks.current_structure_id AS structure_id,
                       assignments.created_at
                FROM education_textbook_assignments AS assignments
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = assignments.textbook_id
                JOIN education_memberships AS memberships
                  ON memberships.household_id = textbooks.household_id
                 AND memberships.user_id = assignments.student_user_id
                 AND memberships.role = 'student'
                WHERE assignments.assignment_id = %s
                  AND assignments.student_user_id = %s
                """,
                (assignment_id, student_user_id),
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


async def upsert_learning_progress(
    *,
    student_user_id: str,
    assignment_id: str | UUID,
    knowledge_point_id: str | UUID,
    status: str,
) -> dict[str, Any] | None:
    """Upsert progress only for a knowledge point in the current assigned book."""

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO education_learning_kp_progress (
                    assignment_id, textbook_id, knowledge_point_id, status,
                    started_at, completed_at, updated_at
                )
                SELECT assignments.assignment_id, assignments.textbook_id,
                       points.knowledge_point_id, %s,
                       CASE WHEN %s = 'learning' THEN NOW() ELSE NULL END,
                       CASE WHEN %s IN ('read', 'review_recommended')
                            THEN NOW() ELSE NULL END,
                       NOW()
                FROM education_textbook_assignments AS assignments
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = assignments.textbook_id
                JOIN education_book_knowledge_points AS points
                  ON points.textbook_id = assignments.textbook_id
                 AND points.structure_id = textbooks.current_structure_id
                 AND points.knowledge_point_id = %s
                WHERE assignments.assignment_id = %s
                  AND assignments.student_user_id = %s
                ON CONFLICT (assignment_id, knowledge_point_id) DO UPDATE
                SET status = EXCLUDED.status,
                    started_at = COALESCE(
                        education_learning_kp_progress.started_at,
                        EXCLUDED.started_at
                    ),
                    completed_at = COALESCE(
                        EXCLUDED.completed_at,
                        education_learning_kp_progress.completed_at
                    ),
                    updated_at = NOW()
                RETURNING assignment_id, textbook_id, knowledge_point_id,
                          status, started_at, completed_at, updated_at
                """,
                (
                    status,
                    status,
                    status,
                    knowledge_point_id,
                    assignment_id,
                    student_user_id,
                ),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def list_learning_items(
    *,
    student_user_id: str,
    assignment_id: str | UUID,
    skill_node_id: str | None = None,
    knowledge_point_id: str | UUID | None = None,
) -> list[dict[str, Any]]:
    """List student-owned learning items within one current assignment."""

    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT items.item_id, items.assignment_id, items.skill_node_id,
                       items.knowledge_point_id, items.kind, items.content,
                       items.source_anchor, items.created_at, items.updated_at
                FROM education_learning_items AS items
                JOIN education_textbook_assignments AS assignments
                  ON assignments.assignment_id = items.assignment_id
                 AND assignments.textbook_id = items.textbook_id
                WHERE items.assignment_id = %s
                  AND assignments.student_user_id = %s
                  AND (%s::text IS NULL OR items.skill_node_id = %s)
                  AND (%s::uuid IS NULL OR items.knowledge_point_id = %s)
                ORDER BY items.created_at DESC, items.item_id
                """,
                (
                    assignment_id,
                    student_user_id,
                    skill_node_id,
                    skill_node_id,
                    knowledge_point_id,
                    knowledge_point_id,
                ),
            )
            return [dict(row) for row in await cur.fetchall()]


async def create_learning_item(
    *,
    student_user_id: str,
    assignment_id: str | UUID,
    expected_structure_id: str | UUID,
    skill_node_id: str | None,
    knowledge_point_id: str | UUID | None,
    kind: str,
    content: str,
    source_anchor: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Create an item only while its validated current structure is still active."""

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
                JOIN education_textbooks AS textbooks
                  ON textbooks.textbook_id = assignments.textbook_id
                 AND textbooks.current_structure_id = %s
                LEFT JOIN education_book_knowledge_points AS points
                  ON points.textbook_id = assignments.textbook_id
                 AND points.structure_id = textbooks.current_structure_id
                 AND points.knowledge_point_id = %s
                WHERE assignments.assignment_id = %s
                  AND assignments.student_user_id = %s
                  AND (%s::uuid IS NULL OR points.knowledge_point_id IS NOT NULL)
                RETURNING item_id, assignment_id, skill_node_id,
                          knowledge_point_id, kind, content, source_anchor,
                          created_at, updated_at
                """,
                (
                    item_id,
                    skill_node_id,
                    knowledge_point_id,
                    kind,
                    content,
                    Jsonb(source_anchor) if source_anchor is not None else None,
                    expected_structure_id,
                    knowledge_point_id,
                    assignment_id,
                    student_user_id,
                    knowledge_point_id,
                ),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def update_learning_item(
    *,
    student_user_id: str,
    assignment_id: str | UUID,
    item_id: str | UUID,
    content: str,
    source_anchor: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE education_learning_items AS items
                SET content = %s, source_anchor = %s, updated_at = NOW()
                FROM education_textbook_assignments AS assignments
                WHERE items.item_id = %s
                  AND items.assignment_id = %s
                  AND assignments.assignment_id = items.assignment_id
                  AND assignments.textbook_id = items.textbook_id
                  AND assignments.student_user_id = %s
                RETURNING items.item_id, items.assignment_id,
                          items.skill_node_id, items.knowledge_point_id,
                          items.kind, items.content, items.source_anchor,
                          items.created_at, items.updated_at
                """,
                (
                    content,
                    Jsonb(source_anchor) if source_anchor is not None else None,
                    item_id,
                    assignment_id,
                    student_user_id,
                ),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def delete_learning_item(
    *,
    student_user_id: str,
    assignment_id: str | UUID,
    item_id: str | UUID,
) -> bool:
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                DELETE FROM education_learning_items AS items
                USING education_textbook_assignments AS assignments
                WHERE items.item_id = %s
                  AND items.assignment_id = %s
                  AND assignments.assignment_id = items.assignment_id
                  AND assignments.textbook_id = items.textbook_id
                  AND assignments.student_user_id = %s
                """,
                (item_id, assignment_id, student_user_id),
            )
            return cur.rowcount > 0
