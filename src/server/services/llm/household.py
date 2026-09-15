"""Household (family) model resolution — this deployment's own LLM path.

A student account does not own a credential. Its models come from the
household owner's configured pool, resolved through
``household_shared_models``, and the turn is billed to the owner (the platform
did not pay). Upstream has no such tier, so this module lives beside the
upstream `config`/`clients`/`availability` split rather than inside it: the
selection pipeline calls :func:`resolve_student_household_config` first and
returns its result unchanged when the account is a household student.

Provenance travels two ways on purpose. ``config.credential_source`` is
``HOUSEHOLD`` so the resolver and the credit gate treat the turn as an own-key
turn, and ``config.llm_runtime_metadata`` carries the household/owner/student
ids for the usage rows. The client's own ``billing_type`` is normalised to
``byok`` — a fourth value would have to be taught to the pricing table and the
metrics, and the household facts are already carried by the metadata.
"""

from __future__ import annotations

from typing import Any, NoReturn

from ptc_agent.config.agent import CredentialSource

from src.server.database.education_members import get_membership_for_user
from src.server.services.household_shared_models import (
    HouseholdModelAccessError,
    HouseholdModelUnavailableError,
    resolve_household_model,
)


def _raise_no_model_available(*, status_code: int = 409) -> NoReturn:
    """Raise the safe, action-oriented error for an unselected family model."""
    from fastapi import HTTPException

    raise HTTPException(
        status_code=status_code,
        detail={
            "message": "No household model is available for this account.",
            "type": "no_model_available",
        },
    )


def resolve_household_llm_client(
    endpoint: dict[str, Any], *, cache_key: str | None = None
) -> Any:
    """Build an owner-backed client without retaining its decrypted key."""
    from src.llms.llm import create_llm_from_custom

    client = create_llm_from_custom(
        endpoint["config"],
        api_key=endpoint.get("api_key") or "",
        base_url=endpoint.get("base_url"),
        cache_key=cache_key,
    )
    # Billing provenance. The credential is the household owner's, so the turn
    # is an own-key turn (never platform credits) and the platform bills the
    # owner; the household ids keep the per-student attribution without adding
    # a fourth ``billing_type`` the pricing table and the metrics do not know.
    metadata = dict(getattr(client, "metadata", None) or {})
    metadata.update(
        {
            "billing_type": "byok",
            "credential_source": CredentialSource.HOUSEHOLD.value,
            "household_id": str(endpoint["household_id"]),
            "model_owner_user_id": str(endpoint["owner_user_id"]),
            "student_user_id": str(endpoint["student_user_id"]),
        }
    )
    client.metadata = metadata
    return client


def _household_runtime_metadata(endpoint: dict[str, Any]) -> dict[str, str]:
    """Return the allow-listed provenance safe for config and run metadata."""
    return {
        "credential_source": CredentialSource.HOUSEHOLD.value,
        "household_id": str(endpoint["household_id"]),
        "model_owner_user_id": str(endpoint["owner_user_id"]),
        "student_user_id": str(endpoint["student_user_id"]),
        "model_key": str(endpoint["model_key"]),
        "display_name": str(endpoint["display_name"]),
        "provider": str(endpoint["provider"]),
        "model_id": str(endpoint["model_id"]),
    }


async def get_household_context(user_id: str) -> dict[str, str]:
    """Return membership context while keeping this resolver testable."""
    membership = await get_membership_for_user(user_id)
    if not membership or not membership.get("household_id"):
        raise HouseholdModelAccessError("Account is not a household member")
    return {
        "user_id": str(membership.get("user_id", user_id)),
        "household_id": str(membership["household_id"]),
        "role": str(membership.get("role", "")),
    }


async def _student_household_context(user_id: str) -> dict[str, str] | None:
    """Return a student household context, preserving non-family resolution."""
    try:
        context = await get_household_context(user_id)
    except PermissionError:
        return None
    return context if context.get("role") == "student" else None


async def resolve_student_household_config(
    base_config: Any,
    user_id: str,
    request_model: str | None,
    *,
    thread_id: str | None,
    enabled_subagents: list[str] | None,
) -> Any | None:
    """Resolve the sealed student runtime path, or ``None`` for other users.

    Returning ``None`` means "not a household student" and lets the upstream
    pipeline run untouched. Every failure for an actual student raises instead:
    a student must never silently fall back to a personal or platform model.
    """
    from fastapi import HTTPException
    from ptc_agent.config import LLMConfig

    context = await _student_household_context(user_id)
    if context is None:
        return None

    try:
        endpoint = await resolve_household_model(user_id, request_model)
    except HouseholdModelAccessError:
        # Membership changes racing the initial context lookup must never leak
        # into a normal-model fallback path.
        raise HTTPException(
            status_code=403,
            detail={
                "message": "Household model is unavailable.",
                "type": "no_model_available",
            },
        ) from None
    except HouseholdModelUnavailableError:
        _raise_no_model_available(status_code=404 if request_model else 409)

    model_id = str(endpoint["model_key"])
    client = resolve_household_llm_client(endpoint, cache_key=thread_id)
    config = base_config.model_copy(deep=True)
    # Student roles deliberately share this same household owner model. No
    # personal fallback/role model may materialize through the normal path.
    config.llm = LLMConfig(
        name=model_id,
        flash=model_id,
        compaction=model_id,
        fetch=model_id,
        fallback=None,
    )
    config.llm_client = client
    config.credential_source = CredentialSource.HOUSEHOLD
    config.resolved_model = model_id
    config.llm_runtime_metadata = _household_runtime_metadata(endpoint)
    config.cache_key = thread_id
    subagents = (
        enabled_subagents if enabled_subagents is not None else config.subagents.enabled
    )
    config.subsidiary_llm_clients = {
        "compaction": client,
        "fetch": client,
        **{f"subagent:{name}": client for name in subagents},
    }
    config.fallback_llm_clients = None
    config.fallback_llm_names = None
    return config
