"""Datalab parser deployment-configuration tests.

``src/config/env`` reads its constants at import time, so these tests reload it
and ``settings`` inside a patched environment and restore both afterwards —
the same shape ``test_document_parsing_config.py`` uses, for the same reason.
"""

from __future__ import annotations

import importlib
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from types import ModuleType

import pytest


_DATALAB_ENV_VARS = (
    "ENABLE_DATALAB_DOCUMENT_PARSER",
    "DATALAB_API_KEY",
    "DATALAB_PIPELINE_ID",
    "DATALAB_CONVERSION_MODE",
    "DATALAB_POLL_BUDGET_SECONDS",
    "DOCUMENT_PARSE_TIMEOUT_SECONDS",
)

_ENABLED = {
    "ENABLE_DATALAB_DOCUMENT_PARSER": "true",
    "DATALAB_API_KEY": "dl-test-key",
}


@contextmanager
def _reloaded_config(
    monkeypatch: pytest.MonkeyPatch,
    values: Mapping[str, str] | None = None,
) -> Iterator[ModuleType]:
    """Reload import-time env constants and leave the shared modules pristine."""
    env_module = importlib.import_module("src.config.env")
    settings_module = importlib.import_module("src.config.settings")

    try:
        with monkeypatch.context() as patch:
            for name in _DATALAB_ENV_VARS:
                patch.delenv(name, raising=False)
            for name, value in (values or {}).items():
                patch.setenv(name, value)

            importlib.reload(env_module)
            yield importlib.reload(settings_module)
    finally:
        importlib.reload(env_module)
        importlib.reload(settings_module)


def test_absent_configuration_reports_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No variables at all is the ordinary deployment: the parser is off."""
    with _reloaded_config(monkeypatch) as settings_module:
        assert settings_module.get_datalab_config() is None


def test_disabled_flag_wins_over_complete_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A key present but the feature switched off must not enable the parser."""
    values = {**_ENABLED, "ENABLE_DATALAB_DOCUMENT_PARSER": "false"}
    with _reloaded_config(monkeypatch, values) as settings_module:
        assert settings_module.get_datalab_config() is None


def test_enabled_without_an_api_key_reports_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The failure that would otherwise surface as an auth error mid-parse."""
    values = {"ENABLE_DATALAB_DOCUMENT_PARSER": "true"}
    with _reloaded_config(monkeypatch, values) as settings_module:
        assert settings_module.get_datalab_config() is None


def test_pipeline_id_is_reserved_not_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``client.convert()`` does not use a pipeline, so its absence is fine.

    The variable stays in the environment for the future multi-step path; a
    deployment that never sets it must still get a working parser.
    """
    with _reloaded_config(monkeypatch, _ENABLED) as settings_module:
        config = settings_module.get_datalab_config()

    assert config is not None
    assert config.pipeline_id == ""


def test_configured_values_are_carried_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = {
        **_ENABLED,
        "DATALAB_PIPELINE_ID": "pl_reserved",
        "DATALAB_CONVERSION_MODE": "accurate",
        "DATALAB_POLL_BUDGET_SECONDS": "120",
        "DOCUMENT_PARSE_TIMEOUT_SECONDS": "300",
    }
    with _reloaded_config(monkeypatch, values) as settings_module:
        config = settings_module.get_datalab_config()

    assert config is not None
    assert config.api_key == "dl-test-key"
    assert config.pipeline_id == "pl_reserved"
    assert config.mode == "accurate"
    assert config.poll_budget_seconds == 120
    assert config.parse_timeout_seconds == 300


def test_defaults_match_the_configured_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pipeline runs ``balanced``; an unset mode must not silently differ."""
    with _reloaded_config(monkeypatch, _ENABLED) as settings_module:
        config = settings_module.get_datalab_config()

    assert config is not None
    assert config.mode == "balanced"


def test_the_poll_budget_expires_before_our_own_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D3's ordering, asserted as a property rather than as two literals.

    If our subprocess timeout fires first, Datalab keeps working and billing for
    a result nobody collects. The budget must therefore be strictly smaller,
    whatever either value is configured to.
    """
    for parse_timeout, budget in (("600", "540"), ("120", "60"), ("60", "30")):
        values = {
            **_ENABLED,
            "DOCUMENT_PARSE_TIMEOUT_SECONDS": parse_timeout,
            "DATALAB_POLL_BUDGET_SECONDS": budget,
        }
        with _reloaded_config(monkeypatch, values) as settings_module:
            config = settings_module.get_datalab_config()

        assert config is not None
        assert config.poll_budget_seconds < config.parse_timeout_seconds


def test_a_budget_at_or_above_the_timeout_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The configuration is wrong, and silently accepting it is worse."""
    values = {
        **_ENABLED,
        "DOCUMENT_PARSE_TIMEOUT_SECONDS": "300",
        "DATALAB_POLL_BUDGET_SECONDS": "600",
    }
    with _reloaded_config(monkeypatch, values) as settings_module:
        assert settings_module.get_datalab_config() is None


def test_the_api_key_is_not_exposed_in_the_repr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """This object reaches logs; a key in a repr is a key in a log."""
    with _reloaded_config(monkeypatch, _ENABLED) as settings_module:
        config = settings_module.get_datalab_config()

    assert config is not None
    assert "dl-test-key" not in repr(config)
