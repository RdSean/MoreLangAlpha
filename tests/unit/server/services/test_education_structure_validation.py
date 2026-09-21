"""Validation contracts for managed textbook structure candidates."""

import copy

import pytest

from src.server.services.education_structure_validation import (
    TextbookStructureValidationError,
    validate_textbook_structure,
)


FROZEN_INPUT = {
    "format": "langalpha-managed-textbook-input/v2",
    "job_id": "8a77d086-0b23-4a1e-89d0-f163fa23d5d1",
    "sources": [
        {
            "source_id": "source-1",
            "content_chapter_id": "f5761267-11d1-4977-8107-e2671c99a2f0",
            "position": 1,
            "slug": "reading-explorer",
            "title": "Reading Explorer",
            "content_sha256": "a" * 64,
            "path": "sources/01-reading-explorer.md",
            "markdown": "# Unit 1\n\nThe world's game.\n\nMore content.\n",
        }
    ],
}


def _candidate() -> dict:
    return {
        "format": "langalpha-managed-textbook-structure/v1",
        "units": [
            {
                "title": "Unit 1: Sports and Fitness",
                "summary": "Sports and fitness",
                "unit_type": "teaching",
                "confidence": 0.96,
                "source_refs": [
                    {
                        "source_id": "source-1",
                        "quote": "The world's game.",
                    }
                ],
                "knowledge_points": [
                    {
                        "title": "世界运动：足球的历史与流行原因",
                        "summary": "足球的历史与传播",
                        "confidence": 0.93,
                        "source_refs": [
                            {
                                "source_id": "source-1",
                                "quote": "The world's game.",
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_generates_positions_and_slugs_for_missing_model_metadata() -> None:
    candidate = _candidate()
    candidate["units"][0]["knowledge_points"][0]["scope_slot"] = "reading_b"
    validated = validate_textbook_structure(candidate, FROZEN_INPUT)

    unit = validated["units"][0]
    knowledge_point = unit["knowledge_points"][0]
    assert unit["position"] == 1
    assert unit["slug"] == "unit-1-sports-and-fitness"
    assert knowledge_point["position"] == 1
    assert knowledge_point["slug"] == "kp-01"
    assert knowledge_point["title"] == "世界运动：足球的历史与流行原因"
    assert knowledge_point["scope_slot"] == "reading_b"


def test_uses_model_slug_hint_when_safe() -> None:
    candidate = _candidate()
    candidate["units"][0]["slug"] = "Unit 1 Sports"
    candidate["units"][0]["knowledge_points"][0]["slug"] = "World Game"

    validated = validate_textbook_structure(candidate, FROZEN_INPUT)

    assert validated["units"][0]["slug"] == "unit-1-sports"
    assert validated["units"][0]["knowledge_points"][0]["slug"] == "world-game"


def test_ignores_model_positions_and_uses_array_order() -> None:
    candidate = _candidate()
    candidate["units"][0]["position"] = 99
    candidate["units"][0]["knowledge_points"][0]["position"] = 99

    validated = validate_textbook_structure(candidate, FROZEN_INPUT)

    assert validated["units"][0]["position"] == 1
    assert validated["units"][0]["knowledge_points"][0]["position"] == 1


def test_missing_source_refs_are_reviewable_with_warning() -> None:
    candidate = _candidate()
    candidate["units"][0]["source_refs"] = []

    validated = validate_textbook_structure(candidate, FROZEN_INPUT)

    assert validated["units"][0]["status"] == "review"
    assert "unit_source_refs_missing" in validated["warnings"]


def test_unresolved_source_quote_is_retained_for_review() -> None:
    candidate = _candidate()
    candidate["units"][0]["source_refs"][0]["quote"] = "Not in source"

    validated = validate_textbook_structure(candidate, FROZEN_INPUT)
    source_ref = validated["units"][0]["source_refs"][0]

    assert source_ref["quote"] == "Not in source"
    assert source_ref["start"] is None
    assert source_ref["end"] is None
    assert source_ref["resolution_status"] == "unresolved"
    assert "source_quote_unresolved" in validated["warnings"]


def test_legacy_offsets_without_quote_are_recovered_when_possible() -> None:
    candidate = _candidate()
    candidate["units"][0]["source_refs"] = [
        {"source_id": "source-1", "start": 10, "end": 27}
    ]
    candidate["units"][0]["knowledge_points"][0]["source_refs"] = []

    validated = validate_textbook_structure(candidate, FROZEN_INPUT)
    source_ref = validated["units"][0]["source_refs"][0]

    assert source_ref["quote"] == "The world's game."
    assert source_ref["start"] == 10
    assert source_ref["end"] == 27
    assert "legacy_source_offsets_recovered" in validated["warnings"]


def test_non_teaching_unit_with_points_is_preserved_as_teaching() -> None:
    candidate = _candidate()
    candidate["units"][0]["unit_type"] = "appendix"

    validated = validate_textbook_structure(candidate, FROZEN_INPUT)

    assert validated["units"][0]["unit_type"] == "teaching"
    assert len(validated["units"][0]["knowledge_points"]) == 1
    assert "unit_type_promoted" in validated["warnings"]


def test_duplicate_slugs_are_made_unique() -> None:
    candidate = _candidate()
    duplicate = copy.deepcopy(candidate["units"][0])
    duplicate["title"] = "Another Unit"
    duplicate["slug"] = "unit-1-sports-and-fitness"
    duplicate["knowledge_points"] = []
    candidate["units"].append(duplicate)

    validated = validate_textbook_structure(candidate, FROZEN_INPUT)

    assert [unit["slug"] for unit in validated["units"]] == [
        "unit-1-sports-and-fitness",
        "unit-1-sports-and-fitness-2",
    ]
    assert "unit_slug_deduplicated" in validated["warnings"]


def test_malformed_optional_unit_is_skipped_when_usable_units_remain() -> None:
    candidate = _candidate()
    candidate["units"].append("not an object")

    validated = validate_textbook_structure(candidate, FROZEN_INPUT)

    assert len(validated["units"]) == 1
    assert "unit_skipped_invalid" in validated["warnings"]


def test_fails_only_when_no_usable_units_remain() -> None:
    with pytest.raises(
        TextbookStructureValidationError,
        match="no usable Units",
    ):
        validate_textbook_structure(
            {
                "format": "langalpha-managed-textbook-structure/v1",
                "units": ["not an object"],
            },
            FROZEN_INPUT,
        )
