"""The generic platform must not register financial HTTP surfaces."""

from __future__ import annotations

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


def test_default_api_has_no_finance_or_market_routes():
    registered_paths = {route.path for route in app.routes}

    assert not [
        path
        for path in registered_paths
        if any(segment in path for segment in RETIRED_ROUTE_SEGMENTS)
    ]
