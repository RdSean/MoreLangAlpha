"""Safety contracts for removing only versioned textbook objects."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = (
    Path(__file__).parents[3]
    / "scripts"
    / "education_purge_prefix.py"
)


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "education_purge_prefix",
        SCRIPT,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_purge_dry_run_never_deletes() -> None:
    module = _load_script()
    listed: list[str] = []
    deleted: list[str] = []
    keys = [
        "education/household/textbook/v1/structures/v1/manifest.json",
        "education/household/textbook/source-bundles/job/01/source.md",
        "education/household/homework.pdf",
    ]

    result = module.purge_education_textbook_prefixes(
        prefixes=["education/household/textbook/"],
        apply=False,
        list_keys=lambda prefix: listed.append(prefix) or keys,
        delete_key=deleted.append,
    )

    assert listed == ["education/household/textbook/"]
    assert deleted == []
    assert result["selected"] == 2
    assert result["skipped"] == 1


def test_purge_apply_deletes_only_versioned_textbook_objects() -> None:
    module = _load_script()
    deleted: list[str] = []
    keys = [
        "education/household/textbook/v1/structures/v1/manifest.json",
        "education/household/textbook/source-bundles/job/01/source.md",
        "education/household/latest-homework.pdf",
        "documents/unrelated.pdf",
    ]

    result = module.purge_education_textbook_prefixes(
        prefixes=["education/household/textbook/"],
        apply=True,
        list_keys=lambda _prefix: keys,
        delete_key=lambda key: deleted.append(key) or True,
    )

    assert deleted == keys[:2]
    assert result["deleted"] == 2
    assert result["skipped"] == 2


def test_purge_rejects_an_unsafe_prefix() -> None:
    module = _load_script()

    try:
        module.purge_education_textbook_prefixes(
            prefixes=["education/"],
            apply=False,
            list_keys=lambda _prefix: [],
            delete_key=lambda _key: True,
        )
    except module.PurgeSafetyError as exc:
        assert "education/<household>/<textbook>/" in str(exc)
    else:
        raise AssertionError("unsafe prefix was accepted")
