"""Tests for resolve_model_client() — the unified resolution primitive.

Covers credential-source attribution (OAUTH / BYOK / PLATFORM / NONE), the
platform-fallback gate (SYSTEM only), the orthogonality of model_source vs
credential_source, and HTTPException propagation from the OAuth path.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ptc_agent.config.agent import CredentialSource

HANDLER = "src.server.services.llm.config"


def _patch_classify(source):
    """Patch classify_model to return (source, {})."""
    from src.server.services.llm.config import ModelSource  # noqa: F401

    return patch(
        f"{HANDLER}.classify_model",
        new_callable=AsyncMock,
        return_value=(source, {}),
    )


@pytest.mark.asyncio
async def test_oauth_present_returns_oauth_and_skips_byok():
    from src.server.services.llm.config import ModelSource, resolve_model_client

    oauth_client = MagicMock(name="oauth-client")
    byok = AsyncMock(name="byok")
    with (
        _patch_classify(ModelSource.SYSTEM),
        patch(
            f"{HANDLER}.resolve_oauth_llm_client",
            new_callable=AsyncMock,
            return_value=oauth_client,
        ),
        patch(f"{HANDLER}.resolve_byok_llm_client", byok),
    ):
        result = await resolve_model_client("u", "m", is_byok=True)

    assert result.client is oauth_client
    assert result.credential_source == CredentialSource.OAUTH
    byok.assert_not_called()


@pytest.mark.asyncio
async def test_byok_present_returns_byok():
    from src.server.services.llm.config import ModelSource, resolve_model_client

    byok_client = MagicMock(name="byok-client")
    with (
        _patch_classify(ModelSource.SYSTEM),
        patch(
            f"{HANDLER}.resolve_oauth_llm_client",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            f"{HANDLER}.resolve_byok_llm_client",
            new_callable=AsyncMock,
            return_value=byok_client,
        ),
    ):
        result = await resolve_model_client("u", "m", is_byok=True)

    assert result.client is byok_client
    assert result.credential_source == CredentialSource.BYOK


@pytest.mark.asyncio
async def test_platform_fallback_when_byok_none_and_system():
    from src.server.services.llm.config import ModelSource, resolve_model_client

    platform_client = MagicMock(name="platform-client")
    with (
        _patch_classify(ModelSource.SYSTEM),
        patch(
            f"{HANDLER}.resolve_oauth_llm_client",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            f"{HANDLER}.resolve_byok_llm_client",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("src.llms.llm.create_llm", return_value=platform_client) as mock_create,
    ):
        result = await resolve_model_client(
            "u", "m", is_byok=True, allow_platform_fallback=True,
        )

    assert result.client is platform_client
    assert result.credential_source == CredentialSource.PLATFORM
    mock_create.assert_called_once()


@pytest.mark.asyncio
async def test_platform_profile_preempts_legacy_environment_fallback(monkeypatch):
    from src.server.services.llm.config import ModelSource, resolve_model_client

    profile_client = MagicMock(name="platform-profile-client")
    legacy_client = MagicMock(name="legacy-environment-client")
    monkeypatch.setenv("PLATFORM_LLM_SOURCE_EMAIL", "service@example.test")
    monkeypatch.setenv("PLATFORM_LLM_MODEL", "managed-model")
    with (
        _patch_classify(ModelSource.SYSTEM),
        patch(
            f"{HANDLER}.resolve_oauth_llm_client",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            f"{HANDLER}.resolve_byok_llm_client",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            "src.server.services.llm.platform_profile.resolve_platform_llm_client",
            new_callable=AsyncMock,
            return_value=profile_client,
        ) as resolve_profile,
        patch("src.llms.llm.create_llm", return_value=legacy_client) as create_legacy,
    ):
        result = await resolve_model_client(
            "parent", "system-model", is_byok=False, allow_platform_fallback=True,
        )

    assert result.client is profile_client
    assert result.credential_source == CredentialSource.PLATFORM
    resolve_profile.assert_awaited_once_with(cache_key=None)
    create_legacy.assert_not_called()


@pytest.mark.asyncio
async def test_no_fallback_when_disabled():
    from src.server.services.llm.config import ModelSource, resolve_model_client

    with (
        _patch_classify(ModelSource.SYSTEM),
        patch(
            f"{HANDLER}.resolve_oauth_llm_client",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            f"{HANDLER}.resolve_byok_llm_client",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("src.llms.llm.create_llm") as mock_create,
    ):
        result = await resolve_model_client(
            "u", "m", is_byok=True, allow_platform_fallback=False,
        )

    assert result.client is None
    assert result.credential_source == CredentialSource.NONE
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_platform_fallback_not_built_for_custom():
    """Platform fallback only applies to SYSTEM models, never CUSTOM."""
    from src.server.services.llm.config import ModelSource, resolve_model_client

    with (
        _patch_classify(ModelSource.CUSTOM),
        patch(
            f"{HANDLER}.resolve_oauth_llm_client",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            f"{HANDLER}.resolve_byok_llm_client",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch("src.llms.llm.create_llm") as mock_create,
    ):
        result = await resolve_model_client(
            "u", "m", is_byok=True, allow_platform_fallback=True,
        )

    assert result.client is None
    assert result.credential_source == CredentialSource.NONE
    mock_create.assert_not_called()


@pytest.mark.asyncio
async def test_byok_on_system_model_is_orthogonal():
    """A BYOK user on a SYSTEM-catalog model: model_source=SYSTEM, cred=BYOK."""
    from src.server.services.llm.config import ModelSource, resolve_model_client

    byok_client = MagicMock(name="byok-client")
    with (
        _patch_classify(ModelSource.SYSTEM),
        patch(
            f"{HANDLER}.resolve_oauth_llm_client",
            new_callable=AsyncMock,
            return_value=None,
        ),
        patch(
            f"{HANDLER}.resolve_byok_llm_client",
            new_callable=AsyncMock,
            return_value=byok_client,
        ),
    ):
        result = await resolve_model_client("u", "m", is_byok=True)

    assert result.model_source == ModelSource.SYSTEM
    assert result.credential_source == CredentialSource.BYOK


@pytest.mark.asyncio
async def test_oauth_required_exception_propagates():
    """An OAuth-required HTTPException must NOT be swallowed."""
    from fastapi import HTTPException

    from src.server.services.llm.config import ModelSource, resolve_model_client

    exc = HTTPException(status_code=400, detail={"type": "oauth_required"})
    with (
        _patch_classify(ModelSource.SYSTEM),
        patch(
            f"{HANDLER}.resolve_oauth_llm_client",
            new_callable=AsyncMock,
            side_effect=exc,
        ),
        patch(f"{HANDLER}.resolve_byok_llm_client", new_callable=AsyncMock) as byok,
    ):
        with pytest.raises(HTTPException) as raised:
            await resolve_model_client("u", "m", is_byok=True)

    assert raised.value.detail["type"] == "oauth_required"
    byok.assert_not_called()
