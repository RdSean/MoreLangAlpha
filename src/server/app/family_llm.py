"""Household-owned LLM endpoint management and student availability APIs."""

from __future__ import annotations

from functools import lru_cache
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.server.database.auth_accounts import ParentMembershipRequiredError
from src.server.services.household_llm_pool import (
    FamilyModelAccessError,
    create_endpoint,
    delete_endpoint,
    get_household_availability,
    get_household_context,
    get_parent_pool_availability,
    list_parent_pool,
    public_model_key,
    set_household_default,
    set_student_preference,
    update_endpoint,
)
from src.server.utils.api import CurrentUserId


router = APIRouter(prefix="/api/v1/family", tags=["Family LLM Pool"])


class _RequestModel(BaseModel):
    """Avoid echoing a submitted credential in validation error responses."""

    model_config = ConfigDict(hide_input_in_errors=True)


def _required_text(value: str) -> str:
    value = value.strip()
    if not value:
        raise ValueError("A non-empty value is required")
    return value


def _validate_base_url(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value.startswith(("http://", "https://")):
        raise ValueError("Base URL must start with http:// or https://")
    return value


def _validate_api_key(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise HTTPException(status_code=422, detail="API key must be a string")
    if len(value) > 4096:
        # Do not let FastAPI's generic validation renderer echo credentials.
        raise HTTPException(status_code=422, detail="API key must be at most 4096 characters")
    if value and not value.isascii():
        raise HTTPException(status_code=422, detail="API key must contain only ASCII characters")
    return value


class EndpointCreateRequest(_RequestModel):
    display_name: str = Field(min_length=1, max_length=128)
    provider: str = Field(min_length=1, max_length=64)
    model_id: str = Field(min_length=1, max_length=255)
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: str | None = None
    enabled: bool = True
    sort_order: int = Field(default=0, ge=-10_000, le=10_000)

    _display_name = field_validator("display_name")(_required_text)
    _provider = field_validator("provider")(_required_text)
    _model_id = field_validator("model_id")(_required_text)
    _base_url = field_validator("base_url")(_validate_base_url)
    _api_key = field_validator("api_key", mode="before")(_validate_api_key)


class EndpointUpdateRequest(_RequestModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    provider: str | None = Field(default=None, min_length=1, max_length=64)
    model_id: str | None = Field(default=None, min_length=1, max_length=255)
    base_url: str | None = Field(default=None, max_length=2048)
    api_key: str | None = None
    enabled: bool | None = None
    sort_order: int | None = Field(default=None, ge=-10_000, le=10_000)

    _display_name = field_validator("display_name")(_required_text)
    _provider = field_validator("provider")(_required_text)
    _model_id = field_validator("model_id")(_required_text)
    _base_url = field_validator("base_url")(_validate_base_url)
    _api_key = field_validator("api_key", mode="before")(_validate_api_key)


class DefaultEndpointRequest(_RequestModel):
    endpoint_id: UUID | None = None


class StudentPreferenceRequest(_RequestModel):
    endpoint_id: UUID | None = None


@lru_cache(maxsize=1)
def _available_providers() -> frozenset[str]:
    """Return manifest-backed providers that can be configured by a family."""
    from src.llms.llm import ModelConfig

    return frozenset(
        name
        for name, info in ModelConfig().flat_providers.items()
        if not info.get("platform")
    )


def _require_available_provider(provider: str) -> None:
    if provider not in _available_providers():
        raise HTTPException(status_code=422, detail="Unsupported LLM provider")


def _parent_endpoint_summary(endpoint: dict[str, Any]) -> dict[str, Any]:
    """Return the explicit parent projection, never a plaintext credential."""
    return {
        "endpoint_id": str(endpoint["endpoint_id"]),
        "display_name": endpoint["display_name"],
        "provider": endpoint["provider"],
        "model_id": endpoint["model_id"],
        "base_url": endpoint.get("base_url"),
        "masked_api_key": endpoint.get("masked_api_key")
        or endpoint.get("masked_key"),
        "enabled": bool(endpoint.get("enabled", True)),
        "sort_order": endpoint.get("sort_order", 0),
    }


def _availability_projection(availability: dict[str, Any]) -> dict[str, Any]:
    """Strip endpoint internals and add the stable public model key."""
    endpoints: list[dict[str, Any]] = []
    for endpoint in availability.get("endpoints", []):
        endpoint_id = str(endpoint["endpoint_id"])
        endpoints.append(
            {
                "endpoint_id": endpoint_id,
                "display_name": endpoint["display_name"],
                "provider": endpoint["provider"],
                "model_id": endpoint["model_id"],
                "enabled": bool(endpoint.get("enabled", True)),
                "sort_order": endpoint.get("sort_order", 0),
                "model_key": public_model_key(endpoint_id),
            }
        )

    preference = availability.get("preference")
    default = availability.get("default")
    selected = preference or default
    selected_source = "preference" if preference else "default" if default else None
    return {
        "endpoints": endpoints,
        "selected_endpoint_id": str(selected["endpoint_id"]) if selected else None,
        "selected_source": selected_source,
        "preference_endpoint_id": str(preference["endpoint_id"])
        if preference
        else None,
        "default_endpoint_id": str(default["endpoint_id"]) if default else None,
    }


def _parent_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ParentMembershipRequiredError):
        return HTTPException(status_code=403, detail="Parent membership required")
    return HTTPException(status_code=404, detail="Household endpoint not found")


def _member_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ParentMembershipRequiredError):
        return HTTPException(status_code=403, detail="Parent membership required")
    return HTTPException(status_code=403, detail="Household membership required")


@router.get("/llm-pool")
async def get_pool(user_id: CurrentUserId):
    try:
        endpoints = await list_parent_pool(user_id)
        availability = await get_parent_pool_availability(user_id)
    except (ParentMembershipRequiredError, FamilyModelAccessError) as exc:
        raise _parent_error(exc) from exc
    default = availability.get("default")
    return {
        "endpoints": [_parent_endpoint_summary(endpoint) for endpoint in endpoints],
        "default_endpoint_id": str(default["endpoint_id"]) if default else None,
    }


@router.post("/llm-pool", status_code=status.HTTP_201_CREATED)
async def create_pool_endpoint(body: EndpointCreateRequest, user_id: CurrentUserId):
    _require_available_provider(body.provider)
    try:
        endpoint = await create_endpoint(user_id, body.model_dump())
    except (ParentMembershipRequiredError, FamilyModelAccessError) as exc:
        raise _parent_error(exc) from exc
    return _parent_endpoint_summary(endpoint)


@router.patch("/llm-pool/{endpoint_id}")
async def patch_pool_endpoint(
    endpoint_id: UUID, body: EndpointUpdateRequest, user_id: CurrentUserId
):
    fields = body.model_dump(exclude_unset=True)
    if "provider" in fields:
        _require_available_provider(fields["provider"])
    try:
        endpoint = await update_endpoint(user_id, str(endpoint_id), fields)
    except (ParentMembershipRequiredError, FamilyModelAccessError) as exc:
        raise _parent_error(exc) from exc
    return _parent_endpoint_summary(endpoint)


@router.delete("/llm-pool/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_pool_endpoint(endpoint_id: UUID, user_id: CurrentUserId) -> Response:
    try:
        await delete_endpoint(user_id, str(endpoint_id))
    except (ParentMembershipRequiredError, FamilyModelAccessError) as exc:
        raise _parent_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/llm-pool/default")
async def update_pool_default(body: DefaultEndpointRequest, user_id: CurrentUserId):
    endpoint_id = str(body.endpoint_id) if body.endpoint_id is not None else None
    try:
        result = await set_household_default(user_id, endpoint_id)
    except ParentMembershipRequiredError as exc:
        raise _parent_error(exc) from exc
    except FamilyModelAccessError as exc:
        raise HTTPException(
            status_code=409, detail="The requested default endpoint is unavailable"
        ) from exc
    return {"default_endpoint_id": result.get("default_endpoint_id")}


async def _availability_for_member(user_id: str) -> tuple[dict[str, str], dict[str, Any]]:
    try:
        context = await get_household_context(user_id)
    except (ParentMembershipRequiredError, FamilyModelAccessError) as exc:
        raise _member_error(exc) from exc
    availability = await get_household_availability(
        context["household_id"], user_id if context["role"] == "student" else None
    )
    return context, availability


@router.get("/llm-availability")
async def get_llm_availability(user_id: CurrentUserId):
    _, availability = await _availability_for_member(user_id)
    return _availability_projection(availability)


@router.put("/llm-preference")
async def update_llm_preference(body: StudentPreferenceRequest, user_id: CurrentUserId):
    try:
        context = await get_household_context(user_id)
    except (ParentMembershipRequiredError, FamilyModelAccessError) as exc:
        raise _member_error(exc) from exc
    if context["role"] != "student":
        raise HTTPException(status_code=403, detail="Only student accounts can set a model preference")
    endpoint_id = str(body.endpoint_id) if body.endpoint_id is not None else None
    try:
        await set_student_preference(user_id, endpoint_id)
    except FamilyModelAccessError as exc:
        # An unavailable selection (including a disabled endpoint) is a state
        # conflict. The service also enforces household membership for the ID.
        raise HTTPException(status_code=409, detail="The requested endpoint is unavailable") from exc
    availability = await get_household_availability(context["household_id"], user_id)
    return _availability_projection(availability)
