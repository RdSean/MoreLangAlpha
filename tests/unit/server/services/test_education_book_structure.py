from __future__ import annotations

import json

import pytest

from src.server.services.education_book_structure import (
    BookStructureValidationError,
    TrustedBookSource,
    get_more_to_skills_identity,
    parse_book_structure,
    project_material_content_files,
)


def _source(*, total_lines: int = 80) -> TrustedBookSource:
    return TrustedBookSource(
        path="inputs/source.md",
        filename="reader.md",
        format="markdown",
        total_lines=total_lines,
        anchor_mode="source_lines",
        line_offset=4,
    )


def _candidate() -> dict[str, object]:
    return {
        "schema_version": "2.1.0",
        "generator": {
            "name": "more-to-skills",
            "version": "2.1.0",
            "generated_at": "2026-09-30T15:10:00+09:00",
        },
        "book": {
            "title": "Reading Explorer",
            "title_source": "normalized",
            "publisher_extension": {"edition": 3},
        },
        "source": {
            "path": "/managed/untrusted/source.md",
            "filename": "invented.md",
            "format": "markdown",
            "total_lines": 999,
            "anchor_mode": "source_lines",
            "line_offset": 999,
        },
        "level_names": ["unit", "lesson", "section"],
        "nodes": [
            {
                "id": "unit-1",
                "title": "Unit 1",
                "anchor": {"start_line": 1, "end_line": 80},
                "vendor_extension": "preserved",
                "children": [
                    {
                        "id": "unit-1-reading-a",
                        "title": "Reading A",
                        "anchor": {"start_line": 5, "end_line": 30},
                        "children": [],
                    },
                    {
                        "id": "unit-1-vocabulary",
                        "title": "Vocabulary",
                        "anchor": {"start_line": 31, "end_line": 40},
                    },
                ],
            }
        ],
        "knowledge_points": [
            {
                "id": "unit-1-k1",
                "title": "Global sport and vocabulary",
                "anchor": {"start_line": 5, "end_line": 40},
                "unit": "unit-1",
                "nodes": ["unit-1-reading-a", "unit-1-vocabulary"],
                "blocks": [1, 2],
                "content_file": "chapters/unit-1-k1.md",
                "difficulty_extension": "intermediate",
            }
        ],
        "coverage": {
            "scope": "Complete book",
            "excluded": [],
            "omitted": [],
            "gaps": [],
        },
        "root_extension": {"reviewed": True},
    }


def test_fixed_skill_and_schema_have_recordable_content_digests() -> None:
    identity = get_more_to_skills_identity()

    assert identity.version == "2.1.0"
    assert identity.skill_sha256 == (
        "3fcfc60c1e218480eb93ebdf8edca71762eafdd23c03eab825c10e0805683886"
    )
    assert identity.schema_sha256 == (
        "601bced7331cb5eac37ead5a8c3f13ed55382f4afa05d2e4227b6ee04d7eb6d1"
    )


def test_parses_recursive_structure_from_trusted_source_without_rebasing_lines() -> (
    None
):
    result = parse_book_structure(
        trusted_source=_source(),
        raw_json=json.dumps(_candidate()),
        allowed_output_paths={"chapters/unit-1-k1.md"},
    )

    assert result.document["source"] == {
        "path": "inputs/source.md",
        "filename": "reader.md",
        "format": "markdown",
        "total_lines": 80,
        "anchor_mode": "source_lines",
        "line_offset": 4,
    }
    assert result.document["nodes"][0]["vendor_extension"] == "preserved"
    assert result.document["root_extension"] == {"reviewed": True}
    assert result.document["knowledge_points"][0]["difficulty_extension"] == (
        "intermediate"
    )
    assert result.knowledge_points == (
        {
            "skill_kp_id": "unit-1-k1",
            "position": 1,
            "title": "Global sport and vocabulary",
            "unit_skill_node_id": "unit-1",
            "node_skill_ids": ("unit-1-reading-a", "unit-1-vocabulary"),
            "start_line": 5,
            "end_line": 40,
            "raw": result.document["knowledge_points"][0],
        },
    )
    assert result.warnings == ()


def test_validation_error_exposes_the_json_path() -> None:
    candidate = _candidate()
    candidate["book"]["title_source"] = None  # type: ignore[index]

    with pytest.raises(
        BookStructureValidationError,
        match=r"\$\.book\.title_source",
    ):
        parse_book_structure(
            trusted_source=_source(),
            raw_json=json.dumps(candidate),
            allowed_output_paths={"chapters/unit-1-k1.md"},
        )


@pytest.mark.parametrize(
    ("raw_json", "message"),
    [
        ('{"schema_version":"2.1.0","schema_version":"2.1.0"}', "duplicate"),
        ('{"schema_version":"2.1.0","value":NaN}', "constant"),
        ('{"schema_version":"2.1.0","value":1e999}', "finite"),
    ],
)
def test_rejects_json_that_postgres_jsonb_cannot_represent(
    raw_json: str,
    message: str,
) -> None:
    with pytest.raises(BookStructureValidationError, match=message):
        parse_book_structure(
            trusted_source=_source(),
            raw_json=raw_json,
            allowed_output_paths=set(),
        )


def test_rejects_unsupported_schema_major_before_schema_validation() -> None:
    candidate = _candidate()
    candidate["schema_version"] = "3.0.0"

    with pytest.raises(
        BookStructureValidationError, match="unsupported schema major 3"
    ):
        parse_book_structure(
            trusted_source=_source(),
            raw_json=json.dumps(candidate),
            allowed_output_paths={"chapters/unit-1-k1.md"},
        )


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            TrustedBookSource(
                path="inputs/source.md",
                filename="reader.md",
                format="markdown",
                total_lines=80,
                anchor_mode="source_lines",
            ),
            "line_offset",
        ),
        (
            TrustedBookSource(
                path="inputs/source.md",
                filename="reader.md",
                format="pdf",
                total_lines=80,
                anchor_mode="workdir_lines",
            ),
            "workdir_text",
        ),
    ],
)
def test_trusted_source_requires_coordinates_for_its_anchor_mode(
    source: TrustedBookSource,
    message: str,
) -> None:
    with pytest.raises(BookStructureValidationError, match=message):
        parse_book_structure(
            trusted_source=source,
            raw_json=json.dumps(_candidate()),
            allowed_output_paths={"chapters/unit-1-k1.md"},
        )


def test_allows_nodes_without_units_or_materials_and_an_empty_kp_list() -> None:
    candidate = _candidate()
    candidate["level_names"] = ["chapter"]
    candidate["nodes"] = [
        {
            "id": "preface",
            "title": "Preface",
            "type": "front_matter",
            "anchor": {"start_line": 1, "end_line": 4},
            "children": [],
        }
    ]
    candidate["knowledge_points"] = []

    result = parse_book_structure(
        trusted_source=_source(),
        raw_json=json.dumps(candidate),
        allowed_output_paths=set(),
    )

    assert result.knowledge_points == ()
    assert result.warnings == ("knowledge_points_empty",)


def test_rejects_node_materials_that_cannot_be_persisted() -> None:
    candidate = _candidate()
    candidate["nodes"][0]["content_file"] = "chapters/unit-1.md"  # type: ignore[index]

    with pytest.raises(
        BookStructureValidationError,
        match="node-level content_file is not supported",
    ):
        parse_book_structure(
            trusted_source=_source(),
            raw_json=json.dumps(candidate),
            allowed_output_paths={
                "chapters/unit-1.md",
                "chapters/unit-1-k1.md",
            },
        )


def test_rejects_duplicate_recursive_node_ids() -> None:
    candidate = _candidate()
    candidate["nodes"][0]["children"][1]["id"] = "unit-1-reading-a"  # type: ignore[index]

    with pytest.raises(BookStructureValidationError, match="duplicate node id"):
        parse_book_structure(
            trusted_source=_source(),
            raw_json=json.dumps(candidate),
            allowed_output_paths={"chapters/unit-1-k1.md"},
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("unit", "missing-unit", "unknown node id"),
        ("nodes", ["unit-1-reading-a", "missing-node"], "unknown node id"),
    ],
)
def test_rejects_invalid_knowledge_point_node_references(
    field: str,
    value: object,
    message: str,
) -> None:
    candidate = _candidate()
    candidate["knowledge_points"][0][field] = value  # type: ignore[index]

    with pytest.raises(BookStructureValidationError, match=message):
        parse_book_structure(
            trusted_source=_source(),
            raw_json=json.dumps(candidate),
            allowed_output_paths={"chapters/unit-1-k1.md"},
        )


@pytest.mark.parametrize(
    ("path", "allowed", "message"),
    [
        ("../secret.md", {"../secret.md"}, "path is invalid"),
        ("chapters/../../secret.md", {"chapters/../../secret.md"}, "path is invalid"),
        ("chapters\\secret.md", {"chapters\\secret.md"}, "path is invalid"),
        ("chapters/missing.md", set(), "material is missing"),
    ],
)
def test_rejects_unsafe_or_missing_material_paths(
    path: str,
    allowed: set[str],
    message: str,
) -> None:
    candidate = _candidate()
    candidate["knowledge_points"][0]["content_file"] = path  # type: ignore[index]

    with pytest.raises(BookStructureValidationError, match=message):
        parse_book_structure(
            trusted_source=_source(),
            raw_json=json.dumps(candidate),
            allowed_output_paths=allowed,
        )


@pytest.mark.parametrize(
    ("start_line", "end_line", "message"),
    [
        (20, 19, "start_line exceeds end_line"),
        (1, 81, "trusted source line count"),
    ],
)
def test_rejects_knowledge_point_ranges_outside_the_trusted_source(
    start_line: int,
    end_line: int,
    message: str,
) -> None:
    candidate = _candidate()
    candidate["knowledge_points"][0]["anchor"] = {  # type: ignore[index]
        "start_line": start_line,
        "end_line": end_line,
    }

    with pytest.raises(BookStructureValidationError, match=message):
        parse_book_structure(
            trusted_source=_source(),
            raw_json=json.dumps(candidate),
            allowed_output_paths={"chapters/unit-1-k1.md"},
        )


def test_rejects_coverage_ranges_outside_the_trusted_source() -> None:
    candidate = _candidate()
    candidate["coverage"]["excluded"] = [  # type: ignore[index]
        {
            "label": "Index",
            "reason": "Back matter",
            "anchor": {"start_line": 79, "end_line": 81},
        }
    ]

    with pytest.raises(
        BookStructureValidationError,
        match=r"\$\.coverage\.excluded\[0\]\.anchor\.end_line",
    ):
        parse_book_structure(
            trusted_source=_source(),
            raw_json=json.dumps(candidate),
            allowed_output_paths={"chapters/unit-1-k1.md"},
        )


def test_material_content_files_are_projected_from_current_materials() -> None:
    document = _candidate()
    document["nodes"][0]["content_file"] = "outputs/stale-node.md"  # type: ignore[index]

    projected = project_material_content_files(
        document,
        {"unit-1-k1": "materials/2a5f.md"},
    )

    assert document["nodes"][0]["content_file"] == "outputs/stale-node.md"  # type: ignore[index]
    assert document["knowledge_points"][0]["content_file"] == (  # type: ignore[index]
        "chapters/unit-1-k1.md"
    )
    assert "content_file" not in projected["nodes"][0]
    assert projected["knowledge_points"][0]["content_file"] == "materials/2a5f.md"

    without_material = project_material_content_files(document, {})
    assert "content_file" not in without_material["knowledge_points"][0]
