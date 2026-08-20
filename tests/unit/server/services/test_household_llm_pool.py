from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.server.database.auth_accounts import ParentMembershipRequiredError
from src.server.services import household_llm_pool as service


HOUSEHOLD_ID = str(uuid4())
ENDPOINT_ID = str(uuid4())


@pytest.fixture
def membership(monkeypatch):
    async def _get(user_id: str):
        role = "parent" if user_id == "parent-1" else "student"
        return {"user_id": user_id, "household_id": HOUSEHOLD_ID, "role": role}

    monkeypatch.setattr(service, "get_membership_for_user", _get)


@pytest.mark.asyncio
async def test_parent_can_create_and_list_masked_endpoint(monkeypatch, membership):
    create = AsyncMock(
        return_value={
            "endpoint_id": ENDPOINT_ID,
            "household_id": HOUSEHOLD_ID,
            "display_name": "Family DeepSeek",
            "provider": "deepseek",
            "model_id": "deepseek-chat",
            "base_url": "https://api.deepseek.com",
            "masked_api_key": "sk-...1234",
            "enabled": True,
        }
    )
    listed = AsyncMock(return_value=[create.return_value])
    monkeypatch.setattr(service, "create_household_endpoint", create)
    monkeypatch.setattr(service, "list_household_endpoints", listed)

    result = await service.create_endpoint(
        "parent-1",
        {
            "display_name": "Family DeepSeek",
            "provider": "deepseek",
            "model_id": "deepseek-chat",
            "base_url": "https://api.deepseek.com",
            "api_key": "sk-secret",
        },
    )
    assert result["masked_api_key"] == "sk-...1234"
    assert "sk-secret" not in str(result)
    create.assert_awaited_once()
    assert create.await_args.kwargs["api_key"] == "sk-secret"

    pool = await service.list_parent_pool("parent-1")
    assert pool[0]["masked_api_key"] == "sk-...1234"
    assert "api_key" not in pool[0]


@pytest.mark.asyncio
async def test_update_omitted_api_key_preserves_existing(monkeypatch, membership):
    update = AsyncMock(return_value={"endpoint_id": ENDPOINT_ID})
    monkeypatch.setattr(service, "update_household_endpoint", update)

    await service.update_endpoint(
        "parent-1",
        ENDPOINT_ID,
        {"display_name": "Renamed", "model_id": "deepseek-chat"},
    )
    assert "api_key" not in update.await_args.kwargs


@pytest.mark.asyncio
async def test_student_resolution_preference_then_default_and_disabled_fallback(
    monkeypatch,
):
    student_membership = AsyncMock(
        return_value={
            "user_id": "student-1",
            "household_id": HOUSEHOLD_ID,
            "role": "student",
        }
    )
    monkeypatch.setattr(service, "get_membership_for_user", student_membership)
    availability = AsyncMock(
        side_effect=[
            {
                "preference": {"endpoint_id": ENDPOINT_ID, "enabled": False},
                "default": {
                    "endpoint_id": "default-id",
                    "enabled": True,
                    "model_id": "gpt",
                },
            },
            {
                "preference": None,
                "default": None,
            },
        ]
    )
    monkeypatch.setattr(service, "get_household_availability", availability)
    monkeypatch.setattr(
        service,
        "get_endpoint_for_runtime",
        AsyncMock(
            return_value={
                "endpoint_id": "default-id",
                "household_id": HOUSEHOLD_ID,
                "provider": "openai",
                "model_id": "gpt",
                "api_key": "runtime-only-key",
            }
        ),
    )
    clear = AsyncMock()
    monkeypatch.setattr(service, "upsert_student_preference", clear)

    resolved = await service.resolve_student_endpoint("student-1")
    assert resolved["endpoint_id"] == "default-id"
    clear.assert_awaited_once_with("student-1", HOUSEHOLD_ID, None)

    assert await service.resolve_student_endpoint("student-1") is None


@pytest.mark.asyncio
async def test_parent_requirement_rejects_student_and_unaffiliated_user(monkeypatch):
    async def _get(user_id: str):
        if user_id == "student":
            return {"user_id": user_id, "household_id": HOUSEHOLD_ID, "role": "student"}
        return None

    monkeypatch.setattr(service, "get_membership_for_user", _get)
    with pytest.raises(ParentMembershipRequiredError):
        await service.require_parent_household("student")
    with pytest.raises(ParentMembershipRequiredError):
        await service.require_parent_household("stranger")


@pytest.mark.asyncio
async def test_family_model_key_rejects_cross_household_and_disabled(monkeypatch):
    monkeypatch.setattr(
        service,
        "get_membership_for_user",
        AsyncMock(
            return_value={
                "user_id": "student",
                "household_id": HOUSEHOLD_ID,
                "role": "student",
            }
        ),
    )
    get_runtime = AsyncMock(return_value=None)
    monkeypatch.setattr(service, "get_endpoint_for_runtime", get_runtime)

    assert (
        await service.resolve_family_model_key("student", f"family:{uuid4()}") is None
    )
    get_runtime.assert_awaited_once()


@pytest.mark.asyncio
async def test_malformed_endpoint_identifiers_are_rejected_before_database_lookup(
    monkeypatch,
):
    monkeypatch.setattr(
        service,
        "get_membership_for_user",
        AsyncMock(
            return_value={
                "user_id": "student",
                "household_id": HOUSEHOLD_ID,
                "role": "student",
            }
        ),
    )
    get_runtime = AsyncMock(side_effect=AssertionError("must not query malformed UUID"))
    monkeypatch.setattr(service, "get_endpoint_for_runtime", get_runtime)

    assert (
        await service.resolve_family_model_key("student", "family:not-a-uuid") is None
    )
    with pytest.raises(service.FamilyModelAccessError):
        await service.set_student_preference("student", "not-a-uuid")
    get_runtime.assert_not_awaited()


@pytest.mark.asyncio
async def test_parent_mutations_reject_malformed_endpoint_identifiers_before_database_lookup(
    monkeypatch, membership
):
    update = AsyncMock(side_effect=AssertionError("must not query malformed UUID"))
    delete = AsyncMock(side_effect=AssertionError("must not query malformed UUID"))
    set_default = AsyncMock(side_effect=AssertionError("must not query malformed UUID"))
    monkeypatch.setattr(service, "update_household_endpoint", update)
    monkeypatch.setattr(service, "delete_household_endpoint", delete)
    monkeypatch.setattr(service, "set_household_default_row", set_default)

    with pytest.raises(service.FamilyModelAccessError):
        await service.update_endpoint("parent-1", "not-a-uuid", {})
    with pytest.raises(service.FamilyModelAccessError):
        await service.delete_endpoint("parent-1", "not-a-uuid")
    with pytest.raises(service.FamilyModelAccessError):
        await service.set_household_default("parent-1", "not-a-uuid")

    update.assert_not_awaited()
    delete.assert_not_awaited()
    set_default.assert_not_awaited()


@pytest.mark.asyncio
async def test_selection_services_distinguish_disabled_from_missing_endpoint(
    monkeypatch, membership
):
    disabled_endpoint = {"endpoint_id": ENDPOINT_ID, "enabled": False}
    list_endpoints = AsyncMock(return_value=[disabled_endpoint])
    monkeypatch.setattr(service, "list_household_endpoints", list_endpoints)
    set_default = AsyncMock(side_effect=AssertionError("disabled endpoint must not be set"))
    monkeypatch.setattr(service, "set_household_default_row", set_default)

    with pytest.raises(service.HouseholdEndpointDisabledError):
        await service.set_household_default("parent-1", ENDPOINT_ID)
    set_default.assert_not_awaited()

    monkeypatch.setattr(service, "get_endpoint_for_runtime", AsyncMock(return_value=None))
    with pytest.raises(service.HouseholdEndpointDisabledError):
        await service.set_student_preference("student-1", ENDPOINT_ID)
    assert list_endpoints.await_count == 2
