from __future__ import annotations

import re

import pytest

from src.server.documents.ids import (
    PublicIdCollisionError,
    new_public_id,
    new_unique_public_id,
)


@pytest.mark.parametrize(
    ("kind", "prefix"),
    [
        ("dataset", "dts"),
        ("document", "doc"),
        ("inspection", "ins"),
        ("job", "job"),
        ("artifact", "art"),
        ("tag", "tag"),
    ],
)
def test_new_public_id_has_typed_base62_shape(kind: str, prefix: str) -> None:
    value = new_public_id(kind)

    assert re.fullmatch(rf"{prefix}-[0-9A-Za-z]{{12}}", value)


def test_new_public_id_rejects_unknown_kind() -> None:
    with pytest.raises(ValueError, match="Unsupported public ID kind"):
        new_public_id("workspace")


def test_unique_public_id_retries_only_taken_candidates(monkeypatch) -> None:
    candidates = iter(("doc-aaaaaaaaaaaa", "doc-bbbbbbbbbbbb"))
    monkeypatch.setattr(
        "src.server.documents.ids.new_public_id",
        lambda kind: next(candidates),
    )

    value = new_unique_public_id(
        "document",
        is_taken=lambda candidate: candidate == "doc-aaaaaaaaaaaa",
    )

    assert value == "doc-bbbbbbbbbbbb"


def test_unique_public_id_stops_after_bounded_collisions(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.server.documents.ids.new_public_id",
        lambda kind: "doc-aaaaaaaaaaaa",
    )

    with pytest.raises(PublicIdCollisionError):
        new_unique_public_id(
            "document",
            is_taken=lambda candidate: True,
            max_attempts=3,
        )
