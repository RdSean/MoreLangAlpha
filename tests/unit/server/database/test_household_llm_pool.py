from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest


def _fake_db(*, fetchone_values):
    cursor = AsyncMock()
    cursor.fetchone = AsyncMock(side_effect=fetchone_values)
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
async def test_create_without_api_key_does_not_read_encryption_key():
    endpoint_id = uuid4()
    household_id = uuid4()
    cursor, fake_db = _fake_db(
        fetchone_values=[
            {
                "endpoint_id": endpoint_id,
                "household_id": household_id,
                "display_name": "Local model",
                "provider": "ollama",
                "model_id": "llama3",
                "base_url": "http://localhost:11434",
                "enabled": True,
                "sort_order": 0,
                "created_by": "parent",
                "created_at": None,
                "updated_at": None,
                "has_api_key": False,
            }
        ]
    )
    with (
        patch("src.server.database.household_llm_pool.get_db_connection", fake_db),
        patch(
            "src.server.database.household_llm_pool._get_encryption_key",
            side_effect=AssertionError("null API key must not require encryption key"),
        ) as get_key,
    ):
        from src.server.database.household_llm_pool import create_household_endpoint

        result = await create_household_endpoint(
            str(household_id),
            "parent",
            display_name="Local model",
            provider="ollama",
            model_id="llama3",
            base_url="http://localhost:11434",
            api_key=None,
        )

    assert result["masked_api_key"] is None
    get_key.assert_not_called()
    assert "PGP_SYM_ENCRYPT" not in cursor.execute.await_args.args[0].upper()


@pytest.mark.asyncio
async def test_runtime_without_api_key_does_not_read_encryption_key():
    endpoint_id = uuid4()
    household_id = uuid4()
    cursor, fake_db = _fake_db(
        fetchone_values=[
            {
                "endpoint_id": endpoint_id,
                "household_id": household_id,
                "display_name": "Local model",
                "provider": "ollama",
                "model_id": "llama3",
                "base_url": "http://localhost:11434",
                "enabled": True,
                "sort_order": 0,
                "created_by": "parent",
                "created_at": None,
                "updated_at": None,
                "api_key": None,
            }
        ]
    )
    with (
        patch("src.server.database.household_llm_pool.get_db_connection", fake_db),
        patch(
            "src.server.database.household_llm_pool._get_encryption_key",
            side_effect=AssertionError("null API key must not require encryption key"),
        ) as get_key,
    ):
        from src.server.database.household_llm_pool import get_endpoint_for_runtime

        result = await get_endpoint_for_runtime(str(household_id), str(endpoint_id))

    assert result["api_key"] is None
    get_key.assert_not_called()
    assert cursor.execute.await_args.args[0].count("pgp_sym_decrypt") == 0


@pytest.mark.asyncio
async def test_set_household_default_locks_candidate_endpoint_before_upsert():
    endpoint_id = uuid4()
    household_id = uuid4()
    cursor, fake_db = _fake_db(
        fetchone_values=[
            {"enabled": True},
            {
                "household_id": household_id,
                "default_endpoint_id": endpoint_id,
                "updated_at": None,
            },
        ]
    )
    with patch("src.server.database.household_llm_pool.get_db_connection", fake_db):
        from src.server.database.household_llm_pool import set_household_default

        result = await set_household_default(str(household_id), str(endpoint_id))

    assert result["default_endpoint_id"] == str(endpoint_id)
    select_sql = cursor.execute.await_args_list[0].args[0]
    assert "FOR UPDATE" in select_sql.upper()
    assert "SELECT ENABLED" in select_sql.upper()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "exception_name"),
    [(None, "HouseholdEndpointNotFoundError"), ({"enabled": False}, "HouseholdEndpointDisabledError")],
)
async def test_default_selection_classifies_missing_and_disabled_endpoint(
    state, exception_name
):
    cursor, fake_db = _fake_db(fetchone_values=[state])
    with patch("src.server.database.household_llm_pool.get_db_connection", fake_db):
        from src.server.database import household_llm_pool as pool

        with pytest.raises(getattr(pool, exception_name)):
            await pool.set_household_default(str(uuid4()), str(uuid4()))

    assert cursor.execute.await_count == 1


@pytest.mark.asyncio
async def test_student_preference_locks_enabled_endpoint_with_its_upsert():
    household_id = uuid4()
    endpoint_id = uuid4()
    cursor, fake_db = _fake_db(
        fetchone_values=[
            {"enabled": True},
            {
                "user_id": "student-1",
                "household_id": household_id,
                "endpoint_id": endpoint_id,
                "updated_at": None,
            },
        ]
    )
    with patch("src.server.database.household_llm_pool.get_db_connection", fake_db):
        from src.server.database.household_llm_pool import upsert_student_preference

        result = await upsert_student_preference(
            "student-1", str(household_id), str(endpoint_id)
        )

    assert result["endpoint_id"] == str(endpoint_id)
    select_sql = cursor.execute.await_args_list[0].args[0]
    assert "SELECT ENABLED" in select_sql.upper()
    assert "FOR UPDATE" in select_sql.upper()


@pytest.mark.asyncio
async def test_clearing_student_preference_skips_endpoint_lock():
    household_id = uuid4()
    cursor, fake_db = _fake_db(
        fetchone_values=[
            {
                "user_id": "student-1",
                "household_id": household_id,
                "endpoint_id": None,
                "updated_at": None,
            }
        ]
    )
    with patch("src.server.database.household_llm_pool.get_db_connection", fake_db):
        from src.server.database.household_llm_pool import upsert_student_preference

        result = await upsert_student_preference("student-1", str(household_id), None)

    assert result["endpoint_id"] is None
    assert cursor.execute.await_count == 1
    assert "FOR UPDATE" not in cursor.execute.await_args.args[0].upper()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("state", "exception_name"),
    [(None, "HouseholdEndpointNotFoundError"), ({"enabled": False}, "HouseholdEndpointDisabledError")],
)
async def test_student_preference_classifies_missing_and_disabled_endpoint(
    state, exception_name
):
    cursor, fake_db = _fake_db(fetchone_values=[state])
    with patch("src.server.database.household_llm_pool.get_db_connection", fake_db):
        from src.server.database import household_llm_pool as pool

        with pytest.raises(getattr(pool, exception_name)):
            await pool.upsert_student_preference("student-1", str(uuid4()), str(uuid4()))

    assert cursor.execute.await_count == 1
