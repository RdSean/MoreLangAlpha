"""Database contracts for the household LLM model pool schema."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar
from uuid import uuid4

import psycopg
import pytest
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from tests.integration.conftest import _ALL_TABLES


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_cleanup_tables_remove_household_rows(db_conn):
    """The integration fixture must not leave standalone households behind."""
    household_id = uuid4()

    async with db_conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO education_households (household_id, name) VALUES (%s, %s)",
            (household_id, "Fixture cleanup household"),
        )
        for table in _ALL_TABLES:
            await cur.execute(f"TRUNCATE TABLE {table} CASCADE")
        await cur.execute(
            "SELECT EXISTS(SELECT 1 FROM education_households WHERE household_id = %s)",
            (household_id,),
        )
        assert (await cur.fetchone())["exists"] is False


async def test_household_llm_pool_schema_is_household_scoped(db_conn):
    """Pool defaults and student preferences cannot cross household boundaries."""
    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_name IN (
                  'household_llm_endpoints',
                  'household_llm_settings',
                  'student_llm_preferences'
              )
            """
        )
        tables = {row["table_name"] for row in await cur.fetchall()}
    assert tables >= {
        "household_llm_endpoints",
        "household_llm_settings",
        "student_llm_preferences",
    }

    household_a = uuid4()
    household_b = uuid4()
    parent_a = f"parent-a-{uuid4()}"
    parent_b = f"parent-b-{uuid4()}"
    student_a = f"student-a-{uuid4()}"

    async with db_conn.cursor() as cur:
        await cur.executemany(
            "INSERT INTO users (user_id, name) VALUES (%s, %s)",
            [
                (parent_a, "Parent A"),
                (parent_b, "Parent B"),
                (student_a, "Student A"),
            ],
        )
        await cur.executemany(
            "INSERT INTO education_households (household_id, name) VALUES (%s, %s)",
            [(household_a, "Household A"), (household_b, "Household B")],
        )
        await cur.executemany(
            """
            INSERT INTO education_memberships
                (household_id, user_id, role, display_name)
            VALUES (%s, %s, %s, %s)
            """,
            [
                (household_a, parent_a, "parent", "Parent A"),
                (household_a, student_a, "student", "Student A"),
                (household_b, parent_b, "parent", "Parent B"),
            ],
        )
        endpoint_a = await cur.execute(
            """
            INSERT INTO household_llm_endpoints
                (household_id, display_name, provider, model_id, created_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING endpoint_id
            """,
            (household_a, "Household A model", "openai", "gpt-test", parent_a),
        )
        endpoint_a_id = (await endpoint_a.fetchone())["endpoint_id"]
        endpoint_b = await cur.execute(
            """
            INSERT INTO household_llm_endpoints
                (household_id, display_name, provider, model_id, created_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING endpoint_id
            """,
            (household_b, "Household B model", "openai", "gpt-test", parent_b),
        )
        endpoint_b_id = (await endpoint_b.fetchone())["endpoint_id"]

        await cur.execute(
            """
            INSERT INTO household_llm_settings (household_id, default_endpoint_id)
            VALUES (%s, %s)
            """,
            (household_a, endpoint_a_id),
        )
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            await cur.execute(
                """
                INSERT INTO household_llm_settings
                    (household_id, default_endpoint_id)
                VALUES (%s, %s)
                """,
                (household_b, endpoint_a_id),
            )

        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            await cur.execute(
                """
                INSERT INTO student_llm_preferences
                    (user_id, household_id, endpoint_id)
                VALUES (%s, %s, %s)
                """,
                (student_a, household_a, endpoint_b_id),
            )

        await cur.execute(
            """
            INSERT INTO student_llm_preferences (user_id, household_id, endpoint_id)
            VALUES (%s, %s, %s)
            """,
            (student_a, household_a, endpoint_a_id),
        )

        usage_id = uuid4()
        await cur.execute(
            """
            INSERT INTO conversation_usages
                (conversation_usage_id, conversation_response_id, user_id,
                 conversation_thread_id, workspace_id, msg_type, status,
                 llm_endpoint_id, household_id, credential_source, model_snapshot)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                usage_id,
                uuid4(),
                parent_a,
                uuid4(),
                uuid4(),
                "flash",
                "completed",
                endpoint_a_id,
                household_a,
                "household",
                Jsonb({"provider": "openai", "model_id": "gpt-test"}),
            ),
        )
        await cur.execute(
            "DELETE FROM household_llm_endpoints WHERE endpoint_id = %s",
            (endpoint_a_id,),
        )
        await cur.execute(
            """
            SELECT household_id, llm_endpoint_id, model_snapshot
            FROM conversation_usages
            WHERE conversation_usage_id = %s
            """,
            (usage_id,),
        )
        usage = await cur.fetchone()
        assert usage["household_id"] == household_a
        assert usage["llm_endpoint_id"] is None
        assert usage["model_snapshot"]["model_id"] == "gpt-test"

        await cur.execute(
            "SELECT endpoint_id FROM student_llm_preferences WHERE user_id = %s",
            (student_a,),
        )
        assert (await cur.fetchone())["endpoint_id"] is None

        await cur.execute(
            "DELETE FROM education_households WHERE household_id = %s",
            (household_a,),
        )
        await cur.execute(
            "SELECT household_id FROM conversation_usages WHERE conversation_usage_id = %s",
            (usage_id,),
        )
        assert (await cur.fetchone())["household_id"] is None


async def test_pool_service_encrypts_keys_and_enforces_household_access(
    cleanup_tables, db_conn, monkeypatch
):
    """Real pgcrypto storage remains private while policy is household-scoped."""
    from src.server.database import education_members, household_llm_pool as pool_db
    from src.server.services import household_llm_pool as pool_service

    monkeypatch.setenv("BYOK_ENCRYPTION_KEY", "household-test-encryption-key")

    @asynccontextmanager
    async def test_connection():
        yield db_conn

    monkeypatch.setattr(pool_db, "get_db_connection", test_connection)
    monkeypatch.setattr(education_members, "get_db_connection", test_connection)

    household_a = uuid4()
    household_b = uuid4()
    parent_a = f"pool-parent-a-{uuid4()}"
    parent_b = f"pool-parent-b-{uuid4()}"
    student_a = f"pool-student-a-{uuid4()}"
    async with db_conn.cursor() as cur:
        await cur.executemany(
            "INSERT INTO users (user_id, name) VALUES (%s, %s)",
            [(parent_a, "Parent A"), (parent_b, "Parent B"), (student_a, "Student A")],
        )
        await cur.executemany(
            "INSERT INTO education_households (household_id, name) VALUES (%s, %s)",
            [(household_a, "Household A"), (household_b, "Household B")],
        )
        await cur.executemany(
            """
            INSERT INTO education_memberships
                (household_id, user_id, role, display_name)
            VALUES (%s, %s, %s, %s)
            """,
            [
                (household_a, parent_a, "parent", "Parent A"),
                (household_a, student_a, "student", "Student A"),
                (household_b, parent_b, "parent", "Parent B"),
            ],
        )

    first = await pool_service.create_endpoint(
        parent_a,
        {
            "display_name": "Family DeepSeek",
            "provider": "deepseek",
            "model_id": "deepseek-chat",
            "base_url": "https://api.deepseek.example/v1",
            "api_key": "test-family-secret",
        },
    )
    first_id = first["endpoint_id"]
    assert first["masked_api_key"] == "********"
    assert first["masked_key"] == "********"
    assert "test-family-secret" not in str(first)
    assert "api_key" not in first

    listed = await pool_service.list_parent_pool(parent_a)
    assert listed[0]["masked_api_key"] == "********"
    assert listed[0]["masked_key"] == "********"
    assert "test-family-secret" not in str(listed)
    async with db_conn.cursor() as cur:
        await cur.execute(
            "SELECT api_key FROM household_llm_endpoints WHERE endpoint_id = %s",
            (first_id,),
        )
        assert bytes((await cur.fetchone())["api_key"]) != b"test-family-secret"

    runtime = await pool_db.get_endpoint_for_runtime(str(household_a), first_id)
    assert runtime is not None
    assert runtime["api_key"] == "test-family-secret"
    assert runtime["base_url"] == "https://api.deepseek.example/v1"

    await pool_service.update_endpoint(parent_a, first_id, {"display_name": "Renamed"})
    runtime_after_update = await pool_db.get_endpoint_for_runtime(
        str(household_a), first_id
    )
    assert runtime_after_update is not None
    assert runtime_after_update["api_key"] == "test-family-secret"
    await pool_service.update_endpoint(
        parent_a, first_id, {"api_key": None, "base_url": None}
    )
    runtime_after_clear = await pool_db.get_endpoint_for_runtime(
        str(household_a), first_id
    )
    assert runtime_after_clear is not None
    assert runtime_after_clear["api_key"] is None
    assert runtime_after_clear["base_url"] is None

    second = await pool_service.create_endpoint(
        parent_a,
        {
            "display_name": "Fallback",
            "provider": "deepseek",
            "model_id": "deepseek-reasoner",
        },
    )
    await pool_service.set_household_default(parent_a, second["endpoint_id"])
    await pool_service.set_student_preference(student_a, first_id)
    student_availability = await pool_db.get_household_availability(
        str(household_a), student_a
    )
    assert "base_url" not in str(student_availability)
    assert "masked_key" not in str(student_availability)
    assert "test-family-secret" not in str(student_availability)
    preferred = await pool_service.resolve_student_model(student_a)
    assert preferred is not None
    assert preferred["endpoint_id"] == first_id

    await pool_service.update_endpoint(parent_a, first_id, {"enabled": False})
    disabled_preference = await pool_db.get_household_availability(
        str(household_a), student_a
    )
    assert disabled_preference["preference"] is None
    assert disabled_preference["_stale_preference"] is True
    fallback = await pool_service.resolve_student_model(student_a)
    assert fallback is not None
    assert fallback["endpoint_id"] == second["endpoint_id"]
    async with db_conn.cursor() as cur:
        await cur.execute(
            "SELECT endpoint_id FROM student_llm_preferences WHERE user_id = %s",
            (student_a,),
        )
        assert (await cur.fetchone())["endpoint_id"] is None

    await pool_service.set_student_preference(student_a, second["endpoint_id"])
    await pool_service.delete_endpoint(parent_a, second["endpoint_id"])
    async with db_conn.cursor() as cur:
        await cur.execute(
            "SELECT endpoint_id FROM student_llm_preferences WHERE user_id = %s",
            (student_a,),
        )
        assert (await cur.fetchone())["endpoint_id"] is None

    disabled_default = await pool_service.create_endpoint(
        parent_a,
        {
            "display_name": "Disabled default",
            "provider": "deepseek",
            "model_id": "deepseek-disabled",
        },
    )
    await pool_service.set_household_default(parent_a, disabled_default["endpoint_id"])
    async with db_conn.cursor() as cur:
        await cur.execute(
            "UPDATE household_llm_endpoints SET enabled = FALSE WHERE endpoint_id = %s",
            (disabled_default["endpoint_id"],),
        )
    disabled_default_availability = await pool_db.get_household_availability(
        str(household_a), student_a
    )
    assert disabled_default_availability["default"] is None

    with pytest.raises(pool_service.FamilyModelAccessError):
        await pool_service.update_endpoint(parent_b, first_id, {"display_name": "Nope"})
    with pytest.raises(PermissionError):
        await pool_service.create_endpoint(
            student_a, {"display_name": "Nope", "provider": "deepseek", "model_id": "x"}
        )
    with pytest.raises(PermissionError):
        await pool_service.list_parent_pool("not-a-household-member")


async def test_null_key_endpoint_needs_no_encryption_environment_and_clears_disabled_default(
    cleanup_tables, db_conn, monkeypatch
):
    """Local endpoints do not need pgcrypto configuration and cannot stay default when disabled."""
    from src.server.database import education_members, household_llm_pool as pool_db
    from src.server.services import household_llm_pool as pool_service

    monkeypatch.delenv("BYOK_ENCRYPTION_KEY", raising=False)

    @asynccontextmanager
    async def test_connection():
        yield db_conn

    monkeypatch.setattr(pool_db, "get_db_connection", test_connection)
    monkeypatch.setattr(education_members, "get_db_connection", test_connection)

    household_id = uuid4()
    parent_id = f"local-parent-{uuid4()}"
    async with db_conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO users (user_id, name) VALUES (%s, %s)",
            (parent_id, "Local Parent"),
        )
        await cur.execute(
            "INSERT INTO education_households (household_id, name) VALUES (%s, %s)",
            (household_id, "Local household"),
        )
        await cur.execute(
            """
            INSERT INTO education_memberships
                (household_id, user_id, role, display_name)
            VALUES (%s, %s, 'parent', %s)
            """,
            (household_id, parent_id, "Local Parent"),
        )

    endpoint = await pool_service.create_endpoint(
        parent_id,
        {
            "display_name": "Local Ollama",
            "provider": "ollama",
            "model_id": "llama3",
            "base_url": "http://localhost:11434",
        },
    )
    runtime = await pool_db.get_endpoint_for_runtime(
        str(household_id), endpoint["endpoint_id"]
    )
    assert runtime is not None
    assert runtime["api_key"] is None

    await pool_service.set_household_default(parent_id, endpoint["endpoint_id"])
    await pool_service.update_endpoint(
        parent_id, endpoint["endpoint_id"], {"enabled": False}
    )
    async with db_conn.cursor() as cur:
        await cur.execute(
            "SELECT default_endpoint_id FROM household_llm_settings WHERE household_id = %s",
            (household_id,),
        )
        assert (await cur.fetchone())["default_endpoint_id"] is None


async def test_default_selection_locks_endpoint_against_concurrent_disable(
    cleanup_tables, db_conn, monkeypatch, test_db_uri
):
    """A disable cannot interleave after default validation and before its write."""
    from src.server.database import household_llm_pool as pool_db

    household_id = uuid4()
    parent_id = f"race-parent-{uuid4()}"
    async with db_conn.cursor() as cur:
        await cur.execute(
            "INSERT INTO users (user_id, name) VALUES (%s, %s)",
            (parent_id, "Race Parent"),
        )
        await cur.execute(
            "INSERT INTO education_households (household_id, name) VALUES (%s, %s)",
            (household_id, "Race household"),
        )
        endpoint = await cur.execute(
            """
            INSERT INTO household_llm_endpoints
                (household_id, display_name, provider, model_id, created_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING endpoint_id
            """,
            (household_id, "Race endpoint", "ollama", "llama3", parent_id),
        )
        endpoint_id = (await endpoint.fetchone())["endpoint_id"]

    candidate_checked = asyncio.Event()
    allow_default_write = asyncio.Event()
    active_connection: ContextVar[object | None] = ContextVar(
        "active_household_pool_connection", default=None
    )

    class PausingCursor:
        def __init__(self, cursor):
            self._cursor = cursor

        async def execute(self, query, params=None):
            result = await self._cursor.execute(query, params)
            normalized = " ".join(query.upper().split())
            if (
                "SELECT ENDPOINT_ID FROM HOUSEHOLD_LLM_ENDPOINTS" in normalized
                and "FOR UPDATE" in normalized
            ):
                candidate_checked.set()
                await allow_default_write.wait()
            return result

        def __getattr__(self, name):
            return getattr(self._cursor, name)

    class PausingConnection:
        def __init__(self, connection):
            self._connection = connection

        @asynccontextmanager
        async def cursor(self, **kwargs):
            async with self._connection.cursor(**kwargs) as cursor:
                yield PausingCursor(cursor)

        @asynccontextmanager
        async def transaction(self):
            async with self._connection.transaction():
                yield

    @asynccontextmanager
    async def routed_connection():
        connection = active_connection.get()
        assert connection is not None
        yield connection

    monkeypatch.setattr(pool_db, "get_db_connection", routed_connection)

    async with (
        await psycopg.AsyncConnection.connect(
            test_db_uri, autocommit=True, row_factory=dict_row
        ) as default_connection,
        await psycopg.AsyncConnection.connect(
            test_db_uri, autocommit=True, row_factory=dict_row
        ) as disable_connection,
    ):

        async def set_default():
            token = active_connection.set(PausingConnection(default_connection))
            try:
                return await pool_db.set_household_default(
                    str(household_id), str(endpoint_id)
                )
            finally:
                active_connection.reset(token)

        async def disable_endpoint():
            token = active_connection.set(disable_connection)
            try:
                return await pool_db.update_household_endpoint(
                    str(household_id), str(endpoint_id), enabled=False
                )
            finally:
                active_connection.reset(token)

        default_task = asyncio.create_task(set_default())
        await candidate_checked.wait()
        disable_task = asyncio.create_task(disable_endpoint())
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(disable_task), timeout=0.2)

        allow_default_write.set()
        await default_task
        await disable_task

    async with db_conn.cursor() as cur:
        await cur.execute(
            "SELECT default_endpoint_id FROM household_llm_settings WHERE household_id = %s",
            (household_id,),
        )
        assert (await cur.fetchone())["default_endpoint_id"] is None
