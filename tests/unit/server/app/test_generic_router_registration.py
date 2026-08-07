"""The generic platform must not register financial HTTP surfaces."""

from __future__ import annotations

from pathlib import Path

from src.server.app.setup import app


RETIRED_ROUTE_SEGMENTS = (
    "/market-data",
    "/chart-annotations",
    "/watchlist",
    "/portfolio",
    "/news",
    "/calendar",
    "/sec-proxy",
    "/insights",
    "/ws/v1/market-data",
)

RETIRED_FINANCE_SOURCE_PATHS = (
    "src/data_client",
    "src/market_protocol",
    "src/tools/market_data",
    "src/tools/sec",
    "src/server/app/bars.py",
    "src/server/app/calendar.py",
    "src/server/app/chart_annotations.py",
    "src/server/app/insights.py",
    "src/server/app/market_data.py",
    "src/server/app/market_data_ws.py",
    "src/server/app/news.py",
    "src/server/app/portfolio.py",
    "src/server/app/sec_proxy.py",
    "src/server/app/watchlist.py",
    "src/server/database/chart_annotation.py",
    "src/server/database/portfolio.py",
    "src/server/database/watchlist.py",
    "src/server/models/calendar.py",
    "src/server/models/market_data.py",
    "src/server/models/news.py",
    "src/server/services/insight_service.py",
    "src/server/services/market_data_feed.py",
    "src/server/services/news_refresh_service.py",
    "src/server/services/onboarding.py",
    "src/server/services/cache/daily_cache_service.py",
    "src/server/services/cache/earnings_cache_service.py",
    "src/server/services/cache/intraday_cache_service.py",
    "src/server/services/cache/news_cache_service.py",
    "src/server/services/cache/quote_cache_service.py",
    "src/server/services/cache/_instrument_clock.py",
    "src/server/services/cache/_ohlcv_envelope.py",
    "src/server/services/cache/_series_cache_core.py",
    "src/server/utils/chart_selection_context.py",
    "src/utils/market_watch.py",
    "mcp_servers/_envelope.py",
    "mcp_servers/_yf_common.py",
    "mcp_servers/fundamentals_mcp_server.py",
    "mcp_servers/macro_mcp_server.py",
    "mcp_servers/options_mcp_server.py",
    "mcp_servers/price_data_mcp_server.py",
    "mcp_servers/yf_analysis_mcp_server.py",
    "mcp_servers/yf_fundamentals_mcp_server.py",
    "mcp_servers/yf_market_mcp_server.py",
    "mcp_servers/yf_price_mcp_server.py",
)


def test_default_api_has_no_finance_or_market_routes():
    registered_paths = {route.path for route in app.routes}

    assert not [
        path
        for path in registered_paths
        if any(segment in path for segment in RETIRED_ROUTE_SEGMENTS)
    ]


def test_retired_finance_packages_are_not_shipped():
    """A disabled import path is not a removed product capability."""
    project_root = Path(__file__).parents[4]

    def is_shipped_source(relative_path: str) -> bool:
        target = project_root / relative_path
        return target.is_file() or (target / "__init__.py").is_file()

    assert not [
        relative_path
        for relative_path in RETIRED_FINANCE_SOURCE_PATHS
        if is_shipped_source(relative_path)
    ]
