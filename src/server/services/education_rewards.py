"""Learning rewards isolated from the agent runtime."""

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from src.server.database import education_rewards as db
from src.server.database.education_members import get_membership_for_user
from src.server.database.education_tasks import (
    list_active_rule_timezones_for_user,
    materialize_task_rule_through,
)
from src.server.services import education_reward_rules as rules
from src.server.services.education_pokemon_catalog import read_card_image


class RewardAccessError(PermissionError):
    pass


class RewardConflict(ValueError):
    pass


class RewardNotFound(LookupError):
    pass


async def scope(
    user_id: str, student_id: str | None = None, *, write=False
) -> tuple[dict, str]:
    member = await get_membership_for_user(user_id)
    if not member or member["role"] not in {"parent", "student"}:
        raise RewardAccessError("请先加入家庭账户。")
    if write and member["role"] != "student":
        raise RewardAccessError("只有学生可以兑换和打开自己的卡包。")
    target = student_id or (user_id if member["role"] == "student" else None)
    if not target or member["role"] == "student" and target != user_id:
        raise RewardAccessError("请选择家庭中的学生。")
    child = member if target == user_id else await get_membership_for_user(target)
    if (
        not child
        or child["role"] != "student"
        or child["household_id"] != member["household_id"]
    ):
        raise RewardAccessError("无法访问这个学生的奖励。")
    return member, target


def local_today(member: dict, now=None):
    return (
        (now or datetime.now(timezone.utc))
        .astimezone(ZoneInfo(member["timezone"]))
        .date()
    )


def pack_policy(pack_type: str) -> dict:
    return {
        level: float(weight)
        for level, weight in rules.PACK_LEVEL_PROBABILITIES[pack_type].items()
    }


async def sync(*, user_id: str, student_id: str | None = None, now=None) -> dict:
    member, student = await scope(user_id, student_id)
    hid = str(member["household_id"])
    today = local_today(member, now)
    async with db.wallet_transaction(hid, student) as (_, wallet):
        start = wallet["settled_through"] + timedelta(days=1)
    # Recurrence takes rule/task locks before the separate wallet transaction.
    for rule in await list_active_rule_timezones_for_user(user_id):
        if rule["assigned_student_id"] != student:
            continue
        cursor = start
        while cursor <= today:
            end = min(today, cursor + timedelta(days=61))
            await materialize_task_rule_through(
                task_rule_id=str(rule["task_rule_id"]),
                from_date=cursor,
                through_date=end,
            )
            cursor = end + timedelta(days=1)
    async with db.wallet_transaction(hid, student) as (cur, wallet):
        await db.credit_completed_tasks(cur, wallet, today)
        tasks, snapshots = await db.settlement_inputs(cur, wallet, today)
        by_day = defaultdict(list)
        for task in tasks:
            by_day[task["occurrence_date"]].append(task)
        day = wallet["settled_through"] + timedelta(days=1)
        zone = ZoneInfo(member["timezone"])
        while day <= today:
            snapshot = snapshots.get(day)
            items = by_day[day]
            if snapshot:
                wallet["streak"] = snapshot["streak"]
                wallet["streak_run_id"] = snapshot["streak_run_id"]
            else:
                cutoff = datetime.combine(
                    day + timedelta(days=1), datetime.min.time(), zone
                )
                complete = bool(items) and all(
                    t["status"] == "completed"
                    and (
                        day == today or t["completed_at"] and t["completed_at"] < cutoff
                    )
                    for t in items
                )
                if day == today and not complete:
                    break
                state = "completed" if complete else "missed" if items else "empty"
                if complete:
                    wallet["streak"] += 1
                elif items:
                    wallet["streak"] = 0
                    wallet["streak_run_id"] = uuid4()
                await db.insert_day(
                    cur,
                    wallet,
                    day=day,
                    timezone=member["timezone"],
                    state=state,
                    task_ids=[t["task_id"] for t in items],
                )
                if complete and day == today:
                    for source, node in [
                        ("daily", None),
                        ("streak", rules.eligible_streak_node(wallet["streak"])),
                    ]:
                        if source == "streak" and node is None:
                            continue
                        code = rules.choose_pack_type(source, node)
                        await db.insert_pack(
                            cur,
                            wallet,
                            source=source,
                            pack_type=code,
                            day=day,
                            probabilities=pack_policy(code),
                            policy_version=rules.POLICY_VERSION,
                            streak_node=node,
                        )
            # Keep today in the cursor range, so its immutable snapshot is reused.
            wallet["settled_through"] = min(day, today - timedelta(days=1))
            day += timedelta(days=1)
        await db.save_cursor(cur, wallet)
    return await summary(user_id=user_id, student_id=student, now=now)


async def summary(*, user_id: str, student_id: str | None = None, now=None) -> dict:
    member, student = await scope(user_id, student_id)
    result = await db.get_summary(
        str(member["household_id"]), student, local_today(member, now)
    )
    return {
        **result,
        "student_id": student,
        "next_streak_node": rules.next_streak_node(result["streak"]),
    }


async def get_settings(*, user_id: str) -> dict:
    member = await get_membership_for_user(user_id)
    if not member:
        raise RewardAccessError("请先加入家庭账户。")
    row = await db.settings(str(member["household_id"])) or {}
    levels = await db.available_levels()
    return dict(
        prices={k: row.get(f"{k}_price", v) for k, v in rules.DEFAULT_PRICES.items()},
        probabilities={k: pack_policy(k) for k in rules.PACK_NAMES},
        effective_probabilities={
            k: rules.effective_probabilities(levels, pack_policy(k))
            for k in rules.PACK_NAMES
        },
        pack_names=rules.PACK_NAMES,
        level_names=rules.LEVEL_NAMES,
        updated_at=row.get("updated_at"),
    )


async def update_settings(*, user_id: str, prices: dict) -> dict:
    member = await get_membership_for_user(user_id)
    if not member or member["role"] != "parent":
        raise RewardAccessError("只有家长可以修改奖励价格。")
    if set(prices) != set(rules.DEFAULT_PRICES) or any(
        type(n) is not int or not 1 <= n <= 10000 for n in prices.values()
    ):
        raise RewardConflict("价格必须是 1–10000 的整数。")
    await db.update_prices(str(member["household_id"]), user_id, prices)
    return await get_settings(user_id=user_id)


async def purchase(
    *, user_id: str, pack_type: str, expected_price: int, idempotency_key: str
) -> dict:
    member, student = await scope(user_id, write=True)
    if pack_type not in rules.PACK_NAMES:
        raise RewardConflict("卡包类型无效。")
    async with db.wallet_transaction(str(member["household_id"]), student) as (
        cur,
        wallet,
    ):
        prior = await db.get_pack(cur, wallet, key=idempotency_key)
        if prior:
            if prior["pack_type"] != pack_type or prior["price"] != expected_price:
                raise RewardConflict("同一兑换请求不能更改卡包或价格。")
            return prior
        price = (await db.settings(str(member["household_id"]), cur))[
            f"{pack_type}_price"
        ]
        if price != expected_price:
            raise RewardConflict("卡包价格已变化，请刷新后重新确认。")
        if wallet["balance"] < price:
            raise RewardConflict("可兑换积分不足。")
        probabilities = pack_policy(pack_type)
        effective = rules.effective_probabilities(
            await db.pool_cards(cur, wallet), probabilities
        )
        if not any(effective.values()):
            raise RewardConflict("卡池暂无可用卡牌。")
        pack = await db.insert_pack(
            cur,
            wallet,
            source="purchase",
            pack_type=pack_type,
            day=local_today(member),
            probabilities=probabilities,
            policy_version=rules.POLICY_VERSION,
            price=price,
            key=idempotency_key,
        )
        await db.adjust_points(cur, wallet, pack, amount=-price, kind="purchase")
        return pack


async def open_pack(*, user_id: str, pack_id: str) -> dict:
    member, student = await scope(user_id, write=True)
    async with db.wallet_transaction(str(member["household_id"]), student) as (
        cur,
        wallet,
    ):
        pack = await db.get_pack(cur, wallet, pack_id=pack_id)
        if not pack:
            raise RewardNotFound("卡包不存在。")
        if not pack["opened_at"]:
            try:
                card, effective = rules.draw_card(
                    await db.pool_cards(cur, wallet), pack["probabilities"]
                )
            except ValueError as exc:
                raise RewardConflict(str(exc)) from exc
            refund = (
                rules.duplicate_return_points(
                    card["reward_level"], pack_price=pack["price"]
                )
                if card["owned_count"]
                else 0
            )
            pack = await db.record_open(
                cur, wallet, pack, card, returned_points=refund, probabilities=effective
            )
    card = await db.owned_card(
        str(member["household_id"]), student, str(pack["card_id"])
    )
    return {**pack, "card": card}


async def list_records(
    *,
    user_id: str,
    student_id: str | None = None,
    kind: str,
    page: int,
    page_size: int,
    **filters,
) -> dict:
    member, student = await scope(user_id, student_id)
    return await db.page_records(
        str(member["household_id"]),
        student,
        kind=kind,
        page=page,
        page_size=page_size,
        **filters,
    )


async def get_card_image(
    *, user_id: str, student_id: str | None, card_id: str, if_none_match: str | None
):
    member, student = await scope(user_id, student_id)
    card = await db.owned_card(str(member["household_id"]), student, card_id)
    if not card:
        raise RewardNotFound("尚未拥有这张卡牌。")
    return await read_card_image(card, if_none_match=if_none_match)
