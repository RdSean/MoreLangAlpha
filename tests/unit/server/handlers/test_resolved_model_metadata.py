from types import SimpleNamespace

from src.server.services.llm.config import resolved_model_name


def test_resolved_model_name_prefers_client_manifest_model():
    config = SimpleNamespace(
        llm_client=SimpleNamespace(metadata={"manifest_model": "deepseek-ai/DeepSeek-V4-Flash"})
    )

    assert resolved_model_name(config, "claude-sonnet-5") == "deepseek-ai/DeepSeek-V4-Flash"


def test_resolved_model_name_falls_back_to_requested_model_without_client_metadata():
    config = SimpleNamespace(llm_client=None)

    assert resolved_model_name(config, "claude-sonnet-5") == "claude-sonnet-5"
