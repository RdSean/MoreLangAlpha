"""Database contracts for owner-backed household model preferences."""

from __future__ import annotations

from uuid import uuid4

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_shared_model_schema_cascades_student_preference_with_household(db_conn):
    owner_id = f"owner-{uuid4()}"
    student_id = f"student-{uuid4()}"
    household_id = uuid4()

    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.executemany(
                "INSERT INTO users (user_id, name) VALUES (%s, %s)",
                [(owner_id, "Owner"), (student_id, "Student")],
            )
            await cur.execute(
                """
                INSERT INTO education_households
                    (household_id, name, model_owner_user_id)
                VALUES (%s, %s, %s)
                """,
                (household_id, "Shared models", owner_id),
            )
            await cur.executemany(
                """
                INSERT INTO education_memberships
                    (household_id, user_id, role, display_name)
                VALUES (%s, %s, %s, %s)
                """,
                [
                    (household_id, owner_id, "parent", "Owner"),
                    (household_id, student_id, "student", "Student"),
                ],
            )
            await cur.execute(
                """
                INSERT INTO student_llm_preferences (user_id, household_id, model_key)
                VALUES (%s, %s, %s)
                """,
                (student_id, household_id, "deepseek-chat"),
            )

    async with db_conn.cursor() as cur:
        await cur.execute(
            "SELECT model_key FROM student_llm_preferences WHERE user_id = %s",
            (student_id,),
        )
        assert (await cur.fetchone())["model_key"] == "deepseek-chat"
        await cur.execute(
            "DELETE FROM education_households WHERE household_id = %s", (household_id,)
        )
        await cur.execute(
            "SELECT 1 FROM student_llm_preferences WHERE user_id = %s", (student_id,)
        )
        assert await cur.fetchone() is None


async def test_endpoint_pool_tables_are_not_part_of_shared_model_schema(db_conn):
    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN ('household_llm_endpoints', 'household_llm_settings')
            """
        )
        assert await cur.fetchall() == []
