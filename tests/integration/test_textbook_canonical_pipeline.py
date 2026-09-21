"""Real Markdown contract for the canonical Reading pipeline."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.server.services.education_lesson_jobs import build_lesson_source_context
from src.server.services.education_reading_assets import build_reading_asset_inputs
from src.server.services.education_structure_scope_validation import (
    validate_structure_scopes,
)
from src.server.services.education_structure_validation import normalize_v2_units


REAL_MARKDOWN = Path(
    os.environ.get(
        "LANGALPHA_REAL_TEXTBOOK_MARKDOWN",
        "/Users/seanlee/DevelopCode/MoreAlpha/LangAlpha/"
        "datalab-output-REX 3e SB3 Page1-50.pdf.md",
    )
)


def _line_number(lines: list[str], needle: str, *, start: int = 0) -> int:
    return next(
        index
        for index, line in enumerate(lines[start:], start=start)
        if needle in line
    ) + 1


@pytest.mark.integration
def test_pipeline_builds_reading_assets_from_real_markdown() -> None:
    if not REAL_MARKDOWN.is_file():
        pytest.skip("REX 3 real Markdown fixture is unavailable")
    markdown = REAL_MARKDOWN.read_text(encoding="utf-8")
    lines = markdown.splitlines()
    unit_start = _line_number(lines, "## SPORTS AND FITNESS")
    reading_a_start = _line_number(lines, "### BEFORE YOU READ", start=unit_start)
    reading_b_start = _line_number(
        lines,
        "### BEFORE YOU READ",
        start=reading_a_start,
    )
    sport_climbing = _line_number(lines, "### SPORT CLIMBING")
    skin_deep = _line_number(lines, "## SKIN DEEP")
    structure = {
        "format": "langalpha-managed-textbook-structure/v2",
        "units": [
            {
                "unit": 1,
                "theme": "Sports and Fitness",
                "line_start": unit_start,
                "line_end": skin_deep - 1,
                "readings": [
                    {
                        "slot": "reading_a",
                        "title": "The World's Game",
                        "line_start": reading_a_start,
                        "line_end": reading_b_start - 1,
                        "summary": "Soccer's global history and local meaning.",
                    },
                    {
                        "slot": "reading_b",
                        "title": "What Makes an Olympic Champion?",
                        "line_start": reading_b_start,
                        "line_end": sport_climbing - 1,
                        "summary": "The traits and training of elite athletes.",
                    },
                ],
            }
        ],
    }

    scopes = validate_structure_scopes(
        structure,
        markdown=markdown,
        source_id="source-1",
    )
    units = normalize_v2_units(structure)
    job = {
        "units": [
            {
                **units[0],
                "unit_id": "unit-1",
                "scopes": [
                    {**scope, "unit_id": "unit-1"}
                    for scope in scopes
                ],
            }
        ]
    }
    built = build_reading_asset_inputs(
        job,
        {"sources": [{"source_id": "source-1", "markdown": markdown}]},
        job["units"][0]["scopes"],
    )

    reading_a = built["files"][
        "inputs/readings/01-unit-1-sports-and-fitness/reading_a.md"
    ]
    reading_b = built["files"][
        "inputs/readings/01-unit-1-sports-and-fitness/reading_b.md"
    ]
    assert reading_a.startswith(b"### BEFORE YOU READ")
    assert b"THE WORLD'S GAME" in reading_a
    assert b"WHAT MAKES AN OLYMPIC CHAMPION?" not in reading_a
    assert reading_b.startswith(b"### BEFORE YOU READ")
    assert b"WHAT MAKES AN OLYMPIC CHAMPION?" in reading_b
    assert b"THE WORLD'S GAME" not in reading_b

    lesson_scope = next(
        scope
        for scope in job["units"][0]["scopes"]
        if scope["slot"] == "reading_b"
    )
    context, warnings = build_lesson_source_context(
        {
            "knowledge_point_scope_slot": "reading_b",
            "knowledge_point_title": "Olympic champions",
        },
        {"sources": [{"source_id": "source-1", "markdown": markdown}]},
        job["units"][0]["scopes"],
    )
    assert warnings == []
    assert lesson_scope["title"] in context
    assert "WHAT MAKES AN OLYMPIC CHAMPION?" in context
