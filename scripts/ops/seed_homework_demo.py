"""Insert demo homework tasks for one household so the dashboard has content.

Development-only. The dashboard's homework-calendar widget renders the real
education API, and an empty household makes it render its empty state — which
proves nothing. This script fills a household with a realistic spread: work
from the previous week as well as the current one, a mix of completed, open and
missed, and recurring rules so the calendar keeps filling itself.

It drives the real service layer (``create_task`` / ``check_in_task``) rather
than raw SQL, so every row satisfies the same validation the app applies:
subject/type pairs come from the dictionaries, the student must carry a grade,
and recurrence is materialised through the normal path. Because the calendar
materialises lazily over whatever window is queried, anchoring a rule a couple
of weeks in the past is enough for the previous week to populate.

Idempotent: every rule carries a ``demo-seed:*`` idempotency key, so re-running
reports what already exists instead of duplicating it.

Usage:
    DB_HOST=127.0.0.1 DB_PORT=15432 uv run python scripts/ops/seed_homework_demo.py
    DB_HOST=127.0.0.1 DB_PORT=15432 uv run python scripts/ops/seed_homework_demo.py --apply

``DB_*`` is read from the environment the same way the app reads it. The
defaults point at 5432, which is *not* the migration worktree's stack — pass
the port explicitly unless you mean the default database.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from psycopg.rows import dict_row

# Run as a script, sys.path[0] is scripts/ops — not the repo root the `src`
# package lives under. Same prelude as the other operator scripts.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.server.database.pool import get_db_connection, get_or_create_pool  # noqa: E402
from src.server.database.education_members import (  # noqa: E402
    list_household_membership_context,
)
from src.server.services.education_tasks import (  # noqa: E402
    check_in_task,
    create_task,
    get_task_calendar,
)

SEED_PREFIX = "demo-seed"

# Both `education_task_rules.idempotency_key` and
# `education_task_submissions.idempotency_key` are `uuid`, not text, so the
# seed derives deterministic UUIDv5s from its own namespace. Same input, same
# key, same row — which is what makes re-running this script a no-op.
SEED_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def seed_key(name: str) -> str:
    """A stable UUID for a seed identity string."""
    return str(uuid.uuid5(SEED_NAMESPACE, name))


@dataclass(frozen=True)
class Rule:
    """One recurring or one-off piece of homework to seed."""

    slug: str
    subject_code: str
    type_code: str
    practice_source_code: str | None
    title: str
    description: str
    frequency: str
    weekdays: list[int] | None
    anchor: date
    due_time: time
    # Past occurrences of this rule are left open, so the previous week shows
    # missed work rather than a wall of ticks.
    keep_open_in_past: bool = False


def _most_recent(weekdays: list[int], on_or_before: date) -> date:
    """The latest date at or before ``on_or_before`` on one of ``weekdays``."""
    candidate = on_or_before
    for _ in range(7):
        if candidate.isoweekday() in weekdays:
            return candidate
        candidate -= timedelta(days=1)
    raise ValueError(f"No weekday in {weekdays} within a week of {on_or_before}")


def _monday_of(day: date) -> date:
    return day - timedelta(days=day.isoweekday() - 1)


def build_rules(*, today: date) -> list[Rule]:
    """The demo schedule, anchored relative to ``today`` in household-local time.

    ``weekly`` recurrence only ever generates occurrences from its anchor date
    forward, so every rule that should cover the previous week anchors two
    weeks back — the most recent matching weekday, minus two weeks.
    """
    chinese_weekdays = [1, 3, 5]
    math_weekdays = [2, 4]
    monday = _monday_of(today)
    return [
        Rule(
            slug="chinese-preview",
            subject_code="chinese",
            type_code="preview",
            practice_source_code=None,
            title="语文预习",
            description="朗读并标注新课文，圈出不认识的字词。",
            frequency="weekly",
            weekdays=chinese_weekdays,
            anchor=_most_recent(chinese_weekdays, today) - timedelta(days=14),
            due_time=time(19, 30),
        ),
        Rule(
            slug="math-practice",
            subject_code="math",
            type_code="practice",
            practice_source_code="schoolwork",
            title="数学练习",
            description="完成练习册当天的两页，错题在订正本上重做一遍。",
            frequency="weekly",
            weekdays=math_weekdays,
            anchor=_most_recent(math_weekdays, today) - timedelta(days=14),
            due_time=time(20, 0),
            keep_open_in_past=True,
        ),
        Rule(
            slug="english-listening",
            subject_code="english",
            type_code="listen",
            practice_source_code=None,
            title="英语听读",
            description="跟读课文音频两遍，再自己朗读一遍录音。",
            frequency="daily",
            weekdays=None,
            anchor=today - timedelta(days=12),
            due_time=time(19, 0),
        ),
        Rule(
            slug="math-correction",
            subject_code="math",
            type_code="review",
            practice_source_code=None,
            title="数学订正",
            description="整理本周错题，写下错因。",
            frequency="weekly",
            weekdays=[6],
            anchor=monday + timedelta(days=5),
            due_time=time(10, 0),
        ),
        Rule(
            slug="chinese-writing",
            subject_code="chinese",
            type_code="write",
            practice_source_code=None,
            title="语文写作",
            description="以「难忘的一天」为题写一篇不少于 400 字的作文。",
            frequency="once",
            weekdays=None,
            anchor=today + timedelta(days=3),
            due_time=time(20, 0),
        ),
        Rule(
            slug="english-recite",
            subject_code="english",
            type_code="recite",
            practice_source_code=None,
            title="英语背诵",
            description="背诵 Unit 3 课文，明天课上抽查。",
            frequency="once",
            weekdays=None,
            anchor=today + timedelta(days=9),
            due_time=time(19, 30),
        ),
    ]


async def _task_count(household_id: str) -> int:
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT count(*) FROM education_tasks WHERE household_id = %s",
                (household_id,),
            )
            row = await cur.fetchone()
    return int(row[0])


async def _resolve_household(household_id: str | None) -> dict[str, Any]:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            if household_id:
                await cur.execute(
                    "SELECT household_id, timezone FROM education_households WHERE household_id = %s",
                    (household_id,),
                )
            else:
                await cur.execute(
                    "SELECT household_id, timezone FROM education_households ORDER BY created_at"
                )
            rows = [dict(row) for row in await cur.fetchall()]

    if not rows:
        raise SystemExit(
            "No education household exists. Create one through the app first."
        )
    if len(rows) > 1:
        listing = "\n".join(
            f"  {row['household_id']}  ({row['timezone']})" for row in rows
        )
        raise SystemExit(
            "More than one household exists; pass --household-id.\n" + listing
        )
    return rows[0]


async def _resolve_members(household_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    members = await list_household_membership_context(household_id)
    parents = [member for member in members if member["role"] == "parent"]
    students = [member for member in members if member["role"] == "student"]
    if not parents:
        raise SystemExit(f"Household {household_id} has no parent member.")
    if not students:
        raise SystemExit(f"Household {household_id} has no student member.")
    return parents[0], students[0]


async def _student_grade(household_id: str, student_user_id: str) -> str | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT grade_code FROM education_student_profiles
                WHERE household_id = %s AND user_id = %s
                """,
                (household_id, student_user_id),
            )
            row = await cur.fetchone()
    return row["grade_code"] if row else None


async def _valid_pairs() -> set[tuple[str, str]]:
    async with get_db_connection() as conn:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT subject_code, type_code FROM education_subject_homework_types"
            )
            rows = await cur.fetchall()
    return {(row[0], row[1]) for row in rows}


async def seed(args: argparse.Namespace) -> int:
    household = await _resolve_household(args.household_id)
    household_id = str(household["household_id"])
    timezone = ZoneInfo(household["timezone"])
    today = datetime.now(timezone).date()

    parent, student = await _resolve_members(household_id)
    parent_user_id = str(parent["user_id"])
    student_user_id = str(student["user_id"])
    grade_code = await _student_grade(household_id, student_user_id)
    if not grade_code:
        raise SystemExit(
            f"Student {student_user_id} has no grade profile; the API refuses to "
            "create tasks for them."
        )

    pairs = await _valid_pairs()
    rules = build_rules(today=today)
    unknown = [r for r in rules if (r.subject_code, r.type_code) not in pairs]
    if unknown:
        listed = ", ".join(f"{r.subject_code}/{r.type_code}" for r in unknown)
        raise SystemExit(f"Dictionary has no such subject/type pair: {listed}")

    print(f"household  {household_id}  ({household['timezone']})")
    print(f"parent     {parent_user_id}  {parent.get('display_name') or ''}".rstrip())
    print(
        f"student    {student_user_id}  {student.get('display_name') or ''}  grade={grade_code}"
    )
    print(f"today      {today.isoformat()}")
    print()

    before = await _task_count(household_id)
    for rule in rules:
        due_at = datetime.combine(rule.anchor, rule.due_time, tzinfo=timezone)
        print(
            f"  rule  {rule.slug:<18} {rule.frequency:<8} "
            f"from {rule.anchor.isoformat()} @ {rule.due_time.strftime('%H:%M')}"
        )
        if not args.apply:
            continue
        await create_task(
            parent_user_id=parent_user_id,
            assigned_student_id=student_user_id,
            title=rule.title,
            description=rule.description,
            due_at=due_at,
            subject_code=rule.subject_code,
            type_code=rule.type_code,
            practice_source_code=rule.practice_source_code,
            frequency=rule.frequency,
            weekdays=rule.weekdays,
            material_asset_ids=[],
            idempotency_key=seed_key(
                f"{SEED_PREFIX}:rule:{rule.slug}:{rule.anchor.isoformat()}"
            ),
        )

    if not args.apply:
        print("\ndry run — re-run with --apply to write")
        return 0

    # Read through the same service the dashboard calls: it is what materialises
    # every recurrence over the window, so listing the table directly would show
    # only the six first occurrences.
    window_start = today - timedelta(days=args.window_days)
    window_end = today + timedelta(days=args.window_days)
    calendar = await get_task_calendar(
        user_id=parent_user_id,
        start_date=window_start,
        end_date=window_end,
    )
    records = [task for day in calendar["days"] for task in day["tasks"]]

    # Leave the oldest missed occurrence of each keep_open_in_past rule alone so
    # the previous week shows overdue work; the rest of the past is checked in.
    keep_open: set[str] = set()
    for rule in rules:
        if not rule.keep_open_in_past:
            continue
        owned = sorted(
            (r for r in records if r["title"] == rule.title),
            key=lambda r: (r["occurrence_date"], str(r["task_id"])),
        )
        if owned:
            keep_open.add(str(owned[0]["task_id"]))

    completed = 0
    skipped = 0
    for record in records:
        task_id = str(record["task_id"])
        if record["status"] != "open" or record["occurrence_date"] >= today:
            continue
        if task_id in keep_open:
            skipped += 1
            continue
        await check_in_task(
            student_user_id=student_user_id,
            task_id=task_id,
            submission_text="（演示数据：已完成）",
            idempotency_key=seed_key(f"{SEED_PREFIX}:checkin:{task_id}"),
            asset_ids=[],
        )
        completed += 1

    after = await _task_count(household_id)
    print()
    print(f"rules ensured   : {len(rules)}")
    print(f"task rows added : {after - before} (0 on a repeat run)")
    print(f"tasks completed : {completed}")
    print(f"left open       : {skipped} (overdue on purpose)")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--household-id", help="target household; required when several exist"
    )
    parser.add_argument(
        "--apply", action="store_true", help="write; without it, dry run"
    )
    parser.add_argument(
        "--window-days",
        type=int,
        default=30,
        help=(
            "how far either side of today to materialise and complete "
            "(default 30; must span the oldest rule anchor)"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    target = (
        f"{os.getenv('DB_USER', 'postgres')}@{os.getenv('DB_HOST', 'localhost')}:"
        f"{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'postgres')}"
    )
    print(f"database   {target}")
    print()
    return asyncio.run(_run(args))


async def _run(args: argparse.Namespace) -> int:
    """Open the shared pool the app would open in its lifespan, then seed.

    ``get_db_connection`` refuses to hand out a connection while the pool is
    closed, and outside the server there is no lifespan to open it.
    """
    pool = get_or_create_pool()
    await pool.open()
    try:
        return await seed(args)
    finally:
        await pool.close()


if __name__ == "__main__":
    raise SystemExit(main())
