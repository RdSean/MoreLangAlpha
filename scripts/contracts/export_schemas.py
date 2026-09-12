"""Export Pydantic models as JSON Schema for the frontend contract layer.

The Pydantic model is the single source of truth for a payload that crosses
from the backend to the frontend. This script emits the JSON Schema the
frontend validates against, so the two sides agree on a generated artifact
instead of on two hand-kept copies.

Run it whenever a model listed in ``OUTPUTS`` changes:

    uv run python scripts/contracts/export_schemas.py

``tests/unit/contracts/test_generated_schemas_are_current.py`` fails until you
do — that test, not discipline, is what keeps the committed file honest.

Why ``format`` is stripped
--------------------------
zod's ``date-time`` validator, when generated from JSON Schema, accepts only a
``Z`` suffix. A perfectly valid value from a household east of UTC
(``2026-09-13T19:00:00+09:00``) is rejected by it. It happens to pass here only
because Pydantic v2 normalises tz-aware datetimes to UTC and emits ``Z`` — one
change of serialisation away from a bug that would look like a rendering
problem.

So the generated file carries the *structural* contract — types, required
fields, arrays, nullability — and nothing about date semantics. The frontend
already handles date strings; it does not need zod to re-decide them.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pydantic

# Run as a script, sys.path[0] is scripts/contracts — not the repo root the
# `src` package lives under. Same prelude as the other scripts under scripts/.
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from src.server.app.education.models import (  # noqa: E402
    EducationTaskCalendarResponse,
)
from src.tools.homework.schemas import HomeworkScheduleArtifact  # noqa: E402

# The registry of exported contracts: repo-relative output path → source model.
# Adding an entry here is the whole act of publishing a new contract; the
# drift test derives from this mapping, so a new entry with no file fails.
OUTPUTS: dict[str, type[pydantic.BaseModel]] = {
    "web/src/contracts/education-calendar.schema.json": EducationTaskCalendarResponse,
    "web/src/contracts/homework-schedule.schema.json": HomeworkScheduleArtifact,
}


def _strip_format(node: Any) -> Any:
    """Recursively drop every ``format`` keyword. See the module docstring."""
    if isinstance(node, dict):
        return {
            key: _strip_format(value) for key, value in node.items() if key != "format"
        }
    if isinstance(node, list):
        return [_strip_format(item) for item in node]
    return node


def build_schemas() -> dict[str, dict[str, Any]]:
    """Return every contract as a JSON-Schema dict, keyed by output path."""
    return {
        relative_path: _strip_format(model.model_json_schema())
        for relative_path, model in OUTPUTS.items()
    }


def _serialize(schema: dict[str, Any]) -> str:
    """Deterministic text so the committed diff shows only real changes.

    Sorted keys stop a reordering of the model's fields from rewriting the whole
    file, and the trailing newline keeps `git diff` quiet.
    """
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    for relative_path, schema in build_schemas().items():
        target = REPO_ROOT / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_serialize(schema), encoding="utf-8")
        print(f"wrote {relative_path}")


if __name__ == "__main__":
    main()
