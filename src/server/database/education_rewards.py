"""Household-scoped reward persistence. Every write serializes on the wallet."""

from contextlib import asynccontextmanager
from datetime import date
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from src.server.database.pool import get_db_connection


@asynccontextmanager
async def wallet_transaction(household_id: str, student_id: str):
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "INSERT INTO education_reward_settings(household_id) VALUES (%s) ON CONFLICT DO NOTHING",
                    (household_id,),
                )
                await cur.execute(
                    """
                    INSERT INTO education_reward_wallets(household_id,student_id,started_on,settled_through,streak_run_id)
                    SELECT m.household_id,m.user_id,
                        (GREATEST(s.activated_at,m.created_at) AT TIME ZONE h.timezone)::date,
                        (GREATEST(s.activated_at,m.created_at) AT TIME ZONE h.timezone)::date-1,%s
                    FROM education_memberships m JOIN education_households h USING(household_id)
                    JOIN education_reward_settings s USING(household_id)
                    WHERE m.household_id=%s AND m.user_id=%s AND m.role='student'
                    ON CONFLICT DO NOTHING
                """,
                    (uuid4(), household_id, student_id),
                )
                await cur.execute(
                    "SELECT * FROM education_reward_wallets WHERE household_id=%s AND student_id=%s FOR UPDATE",
                    (household_id, student_id),
                )
                wallet = await cur.fetchone()
                if not wallet:
                    raise LookupError("Student wallet unavailable")
                yield cur, wallet


async def settings(household_id: str, cur=None) -> dict | None:
    if cur is None:
        async with get_db_connection() as conn:
            async with conn.cursor(row_factory=dict_row) as cursor:
                return await settings(household_id, cursor)
    await cur.execute(
        "SELECT * FROM education_reward_settings WHERE household_id=%s", (household_id,)
    )
    return await cur.fetchone()


async def update_prices(household_id: str, user_id: str, prices: dict) -> None:
    async with get_db_connection() as conn:
        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO education_reward_settings(household_id,daily_price,featured_price,rare_price,updated_by_user_id)
                VALUES (%s,%s,%s,%s,%s) ON CONFLICT(household_id) DO UPDATE
                SET daily_price=EXCLUDED.daily_price,featured_price=EXCLUDED.featured_price,
                    rare_price=EXCLUDED.rare_price,updated_at=NOW(),updated_by_user_id=EXCLUDED.updated_by_user_id
            """,
                (
                    household_id,
                    prices["daily"],
                    prices["featured"],
                    prices["rare"],
                    user_id,
                ),
            )


async def credit_completed_tasks(cur, wallet: dict, today: date) -> int:
    await cur.execute(
        """
        INSERT INTO education_reward_point_entries(entry_id,household_id,student_id,kind,amount,task_id)
        SELECT gen_random_uuid(),t.household_id,t.assigned_student_id,'homework',1,t.task_id
        FROM education_tasks t WHERE t.household_id=%s AND t.assigned_student_id=%s
          AND t.status='completed' AND t.occurrence_date<=%s
        ON CONFLICT DO NOTHING RETURNING entry_id
    """,
        (wallet["household_id"], wallet["student_id"], today),
    )
    n = len(await cur.fetchall())
    if n:
        await cur.execute(
            "UPDATE education_reward_wallets SET balance=balance+%s,homework_points=homework_points+%s WHERE household_id=%s AND student_id=%s",
            (n, n, wallet["household_id"], wallet["student_id"]),
        )
        wallet["balance"] += n
        wallet["homework_points"] += n
    return n


async def settlement_inputs(cur, wallet: dict, today: date) -> tuple[list[dict], dict]:
    scope = (
        wallet["household_id"],
        wallet["student_id"],
        wallet["settled_through"],
        today,
    )
    await cur.execute(
        "SELECT task_id,occurrence_date,status,completed_at FROM education_tasks WHERE household_id=%s AND assigned_student_id=%s AND occurrence_date>%s AND occurrence_date<=%s AND status<>'cancelled' ORDER BY occurrence_date,task_id",
        scope,
    )
    tasks = await cur.fetchall()
    await cur.execute(
        "SELECT * FROM education_reward_days WHERE household_id=%s AND student_id=%s AND reward_date>%s AND reward_date<=%s ORDER BY reward_date",
        scope,
    )
    return tasks, {row["reward_date"]: row for row in await cur.fetchall()}


async def insert_day(
    cur, wallet: dict, *, day: date, timezone: str, state: str, task_ids: list
) -> None:
    await cur.execute(
        "INSERT INTO education_reward_days(household_id,student_id,reward_date,timezone,state,task_ids,streak,streak_run_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
        (
            wallet["household_id"],
            wallet["student_id"],
            day,
            timezone,
            state,
            task_ids,
            wallet["streak"],
            wallet["streak_run_id"],
        ),
    )


async def save_cursor(cur, wallet: dict) -> None:
    await cur.execute(
        "UPDATE education_reward_wallets SET settled_through=%s,streak=%s,streak_run_id=%s WHERE household_id=%s AND student_id=%s",
        (
            wallet["settled_through"],
            wallet["streak"],
            wallet["streak_run_id"],
            wallet["household_id"],
            wallet["student_id"],
        ),
    )


async def get_pack(
    cur, wallet: dict, *, pack_id: str | None = None, key: str | None = None
) -> dict | None:
    await cur.execute(
        "SELECT * FROM education_reward_card_packs WHERE household_id=%s AND student_id=%s AND ((%s::uuid IS NOT NULL AND pack_id=%s) OR (%s::uuid IS NOT NULL AND idempotency_key=%s))",
        (wallet["household_id"], wallet["student_id"], pack_id, pack_id, key, key),
    )
    return await cur.fetchone()


async def insert_pack(
    cur,
    wallet: dict,
    *,
    source: str,
    pack_type: str,
    day: date,
    probabilities: dict,
    policy_version: str,
    streak_node=None,
    price=None,
    key=None,
) -> dict:
    await cur.execute(
        """
        INSERT INTO education_reward_card_packs(pack_id,household_id,student_id,source,pack_type,reward_date,probabilities,policy_version,streak_node,price,idempotency_key)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
    """,
        (
            uuid4(),
            wallet["household_id"],
            wallet["student_id"],
            source,
            pack_type,
            day,
            Jsonb(probabilities),
            policy_version,
            streak_node,
            price,
            key,
        ),
    )
    return await cur.fetchone()


async def adjust_points(
    cur, wallet: dict, pack: dict, *, amount: int, kind: str
) -> None:
    if not amount:
        return
    await cur.execute(
        "INSERT INTO education_reward_point_entries(entry_id,household_id,student_id,kind,amount,pack_id) VALUES (%s,%s,%s,%s,%s,%s)",
        (
            uuid4(),
            wallet["household_id"],
            wallet["student_id"],
            kind,
            amount,
            pack["pack_id"],
        ),
    )
    await cur.execute(
        "UPDATE education_reward_wallets SET balance=balance+%s WHERE household_id=%s AND student_id=%s",
        (amount, wallet["household_id"], wallet["student_id"]),
    )
    wallet["balance"] += amount


async def pool_cards(cur, wallet: dict) -> list[dict]:
    # New imports receive explicit known-rarity mappings; unknown rarities stay excluded.
    await cur.execute(
        """
        SELECT c.*,l.reward_level,COALESCE(o.quantity,0) AS owned_count
        FROM education_pokemon_cards c JOIN education_pokemon_reward_levels l USING(card_id)
        LEFT JOIN education_student_pokemon_cards o ON o.card_id=c.card_id AND o.household_id=%s AND o.student_id=%s
        ORDER BY c.card_id
    """,
        (wallet["household_id"], wallet["student_id"]),
    )
    return await cur.fetchall()


async def record_open(
    cur,
    wallet: dict,
    pack: dict,
    card: dict,
    *,
    returned_points: int,
    probabilities: dict,
) -> dict:
    await cur.execute(
        """
        INSERT INTO education_student_pokemon_cards(household_id,student_id,card_id,quantity)
        VALUES (%s,%s,%s,1) ON CONFLICT(household_id,student_id,card_id)
        DO UPDATE SET quantity=education_student_pokemon_cards.quantity+1,last_obtained_at=NOW()
    """,
        (wallet["household_id"], wallet["student_id"], card["card_id"]),
    )
    await cur.execute(
        """
        UPDATE education_reward_card_packs SET card_id=%s,reward_level=%s,owned_before=%s,
            returned_points=%s,effective_probabilities=%s,opened_at=NOW()
        WHERE pack_id=%s RETURNING *
    """,
        (
            card["card_id"],
            card["reward_level"],
            card["owned_count"],
            returned_points,
            Jsonb(probabilities),
            pack["pack_id"],
        ),
    )
    result = await cur.fetchone()
    await adjust_points(cur, wallet, pack, amount=returned_points, kind="duplicate")
    return result


async def get_summary(household_id: str, student_id: str, today: date) -> dict:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT w.balance,w.homework_points,w.streak,w.settled_through,
                  (SELECT count(*) FROM education_reward_card_packs p WHERE p.household_id=m.household_id AND p.student_id=m.user_id AND p.opened_at IS NULL) AS unopened_count,
                  EXISTS(SELECT 1 FROM education_reward_card_packs p WHERE p.household_id=m.household_id AND p.student_id=m.user_id AND p.source='daily' AND p.reward_date=%s) AS today_rewarded
                FROM education_memberships m LEFT JOIN education_reward_wallets w ON w.household_id=m.household_id AND w.student_id=m.user_id
                WHERE m.household_id=%s AND m.user_id=%s AND m.role='student'
            """,
                (today, household_id, student_id),
            )
            result = await cur.fetchone()
            return {
                **result,
                **{k: result[k] or 0 for k in ("balance", "homework_points", "streak")},
            }


async def owned_card(household_id: str, student_id: str, card_id: str) -> dict | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT c.* FROM education_pokemon_cards c JOIN education_student_pokemon_cards o USING(card_id) WHERE o.household_id=%s AND o.student_id=%s AND o.card_id=%s",
                (household_id, student_id, card_id),
            )
            return await cur.fetchone()


async def available_levels() -> list[dict]:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                "SELECT DISTINCT reward_level FROM education_pokemon_reward_levels"
            )
            return await cur.fetchall()


async def page_records(
    household_id: str,
    student_id: str,
    *,
    kind: str,
    page: int,
    page_size: int,
    level=None,
    set_code=None,
    unopened=False,
) -> dict:
    fragments = {
        "packs": (
            "education_reward_card_packs x",
            "x.*",
            "x.created_at DESC,x.pack_id",
        ),
        "transactions": (
            "education_reward_point_entries x LEFT JOIN education_tasks t ON t.task_id=x.task_id LEFT JOIN education_reward_card_packs p ON p.pack_id=x.pack_id",
            "x.*,t.title AS task_title,p.pack_type",
            "x.created_at DESC,x.entry_id",
        ),
        "collection": (
            "education_student_pokemon_cards x JOIN education_pokemon_cards c USING(card_id) JOIN education_pokemon_reward_levels l USING(card_id)",
            "c.*,x.quantity,x.first_obtained_at,x.last_obtained_at,l.reward_level",
            "x.last_obtained_at DESC,x.card_id",
        ),
    }
    table, columns, order = fragments[kind]
    where = "x.household_id=%s AND x.student_id=%s"
    params = [household_id, student_id]
    if kind == "collection":
        if level:
            where += " AND l.reward_level=%s"
            params.append(level)
        if set_code:
            where += " AND c.set_code=%s"
            params.append(set_code)
    if kind == "packs" and unopened:
        where += " AND x.opened_at IS NULL"
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                f"SELECT count(*) AS n FROM {table} WHERE {where}", params
            )
            total = (await cur.fetchone())["n"]
            page = min(page, max(1, (total + page_size - 1) // page_size))
            await cur.execute(
                f"SELECT {columns} FROM {table} WHERE {where} ORDER BY {order} LIMIT %s OFFSET %s",
                (*params, page_size, (page - 1) * page_size),
            )
            result = dict(
                items=await cur.fetchall(), total=total, page=page, page_size=page_size
            )
            if kind == "collection":
                await cur.execute(
                    "SELECT DISTINCT c.set_code,c.series_name FROM education_student_pokemon_cards x JOIN education_pokemon_cards c USING(card_id) WHERE x.household_id=%s AND x.student_id=%s ORDER BY c.set_code,c.series_name",
                    (household_id, student_id),
                )
                result["series"] = await cur.fetchall()
            return result
