"""Versioned reward policy; independent of persistence and agent runtimes."""

from decimal import Decimal
from random import SystemRandom

POLICY_VERSION = "homework-cards-v1"
CARD_REWARD_LEVELS = {
    "basic": {"普通", "非普通"},
    "rare": {"稀有", "皮卡丘稀有"},
    "featured": {"插画稀有", "未来稀有", "惊人稀有"},
    "premium": {
        "双倍稀有",
        "稀有（闪光）",
        "稀有（闪光）GX",
        "稀有（闪光）EX",
        "闪光稀有 VMAX",
        "BREAK 稀有",
        "稀有 Prime",
        "稀有（闪光）ex",
        "闪光稀有 V",
        "闪光稀有 VSTAR",
        "稀有（闪光）LV.X",
    },
    "legendary": {"特别插画稀有", "LEGEND 传说", "秘密稀有", "超稀有"},
}
LEVEL_NAMES = dict(zip(CARD_REWARD_LEVELS, ["基础", "稀有", "精选", "高级", "传说"]))
PACK_NAMES = {"daily": "日常包", "featured": "精选包", "rare": "稀有包"}
DEFAULT_PRICES = {"daily": 5, "featured": 15, "rare": 30}
PACK_LEVEL_PROBABILITIES = {
    code: dict(zip(CARD_REWARD_LEVELS, map(Decimal, weights)))
    for code, weights in {
        "daily": ["0.85", "0.15", "0", "0", "0"],
        "featured": ["0.20", "0.50", "0.25", "0.05", "0"],
        "rare": ["0", "0.20", "0.45", "0.30", "0.05"],
    }.items()
}


def classify_rarity(rarity: str) -> str | None:
    return next(
        (level for level, names in CARD_REWARD_LEVELS.items() if rarity in names), None
    )


def eligible_streak_node(days: int) -> int | None:
    return days if days in {3, 5, 7} or days > 7 and days % 7 == 0 else None


def next_streak_node(days: int) -> int:
    return next((node for node in (3, 5, 7) if node > days), (days // 7 + 1) * 7)


def weighted_choice(items, weights, rng=None):
    rng = rng or SystemRandom()
    total = sum(weights)
    if not items or total <= 0:
        raise ValueError("卡池暂无可用卡牌。")
    target = rng.random() * float(total)
    running = 0.0
    for item, weight in zip(items, weights, strict=True):
        running += float(weight)
        if target < running:
            return item
    return items[-1]


def choose_pack_type(source: str, streak: int | None, rng=None) -> str:
    if source != "streak":
        return "daily"
    weights = (
        [0.7, 0.3, 0]
        if streak == 3
        else [0.3, 0.6, 0.1]
        if streak == 5
        else [0, 0.7, 0.3]
    )
    return weighted_choice(list(PACK_NAMES), weights, rng)


def effective_probabilities(cards: list[dict], probabilities: dict) -> dict[str, float]:
    available = {card["reward_level"] for card in cards}
    weights = {
        level: float(weight) if level in available else 0.0
        for level, weight in probabilities.items()
    }
    total = sum(weights.values())
    return {
        level: weight / total if total else 0.0 for level, weight in weights.items()
    }


def choose_card(cards: list[dict], rng=None) -> dict:
    return weighted_choice(
        cards, [1 / (1 + 3 * card.get("owned_count", 0)) for card in cards], rng
    )


def draw_card(cards: list[dict], probabilities: dict, rng=None) -> tuple[dict, dict]:
    effective = effective_probabilities(cards, probabilities)
    level = weighted_choice(list(effective), list(effective.values()), rng)
    return choose_card(
        [card for card in cards if card["reward_level"] == level], rng
    ), effective


def duplicate_return_points(level: str, *, pack_price: int | None) -> int:
    points = {"basic": 1, "rare": 2, "featured": 3, "premium": 5, "legendary": 8}[level]
    return points if pack_price is None else min(points, max(0, pack_price - 1))
