"""Contract tests for household models shared from the designated parent."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from tests.conftest import create_test_app


MODULE = "src.server.app.family_llm"

MODELS = [
    {
        "model_key": "deepseek-chat",
        "display_name": "DeepSeek Chat",
        "provider": "deepseek",
        "model_id": "deepseek-chat",
        "capabilities": {"input_modalities": ["text"]},
        "api_key": "owner-secret",
        "base_url": "https://private.example/v1",
    },
    {
        "model_key": "owner-custom",
        "display_name": "Owner Custom",
        "provider": "openai",
        "model_id": "owner-custom-id",
        "capabilities": {"input_modalities": ["text", "image"]},
    },
]

PUBLIC_MODELS = [
    {
        "model_key": "deepseek-chat",
        "display_name": "DeepSeek Chat",
        "provider": "deepseek",
        "model_id": "deepseek-chat",
        "capabilities": {"input_modalities": ["text"]},
    },
    {
        "model_key": "owner-custom",
        "display_name": "Owner Custom",
        "provider": "openai",
        "model_id": "owner-custom-id",
        "capabilities": {"input_modalities": ["text", "image"]},
    },
]


async def _client_for(user_id: str):
    from src.server.app.family_llm import router
    from src.server.utils.api import get_current_user_id

    app = create_test_app(router)
    app.dependency_overrides[get_current_user_id] = lambda: user_id
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_student_availability_returns_owner_models_and_saved_preference():
    availability = {
        "household_id": "household-1",
        "models": MODELS,
        "default_model_key": "deepseek-chat",
    }
    async with await _client_for("student-1") as client:
        with (
        patch(
            f"{MODULE}.get_household_owner_for_user",
            new_callable=AsyncMock,
            return_value={"household_id": "household-1", "role": "student"},
        ),
        patch(
            f"{MODULE}.get_household_model_availability",
            new_callable=AsyncMock,
            return_value=availability,
        ),
        patch(
            f"{MODULE}.get_student_model_preference",
            new_callable=AsyncMock,
            return_value={"model_key": "owner-custom"},
        ),
        ):
            response = await client.get("/api/v1/family/llm-availability")

    assert response.status_code == 200
    body = response.json()
    assert body["models"] == PUBLIC_MODELS
    assert body["default_model_key"] == "deepseek-chat"
    assert body["selected_model_key"] == "owner-custom"
    assert body["selected_source"] == "preference"
    assert body["has_available_models"] is True
    assert "household_id" not in body
    assert "owner-secret" not in str(body)
    assert "base_url" not in body["models"][0]
    assert "api_key" not in body["models"][0]


@pytest.mark.asyncio
async def test_parent_can_read_owner_backed_availability_but_not_write_student_preference():
    availability = {
        "household_id": "household-1",
        "models": MODELS,
        "default_model_key": "deepseek-chat",
    }
    async with await _client_for("parent-1") as client:
        with (
        patch(
            f"{MODULE}.get_household_owner_for_user",
            new_callable=AsyncMock,
            return_value={"household_id": "household-1", "role": "parent"},
        ),
        patch(
            f"{MODULE}.get_household_model_availability",
            new_callable=AsyncMock,
            return_value=availability,
        ),
        ):
            response = await client.get("/api/v1/family/llm-availability")
            preference = await client.put(
                "/api/v1/family/llm-preference", json={"model_key": "owner-custom"}
            )

    assert response.status_code == 200
    assert response.json()["selected_model_key"] == "deepseek-chat"
    assert response.json()["selected_source"] == "default"
    assert preference.status_code == 403


@pytest.mark.asyncio
async def test_student_preference_requires_current_owner_model_and_only_updates_self():
    availability = {
        "household_id": "household-1",
        "models": MODELS,
        "default_model_key": "deepseek-chat",
    }
    save_preference = AsyncMock(return_value={"model_key": "owner-custom"})
    async with await _client_for("student-1") as client:
        with (
        patch(
            f"{MODULE}.get_household_owner_for_user",
            new_callable=AsyncMock,
            return_value={"household_id": "household-1", "role": "student"},
        ),
        patch(
            f"{MODULE}.get_household_model_availability",
            new_callable=AsyncMock,
            return_value=availability,
        ),
        patch(f"{MODULE}.upsert_student_model_preference", save_preference),
        patch(
            f"{MODULE}.get_student_model_preference",
            new_callable=AsyncMock,
            return_value={"model_key": "owner-custom"},
        ),
        ):
            accepted = await client.put(
                "/api/v1/family/llm-preference", json={"model_key": "owner-custom"}
            )
            rejected = await client.put(
                "/api/v1/family/llm-preference", json={"model_key": "foreign-model"}
            )

    assert accepted.status_code == 200
    save_preference.assert_awaited_once_with("student-1", "household-1", "owner-custom")
    assert accepted.json()["selected_model_key"] == "owner-custom"
    assert rejected.status_code == 404


@pytest.mark.asyncio
async def test_student_can_clear_own_preference_and_falls_back_to_owner_default():
    availability = {
        "household_id": "household-1",
        "models": MODELS,
        "default_model_key": "deepseek-chat",
    }
    clear_preference = AsyncMock(return_value=True)
    async with await _client_for("student-1") as client:
        with (
        patch(
            f"{MODULE}.get_household_owner_for_user",
            new_callable=AsyncMock,
            return_value={"household_id": "household-1", "role": "student"},
        ),
        patch(
            f"{MODULE}.get_household_model_availability",
            new_callable=AsyncMock,
            return_value=availability,
        ),
        patch(f"{MODULE}.clear_student_model_preference", clear_preference),
        patch(
            f"{MODULE}.get_student_model_preference",
            new_callable=AsyncMock,
            return_value=None,
        ),
        ):
            response = await client.put("/api/v1/family/llm-preference", json={"model_key": None})

    assert response.status_code == 200
    clear_preference.assert_awaited_once_with("student-1", "household-1")
    assert response.json()["selected_model_key"] == "deepseek-chat"
    assert response.json()["selected_source"] == "default"


@pytest.mark.asyncio
async def test_student_preference_requires_an_explicit_nullable_model_key():
    async with await _client_for("student-1") as client:
        response = await client.put("/api/v1/family/llm-preference", json={})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_unavailable_owner_models_have_explicit_empty_state():
    async with await _client_for("student-1") as client:
        with (
        patch(
            f"{MODULE}.get_household_owner_for_user",
            new_callable=AsyncMock,
            return_value={"household_id": "household-1", "role": "student"},
        ),
        patch(
            f"{MODULE}.get_household_model_availability",
            new_callable=AsyncMock,
            return_value={
                "household_id": "household-1",
                "models": [],
                "default_model_key": None,
            },
        ),
        patch(
            f"{MODULE}.get_student_model_preference",
            new_callable=AsyncMock,
            return_value=None,
        ),
        ):
            response = await client.get("/api/v1/family/llm-availability")

    assert response.status_code == 200
    assert response.json() == {
        "models": [],
        "default_model_key": None,
        "selected_model_key": None,
        "selected_source": None,
        "has_available_models": False,
        "empty_reason": "no_available_models",
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("get", "/api/v1/family/llm-pool"),
        ("post", "/api/v1/family/llm-pool"),
        ("patch", "/api/v1/family/llm-pool/old-endpoint"),
        ("delete", "/api/v1/family/llm-pool/old-endpoint"),
        ("put", "/api/v1/family/llm-pool/default"),
    ],
)
async def test_legacy_endpoint_pool_routes_do_not_exist(method: str, path: str):
    async with await _client_for("parent-1") as client:
        response = await client.request(method.upper(), path, json={} if method != "get" else None)

    assert response.status_code == 404
