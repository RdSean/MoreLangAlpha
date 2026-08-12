"""User preferences must match the generic two-column schema."""

from __future__ import annotations

import inspect

import pytest
from pydantic import ValidationError

from src.server.database import user as user_db
from src.server.models.user import UserPreferencesUpdate


def test_preference_update_rejects_retired_finance_fields():
    """No client can reintroduce removed finance preference buckets."""
    with pytest.raises(ValidationError):
        UserPreferencesUpdate.model_validate(
            {"risk_preference": {"risk_tolerance": "moderate"}}
        )


def test_preference_database_functions_only_reference_generic_columns():
    """The persistence code must stay aligned with the baseline migration."""
    preference_source = "\n".join(
        inspect.getsource(function)
        for function in (
            user_db.get_user_preferences,
            user_db.upsert_user_preferences,
            user_db.get_user_with_preferences,
        )
    )

    assert "agent_preference" in preference_source
    assert "other_preference" in preference_source
    assert "risk_preference" not in preference_source
    assert "investment_preference" not in preference_source
