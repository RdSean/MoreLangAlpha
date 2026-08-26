"""Raw PostgreSQL reads and writes for K12 homework metadata."""

from typing import Any

from psycopg.rows import dict_row

from src.server.database.pool import get_db_connection


async def get_student_grade_profile(
    *, household_id: str, user_id: str
) -> dict[str, Any] | None:
    """Return a student's grade profile without exposing other household data."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT memberships.household_id, memberships.user_id, profiles.grade_code
                FROM education_memberships AS memberships
                LEFT JOIN education_student_profiles AS profiles
                  ON profiles.household_id = memberships.household_id
                 AND profiles.user_id = memberships.user_id
                WHERE memberships.household_id = %s
                  AND memberships.user_id = %s
                  AND memberships.role = 'student'
                """,
                (household_id, user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def upsert_student_grade_profile(
    *, household_id: str, user_id: str, grade_code: str | None
) -> dict[str, Any] | None:
    """Set or clear the grade snapshot only for a known grade level."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            if grade_code is None:
                await cur.execute(
                    """
                    INSERT INTO education_student_profiles (
                        household_id, user_id, grade_code, updated_at
                    ) VALUES (%s, %s, NULL, NOW())
                    ON CONFLICT (household_id, user_id) DO UPDATE
                    SET grade_code = NULL, updated_at = NOW()
                    RETURNING household_id, user_id, grade_code
                    """,
                    (household_id, user_id),
                )
            else:
                await cur.execute(
                    """
                    INSERT INTO education_student_profiles (
                        household_id, user_id, grade_code, updated_at
                    )
                    SELECT %s, %s, grades.code, NOW()
                    FROM education_grade_levels AS grades
                    WHERE grades.code = %s
                    ON CONFLICT (household_id, user_id) DO UPDATE
                    SET grade_code = EXCLUDED.grade_code, updated_at = NOW()
                    RETURNING household_id, user_id, grade_code
                    """,
                    (household_id, user_id, grade_code),
                )
            row = await cur.fetchone()
    return dict(row) if row else None


async def list_homework_dictionaries() -> dict[str, list[dict[str, Any]]]:
    """Read seeded homework classifications in display order."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT subjects.code AS subject_code,
                       subjects.name AS subject_name,
                       subjects.color AS subject_color,
                       subjects.sort_order AS subject_sort_order,
                       types.code AS type_code,
                       types.name AS type_name,
                       types.sort_order AS type_sort_order
                FROM education_subjects AS subjects
                LEFT JOIN education_subject_homework_types AS mappings
                  ON mappings.subject_code = subjects.code
                LEFT JOIN education_homework_types AS types
                  ON types.code = mappings.type_code
                ORDER BY subjects.sort_order, types.sort_order
                """
            )
            subject_rows = await cur.fetchall()
            await cur.execute(
                """
                SELECT code, name, stage, sort_order
                FROM education_grade_levels
                ORDER BY sort_order
                """
            )
            grade_rows = await cur.fetchall()
            await cur.execute(
                """
                SELECT code, name, sort_order
                FROM education_practice_sources
                ORDER BY sort_order
                """
            )
            source_rows = await cur.fetchall()

    subjects_by_code: dict[str, dict[str, Any]] = {}
    for row in subject_rows:
        subject_code = row["subject_code"]
        subject = subjects_by_code.setdefault(
            subject_code,
            {
                "code": subject_code,
                "name": row["subject_name"],
                "color": row["subject_color"],
                "sort_order": row["subject_sort_order"],
                "homework_types": [],
            },
        )
        if row["type_code"] is not None:
            subject["homework_types"].append(
                {
                    "code": row["type_code"],
                    "name": row["type_name"],
                    "sort_order": row["type_sort_order"],
                }
            )

    return {
        "subjects": list(subjects_by_code.values()),
        "grade_levels": [dict(row) for row in grade_rows],
        "practice_sources": [dict(row) for row in source_rows],
    }
