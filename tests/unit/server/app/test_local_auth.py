"""Contract tests for first-party local authentication and family membership."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.server.app.auth import router
from src.server.utils.api import get_current_user_id


NOW = datetime.now(timezone.utc)
PARENT = {
    "user_id": "parent-user",
    "email": "parent@example.test",
    "name": "Parent",
    "role": "parent",
    "household_id": "household-1",
}
CHILD = {
    "user_id": "child-user",
    "email": None,
    "name": "Child",
    "role": "student",
    "household_id": "household-1",
}


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as session:
        yield session


@pytest.mark.asyncio
async def test_register_parent_creates_household_and_sets_http_only_session(client):
    with patch(
        "src.server.app.auth.register_parent_account",
        new=AsyncMock(return_value=PARENT),
    ) as register, patch(
        "src.server.app.auth.create_authenticated_session",
        new=AsyncMock(return_value="opaque-session-token"),
    ):
        response = await client.post(
            "/api/v1/auth/register-parent",
            json={
                "email": "Parent@Example.Test ",
                "password": "a-long-enough-password",
                "name": "Parent",
                "household_name": "Lee family",
                "timezone": "Asia/Tokyo",
            },
        )

    assert response.status_code == 201
    assert response.json() == PARENT
    assert "langalpha_session=opaque-session-token" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    assert register.await_args.kwargs["email"] == "parent@example.test"


@pytest.mark.asyncio
async def test_login_rejects_invalid_credentials_without_setting_a_cookie(client):
    with patch(
        "src.server.app.auth.authenticate_local_account",
        new=AsyncMock(return_value=None),
    ):
        response = await client.post(
            "/api/v1/auth/login",
            json={"login_identifier": "parent@example.test", "password": "wrong"},
        )

    assert response.status_code == 401
    assert "set-cookie" not in response.headers


@pytest.mark.asyncio
async def test_parent_can_create_a_child_account(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-user"
    with patch(
        "src.server.app.auth.create_child_account",
        new=AsyncMock(return_value=CHILD),
    ) as create_child:
        response = await client.post(
            "/api/v1/auth/children",
            json={
                "username": "child.lee",
                "password": "a-long-enough-password",
                "name": "Child",
            },
        )

    assert response.status_code == 201
    assert response.json() == CHILD
    assert create_child.await_args.kwargs["parent_user_id"] == "parent-user"


@pytest.mark.asyncio
async def test_child_creation_requires_an_authenticated_parent(client):
    response = await client.post(
        "/api/v1/auth/children",
        json={
            "username": "child.lee",
            "password": "a-long-enough-password",
            "name": "Child",
        },
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_parent_can_list_children_with_flash_summary(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-user"
    child = {
        **CHILD,
        "username": "child.lee",
        "flash_workspace": {
            "workspace_id": "flash-child",
            "name": "Flash",
            "status": "flash",
            "updated_at": NOW,
        },
    }
    with patch(
        "src.server.app.auth.list_family_children",
        new=AsyncMock(return_value=[child]),
    ):
        response = await client.get("/api/v1/auth/children")

    assert response.status_code == 200
    assert response.json() == [
        {
            **CHILD,
            "username": "child.lee",
            "flash_workspace": {
                "workspace_id": "flash-child",
                "name": "Flash",
                "status": "flash",
                "updated_at": NOW.isoformat().replace("+00:00", "Z"),
            },
        }
    ]


@pytest.mark.asyncio
async def test_parent_can_list_existing_child_without_a_local_username(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-user"
    child = {
        **CHILD,
        "flash_workspace": {
            "workspace_id": "flash-child",
            "name": "Flash",
            "status": "flash",
            "updated_at": NOW,
        },
    }
    with patch(
        "src.server.app.auth.list_family_children",
        new=AsyncMock(return_value=[child]),
    ):
        response = await client.get("/api/v1/auth/children")

    assert response.status_code == 200
    assert response.json()[0]["username"] is None


@pytest.mark.asyncio
async def test_parent_can_read_and_update_a_childs_education_profile(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-user"
    profile = {"household_id": "household-1", "user_id": "child-user", "grade_code": "g4"}
    with patch(
        "src.server.app.auth.get_family_child_education_profile",
        new=AsyncMock(return_value=profile),
    ) as get_profile, patch(
        "src.server.app.auth.update_family_child_education_profile",
        new=AsyncMock(return_value=profile),
    ) as update_profile:
        read = await client.get("/api/v1/auth/children/child-user/education-profile")
        updated = await client.patch(
            "/api/v1/auth/children/child-user/education-profile", json={"grade_code": "g4"}
        )

    assert read.status_code == 200
    assert read.json() == profile
    assert updated.status_code == 200
    get_profile.assert_awaited_once_with("parent-user", "child-user")
    assert update_profile.await_args.args == ("parent-user", "child-user")
    assert update_profile.await_args.kwargs == {"grade_code": "g4"}


@pytest.mark.asyncio
async def test_parent_can_list_child_threads(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-user"
    thread = {
        "conversation_thread_id": "thread-1",
        "workspace_id": "flash-child",
        "thread_index": 0,
        "current_status": "completed",
        "msg_type": "flash",
        "title": "学习记录",
        "first_query_content": "你好",
        "platform": "web",
        "metadata": {},
        "is_shared": False,
        "is_pinned": False,
        "archived_at": None,
        "turn_count": 1,
        "created_at": NOW,
        "updated_at": NOW,
    }
    with patch(
        "src.server.app.auth.list_family_child_threads",
        new=AsyncMock(return_value=([thread], 1, {"workspace_id": "flash-child", "name": "Flash", "status": "flash", "updated_at": NOW})),
    ):
        response = await client.get("/api/v1/auth/children/child-user/threads")

    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["threads"][0]["thread_id"] == "thread-1"


@pytest.mark.asyncio
async def test_parent_replay_only_emits_student_and_assistant_text(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-user"
    replay = (
        "child-user",
        {"conversation_thread_id": "thread-1", "workspace_id": "flash-child"},
        [],
        [],
        [],
        [],
    )
    replay_items = [
        {"event": "user_message", "data": {"content": "今天学什么？"}},
        {
            "event": "user_message",
            "data": {"content": "system instructions must stay private", "query_type": "system"},
        },
        {"event": "tool_calls", "data": {"tool_calls": [{"name": "private_tool"}]}},
        {
            "event": "message_chunk",
            "data": {
                "role": "assistant",
                "content": "internal reasoning must stay private",
                "content_type": "reasoning",
            },
        },
        {
            "event": "message_chunk",
            "data": {
                "role": "assistant",
                "content": "reasoning started",
                "content_type": "reasoning_signal",
            },
        },
        {
            "event": "message_chunk",
            "data": {"role": "assistant", "content": "复习单词。", "content_type": "text"},
        },
    ]
    with patch(
        "src.server.app.auth.get_family_child_replay",
        new=AsyncMock(return_value=replay),
    ), patch(
        "src.server.services.history.replay.build_sse_replay_items",
        return_value=replay_items,
    ):
        response = await client.get("/api/v1/auth/children/child-user/threads/thread-1/replay")

    assert response.status_code == 200
    assert "今天学什么？" in response.text
    assert "复习单词。" in response.text
    assert "private_tool" not in response.text
    assert "internal reasoning must stay private" not in response.text
    assert "reasoning started" not in response.text
    assert "system instructions must stay private" not in response.text
    assert "event: replay_done" in response.text


@pytest.mark.asyncio
async def test_logout_revokes_session_and_clears_cookie(client):
    app = client._transport.app
    app.dependency_overrides[get_current_user_id] = lambda: "parent-user"
    client.cookies.set("langalpha_session", "opaque-session-token")
    with patch(
        "src.server.app.auth.revoke_session_token",
        new=AsyncMock(return_value=True),
    ) as revoke:
        response = await client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    revoke.assert_awaited_once_with("opaque-session-token")
    assert "langalpha_session=\"\"" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_session_rotation_replaces_the_cookie_token(client):
    client.cookies.set("langalpha_session", "old-session-token")
    with patch(
        "src.server.app.auth.rotate_authenticated_session",
        new=AsyncMock(return_value="new-session-token"),
    ) as rotate:
        response = await client.post("/api/v1/auth/session/rotate")

    assert response.status_code == 204
    rotate.assert_awaited_once_with("old-session-token")
    assert "langalpha_session=new-session-token" in response.headers["set-cookie"]


@pytest.mark.asyncio
async def test_current_user_id_resolves_the_user_from_local_cookie():
    from src.server.utils import api

    request = type("Request", (), {"headers": {}, "cookies": {"langalpha_session": "token"}})()
    with patch.object(
        api, "get_user_id_for_session_token", new=AsyncMock(return_value="parent-user")
    ):
        assert await api.get_current_user_id(request, None) == "parent-user"


@pytest.mark.asyncio
async def test_parent_registration_rejects_an_invalid_household_timezone(client):
    response = await client.post(
        "/api/v1/auth/register-parent",
        json={
            "email": "parent@example.test",
            "password": "a-long-enough-password",
            "name": "Parent",
            "household_name": "Lee family",
            "timezone": "Not/A-Timezone",
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["name", "household_name"])
async def test_parent_registration_rejects_blank_identity_fields(client, field):
    payload = {
        "email": "parent@example.test",
        "password": "a-long-enough-password",
        "name": "Parent",
        "household_name": "Lee family",
        "timezone": "Asia/Tokyo",
    }
    payload[field] = "   "

    response = await client.post("/api/v1/auth/register-parent", json=payload)

    assert response.status_code == 422
