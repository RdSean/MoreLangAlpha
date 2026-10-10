"""Real transaction contracts for learning rewards."""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
import pytest_asyncio

from src.server.database import education_rewards as db
from src.server.database.education_pokemon_cards import upsert_pokemon_cards
from src.server.services import education_rewards as rewards
from tests.integration.test_education_pokemon_cards_db import record

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest_asyncio.fixture
async def family(db_conn, patched_get_db_connection):
    parent, student = f"reward-parent-{uuid4()}", f"reward-student-{uuid4()}"
    household, rule = uuid4(), uuid4()
    today = datetime.now(timezone.utc).date()
    await db_conn.execute(
        "INSERT INTO users(user_id,name) VALUES (%s,'Parent'),(%s,'Student')",
        (parent, student),
    )
    async with db_conn.transaction():
        await db_conn.execute(
            "INSERT INTO education_households(household_id,name,timezone,model_owner_user_id) VALUES (%s,'Rewards','UTC',%s)",
            (household, parent),
        )
        await db_conn.execute(
            "INSERT INTO education_memberships(household_id,user_id,role,display_name) VALUES (%s,%s,'parent','Parent'),(%s,%s,'student','Student')",
            (household, parent, household, student),
        )
    await db_conn.execute(
        "INSERT INTO education_task_rules(task_rule_id,household_id,created_by_user_id,assigned_student_id,title,recurrence,timezone,subject_code,type_code,grade_code) VALUES (%s,%s,%s,%s,'Read',%s::jsonb,'UTC','chinese','read','g5')",
        (
            rule,
            household,
            parent,
            student,
            '{"frequency":"once","start_date":"' + str(today) + '","due_time":"18:00"}',
        ),
    )
    await upsert_pokemon_cards([{**record(f"reward-{uuid4()}"), "rarity": "普通"}])
    await db_conn.execute(
        "INSERT INTO education_pokemon_reward_levels SELECT card_id,'basic' FROM education_pokemon_cards WHERE rarity='普通' ON CONFLICT DO NOTHING"
    )
    return dict(
        parent=parent, student=student, household=household, rule=rule, today=today
    )


async def task(conn, f, day, *, completed=True, late=False):
    tid = uuid4()
    at = datetime.combine(
        day + timedelta(days=int(late)), datetime.min.time(), timezone.utc
    )
    result = await conn.execute(
        "INSERT INTO education_tasks(task_id,task_rule_id,household_id,assigned_student_id,occurrence_date,due_at,title,subject_code,type_code,grade_code,status,completed_at) VALUES (%s,%s,%s,%s,%s,%s,'Read','chinese','read','g5',%s,%s) ON CONFLICT(task_rule_id,occurrence_date) DO UPDATE SET status=EXCLUDED.status,completed_at=EXCLUDED.completed_at RETURNING task_id",
        (
            tid,
            f["rule"],
            f["household"],
            f["student"],
            day,
            at,
            "completed" if completed else "open",
            at if completed else None,
        ),
    )
    return (await result.fetchone())["task_id"]


async def test_sync_recovers_points_once_and_daily_pack_once(db_conn, family):
    f = family
    await task(db_conn, f, f["today"] - timedelta(days=1), late=True)
    await task(db_conn, f, f["today"])
    await task(db_conn, f, f["today"] + timedelta(days=1))
    results = await asyncio.gather(
        *(rewards.sync(user_id=f["student"]) for _ in range(3))
    )
    assert all(
        r["balance"] == 2 and r["homework_points"] == 2 and r["unopened_count"] == 1
        for r in results
    )
    assert results[0]["streak"] == 1
    assert (
        await rewards.list_records(
            user_id=f["student"], kind="packs", page=1, page_size=20
        )
    )["total"] == 1


async def test_purchase_and_open_are_atomic_idempotent(db_conn, family):
    f = family
    for n in range(6):
        await task(db_conn, f, f["today"] - timedelta(days=n + 1))
    await rewards.sync(user_id=f["student"])
    key = str(uuid4())
    buys = await asyncio.gather(
        *(
            rewards.purchase(
                user_id=f["student"],
                pack_type="daily",
                expected_price=5,
                idempotency_key=key,
            )
            for _ in range(3)
        )
    )
    assert len({str(p["pack_id"]) for p in buys}) == 1
    with pytest.raises(rewards.RewardConflict):
        await rewards.purchase(
            user_id=f["student"],
            pack_type="rare",
            expected_price=30,
            idempotency_key=key,
        )
    with pytest.raises(rewards.RewardConflict):
        await rewards.purchase(
            user_id=f["student"],
            pack_type="daily",
            expected_price=5,
            idempotency_key=str(uuid4()),
        )
    opened = await asyncio.gather(
        *(
            rewards.open_pack(user_id=f["student"], pack_id=str(buys[0]["pack_id"]))
            for _ in range(3)
        )
    )
    assert len({str(p["card_id"]) for p in opened}) == 1
    assert opened[0]["owned_before"] == 0
    summary = await rewards.summary(user_id=f["student"])
    assert summary["balance"] == 1 and summary["homework_points"] == 6
    cards = await rewards.list_records(
        user_id=f["student"], kind="collection", page=1, page_size=20
    )
    assert cards["total"] == 1 and cards["items"][0]["quantity"] == 1
    async with db.wallet_transaction(str(f["household"]), f["student"]) as (
        cur,
        wallet,
    ):
        await cur.execute(
            "SELECT sum(amount) AS n FROM education_reward_point_entries WHERE household_id=%s AND student_id=%s",
            (f["household"], f["student"]),
        )
        assert (await cur.fetchone())["n"] == wallet["balance"]


async def test_parent_read_only_and_sibling_scope(db_conn, family):
    f = family
    await task(db_conn, f, f["today"])
    await rewards.sync(user_id=f["parent"], student_id=f["student"])
    assert (await rewards.summary(user_id=f["parent"], student_id=f["student"]))[
        "balance"
    ] == 1
    with pytest.raises(rewards.RewardAccessError):
        await rewards.open_pack(user_id=f["parent"], pack_id=str(uuid4()))
    with pytest.raises(rewards.RewardAccessError):
        await rewards.summary(user_id=f["student"], student_id=f["parent"])
    with pytest.raises(rewards.RewardAccessError):
        await rewards.update_settings(
            user_id=f["student"], prices={"daily": 1, "featured": 2, "rare": 3}
        )
    await rewards.update_settings(
        user_id=f["parent"], prices={"daily": 1, "featured": 2, "rare": 3}
    )
    with pytest.raises(rewards.RewardConflict, match="价格"):
        await rewards.purchase(
            user_id=f["student"],
            pack_type="daily",
            expected_price=5,
            idempotency_key=str(uuid4()),
        )


async def test_streak_freezes_late_work_and_ignores_empty_days(db_conn, family):
    f = family
    await rewards.sync(user_id=f["student"])
    start = f["today"] - timedelta(days=5)
    await db_conn.execute(
        "UPDATE education_reward_wallets SET started_on=%s,settled_through=%s WHERE student_id=%s",
        (start, start - timedelta(days=1), f["student"]),
    )
    for d in (0, 2, 4, 5):
        await task(db_conn, f, start + timedelta(days=d))
    result = await rewards.sync(user_id=f["student"])
    assert result["streak"] == 4 and result["unopened_count"] == 1
    # Historical qualifying days advance the streak but do not mint old packs.
    await task(db_conn, f, start + timedelta(days=1), completed=False)
    assert (await rewards.sync(user_id=f["student"]))["streak"] == 4
    await db_conn.execute(
        "UPDATE education_reward_wallets SET settled_through=%s,streak=6 WHERE student_id=%s",
        (f["today"] - timedelta(days=1), f["student"]),
    )
    assert (await rewards.sync(user_id=f["student"]))["streak"] == 4


@pytest.mark.parametrize("streak", [2, 4, 6, 13])
async def test_today_streak_nodes_issue_exactly_one_extra_pack(db_conn, family, streak):
    f = family
    await rewards.sync(user_id=f["student"])
    await db_conn.execute(
        "UPDATE education_reward_wallets SET streak=%s WHERE student_id=%s",
        (streak, f["student"]),
    )
    await task(db_conn, f, f["today"])
    summary = await rewards.sync(user_id=f["student"])
    assert summary["streak"] == streak + 1 and summary["unopened_count"] == 2
    assert (await rewards.sync(user_id=f["student"]))["unopened_count"] == 2
    packs = await rewards.list_records(
        user_id=f["student"], kind="packs", page=1, page_size=20
    )
    extra = next(p for p in packs["items"] if p["source"] == "streak")
    assert extra["streak_node"] == streak + 1


async def test_missed_day_resets_streak_and_late_submission_only_credits_points(
    db_conn, family
):
    f = family
    await rewards.sync(user_id=f["student"])
    yesterday = f["today"] - timedelta(days=1)
    await db_conn.execute(
        "UPDATE education_reward_wallets SET started_on=%s,settled_through=%s,streak=6 WHERE student_id=%s",
        (yesterday, yesterday - timedelta(days=1), f["student"]),
    )
    tid = await task(db_conn, f, yesterday, completed=False)
    await task(db_conn, f, f["today"])
    assert (await rewards.sync(user_id=f["student"]))["streak"] == 1
    await db_conn.execute(
        "UPDATE education_tasks SET status='completed',completed_at=NOW() WHERE task_id=%s",
        (tid,),
    )
    late = await rewards.sync(user_id=f["student"])
    assert late["streak"] == 1 and late["balance"] == 2 and late["unopened_count"] == 1


async def test_future_task_waits_for_household_midnight(db_conn, family):
    f = family
    future = f["today"] + timedelta(days=1)
    await task(db_conn, f, future)
    assert (await rewards.sync(user_id=f["student"]))["balance"] == 0
    clock = datetime.combine(future, datetime.min.time(), timezone.utc)
    assert (await rewards.sync(user_id=f["student"], now=clock))["balance"] == 1


async def test_empty_pool_never_spends_and_duplicate_refunds_once(
    db_conn, family, monkeypatch
):
    f = family
    for n in range(6):
        await task(db_conn, f, f["today"] - timedelta(days=n + 1))
    await rewards.sync(user_id=f["student"])
    await rewards.update_settings(
        user_id=f["parent"], prices={"daily": 1, "featured": 15, "rare": 30}
    )
    # Pick the same known card to test duplicate accounting independently of randomness.
    original = rewards.rules.draw_card

    def fixed(cards, probabilities):
        return cards[0], rewards.rules.effective_probabilities(cards, probabilities)

    monkeypatch.setattr(rewards.rules, "draw_card", fixed)
    for _ in range(2):
        p = await rewards.purchase(
            user_id=f["student"],
            pack_type="daily",
            expected_price=1,
            idempotency_key=str(uuid4()),
        )
        result = await rewards.open_pack(
            user_id=f["student"], pack_id=str(p["pack_id"])
        )
    assert result["owned_before"] == 1 and result["returned_points"] == 0
    await rewards.open_pack(user_id=f["student"], pack_id=str(p["pack_id"]))
    assert (await rewards.summary(user_id=f["student"]))["balance"] == 4
    monkeypatch.setattr(rewards.rules, "draw_card", original)
    await db_conn.execute("DELETE FROM education_pokemon_reward_levels")
    with pytest.raises(rewards.RewardConflict, match="卡池"):
        await rewards.purchase(
            user_id=f["student"],
            pack_type="daily",
            expected_price=1,
            idempotency_key=str(uuid4()),
        )
    assert (await rewards.summary(user_id=f["student"]))["balance"] == 4


async def test_migration_backfills_due_completions_without_historical_packs(
    db_conn, family, test_db_uri
):
    from alembic import command
    from alembic.config import Config

    f = family
    await task(db_conn, f, f["today"] - timedelta(days=30))
    await task(db_conn, f, f["today"] + timedelta(days=30))
    before = (
        await (
            await db_conn.execute("SELECT count(*) AS n FROM education_pokemon_cards")
        ).fetchone()
    )["n"]
    cfg = Config("alembic.ini")
    cfg.set_main_option(
        "sqlalchemy.url",
        test_db_uri.replace("postgresql://", "postgresql+psycopg://", 1),
    )
    await asyncio.to_thread(command.downgrade, cfg, "091_pokemon_cards")
    await asyncio.to_thread(command.upgrade, cfg, "head")
    summary = await rewards.summary(user_id=f["student"])
    assert (
        summary["balance"] == 1
        and summary["homework_points"] == 1
        and summary["unopened_count"] == 0
    )
    assert (
        await (
            await db_conn.execute("SELECT count(*) AS n FROM education_pokemon_cards")
        ).fetchone()
    )["n"] == before
    assert (
        await (
            await db_conn.execute(
                "SELECT count(*) AS n FROM education_tasks WHERE household_id=%s",
                (f["household"],),
            )
        ).fetchone()
    )["n"] == 2


async def test_distinct_simultaneous_purchases_cannot_overdraw(db_conn, family):
    f = family
    for n in range(6):
        await task(db_conn, f, f["today"] - timedelta(days=n + 1))
    await rewards.sync(user_id=f["student"])
    results = await asyncio.gather(
        *(
            rewards.purchase(
                user_id=f["student"],
                pack_type="daily",
                expected_price=5,
                idempotency_key=str(uuid4()),
            )
            for _ in range(3)
        ),
        return_exceptions=True,
    )
    assert sum(isinstance(r, dict) for r in results) == 1
    assert sum(isinstance(r, rewards.RewardConflict) for r in results) == 2
    assert (await rewards.summary(user_id=f["student"]))["balance"] == 1


async def test_parallel_last_checkins_credit_twice_but_award_one_daily_pack(
    db_conn, family
):
    from src.server.services.education_tasks import check_in_task

    f = family
    a = await task(db_conn, f, f["today"], completed=False)
    other_rule = uuid4()
    b = uuid4()
    await db_conn.execute(
        "INSERT INTO education_task_rules(task_rule_id,household_id,created_by_user_id,assigned_student_id,title,recurrence,timezone,subject_code,type_code,grade_code) SELECT %s,household_id,created_by_user_id,assigned_student_id,title,recurrence,timezone,subject_code,type_code,grade_code FROM education_task_rules WHERE task_rule_id=%s",
        (other_rule, f["rule"]),
    )
    await db_conn.execute(
        "INSERT INTO education_tasks(task_id,task_rule_id,household_id,assigned_student_id,occurrence_date,due_at,title,subject_code,type_code,grade_code,status) SELECT %s,%s,household_id,assigned_student_id,occurrence_date,due_at,title,subject_code,type_code,grade_code,'open' FROM education_tasks WHERE task_id=%s",
        (b, other_rule, a),
    )
    await asyncio.gather(
        *(
            check_in_task(
                student_user_id=f["student"],
                task_id=str(tid),
                submission_text="",
                idempotency_key=str(tid),
                asset_ids=[],
            )
            for tid in (a, b)
        )
    )
    summary = await rewards.sync(user_id=f["student"])
    assert summary["balance"] == 2 and summary["unopened_count"] == 1
    # Same-family sibling cannot read this wallet, a pack, or a card image.
    sibling = f"sibling-{uuid4()}"
    await db_conn.execute(
        "INSERT INTO users(user_id,name) VALUES (%s,'Sibling')", (sibling,)
    )
    await db_conn.execute(
        "INSERT INTO education_memberships(household_id,user_id,role,display_name) VALUES (%s,%s,'student','Sibling')",
        (f["household"], sibling),
    )
    with pytest.raises(rewards.RewardAccessError):
        await rewards.summary(user_id=sibling, student_id=f["student"])
    packs = await rewards.list_records(
        user_id=f["student"], kind="packs", page=1, page_size=20
    )
    with pytest.raises(rewards.RewardNotFound):
        await rewards.open_pack(
            user_id=sibling, pack_id=str(packs["items"][0]["pack_id"])
        )
    result = await rewards.open_pack(
        user_id=f["student"], pack_id=str(packs["items"][0]["pack_id"])
    )
    with pytest.raises(rewards.RewardNotFound):
        await rewards.get_card_image(
            user_id=sibling,
            student_id=None,
            card_id=str(result["card_id"]),
            if_none_match=None,
        )
