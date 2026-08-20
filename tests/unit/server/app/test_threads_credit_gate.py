"""Tests for the credit-gate ``is_byok`` logic in ``_handle_send_message``.

The gate reads ``config.credential_source`` (set by ``resolve_llm_config``) to
decide which enforcement path to take:
  - OAUTH, BYOK, or HOUSEHOLD → ``enforce_credit_limit(byok=True)`` (negative-balance only)
  - PLATFORM or NONE → ``enforce_credit_limit(byok=False)`` (daily quota check)

The regression guard: even when ``config.llm_client`` is set (non-None), a
PLATFORM credential_source must still produce ``byok=False``.  The old check
``is_byok = config.llm_client is not None`` would have produced ``byok=True``
for a platform-reasoning user whose eager client build set ``llm_client``.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from ptc_agent.config.agent import CredentialSource
from tests.conftest import create_test_app

THREADS_MOD = "src.server.app.threads.messaging"
THREAD_CREATE_MOD = "src.server.app.threads.create"


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_config(credential_source: CredentialSource, *, llm_client_set: bool = False):
    """Stub ``AgentConfig``-like object returned by ``resolve_llm_config``."""
    cfg = MagicMock()
    cfg.credential_source = credential_source
    # Set llm_client to a non-None object to exercise the regression guard.
    cfg.llm_client = MagicMock(name="platform-client") if llm_client_set else None
    cfg.llm = MagicMock()
    cfg.llm.name = "claude-sonnet-placeholder"
    return cfg


def _empty_async_gen():
    async def _gen():
        if False:
            yield ""

    return _gen()


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def threads_client():
    """Threads router with auth + rate-limit dependencies neutralised."""
    from src.server.app.threads import router
    from src.server.dependencies.usage_limits import ChatAuthResult, enforce_chat_limit

    app = create_test_app(router)
    app.dependency_overrides[enforce_chat_limit] = lambda: ChatAuthResult(
        user_id="usr-placeholder-001", access_tier=0
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest_asyncio.fixture
async def no_provider_threads_client():
    """Threads client for the platform no-provider admission branch."""
    from src.server.app.threads import router
    from src.server.dependencies.usage_limits import ChatAuthResult, enforce_chat_limit

    app = create_test_app(router)
    app.dependency_overrides[enforce_chat_limit] = lambda: ChatAuthResult(
        user_id="usr-placeholder-001", access_tier=-1
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


# ---------------------------------------------------------------------------
# Parametrised gate test
# ---------------------------------------------------------------------------


_GATE_CASES: list[tuple[CredentialSource, bool, bool]] = [
    # (credential_source, llm_client_set, expected_byok)
    # PLATFORM with llm_client set — the core regression case:
    # old code would give byok=True; new code must give byok=False.
    (CredentialSource.PLATFORM, True, False),
    # NONE — no credential at all, platform path.
    (CredentialSource.NONE, False, False),
    # BYOK — user provided own key.
    (CredentialSource.BYOK, True, True),
    # OAUTH — user connected via OAuth.
    (CredentialSource.OAUTH, True, True),
    # HOUSEHOLD — family-owned credentials are non-platform credentials.
    (CredentialSource.HOUSEHOLD, True, True),
]


@pytest.mark.parametrize(
    "credential_source, llm_client_set, expected_byok",
    _GATE_CASES,
    ids=[c[0].value for c in _GATE_CASES],
)
@pytest.mark.asyncio
async def test_credit_gate_byok_arg(
    threads_client,
    credential_source: CredentialSource,
    llm_client_set: bool,
    expected_byok: bool,
):
    """``enforce_credit_limit`` receives the correct ``byok`` kwarg.

    The config stub always carries the given ``credential_source``; when
    ``llm_client_set=True`` the stub also carries a non-None ``llm_client``
    to prove the old ``llm_client is not None`` heuristic would have misfired.
    """
    from src.server.app import setup as setup_module

    stub_config = _make_config(credential_source, llm_client_set=llm_client_set)

    enforce_mock = AsyncMock()
    wm_singleton = MagicMock()
    wm_singleton.has_ready_session.return_value = True

    with (
        patch.object(setup_module, "agent_config", MagicMock()),
        patch(
            "src.server.services.llm.config.resolve_llm_config",
            new=AsyncMock(return_value=stub_config),
        ),
        patch(
            "src.server.dependencies.usage_limits.enforce_credit_limit",
            new=enforce_mock,
        ),
        patch(
            "src.server.database.conversation.get_thread_by_id",
            new=AsyncMock(return_value={"workspace_id": "ws-placeholder"}),
        ),
        # Workspace IDOR guard reads the owner; stub it as the caller's own.
        patch(
            "src.server.database.workspace.get_workspace",
            new=AsyncMock(
                return_value={"user_id": "usr-placeholder-001", "status": "running"}
            ),
        ),
        patch(
            "src.server.services.workspace_manager.WorkspaceManager.get_instance",
            return_value=wm_singleton,
        ),
        patch(
            "src.server.handlers.chat.astream_ptc_workflow",
            return_value=_empty_async_gen(),
        ) as astream,
        patch(
            f"{THREADS_MOD}.observe_chat_stream",
            side_effect=lambda gen, **_: gen,
        ),
        # Transport preflight (I6) would 503 in the Redis-less unit env.
        patch(
            f"{THREADS_MOD}._assert_stream_transport_ready",
            new=AsyncMock(),
        ),
    ):
        async with threads_client.stream(
            "POST",
            "/api/v1/threads/tid-placeholder/messages",
            json={
                "workspace_id": "ws-placeholder",
                "messages": [{"role": "user", "content": "test query"}],
                "agent_mode": "ptc",
            },
        ) as resp:
            assert resp.status_code == 200

    # Verify enforce_credit_limit was called with the expected byok value.
    enforce_mock.assert_awaited_once()
    _, kwargs = enforce_mock.await_args
    actual_byok = kwargs.get("byok")
    assert actual_byok is expected_byok, (
        f"credential_source={credential_source!r} llm_client_set={llm_client_set}: "
        f"expected enforce_credit_limit(byok={expected_byok}), got byok={actual_byok!r}"
    )
    assert astream.call_args.kwargs["is_byok"] is expected_byok


@pytest.mark.asyncio
async def test_household_model_bypasses_platform_no_provider_gate(
    no_provider_threads_client,
):
    """A resolved household credential is admitted despite no personal provider."""
    from src.server.app import setup as setup_module

    resolved = _make_config(CredentialSource.HOUSEHOLD, llm_client_set=True)
    workspace_manager = MagicMock()
    workspace_manager.has_ready_session.return_value = True

    with (
        patch("src.config.settings.HOST_MODE", "platform"),
        patch.object(setup_module, "agent_config", MagicMock()),
        patch(
            "src.server.services.llm.config.resolve_llm_config",
            new=AsyncMock(return_value=resolved),
        ) as resolve_config,
        patch(
            "src.server.services.education_access.is_student_account",
            new=AsyncMock(return_value=True),
        ),
        patch(
            f"{THREADS_MOD}.get_thread_owner_id",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.server.database.workspace.get_workspace",
            new=AsyncMock(
                return_value={"user_id": "usr-placeholder-001", "status": "flash"}
            ),
        ),
        patch(
            "src.server.services.workspace_manager.WorkspaceManager.get_instance",
            return_value=workspace_manager,
        ),
        patch(
            "src.server.handlers.chat.astream_flash_workflow",
            return_value=_empty_async_gen(),
        ),
        patch(
            f"{THREADS_MOD}.observe_chat_stream",
            side_effect=lambda gen, **_: gen,
        ),
        patch(
            f"{THREADS_MOD}._assert_stream_transport_ready",
            new=AsyncMock(),
        ),
        patch(
            "src.server.dependencies.usage_limits.enforce_credit_limit",
            new=AsyncMock(),
        ),
        patch(
            "src.server.services.education_learning_chat.reject_unscoped_learning_thread",
            new=AsyncMock(),
        ),
    ):
        async with no_provider_threads_client.stream(
            "POST",
            "/api/v1/threads/tid-placeholder/messages",
            json={
                "workspace_id": "ws-placeholder",
                "messages": [{"role": "user", "content": "test query"}],
                "agent_mode": "flash",
            },
        ) as response:
            assert response.status_code == 200

    resolve_config.assert_awaited_once()


@pytest.mark.asyncio
async def test_empty_household_pool_returns_resolver_error_not_no_provider(
    no_provider_threads_client,
):
    """No selected family model reaches the resolver before the provider gate."""
    from fastapi import HTTPException
    from src.server.app import setup as setup_module

    no_model = HTTPException(
        status_code=409,
        detail={"type": "no_model_available", "message": "No household model"},
    )
    workspace_manager = MagicMock()
    workspace_manager.has_ready_session.return_value = True

    with (
        patch("src.config.settings.HOST_MODE", "platform"),
        patch.object(setup_module, "agent_config", MagicMock()),
        patch(
            "src.server.services.llm.config.resolve_llm_config",
            new=AsyncMock(side_effect=no_model),
        ) as resolve_config,
        patch(
            "src.server.services.education_access.is_student_account",
            new=AsyncMock(return_value=True),
        ),
        patch(
            f"{THREADS_MOD}.get_thread_owner_id",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.server.database.workspace.get_workspace",
            new=AsyncMock(
                return_value={"user_id": "usr-placeholder-001", "status": "flash"}
            ),
        ),
        patch(
            "src.server.services.workspace_manager.WorkspaceManager.get_instance",
            return_value=workspace_manager,
        ),
        patch("src.server.handlers.chat.astream_flash_workflow") as astream,
    ):
        response = await no_provider_threads_client.post(
            "/api/v1/threads/tid-placeholder/messages",
            json={
                "workspace_id": "ws-placeholder",
                "messages": [{"role": "user", "content": "test query"}],
                "agent_mode": "flash",
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"]["type"] == "no_model_available"
    resolve_config.assert_awaited_once()
    astream.assert_not_called()


@pytest.mark.asyncio
async def test_empty_household_pool_does_not_upsert_flash_workspace(
    no_provider_threads_client,
):
    """A zero-model Flash request fails before its workspace can be persisted."""
    from fastapi import HTTPException
    from src.server.app import setup as setup_module

    no_model = HTTPException(
        status_code=409,
        detail={"type": "no_model_available", "message": "No household model"},
    )
    flash_workspace = AsyncMock(
        return_value={"workspace_id": "flash-ws", "user_id": "usr-placeholder-001", "status": "flash"}
    )

    with (
        patch("src.config.settings.HOST_MODE", "platform"),
        patch.object(setup_module, "agent_config", MagicMock()),
        patch(
            "src.server.services.llm.config.resolve_llm_config",
            new=AsyncMock(side_effect=no_model),
        ) as resolve_config,
        patch(
            "src.server.services.education_access.is_student_account",
            new=AsyncMock(return_value=True),
        ),
        patch(
            f"{THREADS_MOD}.get_thread_owner_id",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.server.database.workspace.get_or_create_flash_workspace",
            new=flash_workspace,
        ),
        patch(
            "src.server.app.threads.messaging.require_student_flash_workspace",
            new=AsyncMock(),
        ),
        patch(
            "src.server.services.education_learning_chat.reject_unscoped_learning_thread",
            new=AsyncMock(),
        ),
    ):
        response = await no_provider_threads_client.post(
            "/api/v1/threads/tid-placeholder/messages",
            json={
                "messages": [{"role": "user", "content": "test query"}],
                "agent_mode": "flash",
            },
        )

    assert response.status_code == 409
    assert response.json()["detail"]["type"] == "no_model_available"
    resolve_config.assert_awaited_once()
    flash_workspace.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_student_no_provider_keeps_early_403_without_flash_upsert(
    no_provider_threads_client,
):
    """Ordinary no-provider requests retain their 403 before LLM or workspace work."""
    from src.server.app import setup as setup_module

    flash_workspace = AsyncMock()

    with (
        patch("src.config.settings.HOST_MODE", "platform"),
        patch.object(setup_module, "agent_config", MagicMock()),
        patch(
            "src.server.services.education_access.is_student_account",
            new=AsyncMock(return_value=False),
        ) as is_student,
        patch(
            "src.server.services.llm.config.resolve_llm_config",
            new=AsyncMock(),
        ) as resolve_config,
        patch(
            "src.server.database.workspace.get_or_create_flash_workspace",
            new=flash_workspace,
        ),
    ):
        response = await no_provider_threads_client.post(
            "/api/v1/threads/tid-placeholder/messages",
            json={
                "messages": [{"role": "user", "content": "test query"}],
                "agent_mode": "flash",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"]["type"] == "no_provider"
    is_student.assert_awaited_once_with("usr-placeholder-001")
    resolve_config.assert_not_awaited()
    flash_workspace.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("agent_mode", ["ptc", "flash"])
async def test_missing_explicit_workspace_is_rejected_before_model_resolution(
    threads_client, agent_mode: str
):
    """An explicit but missing workspace cannot reach model resolution."""
    from src.server.app import setup as setup_module

    with (
        patch("src.config.settings.HOST_MODE", "platform"),
        patch.object(setup_module, "agent_config", MagicMock()),
        patch(
            f"{THREADS_MOD}.get_thread_owner_id",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.server.database.workspace.get_workspace",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "src.server.services.workspace_manager.WorkspaceManager.get_instance",
            return_value=MagicMock(has_ready_session=MagicMock(return_value=True)),
        ),
        patch(
            "src.server.services.llm.config.resolve_llm_config",
            new=AsyncMock(),
        ) as resolve_config,
        patch(f"src.server.handlers.chat.astream_{agent_mode}_workflow") as astream,
    ):
        response = await threads_client.post(
            "/api/v1/threads/tid-placeholder/messages",
            json={
                "workspace_id": "missing-workspace",
                "messages": [{"role": "user", "content": "test query"}],
                "agent_mode": agent_mode,
            },
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Workspace not found"
    resolve_config.assert_not_awaited()
    astream.assert_not_called()


# ---------------------------------------------------------------------------
# POST /threads (pre-create) household admission
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_student_precreate_without_household_model_creates_no_workspace_or_thread():
    """The pre-create door must reject an empty family pool before persistence."""
    from fastapi import HTTPException
    from src.server.app import setup as setup_module
    from src.server.app.threads import router

    app = create_test_app(router)
    no_model = HTTPException(
        status_code=409,
        detail={"type": "no_model_available", "message": "No household model"},
    )
    flash_workspace = AsyncMock()
    create_row = AsyncMock()
    schedule_title = MagicMock()

    with (
        patch.object(setup_module, "agent_config", MagicMock()),
        patch(
            "src.server.services.education_access.is_student_account",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "src.server.services.llm.config.resolve_llm_config",
            new=AsyncMock(side_effect=no_model),
        ) as resolve_config,
        patch(
            f"{THREAD_CREATE_MOD}.get_or_create_flash_workspace",
            new=flash_workspace,
        ),
        patch(f"{THREAD_CREATE_MOD}.create_thread", new=create_row),
        patch(f"{THREAD_CREATE_MOD}.schedule_title_generation", schedule_title),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/threads",
                json={"first_query": "hello", "agent_mode": "flash"},
            )

    assert response.status_code == 409
    assert response.json()["detail"]["type"] == "no_model_available"
    resolve_config.assert_awaited_once()
    flash_workspace.assert_not_awaited()
    create_row.assert_not_awaited()
    schedule_title.assert_not_called()


@pytest.mark.asyncio
async def test_student_precreate_admits_household_model_without_personal_credentials():
    """A student family endpoint is sufficient for pre-create and its quota gate."""
    from src.server.app import setup as setup_module
    from src.server.app.threads import router

    app = create_test_app(router)
    resolved = _make_config(CredentialSource.HOUSEHOLD, llm_client_set=True)
    now = datetime.now(timezone.utc)
    flash_workspace = {
        "workspace_id": "flash-ws",
        "user_id": "test-user-123",
        "status": "flash",
    }
    create_row = {
        "thread_index": 0,
        "created_at": now,
        "updated_at": now,
    }
    enforce_credit = AsyncMock()

    with (
        patch.object(setup_module, "agent_config", MagicMock()),
        patch(f"{THREAD_CREATE_MOD}.HOST_MODE", "platform"),
        patch(
            "src.server.services.education_access.is_student_account",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "src.server.services.llm.config.resolve_llm_config",
            new=AsyncMock(return_value=resolved),
        ) as resolve_config,
        patch(
            f"{THREAD_CREATE_MOD}.get_or_create_flash_workspace",
            new=AsyncMock(return_value=flash_workspace),
        ),
        patch(f"{THREAD_CREATE_MOD}.create_thread", new=AsyncMock(return_value=create_row)) as create_thread,
        patch(f"{THREAD_CREATE_MOD}.schedule_title_generation", return_value=None),
        patch(
            "src.server.dependencies.usage_limits.enforce_credit_limit",
            new=enforce_credit,
        ),
        patch(
            "src.server.database.api_keys.is_byok_active",
            new=AsyncMock(side_effect=AssertionError("student pre-create must not read personal BYOK")),
        ),
        patch(
            "src.server.database.oauth_tokens.has_any_oauth_token",
            new=AsyncMock(side_effect=AssertionError("student pre-create must not read OAuth")),
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/threads",
                json={"first_query": "hello", "agent_mode": "flash"},
            )

    assert response.status_code == 201
    resolve_config.assert_awaited_once()
    enforce_credit.assert_awaited_once_with("test-user-123", byok=True)
    create_thread.assert_awaited_once()


@pytest.mark.asyncio
async def test_student_precreate_rejects_nonflash_workspace_before_model_resolution():
    """A forbidden workspace must not reveal whether the household has a model."""
    from src.server.app import setup as setup_module
    from src.server.app.threads import router

    app = create_test_app(router)
    resolve_config = AsyncMock()
    with (
        patch.object(setup_module, "agent_config", MagicMock()),
        patch(
            "src.server.services.education_access.is_student_account",
            new=AsyncMock(return_value=True),
        ),
        patch(
            f"{THREAD_CREATE_MOD}.get_workspace",
            new=AsyncMock(
                return_value={
                    "workspace_id": "ptc-ws",
                    "user_id": "test-user-123",
                    "status": "running",
                }
            ),
        ),
        patch(
            "src.server.services.llm.config.resolve_llm_config",
            new=resolve_config,
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/v1/threads",
                json={
                    "first_query": "hello",
                    "agent_mode": "ptc",
                    "workspace_id": "ptc-ws",
                },
            )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "Student accounts can use only their private Flash workspace."
    )
    resolve_config.assert_not_awaited()
