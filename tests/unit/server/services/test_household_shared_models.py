from unittest.mock import AsyncMock, MagicMock, patch

import pytest


SERVICE = "src.server.services.household_shared_models"


def _manifest():
    config = MagicMock()
    config.get_model_config.side_effect = lambda name: {
        "gpt-owner": {
            "model_id": "gpt-owner-id",
            "provider": "openai",
            "display_name": "Owner GPT",
            "visible": True,
            "input_modalities": ["text", "image"],
        },
        "no-key": {
            "model_id": "no-key-id",
            "provider": "anthropic",
            "display_name": "No Key",
            "visible": True,
        },
    }.get(name)
    config.llm_config = {
        "gpt-owner": config.get_model_config("gpt-owner"),
        "no-key": config.get_model_config("no-key"),
    }
    config.get_provider_info.side_effect = lambda provider: {
        "openai": {"display_name": "OpenAI", "sdk": "openai", "base_url": "https://api.openai.com/v1"},
        "anthropic": {"display_name": "Anthropic", "sdk": "anthropic"},
    }.get(provider, {})
    config.get_parent_provider.side_effect = lambda provider: provider
    config.get_child_variants.return_value = []
    return config


@pytest.mark.asyncio
async def test_availability_uses_owner_keys_and_preferences_for_all_models():
    from src.server.services.household_shared_models import get_household_model_availability

    owner_prefs = {
        "other_preference": {
            "preferred_model": "custom-owner",
            "custom_models": [
                {
                    "name": "custom-owner",
                    "model_id": "owner-custom-id",
                    "provider": "openai",
                    "input_modalities": ["text"],
                }
            ],
        }
    }
    with (
        patch(f"{SERVICE}.get_household_model_owner", new_callable=AsyncMock, return_value={
            "household_id": "household-1", "model_owner_user_id": "owner-1"
        }),
        patch(f"{SERVICE}.get_owner_api_keys", new_callable=AsyncMock, return_value={
            "byok_enabled": True, "keys": {"openai": "owner-secret"}, "base_urls": {}
        }),
        patch(f"{SERVICE}.get_user_preferences", new_callable=AsyncMock, return_value=owner_prefs),
        patch("src.llms.llm.LLM.get_model_config", return_value=_manifest()),
    ):
        result = await get_household_model_availability("student-1")

    assert result["household_id"] == "household-1"
    assert result["model_owner_user_id"] == "owner-1"
    assert {model["model_key"] for model in result["models"]} == {"gpt-owner", "custom-owner"}
    assert result["default_model_key"] == "custom-owner"
    assert all("api_key" not in model and "base_url" not in model for model in result["models"])


@pytest.mark.asyncio
async def test_availability_omits_catalog_models_without_owner_credentials():
    from src.server.services.household_shared_models import get_household_model_availability

    with (
        patch(f"{SERVICE}.get_household_model_owner", new_callable=AsyncMock, return_value={
            "household_id": "household-1", "model_owner_user_id": "owner-1"
        }),
        patch(f"{SERVICE}.get_owner_api_keys", new_callable=AsyncMock, return_value={
            "byok_enabled": True, "keys": {"openai": "owner-secret"}, "base_urls": {}
        }),
        patch(f"{SERVICE}.get_user_preferences", new_callable=AsyncMock, return_value={"other_preference": {}}),
        patch("src.llms.llm.LLM.get_model_config", return_value=_manifest()),
    ):
        result = await get_household_model_availability("student-1")

    assert [model["model_key"] for model in result["models"]] == ["gpt-owner"]


@pytest.mark.asyncio
async def test_runtime_resolution_returns_owner_credential_for_public_model_key():
    from src.server.services.household_shared_models import resolve_household_model

    with (
        patch(f"{SERVICE}.get_household_model_owner", new_callable=AsyncMock, return_value={
            "household_id": "household-1", "model_owner_user_id": "owner-1"
        }),
        patch(f"{SERVICE}.get_owner_api_keys", new_callable=AsyncMock, return_value={
            "byok_enabled": True, "keys": {"openai": "owner-secret"}, "base_urls": {}
        }),
        patch(f"{SERVICE}.get_user_preferences", new_callable=AsyncMock, return_value={"other_preference": {}}),
        patch("src.llms.llm.LLM.get_model_config", return_value=_manifest()),
    ):
        runtime = await resolve_household_model("student-1", "gpt-owner")

    assert runtime["owner_user_id"] == "owner-1"
    assert runtime["api_key"] == "owner-secret"
    assert runtime["model_id"] == "gpt-owner-id"
    assert runtime["provider"] == "openai"


@pytest.mark.asyncio
async def test_runtime_resolution_rejects_unavailable_public_model_key():
    from src.server.services.household_shared_models import HouseholdModelUnavailableError, resolve_household_model

    with (
        patch(f"{SERVICE}.get_household_model_owner", new_callable=AsyncMock, return_value={
            "household_id": "household-1", "model_owner_user_id": "owner-1"
        }),
        patch(f"{SERVICE}.get_owner_api_keys", new_callable=AsyncMock, return_value={
            "byok_enabled": True, "keys": {}, "base_urls": {}
        }),
        patch(f"{SERVICE}.get_user_preferences", new_callable=AsyncMock, return_value={"other_preference": {}}),
        patch("src.llms.llm.LLM.get_model_config", return_value=_manifest()),
    ):
        with pytest.raises(HouseholdModelUnavailableError):
            await resolve_household_model("student-1", "no-key")
