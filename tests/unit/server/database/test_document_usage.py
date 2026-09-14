"""Usage records: what each conversion cost, aggregated for the Usage page.

These assert on SQL and parameters rather than against a live database, which
is how the other database modules in this package are tested. The properties
worth more than the plumbing have their own cases: a retried job must rewrite
its record instead of adding one, and every read must be owner-scoped.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.server.database import document_usage


@pytest.fixture
def mock_cursor():
    cursor = AsyncMock()
    cursor.execute = AsyncMock()
    cursor.fetchall = AsyncMock(return_value=[])
    cursor.fetchone = AsyncMock(return_value=None)
    return cursor


@pytest.fixture
def mock_connection(mock_cursor):
    conn = AsyncMock()

    @asynccontextmanager
    async def _cursor_cm(*args, **kwargs):
        yield mock_cursor

    @asynccontextmanager
    async def _txn_cm(*args, **kwargs):
        yield None

    conn.cursor = _cursor_cm
    conn.transaction = _txn_cm
    return conn


def _patch_connection(monkeypatch, mock_connection):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(document_usage, "get_db_connection", fake_connection)


class TestRecordUsage:
    @pytest.mark.asyncio
    async def test_inserts_a_row_with_the_reported_cost(
        self, mock_connection, mock_cursor, monkeypatch
    ) -> None:
        _patch_connection(monkeypatch, mock_connection)
        mock_cursor.fetchone.return_value = {"record_id": "use-A1b2C3d4E5f6"}

        result = await document_usage.record_usage(
            job_id="job-A1b2C3d4E5f6",
            owner_user_id="owner-1",
            provider_id="datalab-online",
            pages=12,
            list_cost_cents=24,
            final_cost_cents=24,
        )

        assert result == {"record_id": "use-A1b2C3d4E5f6"}
        sql, params = mock_cursor.execute.await_args.args
        assert "INSERT INTO document_usage_records" in sql
        assert params["pages"] == 12
        assert params["final_cost_cents"] == 24
        assert params["provider_id"] == "datalab-online"

    @pytest.mark.asyncio
    async def test_a_retried_job_rewrites_its_record(
        self, mock_connection, mock_cursor, monkeypatch
    ) -> None:
        """Retries are real (`attempt_count` lives on the jobs table).

        Without the upsert, a job that failed and ran again would bill twice on
        the Usage page for one document — the page would overstate spend, which
        is worse than omitting the row.
        """
        _patch_connection(monkeypatch, mock_connection)
        mock_cursor.fetchone.return_value = {"record_id": "use-A1b2C3d4E5f6"}

        await document_usage.record_usage(
            job_id="job-A1b2C3d4E5f6",
            owner_user_id="owner-1",
            provider_id="datalab-online",
            pages=12,
            list_cost_cents=24,
            final_cost_cents=24,
        )

        sql, _ = mock_cursor.execute.await_args.args
        assert "ON CONFLICT (job_id) DO UPDATE" in sql
        # The rewrite must not reassign the identity: the insert names the
        # column, the update only ever assigns the cost fields. (`RETURNING`
        # mentions record_id too, hence matching on the assignment.)
        assert "record_id =" not in sql
        assert "final_cost_cents = EXCLUDED.final_cost_cents" in sql


class TestAggregateUsage:
    @pytest.mark.asyncio
    async def test_reads_are_owner_scoped(
        self, mock_connection, mock_cursor, monkeypatch
    ) -> None:
        _patch_connection(monkeypatch, mock_connection)

        await document_usage.aggregate_usage(
            owner_user_id="owner-1",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 14),
        )

        sql, params = mock_cursor.execute.await_args.args
        assert "owner_user_id = %s" in sql
        assert "owner-1" in params

    @pytest.mark.asyncio
    async def test_bounds_the_window(
        self, mock_connection, mock_cursor, monkeypatch
    ) -> None:
        _patch_connection(monkeypatch, mock_connection)

        await document_usage.aggregate_usage(
            owner_user_id="owner-1",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 7),
        )

        _, params = mock_cursor.execute.await_args.args
        assert date(2026, 9, 1) in params
        assert date(2026, 9, 7) in params

    @pytest.mark.asyncio
    async def test_rejects_a_window_longer_than_the_page_offers(
        self, monkeypatch
    ) -> None:
        """The UI's longest window is 30 days; anything wider is a bug or abuse."""
        with pytest.raises(ValueError, match="window"):
            await document_usage.aggregate_usage(
                owner_user_id="owner-1",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 12, 31),
            )

    @pytest.mark.asyncio
    async def test_rejects_an_inverted_window(self) -> None:
        with pytest.raises(ValueError, match="window"):
            await document_usage.aggregate_usage(
                owner_user_id="owner-1",
                start_date=date(2026, 9, 7),
                end_date=date(2026, 9, 1),
            )

    @pytest.mark.asyncio
    async def test_returns_daily_buckets_with_integer_totals(
        self, mock_connection, mock_cursor, monkeypatch
    ) -> None:
        _patch_connection(monkeypatch, mock_connection)
        mock_cursor.fetchall.return_value = [
            {"day": date(2026, 9, 1), "pages": 12, "cost_cents": 24, "conversions": 1},
            {"day": date(2026, 9, 3), "pages": 5, "cost_cents": 10, "conversions": 1},
        ]

        rows = await document_usage.aggregate_usage(
            owner_user_id="owner-1",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 7),
        )

        # Days with no activity are absent rather than zero-filled here; the
        # page decides how to draw the gaps, and a sparse series is what it gets.
        assert [row["day"] for row in rows] == [date(2026, 9, 1), date(2026, 9, 3)]
        assert rows[0]["cost_cents"] == 24

    @pytest.mark.asyncio
    async def test_an_empty_window_is_an_empty_series_not_an_error(
        self, mock_connection, mock_cursor, monkeypatch
    ) -> None:
        _patch_connection(monkeypatch, mock_connection)

        rows = await document_usage.aggregate_usage(
            owner_user_id="owner-1",
            start_date=date(2026, 9, 1),
            end_date=date(2026, 9, 7),
        )

        assert rows == []
