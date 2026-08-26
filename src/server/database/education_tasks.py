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


async def get_calendar_context_for_user(user_id: str) -> dict[str, Any] | None:
    """Return the role and timezone needed for a household calendar read."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT memberships.household_id, memberships.role, households.timezone
                FROM education_memberships AS memberships
                JOIN education_households AS households
                  ON households.household_id = memberships.household_id
                WHERE memberships.user_id = %s
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


async def get_task_creation_context(
    *, household_id: str, assigned_student_id: str, subject_code: str, type_code: str,
    practice_source_code: str | None,
) -> dict[str, Any] | None:
    """Return the assigned student's grade and dictionary-pair eligibility."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT TRUE AS student_exists,
                       profiles.grade_code,
                       mappings.subject_code IS NOT NULL AS subject_type_is_valid,
                       sources.code IS NOT NULL AS practice_source_is_valid
                FROM education_memberships AS memberships
                LEFT JOIN education_student_profiles AS profiles
                  ON profiles.household_id = memberships.household_id
                 AND profiles.user_id = memberships.user_id
                LEFT JOIN education_subject_homework_types AS mappings
                  ON mappings.subject_code = %s
                 AND mappings.type_code = %s
                LEFT JOIN education_practice_sources AS sources
                  ON sources.code = %s
                WHERE memberships.household_id = %s
                  AND memberships.user_id = %s
                  AND memberships.role = 'student'
                """,
                (
                    subject_code, type_code, practice_source_code,
                    household_id, assigned_student_id,
                ),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def get_task_by_creation_idempotency(
    *, household_id: str, parent_user_id: str, idempotency_key: str,
) -> dict[str, Any] | None:
    """Find the first materialized task for a parent's retried create request."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT tasks.task_id, tasks.task_rule_id, tasks.household_id,
                       tasks.assigned_student_id, tasks.occurrence_date, tasks.due_at,
                       tasks.title, tasks.description, tasks.subject_code, tasks.type_code,
                       tasks.practice_source_code, tasks.grade_code, tasks.status,
                       tasks.completed_at, tasks.created_at
                FROM education_task_rules AS rules
                JOIN education_tasks AS tasks ON tasks.task_rule_id = rules.task_rule_id
                WHERE rules.household_id = %s
                  AND rules.created_by_user_id = %s
                  AND rules.idempotency_key = %s
                ORDER BY tasks.occurrence_date, tasks.created_at
                LIMIT 1
                """,
                (household_id, parent_user_id, idempotency_key),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def create_task_rule_and_instance(
    *, parent_user_id: str, household_id: str, assigned_student_id: str,
    title: str, description: str, recurrence: dict[str, Any], timezone_name: str,
    occurrence_date: date, due_at: datetime, subject_code: str, type_code: str,
    practice_source_code: str | None, grade_code: str, material_asset_ids: list[str],
    idempotency_key: str | None,
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
                        title, description, recurrence, timezone, subject_code, type_code,
                        practice_source_code, grade_code, idempotency_key, status, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active', NOW())
                    ON CONFLICT (household_id, created_by_user_id, idempotency_key)
                    WHERE idempotency_key IS NOT NULL DO NOTHING
                    RETURNING task_rule_id
                    """,
                    (
                        rule_id, household_id, parent_user_id, assigned_student_id, title,
                        description, Json(recurrence), timezone_name, subject_code, type_code,
                        practice_source_code, grade_code, idempotency_key,
                    ),
                )
                inserted_rule = await cur.fetchone()
                if not inserted_rule:
                    await cur.execute(
                        """
                        SELECT tasks.task_id, tasks.task_rule_id, tasks.household_id,
                               tasks.assigned_student_id, tasks.occurrence_date, tasks.due_at,
                               tasks.title, tasks.description, tasks.subject_code, tasks.type_code,
                               tasks.practice_source_code, tasks.grade_code, tasks.status,
                               tasks.completed_at, tasks.created_at
                        FROM education_task_rules AS rules
                        JOIN education_tasks AS tasks ON tasks.task_rule_id = rules.task_rule_id
                        WHERE rules.household_id = %s
                          AND rules.created_by_user_id = %s
                          AND rules.idempotency_key = %s
                        ORDER BY tasks.occurrence_date, tasks.created_at
                        LIMIT 1
                        """,
                        (household_id, parent_user_id, idempotency_key),
                    )
                    existing_task = await cur.fetchone()
                    if not existing_task:
                        raise RuntimeError("Idempotent task creation did not materialize a task")
                    return dict(existing_task)
                await cur.execute(
                    """
                    INSERT INTO education_tasks (
                        task_id, task_rule_id, household_id, assigned_student_id, occurrence_date,
                        due_at, title, description, subject_code, type_code, practice_source_code,
                        grade_code, status, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'open', NOW())
                    RETURNING task_id, task_rule_id, household_id, assigned_student_id, occurrence_date,
                              due_at, title, description, subject_code, type_code,
                              practice_source_code, grade_code, status, completed_at, created_at
                    """,
                    (
                        task_id, rule_id, household_id, assigned_student_id, occurrence_date,
                        due_at, title, description, subject_code, type_code,
                        practice_source_code, grade_code,
                    ),
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


def _task_occurrence_dates(
    *, recurrence: dict[str, Any], from_date: date | None, through_date: date,
) -> list[date]:
    """Generate only the requested bounded occurrence window for one rule."""
    start = date.fromisoformat(recurrence["start_date"])
    window_start = max(start, from_date) if from_date is not None else start
    if window_start > through_date:
        return []

    frequency = recurrence["frequency"]
    if frequency == "once":
        return [start] if window_start <= start <= through_date else []
    dates = [
        date.fromordinal(day)
        for day in range(window_start.toordinal(), through_date.toordinal() + 1)
    ]
    if frequency == "daily":
        return dates
    if frequency == "weekdays":
        return [occurrence for occurrence in dates if occurrence.isoweekday() <= 5]
    if frequency == "weekly":
        weekdays = {int(value) for value in recurrence["weekdays"]}
        return [occurrence for occurrence in dates if occurrence.isoweekday() in weekdays]
    raise ValueError("Unsupported task recurrence")


async def materialize_task_rule_through(
    *, task_rule_id: str, through_date: date, from_date: date | None = None,
) -> int:
    """Create missing bounded instances under a rule lock using ON CONFLICT idempotence.

    Existing callers may omit ``from_date`` to preserve their established
    materialization behavior. Calendar callers supply it to avoid replaying a
    long-running daily rule from its original start date.
    """
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT task_rule_id, household_id, assigned_student_id, title, description,
                           recurrence, timezone, subject_code, type_code,
                           practice_source_code, grade_code, status
                    FROM education_task_rules WHERE task_rule_id = %s FOR UPDATE
                    """,
                    (task_rule_id,),
                )
                rule = await cur.fetchone()
                if not rule or rule["status"] != "active":
                    return 0
                recurrence = rule["recurrence"]
                dates = _task_occurrence_dates(
                    recurrence=recurrence, from_date=from_date, through_date=through_date
                )
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
                            due_at, title, description, subject_code, type_code,
                            practice_source_code, grade_code, status, created_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'open', NOW())
                        ON CONFLICT (task_rule_id, occurrence_date) DO NOTHING
                        """,
                        (
                            str(uuid4()), rule["task_rule_id"], rule["household_id"],
                            rule["assigned_student_id"], occurrence, due_at, rule["title"],
                            rule["description"], rule["subject_code"], rule["type_code"],
                            rule["practice_source_code"], rule["grade_code"],
                        ),
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
                          tasks.title, tasks.description, tasks.subject_code, tasks.type_code,
                          tasks.practice_source_code, tasks.grade_code, tasks.status,
                          tasks.completed_at, tasks.created_at
                """,
                (parent_user_id, task_id, parent_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def _insert_submission_assets(
    *, cur: Any, submission_id: str, household_id: str, asset_ids: list[str]
) -> None:
    if not asset_ids:
        return
    await cur.execute(
        """
        INSERT INTO education_task_submission_assets (submission_id, asset_id)
        SELECT %s, assets.asset_id FROM education_assets AS assets
        WHERE assets.household_id = %s AND assets.asset_id = ANY(%s::uuid[])
        ON CONFLICT DO NOTHING
        """,
        (submission_id, household_id, asset_ids),
    )
    if cur.rowcount != len(set(asset_ids)):
        raise ValueError("One or more submission assets are outside the household")


async def check_in_task(
    *, task_id: str, student_user_id: str, submission_text: str,
    idempotency_key: str | None, asset_ids: list[str],
) -> dict[str, Any] | None:
    """Atomically create the first check-in and mark an open task completed."""
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
                               idempotency_key, submission_text, submission_kind, created_at
                        FROM education_task_submissions
                        WHERE task_id = %s AND idempotency_key = %s
                        """,
                        (task_id, idempotency_key),
                    )
                    prior = await cur.fetchone()
                    if prior:
                        return dict(prior)
                if task["status"] != "open":
                    raise ValueError(f"Task cannot be checked in from {task['status']}")
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
                        idempotency_key, submission_text, submission_kind, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'check_in', NOW())
                    RETURNING submission_id, task_id, submitted_by_user_id, sequence,
                              idempotency_key, submission_text, submission_kind, created_at
                    """,
                    (submission_id, task_id, student_user_id, sequence, idempotency_key, submission_text),
                )
                submission = dict(await cur.fetchone())
                await _insert_submission_assets(
                    cur=cur, submission_id=submission_id,
                    household_id=str(task["household_id"]), asset_ids=asset_ids,
                )
                await cur.execute(
                    """
                    UPDATE education_tasks
                    SET status = 'completed', completed_at = COALESCE(completed_at, NOW())
                    WHERE task_id = %s AND status = 'open'
                    """,
                    (task_id,),
                )
    return submission


async def append_revision_submission(
    *, task_id: str, student_user_id: str, submission_text: str,
    idempotency_key: str | None, asset_ids: list[str],
) -> dict[str, Any] | None:
    """Append a later revision to a completed task without changing completion."""
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
                               idempotency_key, submission_text, submission_kind, created_at
                        FROM education_task_submissions
                        WHERE task_id = %s AND idempotency_key = %s
                        """,
                        (task_id, idempotency_key),
                    )
                    prior = await cur.fetchone()
                    if prior:
                        return dict(prior)
                if task["status"] != "completed":
                    raise ValueError(f"Task cannot accept a revision from {task['status']}")
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
                        idempotency_key, submission_text, submission_kind, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, 'revision', NOW())
                    RETURNING submission_id, task_id, submitted_by_user_id, sequence,
                              idempotency_key, submission_text, submission_kind, created_at
                    """,
                    (submission_id, task_id, student_user_id, sequence, idempotency_key, submission_text),
                )
                submission = dict(await cur.fetchone())
                await _insert_submission_assets(
                    cur=cur, submission_id=submission_id,
                    household_id=str(task["household_id"]), asset_ids=asset_ids,
                )
    return submission


async def review_task(
    *, task_id: str, parent_user_id: str, feedback_text: str, decision: str
) -> dict[str, Any] | None:
    """Append text-only parent feedback without changing task completion."""
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
                if task["status"] != "completed":
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
    return review


async def list_tasks_for_user(user_id: str) -> list[dict[str, Any]]:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT tasks.task_id, tasks.task_rule_id, tasks.household_id, tasks.assigned_student_id,
                       tasks.occurrence_date, tasks.due_at, tasks.title, tasks.description,
                       tasks.subject_code, tasks.type_code, tasks.practice_source_code,
                       tasks.grade_code, tasks.status, tasks.completed_at, tasks.created_at,
                       latest_review.decision AS latest_review_decision,
                       latest_review.feedback_text AS latest_feedback_text
                FROM education_tasks AS tasks
                JOIN education_memberships AS memberships ON memberships.household_id = tasks.household_id
                LEFT JOIN LATERAL (
                    SELECT reviews.decision, reviews.feedback_text
                    FROM education_task_submissions AS submissions
                    JOIN education_task_reviews AS reviews ON reviews.submission_id = submissions.submission_id
                    WHERE submissions.task_id = tasks.task_id
                    ORDER BY reviews.created_at DESC, reviews.review_id DESC
                    LIMIT 1
                ) AS latest_review ON TRUE
                WHERE memberships.user_id = %s
                  AND (memberships.role = 'parent' OR tasks.assigned_student_id = %s)
                ORDER BY tasks.due_at ASC, tasks.created_at ASC
                """,
                (user_id, user_id),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def list_calendar_task_records(
    *, household_id: str, assigned_student_id: str | None,
    start_date: date, end_date: date,
) -> list[dict[str, Any]]:
    """Read stable task summaries for a bounded calendar window.

    Cancelled tasks remain in history but are not shown as work on a calendar.
    """
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT tasks.task_id, tasks.task_rule_id, tasks.household_id,
                       tasks.assigned_student_id, tasks.occurrence_date, tasks.due_at,
                       tasks.title, tasks.description, tasks.subject_code,
                       subjects.color AS subject_color, tasks.type_code,
                       tasks.practice_source_code, tasks.grade_code, tasks.status,
                       tasks.completed_at, tasks.created_at
                FROM education_tasks AS tasks
                LEFT JOIN education_subjects AS subjects ON subjects.code = tasks.subject_code
                WHERE tasks.household_id = %s
                  AND tasks.occurrence_date BETWEEN %s AND %s
                  AND tasks.status <> 'cancelled'
                  AND (%s::text IS NULL OR tasks.assigned_student_id = %s)
                ORDER BY tasks.occurrence_date ASC, tasks.due_at ASC,
                         tasks.created_at ASC, tasks.task_id ASC
                """,
                (household_id, start_date, end_date, assigned_student_id, assigned_student_id),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_calendar_progress_counts(
    *, household_id: str, assigned_student_id: str | None, today: date,
    week_start: date, week_end: date, start_date: date, end_date: date,
    now: datetime,
) -> dict[str, int]:
    """Return header progress counts in the caller's household calendar scope."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT
                    COUNT(*) FILTER (
                        WHERE tasks.occurrence_date = %s AND tasks.status = 'open'
                    ) AS today_count,
                    COUNT(*) FILTER (
                        WHERE tasks.occurrence_date BETWEEN %s AND %s
                          AND tasks.status = 'completed'
                    ) AS week_count,
                    COUNT(*) FILTER (
                        WHERE tasks.status = 'open' AND tasks.due_at < %s
                    ) AS overdue_count,
                    COUNT(*) FILTER (
                        WHERE tasks.status = 'completed'
                          AND tasks.occurrence_date BETWEEN %s AND %s
                    ) AS completed_count
                FROM education_tasks AS tasks
                WHERE tasks.household_id = %s
                  AND tasks.status <> 'cancelled'
                  AND (%s::text IS NULL OR tasks.assigned_student_id = %s)
                """,
                (
                    today, week_start, week_end, now, start_date, end_date,
                    household_id, assigned_student_id, assigned_student_id,
                ),
            )
            row = await cur.fetchone()
    return {
        "today_count": int(row["today_count"]),
        "week_count": int(row["week_count"]),
        "overdue_count": int(row["overdue_count"]),
        "completed_count": int(row["completed_count"]),
    }


async def get_task_detail_for_user(*, task_id: str, user_id: str) -> dict[str, Any] | None:
    """Return one task timeline only to a household parent or its assignee."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT tasks.task_id, tasks.task_rule_id, tasks.household_id,
                       tasks.assigned_student_id, tasks.occurrence_date, tasks.due_at,
                       tasks.title, tasks.description, tasks.subject_code, tasks.type_code,
                       tasks.practice_source_code, tasks.grade_code, tasks.status,
                       tasks.completed_at, tasks.created_at
                FROM education_tasks AS tasks
                JOIN education_memberships AS memberships
                  ON memberships.household_id = tasks.household_id
                WHERE tasks.task_id = %s
                  AND memberships.user_id = %s
                  AND (
                      memberships.role = 'parent'
                      OR (
                          memberships.role = 'student'
                          AND tasks.assigned_student_id = %s
                      )
                  )
                LIMIT 1
                """,
                (task_id, user_id, user_id),
            )
            task = await cur.fetchone()
            if not task:
                return None

            detail = dict(task)
            await cur.execute(
                """
                SELECT assets.asset_id, assets.original_filename, assets.content_type,
                       assets.size_bytes, assets.created_at
                FROM education_task_material_assets AS materials
                JOIN education_assets AS assets ON assets.asset_id = materials.asset_id
                WHERE materials.task_id = %s
                ORDER BY assets.created_at ASC, assets.asset_id ASC
                """,
                (task_id,),
            )
            detail["parent_materials"] = [dict(row) for row in await cur.fetchall()]

            await cur.execute(
                """
                SELECT submission_id, task_id, submitted_by_user_id, sequence,
                       submission_text, submission_kind, created_at
                FROM education_task_submissions
                WHERE task_id = %s
                ORDER BY sequence ASC, created_at ASC, submission_id ASC
                """,
                (task_id,),
            )
            submissions = [dict(row) for row in await cur.fetchall()]
            submission_by_id = {
                str(submission["submission_id"]): submission for submission in submissions
            }
            for submission in submissions:
                submission["assets"] = []
                submission["reviews"] = []

            await cur.execute(
                """
                SELECT submission_assets.submission_id, assets.asset_id,
                       assets.original_filename, assets.content_type, assets.size_bytes,
                       assets.created_at
                FROM education_task_submission_assets AS submission_assets
                JOIN education_task_submissions AS submissions
                  ON submissions.submission_id = submission_assets.submission_id
                JOIN education_assets AS assets ON assets.asset_id = submission_assets.asset_id
                WHERE submissions.task_id = %s
                ORDER BY submissions.sequence ASC, assets.created_at ASC, assets.asset_id ASC
                """,
                (task_id,),
            )
            for row in await cur.fetchall():
                asset = dict(row)
                submission = submission_by_id.get(str(asset.pop("submission_id")))
                if submission is not None:
                    submission["assets"].append(asset)

            await cur.execute(
                """
                SELECT reviews.review_id, reviews.submission_id,
                       reviews.reviewed_by_user_id, reviews.decision,
                       reviews.feedback_text, reviews.created_at
                FROM education_task_reviews AS reviews
                JOIN education_task_submissions AS submissions
                  ON submissions.submission_id = reviews.submission_id
                WHERE submissions.task_id = %s
                ORDER BY submissions.sequence ASC, reviews.created_at ASC, reviews.review_id ASC
                """,
                (task_id,),
            )
            for row in await cur.fetchall():
                review = dict(row)
                submission = submission_by_id.get(str(review["submission_id"]))
                if submission is not None:
                    submission["reviews"].append(review)

            detail["submissions"] = submissions
    return detail


async def list_active_rule_timezones_for_user(user_id: str) -> list[dict[str, Any]]:
    """Return active rules visible to the caller so recurrence is materialized locally."""
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT rules.task_rule_id, rules.assigned_student_id, rules.timezone
                FROM education_task_rules AS rules
                JOIN education_memberships AS memberships ON memberships.household_id = rules.household_id
                WHERE memberships.user_id = %s AND rules.status = 'active'
                  AND (memberships.role = 'parent' OR rules.assigned_student_id = %s)
                """,
                (user_id, user_id),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]
