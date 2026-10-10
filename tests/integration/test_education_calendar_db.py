"""Real PostgreSQL household ICS import, sharing, replacement and isolation."""

from contextlib import asynccontextmanager
import asyncio
from datetime import date
from uuid import uuid4

import pytest

from src.server.database import education_calendar as db, education_members
from src.server.services import education_calendar as service

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def ics(title="Lesson"):
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//Test//EN\r\n"
        "BEGIN:VEVENT\r\nUID:shared\r\nDTSTART:20261010T090000Z\r\n"
        f"SUMMARY:{title}\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"
    ).encode()


async def test_household_import_share_update_delete_and_isolation(db_conn, monkeypatch):
    household, foreign = uuid4(), uuid4()
    parent, student, other = [f"ics-{uuid4()}" for _ in range(3)]
    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.executemany(
                "INSERT INTO users (user_id, name) VALUES (%s, %s)",
                [(user, user) for user in (parent, student, other)],
            )
            await cur.executemany(
                "INSERT INTO education_households (household_id, name, timezone, model_owner_user_id) VALUES (%s, 'ICS', 'Asia/Tokyo', %s)",
                [(household, parent), (foreign, other)],
            )
            await cur.executemany(
                "INSERT INTO education_memberships (household_id, user_id, role, display_name) VALUES (%s, %s, %s, %s)",
                [
                    (household, parent, "parent", "Parent"),
                    (household, student, "student", "Student"),
                    (foreign, other, "parent", "Other"),
                ],
            )

    @asynccontextmanager
    async def connection():
        yield db_conn

    monkeypatch.setattr(db, "get_db_connection", connection)
    monkeypatch.setattr(education_members, "get_db_connection", connection)
    source = await service.import_calendar(
        user_id=parent, filename="classes.ics", content=ics()
    )
    duplicate = await service.import_calendar(
        user_id=parent, filename="copy.ics", content=ics()
    )
    assert duplicate["source_id"] == source["source_id"]
    assert len(await service.list_sources(user_id=student)) == 1
    result = await service.get_events(
        user_id=student, start_date=date(2026, 10, 10), end_date=date(2026, 10, 10)
    )
    assert result["events"][0]["title"] == "Lesson"
    assert result["events"][0]["start_at"].endswith("18:00:00+09:00")
    assert (
        await service.get_events(
            user_id=other, start_date=date(2026, 10, 10), end_date=date(2026, 10, 10)
        )
    )["events"] == []
    with pytest.raises(service.CalendarAccessError):
        await service.import_calendar(
            user_id=student, filename="bad.ics", content=ics()
        )
    with pytest.raises(service.CalendarNotFoundError):
        await service.import_calendar(
            user_id=other,
            filename="bad.ics",
            content=ics(),
            source_id=str(source["source_id"]),
        )
    updated = await service.import_calendar(
        user_id=parent, filename="classes.ics", content=ics("Updated")
    )
    assert updated["source_id"] == source["source_id"]
    with pytest.raises(service.CalendarValidationError):
        await service.import_calendar(
            user_id=parent, filename="classes.ics", content=b"invalid"
        )
    assert (
        await service.get_events(
            user_id=parent, start_date=date(2026, 10, 10), end_date=date(2026, 10, 10)
        )
    )["events"][0]["title"] == "Updated"
    with pytest.raises(service.CalendarNotFoundError):
        await service.delete_source(user_id=other, source_id=str(source["source_id"]))
    with pytest.raises(service.CalendarAccessError):
        await service.delete_source(user_id=student, source_id=str(source["source_id"]))
    await service.delete_source(user_id=parent, source_id=str(source["source_id"]))
    assert await service.list_sources(user_id=student) == []


async def test_migration_downgrade_and_reupgrade_preserves_homework(
    db_conn, test_db_uri
):
    from alembic import command
    from alembic.config import Config

    household, rule, task = uuid4(), uuid4(), uuid4()
    parent, student = f"migration-parent-{uuid4()}", f"migration-student-{uuid4()}"
    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.executemany(
                "INSERT INTO users (user_id, name) VALUES (%s, %s)",
                [(parent, "Parent"), (student, "Student")],
            )
            await cur.execute(
                "INSERT INTO education_households (household_id, name, timezone, model_owner_user_id) VALUES (%s, 'Migration household', 'Asia/Tokyo', %s)",
                (household, parent),
            )
            await cur.executemany(
                "INSERT INTO education_memberships (household_id, user_id, role, display_name) VALUES (%s,%s,%s,%s)",
                [
                    (household, parent, "parent", "Parent"),
                    (household, student, "student", "Student"),
                ],
            )
            await cur.execute(
                """INSERT INTO education_task_rules (task_rule_id, household_id, created_by_user_id, assigned_student_id, title, recurrence, timezone, subject_code, type_code, grade_code) VALUES (%s,%s,%s,%s,'Existing homework','{"frequency":"once","start_date":"2026-10-10","due_time":"09:00"}'::jsonb,'Asia/Tokyo','chinese','read','g4')""",
                (rule, household, parent, student),
            )
            await cur.execute(
                "INSERT INTO education_tasks (task_id, task_rule_id, household_id, assigned_student_id, occurrence_date, due_at, title, subject_code, type_code, grade_code, status) VALUES (%s,%s,%s,%s,'2026-10-10','2026-10-10T09:00:00Z','Existing homework','chinese','read','g4','open')",
                (task, rule, household, student),
            )
    async with db_conn.cursor() as cur:
        await cur.execute("SELECT COUNT(*) AS count FROM education_task_rules")
        before = (await cur.fetchone())["count"]
    cfg = Config("alembic.ini")
    cfg.set_main_option(
        "sqlalchemy.url",
        test_db_uri.replace("postgresql://", "postgresql+psycopg://", 1),
    )
    await asyncio.to_thread(command.downgrade, cfg, "089_textbook_covers")
    async with db_conn.cursor() as cur:
        await cur.execute(
            "SELECT to_regclass('education_calendar_sources') AS table_name"
        )
        assert (await cur.fetchone())["table_name"] is None
    await asyncio.to_thread(command.upgrade, cfg, "head")
    async with db_conn.cursor() as cur:
        await cur.execute("SELECT COUNT(*) AS count FROM education_task_rules")
        assert (await cur.fetchone())["count"] == before
        await cur.execute(
            "SELECT title, status FROM education_tasks WHERE task_id = %s", (task,)
        )
        assert dict(await cur.fetchone()) == {
            "title": "Existing homework",
            "status": "open",
        }
        await cur.execute("SELECT version_num FROM alembic_version")
        assert (await cur.fetchone())["version_num"] == "090_household_calendars"
