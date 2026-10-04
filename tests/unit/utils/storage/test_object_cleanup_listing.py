from types import SimpleNamespace
from unittest.mock import Mock

import pytest


def test_strict_s3_listing_propagates_failure(monkeypatch):
    from src.utils.storage import s3_compatible as storage

    monkeypatch.setattr(
        storage, "_get_client", Mock(side_effect=RuntimeError("offline"))
    )
    with pytest.raises(RuntimeError, match="offline"):
        storage.list_object_keys("education/exact/", strict=True)
    assert storage.list_object_keys("education/exact/") == []


def test_oss_listing_collects_every_page(monkeypatch):
    from src.utils.storage import oss_uploader as storage

    listing = Mock(
        side_effect=[
            SimpleNamespace(
                contents=[SimpleNamespace(key="education/a")],
                is_truncated=True,
                next_continuation_token="next",
            ),
            SimpleNamespace(
                contents=[SimpleNamespace(key="education/b")], is_truncated=False
            ),
        ]
    )
    monkeypatch.setattr(
        storage, "get_oss_client", lambda: SimpleNamespace(list_objects_v2=listing)
    )
    assert storage.list_object_keys("education/", strict=True) == [
        "education/a",
        "education/b",
    ]
    assert listing.call_args_list[1].args[0].continuation_token == "next"
