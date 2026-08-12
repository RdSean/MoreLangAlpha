"""First-party local account and household membership API."""

import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from src.server.auth.local_sessions import (
    SESSION_COOKIE_NAME,
    hash_password,
    hash_session_token,
    new_session_token,
    session_cookie_options,
    session_ttl,
)
from src.server.database.auth_accounts import (
    AccountAlreadyExistsError,
    ParentMembershipRequiredError,
    create_child_account,
    create_session_record,
    get_account_for_login,
    get_member_for_user,
    list_household_members_for_parent,
    register_parent_account,
    revoke_session_digest,
    rotate_session_record,
    session_expiry,
)
from src.server.utils.api import CurrentUserId

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


def _required_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("A non-empty value is required")
    return normalized


class MemberResponse(BaseModel):
    user_id: str
    email: str | None = None
    name: str
    role: str
    household_id: str


class ParentRegistrationRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=12, max_length=512)
    name: str = Field(min_length=1, max_length=255)
    household_name: str = Field(min_length=1, max_length=255)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not _EMAIL_RE.fullmatch(normalized):
            raise ValueError("A valid email address is required")
        return normalized

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        normalized = value.strip()
        try:
            ZoneInfo(normalized)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("A valid IANA timezone is required") from exc
        return normalized

    @field_validator("name", "household_name")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _required_text(value)


class LocalLoginRequest(BaseModel):
    login_identifier: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=512)


class ChildAccountRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=512)
    name: str = Field(min_length=1, max_length=255)

    @field_validator("username")
    @classmethod
    def validate_username(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not _USERNAME_RE.fullmatch(normalized):
            raise ValueError("Username must be 3-64 lowercase letters, numbers, dots, hyphens, or underscores")
        return normalized

    @field_validator("name")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        return _required_text(value)


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(SESSION_COOKIE_NAME, token, **session_cookie_options())


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=session_cookie_options()["secure"],
        samesite="lax",
    )


async def create_authenticated_session(user_id: str) -> str:
    """Persist a digest then return the only copy of the browser session token."""
    token = new_session_token()
    await create_session_record(
        user_id=user_id,
        token_digest=hash_session_token(token),
        expires_at=session_expiry(session_ttl()),
    )
    return token


async def authenticate_local_account(
    login_identifier: str, password: str
) -> dict | None:
    """Validate a password without revealing whether the identifier exists."""
    from src.server.auth.local_sessions import verify_password

    account = await get_account_for_login(login_identifier)
    if not account or not verify_password(password, account["password_hash"]):
        return None
    return {
        "user_id": account["user_id"],
        "email": account["email"],
        "name": account["display_name"],
        "role": account["role"],
        "household_id": str(account["household_id"]),
    }


async def revoke_session_token(token: str) -> bool:
    """Revoke the stored digest of a browser session token."""
    return await revoke_session_digest(hash_session_token(token))


async def rotate_authenticated_session(old_token: str) -> str | None:
    """Replace a valid cookie token with a fresh opaque token."""
    new_token = new_session_token()
    user_id = await rotate_session_record(
        old_token_digest=hash_session_token(old_token),
        new_token_digest=hash_session_token(new_token),
        expires_at=session_expiry(session_ttl()),
    )
    return new_token if user_id else None


@router.post("/register-parent", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def register_parent(body: ParentRegistrationRequest, response: Response):
    try:
        member = await register_parent_account(
            email=body.email,
            password_hash=hash_password(body.password),
            name=body.name.strip(),
            household_name=body.household_name.strip(),
            timezone_name=body.timezone.strip(),
        )
    except AccountAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    token = await create_authenticated_session(member["user_id"])
    _set_session_cookie(response, token)
    return member


@router.post("/login", response_model=MemberResponse)
async def login(body: LocalLoginRequest, response: Response):
    member = await authenticate_local_account(body.login_identifier, body.password)
    if not member:
        raise HTTPException(status_code=401, detail="Invalid login identifier or password")
    token = await create_authenticated_session(member["user_id"])
    _set_session_cookie(response, token)
    return member


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        await revoke_session_token(token)
    _clear_session_cookie(response)


@router.post("/session/rotate", status_code=status.HTTP_204_NO_CONTENT)
async def rotate_session(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=401, detail="Missing authentication")
    replacement = await rotate_authenticated_session(token)
    if not replacement:
        raise HTTPException(status_code=401, detail="Session expired or revoked")
    _set_session_cookie(response, replacement)


@router.get("/me", response_model=MemberResponse)
async def get_current_member(user_id: CurrentUserId):
    member = await get_member_for_user(user_id)
    if not member:
        raise HTTPException(status_code=404, detail="Account membership not found")
    return member


@router.post("/children", response_model=MemberResponse, status_code=status.HTTP_201_CREATED)
async def create_child(body: ChildAccountRequest, user_id: CurrentUserId):
    try:
        return await create_child_account(
            parent_user_id=user_id,
            username=body.username,
            password_hash=hash_password(body.password),
            name=body.name.strip(),
        )
    except ParentMembershipRequiredError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AccountAlreadyExistsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/members", response_model=list[MemberResponse])
async def list_household_members(user_id: CurrentUserId):
    try:
        return await list_household_members_for_parent(user_id)
    except ParentMembershipRequiredError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
