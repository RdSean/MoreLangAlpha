"""First-party local account and household membership API."""

import json
import re
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
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
from src.server.models.conversation import WorkspaceThreadListItem, WorkspaceThreadsListResponse
from src.server.services.family_accounts import (
    FamilyGradeNotFoundError,
    FamilyMemberNotFoundError,
    FamilyThreadNotFoundError,
    FamilyWorkspaceNotFoundError,
    get_family_child_replay,
    get_family_child_education_profile,
    get_family_child_workspace,
    list_family_child_threads,
    list_family_children,
    update_family_child_education_profile,
)
from src.server.app.education.models import (
    EducationStudentProfileResponse,
    UpdateEducationStudentProfileRequest,
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


class FlashWorkspaceSummaryResponse(BaseModel):
    workspace_id: str
    name: str
    status: str | None = None
    updated_at: datetime | None = None


class FamilyChildResponse(MemberResponse):
    username: str | None = None
    flash_workspace: FlashWorkspaceSummaryResponse


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


def _family_thread_item(row: dict[str, Any]) -> WorkspaceThreadListItem:
    """Project a database thread row without exposing write capabilities."""
    return WorkspaceThreadListItem(
        thread_id=str(row["conversation_thread_id"]),
        workspace_id=str(row["workspace_id"]),
        thread_index=row["thread_index"],
        current_status=row["current_status"],
        msg_type=row.get("msg_type"),
        title=row.get("title"),
        first_query_content=row.get("first_query_content"),
        platform=row.get("platform"),
        metadata=row.get("metadata") or {},
        is_shared=bool(row.get("is_shared", False)),
        is_pinned=bool(row.get("is_pinned", False)),
        archived_at=row.get("archived_at"),
        turn_count=row.get("turn_count"),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        run_status=row.get("latest_run_status"),
        interrupt_reason=row.get("latest_interrupt_reason"),
        latest_run_seq=row.get("latest_run_seq"),
        latest_run_id=row.get("latest_run_id"),
        last_seen_run_seq=row.get("last_seen_run_seq"),
        run_started_at=row.get("latest_run_started_at"),
    )


def _safe_family_replay_item(item: dict[str, Any]) -> dict[str, Any] | None:
    """Keep the family view to original user and assistant text only."""
    event = item.get("event")
    data = item.get("data") or {}
    if (
        event == "user_message"
        and data.get("query_type") != "system"
        and isinstance(data.get("content"), str)
    ):
        return {"event": event, "data": {"content": data["content"], "timestamp": data.get("timestamp")}}
    if (
        event == "message_chunk"
        and data.get("role") == "assistant"
        and data.get("content_type") == "text"
        and isinstance(data.get("content"), str)
    ):
        return {"event": event, "data": {"role": "assistant", "content": data["content"], "timestamp": data.get("timestamp")}}
    return None


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


@router.get("/children", response_model=list[FamilyChildResponse])
async def list_children(user_id: CurrentUserId):
    """List a parent's students and their private Flash workspace summaries."""
    try:
        return await list_family_children(user_id)
    except ParentMembershipRequiredError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FamilyWorkspaceNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/children/{student_user_id}/workspace", response_model=FlashWorkspaceSummaryResponse)
async def get_child_workspace(student_user_id: str, user_id: CurrentUserId):
    try:
        return await get_family_child_workspace(user_id, student_user_id)
    except ParentMembershipRequiredError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FamilyMemberNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FamilyWorkspaceNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get(
    "/children/{student_user_id}/education-profile",
    response_model=EducationStudentProfileResponse,
)
async def get_child_education_profile(student_user_id: str, user_id: CurrentUserId):
    try:
        return await get_family_child_education_profile(user_id, student_user_id)
    except ParentMembershipRequiredError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FamilyMemberNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch(
    "/children/{student_user_id}/education-profile",
    response_model=EducationStudentProfileResponse,
)
async def update_child_education_profile(
    student_user_id: str,
    body: UpdateEducationStudentProfileRequest,
    user_id: CurrentUserId,
):
    try:
        return await update_family_child_education_profile(
            user_id, student_user_id, grade_code=body.grade_code
        )
    except ParentMembershipRequiredError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FamilyMemberNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FamilyGradeNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/children/{student_user_id}/threads", response_model=WorkspaceThreadsListResponse)
async def list_child_threads(
    student_user_id: str,
    user_id: CurrentUserId,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    sort_by: Literal["created_at", "updated_at", "thread_index"] = Query("updated_at"),
    sort_order: Literal["asc", "desc"] = Query("desc"),
):
    try:
        threads, total, _workspace = await list_family_child_threads(
            user_id,
            student_user_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
        )
    except ParentMembershipRequiredError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except FamilyMemberNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FamilyWorkspaceNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return WorkspaceThreadsListResponse(
        threads=[_family_thread_item(thread) for thread in threads],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/children/{student_user_id}/threads/{thread_id}/replay")
async def replay_child_thread(
    student_user_id: str,
    thread_id: str,
    user_id: CurrentUserId,
    source: Literal["auto", "checkpoint", "sse"] = Query("auto"),
    limit: int | None = Query(None, ge=1),
):
    try:
        _, thread, queries, responses, usages, provenance = await get_family_child_replay(
            user_id, student_user_id, thread_id
        )
    except ParentMembershipRequiredError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except (FamilyMemberNotFoundError, FamilyThreadNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FamilyWorkspaceNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    from src.server.services.history.replay import (
        CheckpointReplayUnavailable,
        build_checkpoint_replay_items,
        build_sse_replay_items,
    )

    responses_by_turn = {
        row.get("turn_index"): row for row in responses if isinstance(row, dict)
    }
    replay_items: list[dict[str, Any]] | None = None
    if source in ("auto", "checkpoint") and thread.get("latest_checkpoint_id"):
        try:
            replay_items = await build_checkpoint_replay_items(
                thread_id,
                queries,
                responses_by_turn,
                branch_tip_checkpoint_id=thread["latest_checkpoint_id"],
                last_n_turns=limit,
                usages=usages,
                provenance=provenance,
            )
        except CheckpointReplayUnavailable:
            if source == "checkpoint":
                raise HTTPException(status_code=409, detail="Checkpoint replay unavailable") from None
        except Exception:
            if source == "checkpoint":
                raise
    if replay_items is None:
        replay_items = build_sse_replay_items(thread_id, queries, responses_by_turn)

    async def event_generator():
        sequence = 0
        for item in replay_items or []:
            safe_item = _safe_family_replay_item(item)
            if safe_item is None:
                continue
            sequence += 1
            yield (
                f"id: {sequence}\n"
                f"event: {safe_item['event']}\n"
                f"data: {json.dumps(safe_item['data'], ensure_ascii=False, default=str)}\n\n"
            )
        sequence += 1
        yield f"id: {sequence}\nevent: replay_done\ndata: {json.dumps({'thread_id': thread_id})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/members", response_model=list[MemberResponse])
async def list_household_members(user_id: CurrentUserId):
    try:
        return await list_household_members_for_parent(user_id)
    except ParentMembershipRequiredError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
