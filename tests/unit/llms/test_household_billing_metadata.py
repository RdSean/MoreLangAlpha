"""Household endpoint clients must not inherit platform billing semantics."""

from unittest.mock import MagicMock, patch


def test_keyless_household_client_is_family_funded_not_platform():
    """A local endpoint may need an empty key, and the family still funds it.

    Household turns run on the owner's credential, so they must never be
    metered as ``platform`` (the platform did not pay) and the household ids
    travel alongside for per-student attribution. ``billing_type`` stays one of
    the values the pricing table and metrics know.
    """
    from src.server.services.llm.household import resolve_household_llm_client

    client = MagicMock()
    client.metadata = {}
    with patch("src.llms.llm.LLM._get_openai_llm", return_value=client):
        resolved = resolve_household_llm_client(
            {
                "config": {
                    "name": "Local Flash",
                    "model_id": "local-model",
                    "provider": "openai",
                },
                "api_key": "",
                "base_url": "http://127.0.0.1:11434/v1",
                "household_id": "hh-1",
                "owner_user_id": "parent-1",
                "student_user_id": "student-1",
            }
        )

    assert resolved is client
    assert resolved.metadata["billing_type"] == "byok"
    assert resolved.metadata["credential_source"] == "household"
    assert resolved.metadata["model_owner_user_id"] == "parent-1"
    assert resolved.metadata["student_user_id"] == "student-1"
