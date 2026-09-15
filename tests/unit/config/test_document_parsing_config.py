"""Document parsing runtime-limit configuration tests."""

from __future__ import annotations

import importlib
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from types import ModuleType

import pytest


_DOCUMENT_ENV_VARS = (
    "DOCUMENT_MAX_UPLOAD_BYTES",
    "DOCUMENT_SYNC_WAIT_SECONDS",
    "DOCUMENT_PARSE_TIMEOUT_SECONDS",
    "DOCUMENT_MAX_IMAGE_ARTIFACTS",
    "DOCUMENT_MAX_IMAGE_BYTES",
)


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
            for name in _DOCUMENT_ENV_VARS:
                patch.delenv(name, raising=False)
            for name, value in (values or {}).items():
                patch.setenv(name, value)

            importlib.reload(env_module)
            yield importlib.reload(settings_module)
    finally:
        importlib.reload(env_module)
        importlib.reload(settings_module)


def test_document_parsing_config_uses_bounded_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _reloaded_config(monkeypatch) as settings:
        config = settings.get_document_parsing_config()

    assert config.max_upload_bytes == 52_428_800
    assert config.sync_wait_seconds == 30
    assert config.parse_timeout_seconds == 600
    # Images get their own budget: a picture-heavy scan should not have to fit
    # inside the markdown's allowance (or the other way round).
    assert config.max_image_artifacts == 200
    assert config.max_image_bytes == 33_554_432


def test_document_parsing_config_uses_environment_overrides(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _reloaded_config(
        monkeypatch,
        {
            "DOCUMENT_MAX_UPLOAD_BYTES": "1048576",
            "DOCUMENT_SYNC_WAIT_SECONDS": "12",
            "DOCUMENT_PARSE_TIMEOUT_SECONDS": "90",
            "DOCUMENT_MAX_IMAGE_ARTIFACTS": "7",
            "DOCUMENT_MAX_IMAGE_BYTES": "2048",
        },
    ) as settings:
        config = settings.get_document_parsing_config()

    assert config.max_upload_bytes == 1_048_576
    assert config.sync_wait_seconds == 12
    assert config.parse_timeout_seconds == 90
    assert config.max_image_artifacts == 7
    assert config.max_image_bytes == 2048


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("DOCUMENT_MAX_UPLOAD_BYTES", "0"),
        ("DOCUMENT_MAX_UPLOAD_BYTES", "not-an-integer"),
        ("DOCUMENT_SYNC_WAIT_SECONDS", "-1"),
        ("DOCUMENT_SYNC_WAIT_SECONDS", "1.5"),
        ("DOCUMENT_PARSE_TIMEOUT_SECONDS", "0"),
        ("DOCUMENT_PARSE_TIMEOUT_SECONDS", "forever"),
        ("DOCUMENT_MAX_IMAGE_ARTIFACTS", "0"),
        ("DOCUMENT_MAX_IMAGE_ARTIFACTS", "lots"),
        ("DOCUMENT_MAX_IMAGE_BYTES", "-1"),
        ("DOCUMENT_MAX_IMAGE_BYTES", "32M"),
    ],
)
def test_document_parsing_config_rejects_invalid_positive_integers(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
) -> None:
    with pytest.raises(ValueError, match=name):
        with _reloaded_config(monkeypatch, {name: value}):
            pytest.fail("invalid configuration unexpectedly loaded")
