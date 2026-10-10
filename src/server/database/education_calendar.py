"""Household-scoped persistence for imported calendar sources."""

from uuid import uuid4

from psycopg.rows import dict_row

from src.server.database.pool import get_db_connection

METADATA = "source_id, household_id, name, filename, event_count, updated_at"


class CalendarSourceLimitError(ValueError):
    pass


class CalendarSourceConflictError(ValueError):
    pass


async def list_calendar_sources(
    household_id: str, *, include_content: bool = False
) -> list[dict]:
    fields = METADATA + (", content" if include_content else "")
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"SELECT {fields} FROM education_calendar_sources WHERE household_id = %s ORDER BY updated_at DESC, source_id",
                (household_id,),
            )
            return [dict(row) for row in await cur.fetchall()]


async def save_calendar_source(
    *,
    household_id: str,
    user_id: str,
    filename: str,
    name: str,
    content: str,
    digest: str,
    event_count: int,
    source_id: str | None = None,
) -> dict | None:
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                # Serialize imports within a household, including duplicate/limit checks.
                await cur.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                    ("education-calendar:" + household_id,),
                )
                existing = None
                if source_id:
                    await cur.execute(
                        "SELECT source_id FROM education_calendar_sources WHERE household_id = %s AND source_id = %s FOR UPDATE",
                        (household_id, source_id),
                    )
                    existing = await cur.fetchone()
                    if not existing:
                        return None
                await cur.execute(
                    f"SELECT {METADATA} FROM education_calendar_sources WHERE household_id = %s AND sha256 = %s",
                    (household_id, digest),
                )
                duplicate = await cur.fetchone()
                if duplicate:
                    if source_id and str(duplicate["source_id"]) != source_id:
                        raise CalendarSourceConflictError(
                            "该文件已作为另一份家庭日历导入。"
                        )
                    return dict(duplicate)
                if not source_id:
                    await cur.execute(
                        "SELECT source_id FROM education_calendar_sources WHERE household_id = %s AND filename_key = %s FOR UPDATE",
                        (household_id, filename.lower()),
                    )
                    existing = await cur.fetchone()
                target_id = existing["source_id"] if existing else uuid4()
                if existing:
                    await cur.execute(
                        "SELECT source_id FROM education_calendar_sources WHERE household_id = %s AND filename_key = %s AND source_id <> %s",
                        (household_id, filename.lower(), target_id),
                    )
                    if await cur.fetchone():
                        raise CalendarSourceConflictError(
                            "另一份家庭日历已使用此文件名。"
                        )
                    await cur.execute(
                        f"""UPDATE education_calendar_sources SET name = %s, filename = %s, filename_key = %s, content = %s, sha256 = %s, event_count = %s, updated_at = NOW() WHERE household_id = %s AND source_id = %s RETURNING {METADATA}""",
                        (
                            name,
                            filename,
                            filename.lower(),
                            content,
                            digest,
                            event_count,
                            household_id,
                            target_id,
                        ),
                    )
                else:
                    await cur.execute(
                        "SELECT COUNT(*) AS count FROM education_calendar_sources WHERE household_id = %s",
                        (household_id,),
                    )
                    if (await cur.fetchone())["count"] >= 20:
                        raise CalendarSourceLimitError("每个家庭最多保留 20 份日历。")
                    await cur.execute(
                        f"""INSERT INTO education_calendar_sources (source_id, household_id, created_by_user_id, name, filename, filename_key, content, sha256, event_count) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING {METADATA}""",
                        (
                            target_id,
                            household_id,
                            user_id,
                            name,
                            filename,
                            filename.lower(),
                            content,
                            digest,
                            event_count,
                        ),
                    )
                return dict(await cur.fetchone())


async def delete_calendar_source(*, household_id: str, source_id: str) -> bool:
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    "DELETE FROM education_calendar_sources WHERE household_id = %s AND source_id = %s RETURNING source_id",
                    (household_id, source_id),
                )
                return await cur.fetchone() is not None
