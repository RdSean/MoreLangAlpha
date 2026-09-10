"""Deployment-level platform model profile backed by a service account."""

from __future__ import annotations

import logging
import os

from src.server.database.api_keys import is_byok_active
from src.server.database.user import find_user_by_email

from .clients import resolve_byok_llm_client

logger = logging.getLogger(__name__)


def _configured_profile() -> tuple[str, str] | None:
    source_email = os.getenv("PLATFORM_LLM_SOURCE_EMAIL", "").strip()
    model_name = os.getenv("PLATFORM_LLM_MODEL", "").strip()
    if not source_email or not model_name:
        return None
    return source_email, model_name


def is_platform_model_profile_configured() -> bool:
    """Whether a complete non-secret platform model profile is configured."""
    return _configured_profile() is not None


async def resolve_platform_llm_client(*, cache_key: str | None = None):
    """Build the platform client from the configured service account, or fail closed."""
    profile = _configured_profile()
    if profile is None:
        return None

    source_email, model_name = profile
    try:
        account = await find_user_by_email(source_email)
        if not account:
            logger.warning("[PLATFORM] Configured model profile source account is unavailable")
            return None
        source_user_id = str(account["user_id"])
        if not await is_byok_active(source_user_id):
            logger.warning("[PLATFORM] Configured model profile has no active credential")
            return None
        client = await resolve_byok_llm_client(
            source_user_id,
            model_name,
            True,
            cache_key=cache_key,
        )
        if client is None:
            logger.warning("[PLATFORM] Configured model profile could not resolve its model")
        return client
    except Exception:
        logger.exception("[PLATFORM] Configured model profile lookup failed")
        return None
