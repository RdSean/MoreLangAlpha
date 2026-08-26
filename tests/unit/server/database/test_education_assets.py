"""Locking contracts for education attachment cleanup."""

from contextlib import asynccontextmanager

import pytest

from src.server.database import education_assets


@pytest.mark.asyncio
async def test_cleanup_claim_holds_an_asset_row_lock_until_metadata_is_deleted(
    mock_connection, mock_cursor, monkeypatch,
):
    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    monkeypatch.setattr(education_assets, "get_db_connection", fake_connection)
    mock_cursor.fetchone.side_effect = [
        {
            "asset_id": "asset-1",
            "storage_key": "education/household-1/asset-1.pdf",
        },
        {"asset_id": "asset-1"},
    ]

    async with education_assets.claim_unreferenced_education_asset(
        asset_id="asset-1", created_by_user_id="student-1",
    ) as (asset, delete_metadata):
        assert asset is not None
        assert delete_metadata is not None
        await delete_metadata()

    claim_sql = mock_cursor.execute.await_args_list[0].args[0]
    delete_sql = mock_cursor.execute.await_args_list[1].args[0]
    assert "FOR UPDATE OF assets" in claim_sql
    assert "DELETE FROM education_assets" in delete_sql
