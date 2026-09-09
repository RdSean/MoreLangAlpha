"""Pydantic models for user records and preferences."""

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


def normalize_instrument_type(value: Any) -> Any:
    """Normalize optional finance instrument types without changing local models."""
    return value.strip().lower() if isinstance(value, str) else value


class AgentPreference(BaseModel):
    """AI agent behavior preferences stored in JSONB."""

    model_config = ConfigDict(extra="allow")

    output_style: Optional[str] = Field(None, description="Preferred output style")
    output_format: Optional[str] = Field(
        None,
        description=(
            "Preferred output format: 'markdown' or 'html' (absent = default). "
            "Not a Literal so the endpoint validates and None-means-delete JSONB-"
            "merge semantics are preserved."
        ),
    )


class OtherPreference(BaseModel):
    """Miscellaneous preferences stored in JSONB."""

    model_config = ConfigDict(extra="allow")


class UserBase(BaseModel):
    """Base user fields."""

    email: Optional[str] = Field(None, max_length=255, description="User email")
    name: Optional[str] = Field(None, max_length=255, description="User display name")
    avatar_url: Optional[str] = Field(None, description="URL to user avatar")
    timezone: Optional[str] = Field(
        None, max_length=100, description="User timezone (e.g., 'America/New_York')"
    )
    locale: Optional[str] = Field(
        None, max_length=20, description="User locale (e.g., 'en-US')"
    )


class UserCreate(UserBase):
    """Request model for creating a new user."""

    user_id: str = Field(
        ..., max_length=255, description="External auth ID (e.g., Clerk, Auth0)"
    )


class UserUpdate(UserBase):
    """Request model for updating user profile."""

    onboarding_completed: Optional[bool] = Field(
        None, description="Whether onboarding is completed"
    )
    personalization_completed: Optional[bool] = Field(
        None, description="Whether personalization wizard is completed"
    )


class UserResponse(UserBase):
    """Response model for user details."""

    user_id: str = Field(description="User ID")
    onboarding_completed: bool = Field(
        default=False, description="Whether onboarding is completed"
    )
    personalization_completed: bool = Field(
        default=False, description="Whether personalization wizard is completed"
    )
    has_api_key: bool = Field(
        default=False, description="Whether user has at least one API key configured"
    )
    has_oauth_token: bool = Field(
        default=False, description="Whether user has at least one OAuth token connected"
    )
    access_tier: int = Field(
        default=-1, description="Platform access tier. -1 = no access, 0+ = tier level."
    )
    plan_display_name: Optional[str] = Field(
        default=None,
        description="Display name of the user's active plan (e.g. 'Pro'). None when no subscription.",
    )
    auth_provider: Optional[str] = Field(
        None, description="Authentication provider (e.g. google, github, email)"
    )
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")
    last_login_at: Optional[datetime] = Field(None, description="Last login timestamp")

    model_config = ConfigDict(from_attributes=True)


class UserPreferencesBase(BaseModel):
    """Base preferences fields."""

    model_config = ConfigDict(extra="forbid")

    agent_preference: Optional[AgentPreference] = Field(
        default_factory=AgentPreference, description="AI agent behavior settings"
    )
    other_preference: Optional[OtherPreference] = Field(
        default_factory=OtherPreference, description="Miscellaneous preferences"
    )


class UserPreferencesCreate(UserPreferencesBase):
    """Request model for creating user preferences."""


class UserPreferencesUpdate(UserPreferencesBase):
    """Request model for updating user preferences."""


class UserPreferencesResponse(UserPreferencesBase):
    """Response model for user preferences."""

    user_preference_id: UUID = Field(description="Preference record ID")
    user_id: str = Field(description="User ID")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")

    model_config = ConfigDict(from_attributes=True, extra="forbid")


class UserWithPreferencesResponse(BaseModel):
    """Combined response for GET /users/me endpoint."""

    user: UserResponse = Field(description="User profile")
    preferences: Optional[UserPreferencesResponse] = Field(
        None, description="User preferences (may be null if not set)"
    )
