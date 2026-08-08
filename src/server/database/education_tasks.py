"""PostgreSQL persistence for materialized household homework tasks."""

from datetime import date, datetime, time
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row
from psycopg.types.json import Json

from src.server.database.pool import get_db_connection


async def get_household_context_for_parent(user_id: str) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT memberships.household_id, households.timezone
                FROM education_memberships AS memberships
                JOIN education_households AS households ON households.household_id = memberships.household_id
                WHERE memberships.user_id = %s AND memberships.role = 'parent'
                LIMIT 1
                """,
                (user_id,),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def is_student_in_household(*, household_id: str, user_id: str) -> bool:
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                SELECT 1 FROM education_memberships
                WHERE household_id = %s AND user_id = %s AND role = 'student'
                """,
                (household_id, user_id),
            )
            return await cur.fetchone() is not None


async def create_task_rule_and_instance(
    *, parent_user_id: str, household_id: str, assigned_student_id: str,
    title: str, description: str, recurrence: dict[str, Any], timezone_name: str,
    occurrence_date: date, due_at: datetime, material_asset_ids: list[str],
) -> dict[str, Any]:
    """Create a rule and first instance atomically; all asset IDs must be household-owned."""
    rule_id = str(uuid4())
    task_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    INSERT INTO education_task_rules (
                        task_rule_id, household_id, created_by_user_id, assigned_student_id,
                        title, description, recurrence, timezone, status, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active', NOW())
                    """,
                    (rule_id, household_id, parent_user_id, assigned_student_id, title, description, Json(recurrence), timezone_name),
                )
                await cur.execute(
                    """
                    INSERT INTO education_tasks (
                        task_id, task_rule_id, household_id, assigned_student_id, occurrence_date,
                        due_at, title, description, status, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'open', NOW())
                    RETURNING task_id, task_rule_id, household_id, assigned_student_id, occurrence_date,
                              due_at, title, description, status, created_at
                    """,
                    (task_id, rule_id, household_id, assigned_student_id, occurrence_date, due_at, title, description),
                )
                task = dict(await cur.fetchone())
                if material_asset_ids:
                    await cur.execute(
                        """
                        INSERT INTO education_task_material_assets (task_id, asset_id)
                        SELECT %s, assets.asset_id
                        FROM education_assets AS assets
                        WHERE assets.household_id = %s AND assets.asset_id = ANY(%s::uuid[])
                        ON CONFLICT DO NOTHING
                        """,
                        (task_id, household_id, material_asset_ids),
                    )
                    if cur.rowcount != len(set(material_asset_ids)):
                        raise ValueError("One or more material assets are outside the household")
    return task


async def materialize_task_rule_through(*, task_rule_id: str, through_date: date) -> int:
    """Create missing dated instances under a rule lock using ON CONFLICT idempotence."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT task_rule_id, household_id, assigned_student_id, title, description,
                           recurrence, timezone, status
                    FROM education_task_rules WHERE task_rule_id = %s FOR UPDATE
                    """,
                    (task_rule_id,),
                )
                rule = await cur.fetchone()
                if not rule or rule["status"] != "active":
                    return 0
                recurrence = rule["recurrence"]
                start = date.fromisoformat(recurrence["start_date"])
                frequency = recurrence["frequency"]
                if frequency == "once":
                    dates = [start] if start <= through_date else []
                elif frequency == "daily":
                    dates = [date.fromordinal(day) for day in range(start.toordinal(), through_date.toordinal() + 1)]
                else:
                    raise ValueError("Unsupported task recurrence")
                due_time = time.fromisoformat(recurrence["due_time"])
                created = 0
                for occurrence in dates:
                    due_at = datetime.combine(
                        occurrence, due_time, tzinfo=ZoneInfo(rule["timezone"])
                    )
                    await cur.execute(
                        """
                        INSERT INTO education_tasks (
                            task_id, task_rule_id, household_id, assigned_student_id, occurrence_date,
                            due_at, title, description, status, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'open', NOW())
                        ON CONFLICT (task_rule_id, occurrence_date) DO NOTHING
                        """,
                        (str(uuid4()), rule["task_rule_id"], rule["household_id"], rule["assigned_student_id"], occurrence, due_at, rule["title"], rule["description"]),
                    )
                    created += cur.rowcount
    return created


async def stop_task_rule(*, task_rule_id: str, parent_user_id: str) -> bool:
    """Stop future materialization without deleting any existing task history."""
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE education_task_rules AS rules
                SET status = 'stopped', stopped_at = NOW()
                FROM education_memberships AS memberships
                WHERE rules.task_rule_id = %s AND rules.household_id = memberships.household_id
                  AND memberships.user_id = %s AND memberships.role = 'parent'
                  AND rules.status = 'active'
                """,
                (task_rule_id, parent_user_id),
            )
            return cur.rowcount == 1


async def cancel_task(*, task_id: str, parent_user_id: str) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                UPDATE education_tasks AS tasks
                SET status = 'cancelled', cancelled_by_user_id = %s, cancelled_at = NOW()
                FROM education_memberships AS memberships
                WHERE tasks.task_id = %s AND tasks.household_id = memberships.household_id
                  AND memberships.user_id = %s AND memberships.role = 'parent'
                  AND tasks.status NOT IN ('completed', 'cancelled')
                RETURNING tasks.task_id, tasks.task_rule_id, tasks.household_id,
                          tasks.assigned_student_id, tasks.occurrence_date, tasks.due_at,
                          tasks.title, tasks.description, tasks.status, tasks.created_at
                """,
                (parent_user_id, task_id, parent_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def submit_task(
    *, task_id: str, student_user_id: str, submission_text: str,
    idempotency_key: str | None, asset_ids: list[str],
) -> dict[str, Any] | None:
    """Append one immutable student submission while holding the task row lock."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT tasks.task_id, tasks.household_id, tasks.assigned_student_id, tasks.status
                    FROM education_tasks AS tasks
                    JOIN education_memberships AS memberships ON memberships.household_id = tasks.household_id
                    WHERE tasks.task_id = %s AND memberships.user_id = %s AND memberships.role = 'student'
                    FOR UPDATE
                    """,
                    (task_id, student_user_id),
                )
                task = await cur.fetchone()
                if not task or task["assigned_student_id"] != student_user_id:
                    return None
                if idempotency_key:
                    await cur.execute(
                        """
                        SELECT submission_id, task_id, submitted_by_user_id, sequence,
                               idempotency_key, submission_text, created_at
                        FROM education_task_submissions
                        WHERE task_id = %s AND idempotency_key = %s
                        """,
                        (task_id, idempotency_key),
                    )
                    prior = await cur.fetchone()
                    if prior:
                        return dict(prior)
                if task["status"] not in {"open", "revision_requested"}:
                    raise ValueError(f"Task cannot be submitted from {task['status']}")
                await cur.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence FROM education_task_submissions WHERE task_id = %s",
                    (task_id,),
                )
                sequence = (await cur.fetchone())["sequence"]
                submission_id = str(uuid4())
                await cur.execute(
                    """
                    INSERT INTO education_task_submissions (
                        submission_id, task_id, submitted_by_user_id, sequence,
                        idempotency_key, submission_text, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    RETURNING submission_id, task_id, submitted_by_user_id, sequence,
                              idempotency_key, submission_text, created_at
                    """,
                    (submission_id, task_id, student_user_id, sequence, idempotency_key, submission_text),
                )
                submission = dict(await cur.fetchone())
                if asset_ids:
                    await cur.execute(
                        """
                        INSERT INTO education_task_submission_assets (submission_id, asset_id)
                        SELECT %s, assets.asset_id FROM education_assets AS assets
                        WHERE assets.household_id = %s AND assets.asset_id = ANY(%s::uuid[])
                        ON CONFLICT DO NOTHING
                        """,
                        (submission_id, task["household_id"], asset_ids),
                    )
                    if cur.rowcount != len(set(asset_ids)):
                        raise ValueError("One or more submission assets are outside the household")
                await cur.execute("UPDATE education_tasks SET status = 'submitted' WHERE task_id = %s", (task_id,))
    return submission


async def review_task(
    *, task_id: str, parent_user_id: str, feedback_text: str, decision: str
) -> dict[str, Any] | None:
    """Store a text-only parent review and atomically move the submitted task."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT tasks.task_id, tasks.status
                    FROM education_tasks AS tasks
                    JOIN education_memberships AS memberships ON memberships.household_id = tasks.household_id
                    WHERE tasks.task_id = %s AND memberships.user_id = %s AND memberships.role = 'parent'
                    FOR UPDATE
                    """,
                    (task_id, parent_user_id),
                )
                task = await cur.fetchone()
                if not task:
                    return None
                if task["status"] != "submitted":
                    raise ValueError(f"Task cannot be reviewed from {task['status']}")
                await cur.execute(
                    """
                    SELECT submission_id FROM education_task_submissions
                    WHERE task_id = %s ORDER BY sequence DESC LIMIT 1
                    """,
                    (task_id,),
                )
                submission = await cur.fetchone()
                if not submission:
                    raise RuntimeError("Submitted task has no submission")
                review_id = str(uuid4())
                await cur.execute(
                    """
                    INSERT INTO education_task_reviews (
                        review_id, submission_id, reviewed_by_user_id, decision, feedback_text, created_at
                    ) VALUES (%s, %s, %s, %s, %s, NOW())
                    RETURNING review_id, submission_id, reviewed_by_user_id, decision, feedback_text, created_at
                    """,
                    (review_id, submission["submission_id"], parent_user_id, decision, feedback_text),
                )
                review = dict(await cur.fetchone())
                await cur.execute("UPDATE education_tasks SET status = %s WHERE task_id = %s", (decision, task_id))
    return review


async def list_tasks_for_user(user_id: str) -> list[dict[str, Any]]:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT tasks.task_id, tasks.task_rule_id, tasks.household_id, tasks.assigned_student_id,
                       tasks.occurrence_date, tasks.due_at, tasks.title, tasks.description,
                       tasks.status, tasks.created_at
                FROM education_tasks AS tasks
                JOIN education_memberships AS memberships ON memberships.household_id = tasks.household_id
                WHERE memberships.user_id = %s
                  AND (memberships.role = 'parent' OR tasks.assigned_student_id = %s)
                ORDER BY tasks.due_at ASC, tasks.created_at ASC
                """,
                (user_id, user_id),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def list_active_rule_timezones_for_user(user_id: str) -> list[dict[str, Any]]:
    """Return active rules visible to the caller so recurrence is materialized locally."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT rules.task_rule_id, rules.timezone
                FROM education_task_rules AS rules
                JOIN education_memberships AS memberships ON memberships.household_id = rules.household_id
                WHERE memberships.user_id = %s AND rules.status = 'active'
                  AND (memberships.role = 'parent' OR rules.assigned_student_id = %s)
                """,
                (user_id, user_id),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]
