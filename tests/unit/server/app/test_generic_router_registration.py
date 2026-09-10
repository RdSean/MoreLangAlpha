"""The generic platform must not register financial HTTP surfaces.

The source-package half of this file's original guard is retired while the
financial bundles are intentionally retained for validation: `src/data_client`
and `src/market_protocol` ship again with them. The dependency-ordered removal
pass restores that assertion (see the migration runbook).
"""

from __future__ import annotations

from pathlib import Path
from typing import get_args

from src.server.app.setup import app
from src.server.models.automation import AutomationCreate


RETIRED_ROUTE_SEGMENTS = (
    "/market-data",
    "/chart-annotations",
    "/watchlist",
    "/portfolio",
    "/news",
    "/api/v1/calendar",
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


def test_default_api_registers_document_library_routes():
    registered_paths = {route.path for route in app.routes}

    assert "/api/v1/documents" in registered_paths
    assert "/api/v1/document-jobs/{job_id}/events" in registered_paths


def test_speech_relay_route_is_registered():
    assert "/ws/v1/speech/transcribe" in {route.path for route in app.routes}


def test_general_automation_routes_and_schedule_contract_remain_available():
    """Finance cleanup may remove price triggers, never general task automation."""
    registered_methods = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
    }

    assert {
        ("POST", "/api/v1/automations"),
        ("GET", "/api/v1/automations"),
        ("GET", "/api/v1/automations/{automation_id}"),
        ("PATCH", "/api/v1/automations/{automation_id}"),
        ("DELETE", "/api/v1/automations/{automation_id}"),
        ("POST", "/api/v1/automations/{automation_id}/trigger"),
        ("POST", "/api/v1/automations/{automation_id}/pause"),
        ("POST", "/api/v1/automations/{automation_id}/resume"),
        ("GET", "/api/v1/automations/{automation_id}/executions"),
    } <= registered_methods
    assert set(get_args(AutomationCreate.model_fields["trigger_type"].annotation)) == {
        "cron",
        "once",
    }
