"""Resolve household student models from the designated parent's settings.

The household model owner is the only credential source.  This module exposes a
sanitized availability projection for API/UI consumers and a private runtime
record for the LLM resolver.  Student identifiers are used only to resolve
membership and remain the audit subject; credentials are always loaded with the
owner identifier.
"""

from __future__ import annotations

import copy
import os
from typing import Any

from src.config.settings import HOST_MODE
from src.server.database.api_keys import get_owner_api_keys
from src.server.database.household_shared_models import get_household_model_owner
from src.server.database.household_shared_models import get_student_model_preference
from src.server.database.user import get_user_preferences


class HouseholdModelAccessError(PermissionError):
    """The account has no valid designated owner."""


class HouseholdModelUnavailableError(LookupError):
    """A requested model is not currently usable by the household owner."""


def _model_config():
    from src.llms.llm import LLM

    return LLM.get_model_config()


def _owner_preferences(pref_row: dict[str, Any] | None) -> dict[str, Any]:
    if not pref_row:
        return {}
    other = pref_row.get("other_preference")
    return other if isinstance(other, dict) else {}


def _provider_candidates(provider: str, manifest) -> list[str]:
    candidates = [provider]
    parent = manifest.get_parent_provider(provider)
    if parent not in candidates:
        candidates.append(parent)
    for sibling in manifest.get_child_variants(parent):
        if sibling not in candidates:
            candidates.append(sibling)
    return candidates


def _provider_credential(
    provider: str,
    *,
    keys: dict[str, str],
    base_urls: dict[str, str | None],
    byok_enabled: bool,
    manifest,
) -> tuple[str | None, str | None, str | None] | None:
    """Return ``(api_key, base_url, holding_provider)`` without exposing it."""
    for candidate in _provider_candidates(provider, manifest):
        api_key = keys.get(candidate) if byok_enabled else None
        base_url = base_urls.get(candidate)
        provider_info = manifest.get_provider_info(candidate)
        env_key = provider_info.get("env_key")
        if api_key or base_url:
            return api_key, base_url, candidate
        # Server env credentials are user-owned only in OSS deployments, which
        # is the same rule used by the existing model settings endpoint.
        if HOST_MODE == "oss" and env_key and os.getenv(env_key):
            return os.getenv(env_key), base_url, candidate
    return None


def _public_entry(model_key: str, model: dict[str, Any], provider_info: dict[str, Any], source: str) -> dict[str, Any]:
    return {
        "model_key": model_key,
        "model_id": str(model.get("model_id") or model_key),
        "provider": str(model.get("provider") or "unknown"),
        "display_name": model.get("display_name") or model_key,
        "source": source,
        "capabilities": {
            "input_modalities": list(model.get("input_modalities") or ["text"]),
        },
        "provider_display_name": provider_info.get("display_name"),
    }


async def _load_owner_state(member_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    owner_context = await get_household_model_owner(member_id)
    if not owner_context or not owner_context.get("model_owner_user_id"):
        raise HouseholdModelAccessError("Account is not in a household with a valid model owner")
    owner_id = str(owner_context["model_owner_user_id"])
    credentials = await get_owner_api_keys(owner_id)
    preferences = _owner_preferences(await get_user_preferences(owner_id))
    return owner_context, credentials, preferences, _model_config()


async def _available_runtime_entries(member_id: str) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    context, credentials, preferences, manifest = await _load_owner_state(member_id)
    keys = credentials.get("keys") or {}
    base_urls = credentials.get("base_urls") or {}
    byok_enabled = bool(credentials.get("byok_enabled"))
    entries: dict[str, dict[str, Any]] = {}

    for model_key, model in (manifest.llm_config or {}).items():
        if not isinstance(model, dict) or not model.get("visible", False):
            continue
        provider = model.get("provider")
        creds = _provider_credential(
            provider,
            keys=keys,
            base_urls=base_urls,
            byok_enabled=byok_enabled,
            manifest=manifest,
        ) if provider else None
        if not creds:
            continue
        api_key, base_url, holding = creds
        entries[model_key] = {
            **_public_entry(model_key, model, manifest.get_provider_info(provider), "system"),
            "config": {"name": model_key, **copy.deepcopy(model)},
            "api_key": api_key,
            "base_url": base_url or manifest.get_provider_info(provider).get("base_url"),
            "holding_provider": holding,
        }

    custom_providers = {
        item.get("name"): item
        for item in preferences.get("custom_providers") or []
        if isinstance(item, dict) and item.get("name")
    }
    for custom in preferences.get("custom_models") or []:
        if not isinstance(custom, dict) or not custom.get("name") or not custom.get("model_id"):
            continue
        model_key = str(custom["name"])
        provider = str(custom.get("provider") or "")
        if not provider:
            continue
        custom_provider = custom_providers.get(provider)
        parent_provider = str(custom_provider.get("parent_provider") or provider) if custom_provider else provider
        # A custom provider's own key/base URL takes precedence.  If it was
        # not configured independently, it can use its manifest parent's key.
        direct = (
            keys.get(provider) if byok_enabled else None,
            base_urls.get(provider),
            provider,
        )
        creds = direct if direct[0] or direct[1] else _provider_credential(
            parent_provider,
            keys=keys,
            base_urls=base_urls,
            byok_enabled=byok_enabled,
            manifest=manifest,
        )
        if not creds:
            continue
        api_key, base_url, holding = creds
        provider_info = manifest.get_provider_info(parent_provider)
        config = {"name": model_key, **copy.deepcopy(custom)}
        # Unknown provider slugs inherit their declared non-OpenAI parent's
        # SDK and protocol settings, exactly as regular owner custom models do.
        if custom_provider:
            if custom_provider.get("use_response_api"):
                config["_use_response_api"] = True
            if provider_info.get("sdk") not in (None, "openai"):
                config["provider"] = parent_provider
        entries[model_key] = {
            **_public_entry(model_key, custom, provider_info, "custom"),
            "config": config,
            "api_key": api_key,
            "base_url": base_url or provider_info.get("base_url"),
            "holding_provider": holding,
        }

    return context, entries


async def get_household_model_availability(member_id: str) -> dict[str, Any]:
    """Return all currently usable owner models without any secret fields."""
    context, entries = await _available_runtime_entries(member_id)
    preferences = _owner_preferences(
        await get_user_preferences(str(context["model_owner_user_id"]))
    )
    preferred = preferences.get("preferred_model")
    if preferred not in entries:
        preferred = preferences.get("preferred_flash_model")
    public_models = []
    for entry in entries.values():
        public_models.append({key: value for key, value in entry.items() if key not in {"config", "api_key", "base_url", "holding_provider"}})
    public_models.sort(key=lambda item: str(item["model_key"]))
    return {
        "household_id": str(context["household_id"]),
        "model_owner_user_id": str(context["model_owner_user_id"]),
        "models": public_models,
        "default_model_key": preferred if preferred in entries else (public_models[0]["model_key"] if public_models else None),
    }


async def resolve_household_model(member_id: str, model_key: str | None) -> dict[str, Any]:
    """Resolve a public model key to an owner-backed, secret-bearing runtime record."""
    context, entries = await _available_runtime_entries(member_id)
    if model_key is None:
        student_preference = await get_student_model_preference(
            member_id, str(context["household_id"])
        )
        preferences = _owner_preferences(
            await get_user_preferences(str(context["model_owner_user_id"]))
        )
        model_key = (
            student_preference.get("model_key") if student_preference else None
        ) or preferences.get("preferred_model") or preferences.get("preferred_flash_model")
        if model_key not in entries:
            model_key = next(iter(entries), None)
    if not model_key or model_key not in entries:
        raise HouseholdModelUnavailableError("Household model is unavailable")
    return {
        **entries[model_key],
        "household_id": str(context["household_id"]),
        "owner_user_id": str(context["model_owner_user_id"]),
        "student_user_id": str(member_id),
    }


__all__ = [
    "HouseholdModelAccessError",
    "HouseholdModelUnavailableError",
    "get_household_model_availability",
    "resolve_household_model",
]
