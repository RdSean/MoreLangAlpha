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
            "markdown": "# Unit 1\n\n" + ("content " * 1_000),
        }
    ],
}


STRUCTURE = {
    "format": "langalpha-managed-textbook-structure/v1",
    "units": [
        {
            "position": 1,
            "slug": "unit-1-sports",
            "title": "Unit 1: Sports and Fitness",
            "summary": "Sports and fitness",
            "unit_type": "teaching",
            "confidence": 0.96,
            "source_refs": [
                {
                    "source_id": "source-1",
                    "start": 0,
                    "end": 50,
                    "quote": "Unit 1",
                }
            ],
            "knowledge_points": [
                {
                    "position": 1,
                    "slug": "world-game",
                    "title": "世界运动：足球的历史与流行原因",
                    "summary": "足球的历史与传播",
                    "confidence": 0.93,
                    "source_refs": [
                        {
                            "source_id": "source-1",
                            "start": 0,
                            "end": 40,
                        }
                    ],
                }
            ],
        }
    ],
}


def test_accepts_a_source_grounded_structure() -> None:
    validated = validate_textbook_structure(STRUCTURE, FROZEN_INPUT)

    assert validated["units"][0]["status"] == "review"
    assert validated["units"][0]["knowledge_points"][0]["title"] == (
        "世界运动：足球的历史与流行原因"
    )


def test_non_teaching_unit_may_have_no_knowledge_points() -> None:
    structure = copy.deepcopy(STRUCTURE)
    unit = structure["units"][0]
    unit["unit_type"] = "front_matter"
    unit["knowledge_points"] = []

    validated = validate_textbook_structure(structure, FROZEN_INPUT)

    assert validated["units"][0]["knowledge_points"] == []


def test_teaching_unit_may_be_empty_until_parent_review() -> None:
    structure = copy.deepcopy(STRUCTURE)
    structure["units"][0]["knowledge_points"] = []

    validated = validate_textbook_structure(structure, FROZEN_INPUT)

    assert validated["units"][0]["knowledge_points"] == []


def test_rejects_generated_knowledge_points_for_non_teaching_unit() -> None:
    structure = copy.deepcopy(STRUCTURE)
    structure["units"][0]["unit_type"] = "appendix"

    with pytest.raises(
        TextbookStructureValidationError,
        match="non-teaching Unit",
    ):
        validate_textbook_structure(structure, FROZEN_INPUT)


def test_rejects_unit_without_source_evidence() -> None:
    structure = copy.deepcopy(STRUCTURE)
    structure["units"][0]["source_refs"] = []

    with pytest.raises(TextbookStructureValidationError, match="source"):
        validate_textbook_structure(structure, FROZEN_INPUT)


def test_rejects_unknown_source_and_invalid_offsets() -> None:
    structure = copy.deepcopy(STRUCTURE)
    structure["units"][0]["source_refs"][0]["source_id"] = "missing"

    with pytest.raises(TextbookStructureValidationError, match="source"):
        validate_textbook_structure(structure, FROZEN_INPUT)

    structure = copy.deepcopy(STRUCTURE)
    structure["units"][0]["source_refs"][0]["end"] = 0

    with pytest.raises(TextbookStructureValidationError, match="range"):
        validate_textbook_structure(structure, FROZEN_INPUT)


def test_rejects_duplicate_positions_or_slugs() -> None:
    structure = copy.deepcopy(STRUCTURE)
    structure["units"].append(copy.deepcopy(structure["units"][0]))

    with pytest.raises(TextbookStructureValidationError, match="position"):
        validate_textbook_structure(structure, FROZEN_INPUT)

    structure = copy.deepcopy(STRUCTURE)
    duplicate = copy.deepcopy(structure["units"][0]["knowledge_points"][0])
    duplicate["position"] = 2
    structure["units"][0]["knowledge_points"].append(duplicate)

    with pytest.raises(TextbookStructureValidationError, match="slug"):
        validate_textbook_structure(structure, FROZEN_INPUT)
