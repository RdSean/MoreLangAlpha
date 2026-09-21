"""Per-Reading canonical asset contracts."""

import json

import pytest

from src.server.services.education_reading_assets import (
    ReadingAssetValidationError,
    build_reading_asset_inputs,
    validate_reading_asset_content,
    validate_reading_asset_manifest,
)


SOURCE = (
    "# Unit 1\n\n"
    "### THE WORLD'S GAME\n\n"
    "Soccer is global.\n\n"
    "### SOCCER WITHOUT BORDERS\n\n"
    "The game crosses borders.\n"
)


def _job() -> dict[str, object]:
    return {
        "units": [
            {
                "unit_id": "unit-1",
                "position": 1,
                "slug": "unit-1-sports",
                "title": "Unit 1: Sports",
            }
        ]
    }


def _frozen_input() -> dict[str, object]:
    return {
        "sources": [
            {
                "source_id": "source-1",
                "markdown": SOURCE,
            }
        ]
    }


def _scopes() -> list[dict[str, object]]:
    soccer_start = SOURCE.index("### THE WORLD'S GAME")
    borders_start = SOURCE.index("### SOCCER WITHOUT BORDERS")
    return [
        {
            "unit_id": "unit-1",
            "slot": "reading_a",
            "title": "The World's Game",
            "source_id": "source-1",
            "line_start": 3,
            "line_end": 5,
            "char_start": soccer_start,
            "char_end": borders_start,
        },
        {
            "unit_id": "unit-1",
            "slot": "reading_b",
            "title": "Soccer Without Borders",
            "source_id": "source-1",
            "line_start": 5,
            "line_end": 7,
            "char_start": borders_start,
            "char_end": len(SOURCE),
        },
    ]


def test_reading_asset_staging_uses_the_scope_slice() -> None:
    built = build_reading_asset_inputs(_job(), _frozen_input(), _scopes())

    reading_a = built["files"][
        "inputs/readings/01-unit-1-sports/reading_a.md"
    ]
    assert reading_a.startswith(b"### THE WORLD'S GAME")
    assert b"SOCCER WITHOUT BORDERS" not in reading_a
    manifest = json.loads(
        built["files"]["inputs/readings_manifest.json"].decode("utf-8")
    )
    assert manifest["readings"][0]["outputs"]["knowledge"].endswith(
        "/reading_a/knowledge.md"
    )


def test_reading_asset_manifest_requires_all_fixed_outputs() -> None:
    with pytest.raises(ReadingAssetValidationError, match="asset path"):
        validate_reading_asset_manifest(
            {
                "format": "langalpha-managed-reading-assets/v2",
                "readings": [
                    {
                        "unit_id": "unit-1",
                        "slot": "reading_a",
                        "title": "The World's Game",
                        "outputs": {
                            "knowledge": "../knowledge.md",
                            "glossary": "readings/a/glossary.md",
                            "cheatsheet": "readings/a/cheatsheet.md",
                        },
                    }
                ],
            }
        )


def test_reading_asset_content_hashes_only_manifest_files() -> None:
    manifest = validate_reading_asset_manifest(
        {
            "format": "langalpha-managed-reading-assets/v2",
            "readings": [
                {
                    "unit_id": "unit-1",
                    "slot": "reading_a",
                    "title": "The World's Game",
                    "outputs": {
                        "knowledge": "readings/a/knowledge.md",
                        "glossary": "readings/a/glossary.md",
                        "cheatsheet": "readings/a/cheatsheet.md",
                    },
                }
            ],
        }
    )

    validated = validate_reading_asset_content(
        manifest,
        {
            "readings/a/knowledge.md": b"# Knowledge\n",
            "readings/a/glossary.md": b"# Glossary\n",
            "readings/a/cheatsheet.md": b"# Cheatsheet\n",
            "readings/a/ignored.md": b"# Ignored\n",
        },
    )

    assert len(validated["readings"][0]["files"]) == 3
    assert "ignored" not in validated["readings"][0]["files"]
