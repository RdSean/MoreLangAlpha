"""Read-only household model availability and student selection APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.server.database.household_shared_models import (
    clear_student_model_preference,
    get_household_owner_for_user,
    get_student_model_preference,
    upsert_student_model_preference,
)
from src.server.services.household_shared_models import (
    HouseholdModelAccessError,
    get_household_model_availability,
)
from src.server.utils.api import CurrentUserId


router = APIRouter(prefix="/api/v1/family", tags=["Family Models"])


class StudentPreferenceRequest(BaseModel):
    """A student's optional selection from the current owner-backed models."""

    model_config = ConfigDict(extra="forbid")

    model_key: str | None = Field(..., max_length=255)

    @field_validator("model_key")
    @classmethod
    def normalize_model_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("model_key must not be empty")
        return value


async def _member_context(user_id: str) -> dict[str, Any]:
    context = await get_household_owner_for_user(user_id)
    if context is None:
        raise HTTPException(status_code=403, detail="Household membership required")
    return context


async def _owner_availability(user_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    context = await _member_context(user_id)
    try:
        availability = await get_household_model_availability(user_id)
    except HouseholdModelAccessError as exc:
        raise HTTPException(
            status_code=403, detail="Household model owner is unavailable"
        ) from exc
    return context, availability


async def _availability_projection(
    user_id: str,
    context: dict[str, Any],
    availability: dict[str, Any],
    *,
    selected_override: str | None | object = ...,
) -> dict[str, Any]:
    """Add the member-specific selection without exposing owner internals."""
    models = _public_models(availability.get("models") or [])
    available_keys = {
        str(model["model_key"])
        for model in models
        if isinstance(model, dict) and model.get("model_key")
    }
    default_model_key = availability.get("default_model_key")
    if default_model_key not in available_keys:
        default_model_key = None

    selected_model_key = default_model_key
    selected_source = "default" if selected_model_key else None
    if context.get("role") == "student":
        if selected_override is ...:
            preference = await get_student_model_preference(
                user_id, str(context["household_id"])
            )
            preferred_key = preference.get("model_key") if preference else None
        else:
            preferred_key = selected_override
        if preferred_key in available_keys:
            selected_model_key = preferred_key
            selected_source = "preference"

    has_available_models = bool(models)
    return {
        "models": models,
        "default_model_key": default_model_key,
        "selected_model_key": selected_model_key,
        "selected_source": selected_source,
        "has_available_models": has_available_models,
        "empty_reason": None if has_available_models else "no_available_models",
    }


def _public_models(models: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy only fields that are safe for members to receive."""
    public_models: list[dict[str, Any]] = []
    for model in models:
        if not isinstance(model, dict) or not model.get("model_key"):
            continue
        public_model = {
            "model_key": str(model["model_key"]),
            "display_name": str(model.get("display_name") or model["model_key"]),
            "provider": str(model.get("provider") or "unknown"),
            "model_id": str(model.get("model_id") or model["model_key"]),
        }
        capabilities = model.get("capabilities")
        if isinstance(capabilities, dict):
            input_modalities = capabilities.get("input_modalities")
            if isinstance(input_modalities, list):
                public_model["capabilities"] = {
                    "input_modalities": [
                        str(modality) for modality in input_modalities
                    ]
                }
        public_models.append(public_model)
    return public_models


@router.get("/llm-availability")
async def get_llm_availability(user_id: CurrentUserId):
    """Return the designated parent's usable models for a household member."""
    context, availability = await _owner_availability(user_id)
    return await _availability_projection(user_id, context, availability)


@router.put("/llm-preference")
async def update_llm_preference(body: StudentPreferenceRequest, user_id: CurrentUserId):
    """Save or clear the authenticated student's selection only."""
    context, availability = await _owner_availability(user_id)
    if context.get("role") != "student":
        raise HTTPException(
            status_code=403, detail="Only student accounts can set a model preference"
        )

    model_key = body.model_key
    available_keys = {
        str(model["model_key"])
        for model in availability.get("models") or []
        if isinstance(model, dict) and model.get("model_key")
    }
    if model_key is not None and model_key not in available_keys:
        # Do not distinguish disabled, deleted, or foreign model keys.
        raise HTTPException(status_code=404, detail="Household model is unavailable")

    household_id = str(context["household_id"])
    if model_key is None:
        await clear_student_model_preference(user_id, household_id)
    else:
        await upsert_student_model_preference(user_id, household_id, model_key)

    return await _availability_projection(
        user_id, context, availability, selected_override=model_key
    )
