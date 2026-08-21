from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _fake_db(*, fetchone_values=()):
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(side_effect=list(fetchone_values))
    cursor.fetchall = AsyncMock(return_value=[])
    connection = MagicMock()

    @asynccontextmanager
    async def cursor_context(**kwargs):
        yield cursor

    @asynccontextmanager
    async def transaction_context():
        yield

    connection.cursor = cursor_context
    connection.transaction = transaction_context

    @asynccontextmanager
    async def db_context():
        yield connection

    return cursor, db_context


@pytest.mark.asyncio
async def test_register_parent_assigns_creator_as_model_owner():
    cursor, fake_db = _fake_db()
    with patch("src.server.database.auth_accounts.get_db_connection", fake_db):
        from src.server.database.auth_accounts import register_parent_account

        result = await register_parent_account(
            email="parent@example.test",
            password_hash="hashed",
            name="Parent",
            household_name="Lee family",
            timezone_name="Asia/Tokyo",
        )

    household_insert = next(
        call.args[0]
        for call in cursor.execute.await_args_list
        if "INSERT INTO education_households" in call.args[0]
    )
    household_call = next(
        call for call in cursor.execute.await_args_list
        if "INSERT INTO education_households" in call.args[0]
    )
    assert "model_owner_user_id" in household_insert
    assert household_call.args[1][3] == result["user_id"]
    assert result["role"] == "parent"


def test_household_pool_migration_uses_owner_and_public_model_key():
    migration = (
        Path(__file__).parents[4] / "migrations/versions/033_add_household_llm_pool.py"
    ).read_text()

    assert "model_owner_user_id" in migration
    assert "model_key" in migration
    assert "CREATE TABLE household_llm_endpoints" not in migration
    assert "CREATE TABLE household_llm_settings" not in migration
    assert "endpoint_id UUID" not in migration
    assert "llm_endpoint_id" not in migration
    assert "api_key" not in migration


@pytest.mark.asyncio
async def test_get_household_model_owner_requires_parent_member():
    cursor, fake_db = _fake_db(
        fetchone_values=[
            {"household_id": "household-1", "model_owner_user_id": "owner-1"},
            {"user_id": "owner-1"},
        ]
    )
    with patch(
        "src.server.database.household_shared_models.get_db_connection", fake_db
    ):
        from src.server.database.household_shared_models import get_household_model_owner

        result = await get_household_model_owner("student-1")

    assert result == {
        "household_id": "household-1",
        "model_owner_user_id": "owner-1",
    }
    assert cursor.execute.await_count == 2
    assert "model_owner_user_id" in cursor.execute.await_args_list[0].args[0]
    assert "role = 'parent'" in cursor.execute.await_args_list[1].args[0]


@pytest.mark.asyncio
async def test_get_household_model_owner_rejects_owner_outside_parent_membership():
    cursor, fake_db = _fake_db(
        fetchone_values=[
            {"household_id": "household-1", "model_owner_user_id": "owner-1"},
            None,
        ]
    )
    with patch(
        "src.server.database.household_shared_models.get_db_connection", fake_db
    ):
        from src.server.database.household_shared_models import get_household_model_owner

        result = await get_household_model_owner("student-1")

    assert result is None


@pytest.mark.asyncio
async def test_student_preference_reads_and_writes_public_model_key_only():
    cursor, fake_db = _fake_db(
        fetchone_values=[
            {
                "user_id": "student-1",
                "household_id": "household-1",
                "model_key": "deepseek-chat",
                "updated_at": None,
            },
            {
                "user_id": "student-1",
                "household_id": "household-1",
                "model_key": "deepseek-chat",
                "updated_at": None,
            },
        ]
    )
    with patch(
        "src.server.database.household_shared_models.get_db_connection", fake_db
    ):
        from src.server.database.household_shared_models import (
            get_student_model_preference,
            upsert_student_model_preference,
        )

        preference = await get_student_model_preference("student-1", "household-1")
        saved = await upsert_student_model_preference(
            "student-1", "household-1", "deepseek-chat"
        )

    assert preference["model_key"] == "deepseek-chat"
    assert saved["model_key"] == "deepseek-chat"
    write_sql = cursor.execute.await_args_list[-1].args[0]
    assert "model_key" in write_sql
    assert "endpoint_id" not in write_sql
    assert "api_key" not in write_sql
