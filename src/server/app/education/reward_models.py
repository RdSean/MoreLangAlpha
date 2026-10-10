"""Public reward contracts; storage object locations never leave the server."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.server.app.education.pokemon_cards import PokemonCardResponse

PackType = Literal["daily", "featured", "rare"]
RewardLevel = Literal["basic", "rare", "featured", "premium", "legendary"]


class RewardSummary(BaseModel):
    student_id: str
    balance: int
    homework_points: int
    streak: int
    next_streak_node: int
    unopened_count: int
    today_rewarded: bool
    settled_through: date | None


class RewardPack(BaseModel):
    pack_id: UUID
    source: Literal["daily", "streak", "purchase"]
    pack_type: PackType
    reward_date: date
    streak_node: int | None
    price: int | None
    probabilities: dict[RewardLevel, float]
    policy_version: str
    card_id: UUID | None
    reward_level: RewardLevel | None
    owned_before: int | None
    returned_points: int
    effective_probabilities: dict[RewardLevel, float] | None
    created_at: datetime
    opened_at: datetime | None


class OpenedRewardPack(RewardPack):
    card: PokemonCardResponse


class RewardCollectionCard(PokemonCardResponse):
    quantity: int
    reward_level: RewardLevel
    first_obtained_at: datetime
    last_obtained_at: datetime


class RewardTransaction(BaseModel):
    entry_id: UUID
    kind: Literal["homework", "purchase", "duplicate"]
    amount: int
    task_id: UUID | None
    task_title: str | None
    pack_id: UUID | None
    pack_type: PackType | None
    created_at: datetime


class RewardPage[T](BaseModel):
    items: list[T]
    total: int
    page: int
    page_size: int


class CollectionSeries(BaseModel):
    set_code: str
    series_name: str


class RewardCollectionPage(RewardPage[RewardCollectionCard]):
    series: list[CollectionSeries]


class PurchaseRequest(BaseModel):
    pack_type: PackType
    expected_price: int = Field(ge=1, le=10000, strict=True)
    idempotency_key: UUID


class RewardPrices(BaseModel):
    daily: int = Field(ge=1, le=10000, strict=True)
    featured: int = Field(ge=1, le=10000, strict=True)
    rare: int = Field(ge=1, le=10000, strict=True)


class RewardSettings(BaseModel):
    prices: RewardPrices
    probabilities: dict[PackType, dict[RewardLevel, float]]
    effective_probabilities: dict[PackType, dict[RewardLevel, float]]
    pack_names: dict[PackType, str]
    level_names: dict[RewardLevel, str]
    updated_at: datetime | None
