"""Tests for bounded generic channel gateway runtime configuration."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.config.models import InfrastructureConfig
from src.config.settings import get_channel_gateway_config


def test_channel_gateway_defaults_are_bounded() -> None:
    config = InfrastructureConfig().channels

    assert config.default_idle_timeout_seconds == 21_600
    assert config.worker_concurrency > 0
    assert config.max_image_bytes > 0
    assert config.max_image_pixels > 0
    assert config.max_ilink_text_length > 0
    assert config.max_delivery_attempts > 0


@pytest.mark.parametrize(
    ("override", "field"),
    [
        ({"worker_concurrency": 0}, "worker_concurrency"),
        ({"max_image_bytes": 0}, "max_image_bytes"),
        ({"max_image_pixels": 0}, "max_image_pixels"),
        ({"default_idle_timeout_seconds": 0}, "default_idle_timeout_seconds"),
        ({"max_ilink_text_length": 0}, "max_ilink_text_length"),
        ({"max_delivery_attempts": 0}, "max_delivery_attempts"),
    ],
)
def test_channel_gateway_rejects_unbounded_or_invalid_values(
    override: dict[str, int], field: str
) -> None:
    with pytest.raises(ValidationError, match=field):
        InfrastructureConfig(channels=override)


def test_channel_gateway_accessor_returns_typed_infrastructure_section(
    monkeypatch,
) -> None:
    expected = InfrastructureConfig(channels={"worker_concurrency": 7}).channels
    monkeypatch.setattr(
        "src.config.settings.get_infrastructure_config",
        lambda: InfrastructureConfig(channels={"worker_concurrency": 7}),
    )

    assert get_channel_gateway_config() == expected
