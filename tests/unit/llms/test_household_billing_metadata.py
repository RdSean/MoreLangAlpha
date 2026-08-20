"""Household endpoint clients must not inherit platform billing semantics."""

from unittest.mock import MagicMock, patch


def test_keyless_household_client_keeps_nonplatform_billing_marker():
    """A local endpoint may require an empty key but is still family-funded."""
    from src.llms.llm import create_llm_from_custom

    client = MagicMock()
    client.metadata = {}
    with patch("src.llms.llm.LLM._get_openai_llm", return_value=client):
        resolved = create_llm_from_custom(
            {
                "name": "Local Flash",
                "model_id": "local-model",
                "provider": "openai",
            },
            api_key="",
            base_url="http://127.0.0.1:11434/v1",
            billing_type_override="household",
        )

    assert resolved is client
    assert resolved.metadata["billing_type"] == "household"
