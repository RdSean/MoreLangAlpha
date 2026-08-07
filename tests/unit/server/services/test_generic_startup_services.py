"""The generic platform must not boot financial background services."""

from __future__ import annotations

import inspect
from pathlib import Path

import yaml

from src.server.app import setup


RETIRED_STARTUP_COMPONENTS = (
    "market_data_feed",
    "price_monitor",
    "insight_service",
    "news_refresh_service",
    "market_protocol.calendars",
)

RETIRED_CONFIG_KEYS = {
    "market_data",
    "news_data",
    "news_poll",
    "market_watch",
    "market_insight",
}

RETIRED_SCHEMA_TERMS = (
    "watchlists",
    "watchlist_items",
    "user_portfolios",
    "market_insights",
    "risk_preference",
    "investment_preference",
)


def test_lifespan_has_no_finance_startup_or_shutdown_components():
    lifecycle_source = inspect.getsource(setup.lifespan)

    assert not [
        component
        for component in RETIRED_STARTUP_COMPONENTS
        if component in lifecycle_source
    ]


def test_platform_config_has_no_finance_service_sections():
    config_path = Path(__file__).parents[4] / "config.yaml"
    config = yaml.safe_load(config_path.read_text())

    assert not (RETIRED_CONFIG_KEYS & set(config))
    assert "market_watch" not in config["redis"]["ttl"]
    assert "ohlcv" not in config["redis"]["ttl"]


def test_initial_schema_has_no_finance_tables_or_preferences():
    migration_path = (
        Path(__file__).parents[4] / "migrations/versions/001_initial_schema.py"
    )
    migration_source = migration_path.read_text()

    assert not [term for term in RETIRED_SCHEMA_TERMS if term in migration_source]
