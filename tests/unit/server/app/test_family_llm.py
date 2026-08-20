"""HTTP contracts for the household LLM pool APIs."""

from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.server.app.family_llm import router
from src.server.database.auth_accounts import ParentMembershipRequiredError
from src.server.services.household_llm_pool import (
    FamilyModelAccessError,
    HouseholdEndpointDisabledError,
)
from src.server.utils.api import get_current_user_id


PARENT = "parent-1"
STUDENT = "student-1"
ENDPOINT_ID = str(uuid4())


@pytest_asyncio.fixture
async def client():
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as session:
        yield session


def _parent_endpoint(**overrides):
    return {
        "endpoint_id": ENDPOINT_ID,
        "display_name": "Family DeepSeek",
        "provider": "deepseek",
        "model_id": "deepseek-chat",
        "base_url": "https://api.deepseek.com",
        "masked_api_key": "sk-...1234",
        "enabled": True,
        "sort_order": 0,
        **overrides,
    }


def _availability(**overrides):
    return {
        "household_id": "household-1",
        "endpoints": [
            {
                "endpoint_id": ENDPOINT_ID,
                "display_name": "Family DeepSeek",
                "provider": "deepseek",
                "model_id": "deepseek-chat",
                "enabled": True,
            }
        ],
        "default": {
            "endpoint_id": ENDPOINT_ID,
            "display_name": "Family DeepSeek",
            "provider": "deepseek",
            "model_id": "deepseek-chat",
            "enabled": True,
        },
        "preference": None,
        **overrides,
    }


def _user(app: FastAPI, user_id: str):
    app.dependency_overrides[get_current_user_id] = lambda: user_id


@pytest.mark.asyncio
async def test_parent_pool_response_masks_api_key(client):
    app = client._transport.app
    _user(app, PARENT)
    with patch(
        "src.server.app.family_llm.list_parent_pool",
        new=AsyncMock(return_value=[_parent_endpoint(api_key="raw-secret")]),
    ), patch(
        "src.server.app.family_llm.get_parent_pool_availability",
        new=AsyncMock(return_value=_availability()),
    ):
        response = await client.get("/api/v1/family/llm-pool")

    assert response.status_code == 200
    body = response.json()
    endpoint = body["endpoints"][0]
    assert endpoint["masked_api_key"] == "sk-...1234"
    assert endpoint["base_url"] == "https://api.deepseek.com"
    assert "api_key" not in endpoint
    assert "raw-secret" not in response.text


@pytest.mark.asyncio
async def test_parent_can_create_endpoint_and_explicitly_clear_api_key(client):
    app = client._transport.app
    _user(app, PARENT)
    created = _parent_endpoint()
    with patch(
        "src.server.app.family_llm.create_endpoint",
        new=AsyncMock(return_value=created),
    ) as create:
        response = await client.post(
            "/api/v1/family/llm-pool",
            json={
                "display_name": "Family DeepSeek",
                "provider": "deepseek",
                "model_id": "deepseek-chat",
                "base_url": "https://api.deepseek.com",
                "api_key": "sk-secret",
            },
        )

    assert response.status_code == 201
    assert create.await_args.args[0] == PARENT
    assert create.await_args.args[1]["api_key"] == "sk-secret"
    assert "sk-secret" not in response.text

    with patch(
        "src.server.app.family_llm.update_endpoint",
        new=AsyncMock(return_value=created),
    ) as update:
        response = await client.patch(
            f"/api/v1/family/llm-pool/{ENDPOINT_ID}",
            json={"api_key": None, "display_name": "Updated"},
        )
    assert response.status_code == 200
    assert update.await_args.args[2]["api_key"] is None


@pytest.mark.asyncio
async def test_omitted_patch_api_key_is_not_sent_to_service(client):
    app = client._transport.app
    _user(app, PARENT)
    with patch(
        "src.server.app.family_llm.update_endpoint",
        new=AsyncMock(return_value=_parent_endpoint()),
    ) as update:
        response = await client.patch(
            f"/api/v1/family/llm-pool/{ENDPOINT_ID}",
            json={"display_name": "Updated"},
        )
    assert response.status_code == 200
    assert "api_key" not in update.await_args.args[2]


@pytest.mark.asyncio
async def test_student_cannot_use_parent_crud(client):
    app = client._transport.app
    _user(app, STUDENT)
    with patch(
        "src.server.app.family_llm.list_parent_pool",
        new=AsyncMock(side_effect=ParentMembershipRequiredError("parent required")),
    ):
        response = await client.get("/api/v1/family/llm-pool")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_student_cannot_update_delete_or_set_parent_default(client):
    app = client._transport.app
    _user(app, STUDENT)
    with patch(
        "src.server.app.family_llm.update_endpoint",
        new=AsyncMock(side_effect=ParentMembershipRequiredError("parent required")),
    ):
        response = await client.patch(
            f"/api/v1/family/llm-pool/{ENDPOINT_ID}", json={"enabled": False}
        )
    assert response.status_code == 403

    with patch(
        "src.server.app.family_llm.delete_endpoint",
        new=AsyncMock(side_effect=ParentMembershipRequiredError("parent required")),
    ):
        response = await client.delete(f"/api/v1/family/llm-pool/{ENDPOINT_ID}")
    assert response.status_code == 403

    with patch(
        "src.server.app.family_llm.set_household_default",
        new=AsyncMock(side_effect=ParentMembershipRequiredError("parent required")),
    ):
        response = await client.put(
            "/api/v1/family/llm-pool/default", json={"endpoint_id": ENDPOINT_ID}
        )
    assert response.status_code == 403

    with patch(
        "src.server.app.family_llm.create_endpoint",
        new=AsyncMock(side_effect=ParentMembershipRequiredError("parent required")),
    ):
        response = await client.post(
            "/api/v1/family/llm-pool",
            json={"display_name": "x", "provider": "deepseek", "model_id": "chat"},
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_student_availability_has_model_key_but_no_url_or_credentials(client):
    app = client._transport.app
    _user(app, STUDENT)
    with patch(
        "src.server.app.family_llm.get_household_context",
        new=AsyncMock(return_value={"household_id": "household-1", "role": "student"}),
    ), patch(
        "src.server.app.family_llm.get_household_availability",
        new=AsyncMock(return_value=_availability()),
    ):
        response = await client.get("/api/v1/family/llm-availability")

    assert response.status_code == 200
    body = response.json()
    assert body["selected_endpoint_id"] == ENDPOINT_ID
    assert body["default_endpoint_id"] == ENDPOINT_ID
    model = body["endpoints"][0]
    assert model["model_key"] == f"family:{ENDPOINT_ID}"
    assert "base_url" not in model
    assert "api_key" not in model
    assert "masked_api_key" not in model


@pytest.mark.asyncio
async def test_disabled_student_preference_is_a_conflict(client):
    app = client._transport.app
    _user(app, STUDENT)
    with patch(
        "src.server.app.family_llm.get_household_context",
        new=AsyncMock(return_value={"household_id": "household-1", "role": "student"}),
    ), patch(
        "src.server.app.family_llm.set_student_preference",
        new=AsyncMock(side_effect=HouseholdEndpointDisabledError("Endpoint is disabled")),
    ), patch(
        "src.server.app.family_llm.get_household_availability",
        new=AsyncMock(return_value=_availability()),
    ):
        response = await client.put(
            "/api/v1/family/llm-preference", json={"endpoint_id": ENDPOINT_ID}
        )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_preference_update_returns_refreshed_availability(client):
    app = client._transport.app
    _user(app, STUDENT)
    refreshed = _availability(
        preference={
            "endpoint_id": ENDPOINT_ID,
            "display_name": "Family DeepSeek",
            "provider": "deepseek",
            "model_id": "deepseek-chat",
            "enabled": True,
        }
    )
    with patch(
        "src.server.app.family_llm.get_household_context",
        new=AsyncMock(return_value={"household_id": "household-1", "role": "student"}),
    ), patch(
        "src.server.app.family_llm.set_student_preference",
        new=AsyncMock(),
    ), patch(
        "src.server.app.family_llm.get_household_availability",
        new=AsyncMock(return_value=refreshed),
    ):
        response = await client.put(
            "/api/v1/family/llm-preference", json={"endpoint_id": ENDPOINT_ID}
        )
    assert response.status_code == 200
    assert response.json()["selected_source"] == "preference"
    assert response.json()["selected_endpoint_id"] == ENDPOINT_ID


@pytest.mark.asyncio
async def test_parent_cannot_set_student_preference(client):
    app = client._transport.app
    _user(app, PARENT)
    with patch(
        "src.server.app.family_llm.get_household_context",
        new=AsyncMock(return_value={"household_id": "household-1", "role": "parent"}),
    ):
        response = await client.put(
            "/api/v1/family/llm-preference", json={"endpoint_id": ENDPOINT_ID}
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_non_member_cannot_read_availability(client):
    app = client._transport.app
    _user(app, "stranger")
    with patch(
        "src.server.app.family_llm.get_household_context",
        new=AsyncMock(side_effect=FamilyModelAccessError("not a member")),
    ):
        response = await client.get("/api/v1/family/llm-availability")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unknown_parent_endpoint_is_not_found(client):
    app = client._transport.app
    _user(app, PARENT)
    with patch(
        "src.server.app.family_llm.update_endpoint",
        new=AsyncMock(side_effect=FamilyModelAccessError("Endpoint unavailable")),
    ):
        response = await client.patch(
            f"/api/v1/family/llm-pool/{uuid4()}", json={"enabled": False}
        )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_provider_must_be_a_non_platform_manifest_provider(client):
    app = client._transport.app
    _user(app, PARENT)
    with patch(
        "src.server.app.family_llm._available_providers",
        return_value={"deepseek"},
    ):
        response = await client.post(
            "/api/v1/family/llm-pool",
            json={"display_name": "x", "provider": "platform-only", "model_id": "chat"},
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_base_url_must_use_http_or_https(client):
    app = client._transport.app
    _user(app, PARENT)
    response = await client.post(
        "/api/v1/family/llm-pool",
        json={"display_name": "x", "provider": "deepseek", "model_id": "chat", "base_url": "ftp://example.test"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_api_key_length_error_never_echoes_submitted_key(client):
    app = client._transport.app
    _user(app, PARENT)
    api_key = "s" * 4097
    response = await client.post(
        "/api/v1/family/llm-pool",
        json={"display_name": "x", "provider": "deepseek", "model_id": "chat", "api_key": api_key},
    )
    assert response.status_code == 422
    assert api_key not in response.text


@pytest.mark.asyncio
async def test_api_key_type_error_never_echoes_submitted_value(client):
    app = client._transport.app
    _user(app, PARENT)
    secret = "nested-secret"
    response = await client.post(
        "/api/v1/family/llm-pool",
        json={
            "display_name": "x",
            "provider": "deepseek",
            "model_id": "chat",
            "api_key": {"credential": secret},
        },
    )
    assert response.status_code == 422
    assert secret not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["display_name", "provider", "model_id"])
async def test_patch_required_text_does_not_accept_explicit_null(client, field):
    app = client._transport.app
    _user(app, PARENT)
    update = AsyncMock()
    api_key = "secret-that-must-not-be-echoed"
    with patch("src.server.app.family_llm.update_endpoint", new=update):
        response = await client.patch(
            f"/api/v1/family/llm-pool/{ENDPOINT_ID}",
            json={field: None, "api_key": api_key},
        )
    assert response.status_code == 422
    assert api_key not in response.text
    update.assert_not_awaited()


@pytest.mark.asyncio
async def test_default_endpoint_must_be_explicit_and_nullable(client):
    app = client._transport.app
    _user(app, PARENT)
    set_default = AsyncMock(return_value={"default_endpoint_id": None})
    with patch("src.server.app.family_llm.set_household_default", new=set_default):
        omitted = await client.put("/api/v1/family/llm-pool/default", json={})
        cleared = await client.put(
            "/api/v1/family/llm-pool/default", json={"endpoint_id": None}
        )
    assert omitted.status_code == 422
    set_default.assert_awaited_once_with(PARENT, None)
    assert cleared.status_code == 200


@pytest.mark.asyncio
async def test_student_preference_must_be_explicit_and_nullable(client):
    app = client._transport.app
    _user(app, STUDENT)
    preference = AsyncMock()
    context = AsyncMock(
        return_value={"household_id": "household-1", "role": "student"}
    )
    with patch("src.server.app.family_llm.get_household_context", new=context), patch(
        "src.server.app.family_llm.set_student_preference", new=preference
    ), patch(
        "src.server.app.family_llm.get_household_availability",
        new=AsyncMock(return_value=_availability()),
    ):
        omitted = await client.put("/api/v1/family/llm-preference", json={})
        cleared = await client.put(
            "/api/v1/family/llm-preference", json={"endpoint_id": None}
        )
    assert omitted.status_code == 422
    context.assert_awaited_once_with(STUDENT)
    preference.assert_awaited_once_with(STUDENT, None)
    assert cleared.status_code == 200


@pytest.mark.asyncio
async def test_disabled_default_endpoint_is_a_conflict_but_unknown_is_not_found(client):
    app = client._transport.app
    _user(app, PARENT)
    with patch(
        "src.server.app.family_llm.set_household_default",
        new=AsyncMock(side_effect=HouseholdEndpointDisabledError("disabled")),
    ):
        disabled = await client.put(
            "/api/v1/family/llm-pool/default", json={"endpoint_id": ENDPOINT_ID}
        )
    with patch(
        "src.server.app.family_llm.set_household_default",
        new=AsyncMock(side_effect=FamilyModelAccessError("unavailable")),
    ):
        missing = await client.put(
            "/api/v1/family/llm-pool/default", json={"endpoint_id": ENDPOINT_ID}
        )
    assert disabled.status_code == 409
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_disabled_preference_is_a_conflict_but_unknown_is_not_found(client):
    app = client._transport.app
    _user(app, STUDENT)
    context = AsyncMock(
        return_value={"household_id": "household-1", "role": "student"}
    )
    with patch("src.server.app.family_llm.get_household_context", new=context), patch(
        "src.server.app.family_llm.set_student_preference",
        new=AsyncMock(side_effect=HouseholdEndpointDisabledError("disabled")),
    ):
        disabled = await client.put(
            "/api/v1/family/llm-preference", json={"endpoint_id": ENDPOINT_ID}
        )
    with patch("src.server.app.family_llm.get_household_context", new=context), patch(
        "src.server.app.family_llm.set_student_preference",
        new=AsyncMock(side_effect=FamilyModelAccessError("unavailable")),
    ):
        missing = await client.put(
            "/api/v1/family/llm-preference", json={"endpoint_id": ENDPOINT_ID}
        )
    assert disabled.status_code == 409
    assert missing.status_code == 404
