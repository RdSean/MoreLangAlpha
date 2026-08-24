"""Deployment configuration for the Volcengine ASR relay."""

from __future__ import annotations

from src.config import env
from src.config.settings import get_volcengine_asr_config


def test_returns_none_when_required_asr_values_are_missing(monkeypatch) -> None:
    monkeypatch.setattr(env, "VOLCENGINE_ASR_APP_ID", "")
    monkeypatch.setattr(env, "VOLCENGINE_ASR_ACCESS_TOKEN", "")
    monkeypatch.setattr(env, "VOLCENGINE_ASR_CLUSTER", "")

    assert get_volcengine_asr_config() is None


def test_reads_token_authenticated_deployment_asr_config(monkeypatch) -> None:
    monkeypatch.setattr(env, "VOLCENGINE_ASR_APP_ID", "test-app")
    monkeypatch.setattr(env, "VOLCENGINE_ASR_ACCESS_TOKEN", "test-access-token")
    monkeypatch.setattr(env, "VOLCENGINE_ASR_CLUSTER", "test-cluster")
    monkeypatch.setattr(env, "VOLCENGINE_ASR_WS_URL", "wss://asr.example.test/api/v2/asr")

    config = get_volcengine_asr_config()

    assert config is not None
    assert config.app_id == "test-app"
    assert config.cluster == "test-cluster"
    assert config.ws_url == "wss://asr.example.test/api/v2/asr"
    assert "test-access-token" not in repr(config)
