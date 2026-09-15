from types import SimpleNamespace

from src.server.services.llm.clients import _resolved_model_name


def test_resolved_model_name_prefers_client_manifest_model():
    client = SimpleNamespace(
        metadata={"manifest_model": "deepseek-ai/DeepSeek-V4-Flash"}
    )

    assert _resolved_model_name(client, "claude-sonnet-5") == "deepseek-ai/DeepSeek-V4-Flash"


def test_resolved_model_name_falls_back_to_requested_model_without_client_metadata():
    assert _resolved_model_name(None, "claude-sonnet-5") == "claude-sonnet-5"
