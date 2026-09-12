"""The committed JSON Schema must be exactly what the exporter produces.

This is the only place a contract can drift. The frontend consumes the
committed file, so it cannot diverge structurally from it; the file can only
fall behind the Pydantic model it is generated from, and this test is what
catches that.

Regenerate with:

    uv run python scripts/contracts/export_schemas.py
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts.contracts.export_schemas import OUTPUTS, build_schemas

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_committed_schemas_match_generated() -> None:
    for relative_path, schema in build_schemas().items():
        on_disk = json.loads((REPO_ROOT / relative_path).read_text())
        assert on_disk == schema, (
            f"{relative_path} is stale — re-run "
            "`uv run python scripts/contracts/export_schemas.py`"
        )


def test_every_declared_output_is_covered() -> None:
    # Catches adding a model to OUTPUTS and forgetting to emit its file.
    assert set(build_schemas()) == set(OUTPUTS)


def test_no_format_keyword_survives() -> None:
    """`format` is stripped on purpose — see the exporter's docstring.

    zod's JSON-Schema-derived `date-time` validator accepts only a `Z` suffix,
    so a valid `+09:00` value from a household east of UTC would be rejected.
    Asserting the strip here means a future edit that "restores fidelity" has to
    argue with a failing test rather than silently reintroducing the trap.
    """

    def find_format(node: object, path: str = "$") -> list[str]:
        found: list[str] = []
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "format":
                    found.append(f"{path}.{key}")
                found.extend(find_format(value, f"{path}.{key}"))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                found.extend(find_format(value, f"{path}[{index}]"))
        return found

    for relative_path, schema in build_schemas().items():
        assert find_format(schema) == [], (
            f"{relative_path} still carries a `format` keyword"
        )
