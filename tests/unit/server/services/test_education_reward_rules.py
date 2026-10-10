from decimal import Decimal

import pytest

from src.server.services.education_reward_rules import (
    CARD_REWARD_LEVELS,
    PACK_LEVEL_PROBABILITIES,
    choose_card,
    choose_pack_type,
    classify_rarity,
    duplicate_return_points,
    draw_card,
    effective_probabilities,
    eligible_streak_node,
    next_streak_node,
)


class SequenceRandom:
    def __init__(self, values):
        self.values = iter(values)

    def random(self):
        return next(self.values)


def test_classifies_known_rarities_without_falling_back_to_basic():
    assert classify_rarity("普通") == "basic"
    assert classify_rarity("插画稀有") == "featured"
    assert classify_rarity("特别插画稀有") == "legendary"
    assert classify_rarity("未来稀有") == "featured"
    assert classify_rarity("未知稀有度") is None


@pytest.mark.parametrize(
    "days,expected",
    [
        (1, None),
        (2, None),
        (3, 3),
        (4, None),
        (5, 5),
        (7, 7),
        (14, 14),
        (21, 21),
        (8, None),
    ],
)
def test_streak_nodes(days, expected):
    assert eligible_streak_node(days) == expected


def test_pack_type_uses_node_probabilities_and_deterministic_random_source():
    assert choose_pack_type("streak", 3, SequenceRandom([0.0])) == "daily"
    assert choose_pack_type("streak", 3, SequenceRandom([0.71])) == "featured"
    assert choose_pack_type("streak", 5, SequenceRandom([0.95])) == "rare"
    assert choose_pack_type("purchase", None, SequenceRandom([0.99])) == "daily"
    assert PACK_LEVEL_PROBABILITIES["rare"]["legendary"] == Decimal("0.05")


def test_choose_card_reduces_duplicate_weight_without_excluding_owned_cards():
    cards = [
        {"card_id": "new", "reward_level": "basic", "owned_count": 0},
        {"card_id": "owned", "reward_level": "basic", "owned_count": 1},
    ]
    assert choose_card(cards, SequenceRandom([0.99]))["card_id"] == "owned"
    assert choose_card(cards, SequenceRandom([0.75]))["card_id"] == "new"
    assert choose_card(cards, SequenceRandom([0.5]))["card_id"] == "new"


@pytest.mark.parametrize(
    "level,points",
    [("basic", 1), ("rare", 2), ("featured", 3), ("premium", 5), ("legendary", 8)],
)
def test_duplicate_points_are_bounded_by_pack_price(level, points):
    assert duplicate_return_points(level, pack_price=3) <= 2
    assert duplicate_return_points(level, pack_price=None) == points


def test_all_imported_levels_are_declared():
    assert set(CARD_REWARD_LEVELS) == {
        "basic",
        "rare",
        "featured",
        "premium",
        "legendary",
    }


def test_empty_levels_renormalize_without_changing_duplicate_level_odds():
    cards = [{"card_id": "a", "reward_level": "rare", "owned_count": 99}]
    values = effective_probabilities(cards, PACK_LEVEL_PROBABILITIES["daily"])
    assert values["rare"] == 1 and values["basic"] == 0
    card, effective = draw_card(
        cards, PACK_LEVEL_PROBABILITIES["daily"], SequenceRandom([0.99, 0.99])
    )
    assert card["card_id"] == "a" and effective == values
    with pytest.raises(ValueError, match="卡池"):
        draw_card([], PACK_LEVEL_PROBABILITIES["daily"])


@pytest.mark.parametrize(
    "days,node", [(0, 3), (3, 5), (5, 7), (7, 14), (13, 14), (14, 21)]
)
def test_next_streak_reward(days, node):
    assert next_streak_node(days) == node
