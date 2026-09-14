"""The document-usage endpoint behind the Usage page.

Owner scoping is the security property here, and it is enforced in the query
layer rather than by a role check: a caller sees the spend attributable to
documents they own, full stop. A student account therefore gets an empty series
rather than a refusal — it owns no documents — and the Settings page simply
does not offer them the tab.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.server.utils.api import get_current_user_id


@pytest_asyncio.fixture
async def api(monkeypatch):
    from src.server.app import documents

    recorder = AsyncMock()
    monkeypatch.setattr(documents, "aggregate_usage", recorder)

    app = FastAPI()
    app.include_router(documents.router)
    app.dependency_overrides[get_current_user_id] = lambda: "owner-1"
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client, recorder


@pytest.mark.asyncio
async def test_returns_daily_buckets_and_totals(api) -> None:
    client, recorder = api
    recorder.return_value = [
        {"day": date(2026, 9, 1), "pages": 12, "cost_cents": 24, "conversions": 1},
        {"day": date(2026, 9, 3), "pages": 5, "cost_cents": 10, "conversions": 1},
    ]

    response = await client.get("/api/v1/document-usage?range=7d")

    assert response.status_code == 200
    body = response.json()
    assert body["totals"] == {"pages": 17, "cost_cents": 34, "conversions": 2}
    assert [bucket["day"] for bucket in body["days"]] == ["2026-09-01", "2026-09-03"]


@pytest.mark.asyncio
async def test_totals_are_computed_by_the_endpoint_not_the_client(api) -> None:
    """One source for the numbers on screen.

    Letting the page sum the buckets would mean two implementations of
    "total spend", and the header and the chart could disagree.
    """
    client, recorder = api
    recorder.return_value = [
        {"day": date(2026, 9, 1), "pages": 3, "cost_cents": 7, "conversions": 1},
    ]

    response = await client.get("/api/v1/document-usage?range=14d")

    assert response.json()["totals"] == {
        "pages": 3,
        "cost_cents": 7,
        "conversions": 1,
    }


@pytest.mark.asyncio
async def test_scopes_the_read_to_the_calling_user(api) -> None:
    client, recorder = api
    recorder.return_value = []

    await client.get("/api/v1/document-usage?range=7d")

    assert recorder.await_args.kwargs["owner_user_id"] == "owner-1"


@pytest.mark.asyncio
async def test_translates_the_range_into_a_window(api) -> None:
    client, recorder = api
    recorder.return_value = []

    response = await client.get("/api/v1/document-usage?range=30d")

    kwargs = recorder.await_args.kwargs
    window = (kwargs["end_date"] - kwargs["start_date"]).days
    assert window == 29  # inclusive end: 30 days of buckets
    assert response.json()["range"] == "30d"


@pytest.mark.asyncio
async def test_rejects_an_unknown_range(api) -> None:
    client, _ = api

    response = await client.get("/api/v1/document-usage?range=1y")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_an_empty_series_is_a_success_not_a_404(api) -> None:
    client, recorder = api
    recorder.return_value = []

    response = await client.get("/api/v1/document-usage?range=7d")

    assert response.status_code == 200
    assert response.json() == {
        "range": "7d",
        "totals": {"pages": 0, "cost_cents": 0, "conversions": 0},
        "days": [],
    }
