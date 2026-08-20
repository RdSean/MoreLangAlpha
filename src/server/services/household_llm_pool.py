"""Household model-pool policy and runtime resolution."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from src.server.database.auth_accounts import ParentMembershipRequiredError
from src.server.database.education_members import get_membership_for_user
from src.server.database.household_llm_pool import (
    create_household_endpoint,
    delete_household_endpoint,
    get_endpoint_for_runtime,
    get_household_availability,
    list_household_endpoints,
    set_household_default as set_household_default_row,
    update_household_endpoint,
    upsert_student_preference,
)


FAMILY_MODEL_PREFIX = "family:"


class FamilyModelAccessError(PermissionError):
    """The account is not allowed to access the requested household pool."""


class NoFamilyModelAvailableError(LookupError):
    """The household has no enabled endpoint to run."""


def _normalize_endpoint_id(endpoint_id: str) -> str:
    try:
        return str(UUID(str(endpoint_id)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise FamilyModelAccessError("Endpoint identifier is invalid") from exc


async def get_household_context(user_id: str) -> dict[str, str]:
    """Return the authenticated user's household membership context."""
    membership = await get_membership_for_user(user_id)
    if not membership or not membership.get("household_id"):
        raise FamilyModelAccessError("Account is not a household member")
    return {
        "user_id": str(membership.get("user_id", user_id)),
        "household_id": str(membership["household_id"]),
        "role": str(membership.get("role", "")),
    }


async def require_parent_household(user_id: str) -> str:
    """Require a parent membership and return its household ID."""
    membership = await get_membership_for_user(user_id)
    if not membership or membership.get("role") != "parent":
        raise ParentMembershipRequiredError("Only a household parent can manage models")
    return str(membership["household_id"])


async def create_endpoint(parent_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    household_id = await require_parent_household(parent_id)
    return await create_household_endpoint(
        household_id,
        parent_id,
        display_name=fields["display_name"],
        provider=fields["provider"],
        model_id=fields["model_id"],
        base_url=fields.get("base_url"),
        api_key=fields.get("api_key"),
        enabled=fields.get("enabled", True),
        sort_order=fields.get("sort_order", 0),
    )


async def list_parent_pool(parent_id: str) -> list[dict[str, Any]]:
    household_id = await require_parent_household(parent_id)
    return await list_household_endpoints(household_id, include_disabled=True)


async def update_endpoint(
    parent_id: str, endpoint_id: str, fields: dict[str, Any]
) -> dict[str, Any] | None:
    household_id = await require_parent_household(parent_id)
    endpoint_id = _normalize_endpoint_id(endpoint_id)
    kwargs: dict[str, Any] = {}
    for name in (
        "display_name",
        "provider",
        "model_id",
        "base_url",
        "enabled",
        "sort_order",
    ):
        if name in fields:
            kwargs[name] = fields[name]
    # Do not pass this keyword unless the caller supplied it.  The database
    # sentinel preserves an existing key for ordinary metadata edits.
    if "api_key" in fields:
        kwargs["api_key"] = fields["api_key"]
    endpoint = await update_household_endpoint(household_id, endpoint_id, **kwargs)
    if endpoint is None:
        raise FamilyModelAccessError("Endpoint is unavailable in this household")
    return endpoint


async def delete_endpoint(parent_id: str, endpoint_id: str) -> bool:
    household_id = await require_parent_household(parent_id)
    endpoint_id = _normalize_endpoint_id(endpoint_id)
    if not await delete_household_endpoint(household_id, endpoint_id):
        raise FamilyModelAccessError("Endpoint is unavailable in this household")
    return True


async def set_household_default(
    parent_id: str, endpoint_id: str | None
) -> dict[str, Any]:
    household_id = await require_parent_household(parent_id)
    if endpoint_id is not None:
        endpoint_id = _normalize_endpoint_id(endpoint_id)
    result = await set_household_default_row(household_id, endpoint_id)
    if endpoint_id is not None and result.get("default_endpoint_id") is None:
        raise FamilyModelAccessError("Endpoint is unavailable in this household")
    return result


async def get_parent_pool_availability(parent_id: str) -> dict[str, Any]:
    household_id = await require_parent_household(parent_id)
    return await get_household_availability(household_id)


async def set_student_preference(
    student_id: str, endpoint_id: str | None
) -> dict[str, Any]:
    context = await get_household_context(student_id)
    if context["role"] != "student":
        raise FamilyModelAccessError("Only student accounts can set a model preference")
    if endpoint_id is not None:
        endpoint_id = _normalize_endpoint_id(endpoint_id)
        endpoint = await get_endpoint_for_runtime(context["household_id"], endpoint_id)
        if endpoint is None:
            raise FamilyModelAccessError("Endpoint is unavailable in this household")
    return await upsert_student_preference(
        student_id, context["household_id"], endpoint_id
    )


def public_model_key(endpoint_id: str) -> str:
    return f"{FAMILY_MODEL_PREFIX}{endpoint_id}"


async def _resolve_candidate(
    household_id: str, candidate: dict[str, Any] | None
) -> dict[str, Any] | None:
    if not candidate or not candidate.get("enabled", True):
        return None
    endpoint_id = candidate.get("endpoint_id")
    if not endpoint_id:
        return None
    # Availability rows are intentionally safe projections. Resolve the
    # encrypted details only after the candidate has passed policy checks.
    runtime = await get_endpoint_for_runtime(household_id, str(endpoint_id))
    return runtime


async def resolve_student_endpoint(user_id: str) -> dict[str, Any] | None:
    """Resolve preference, then household default, for a student runtime."""
    context = await get_household_context(user_id)
    if context["role"] != "student":
        raise FamilyModelAccessError("Only student accounts use student resolution")
    household_id = context["household_id"]
    availability = await get_household_availability(household_id, user_id)
    preference = availability.get("preference")
    if availability.get("_stale_preference"):
        await upsert_student_preference(user_id, household_id, None)
    if preference:
        preferred = await _resolve_candidate(household_id, preference)
        if preferred:
            return preferred
        # Keep the invalidation close to resolution so disabled/deleted
        # preferences cannot repeatedly win a future request.
        await upsert_student_preference(user_id, household_id, None)
    return await _resolve_candidate(household_id, availability.get("default"))


resolve_student_model = resolve_student_endpoint


async def resolve_family_model_key(
    user_id: str, model_key: str | None
) -> dict[str, Any] | None:
    """Resolve a ``family:<uuid>`` key only inside the caller's household."""
    context = await get_household_context(user_id)
    if model_key is None:
        if context["role"] == "student":
            return await resolve_student_endpoint(user_id)
        availability = await get_household_availability(context["household_id"])
        return await _resolve_candidate(
            context["household_id"], availability.get("default")
        )
    if not model_key.startswith(FAMILY_MODEL_PREFIX):
        return None
    endpoint_id = model_key[len(FAMILY_MODEL_PREFIX) :]
    if not endpoint_id:
        return None
    try:
        endpoint_id = str(UUID(endpoint_id))
    except (TypeError, ValueError, AttributeError):
        return None
    return await get_endpoint_for_runtime(context["household_id"], endpoint_id)


__all__ = [
    "FAMILY_MODEL_PREFIX",
    "FamilyModelAccessError",
    "NoFamilyModelAvailableError",
    "create_endpoint",
    "delete_endpoint",
    "get_household_context",
    "get_parent_pool_availability",
    "list_parent_pool",
    "public_model_key",
    "require_parent_household",
    "resolve_family_model_key",
    "resolve_student_endpoint",
    "resolve_student_model",
    "set_household_default",
    "set_student_preference",
    "update_endpoint",
]
