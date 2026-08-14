"""Platform-model profile resolution contracts."""

from importlib import import_module
from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_platform_profile_is_inactive_without_a_complete_deployment_config(monkeypatch):
    module = import_module("src.server.services.llm.platform_profile")
    monkeypatch.delenv("PLATFORM_LLM_SOURCE_EMAIL", raising=False)
    monkeypatch.delenv("PLATFORM_LLM_MODEL", raising=False)
    find_user = AsyncMock()
    monkeypatch.setattr(module, "find_user_by_email", find_user)

    assert module.is_platform_model_profile_configured() is False
    assert await module.resolve_platform_llm_client(cache_key="teaching-run") is None
    find_user.assert_not_awaited()


@pytest.mark.asyncio
async def test_platform_profile_resolves_only_the_declared_service_account(monkeypatch):
    module = import_module("src.server.services.llm.platform_profile")
    monkeypatch.setenv("PLATFORM_LLM_SOURCE_EMAIL", "service@example.test")
    monkeypatch.setenv("PLATFORM_LLM_MODEL", "managed-model")
    client = MagicMock(name="platform-profile-client")
    find_user = AsyncMock(return_value={"user_id": "service-user"})
    is_byok_active = AsyncMock(return_value=True)
    resolve_byok = AsyncMock(return_value=client)
    monkeypatch.setattr(module, "find_user_by_email", find_user)
    monkeypatch.setattr(module, "is_byok_active", is_byok_active)
    monkeypatch.setattr(module, "resolve_byok_llm_client", resolve_byok)

    assert module.is_platform_model_profile_configured() is True
    assert await module.resolve_platform_llm_client(cache_key="teaching-run") is client
    find_user.assert_awaited_once_with("service@example.test")
    is_byok_active.assert_awaited_once_with("service-user")
    resolve_byok.assert_awaited_once_with(
        "service-user",
        "managed-model",
        True,
        cache_key="teaching-run",
    )


@pytest.mark.asyncio
async def test_platform_profile_fails_closed_when_service_account_has_no_active_key(monkeypatch):
    module = import_module("src.server.services.llm.platform_profile")
    monkeypatch.setenv("PLATFORM_LLM_SOURCE_EMAIL", "service@example.test")
    monkeypatch.setenv("PLATFORM_LLM_MODEL", "managed-model")
    resolve_byok = AsyncMock()
    monkeypatch.setattr(module, "find_user_by_email", AsyncMock(return_value={"user_id": "service-user"}))
    monkeypatch.setattr(module, "is_byok_active", AsyncMock(return_value=False))
    monkeypatch.setattr(module, "resolve_byok_llm_client", resolve_byok)

    assert await module.resolve_platform_llm_client() is None
    resolve_byok.assert_not_awaited()
