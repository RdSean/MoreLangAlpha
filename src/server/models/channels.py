"""Public, secret-free models for channel binding APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChannelStatus(BaseModel):
    channel_type: str
    status: Literal["unlinked", "active", "reauth_required", "disabled"]
    display_name: str | None = None
    idle_timeout_seconds: int = Field(ge=60, le=604800)
    last_error_code: str | None = None


class LinkAttemptResponse(BaseModel):
    attempt_id: UUID
    channel_type: str
    status: Literal[
        "waiting", "scanned", "verification_required", "linked", "expired", "failed", "cancelled"
    ]
    qr_code_url: str | None = None
    expires_at: datetime
    verification_required: bool = False


class LinkPollRequest(BaseModel):
    verification_code: str | None = Field(default=None, min_length=4, max_length=16, pattern=r"^[0-9]+$")


class UpdateChannelRequest(BaseModel):
    idle_timeout_seconds: int = Field(ge=60, le=604800)
