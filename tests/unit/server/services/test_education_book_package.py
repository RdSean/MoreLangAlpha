from __future__ import annotations

import copy
import math

import pytest

from src.server.services import education_book_package
from src.server.services.education_book_package import (
    BookPackageValidationError,
    validate_book_package,
)


MARKDOWN = """\
# Unit 1

Sports and fitness.

# Reading A

The world's game is global.

# Reading B

Olympic champions train deliberately.
"""

MARKDOWN_SECOND = """\
# Unit 2

Geometry connects shapes, proofs, and measurements.

# Reading C

Triangles have three angles whose measures sum to 180 degrees.
"""


def _candidate() -> dict:
    reading_start = MARKDOWN.index("# Reading A")
    reading_end = MARKDOWN.index("# Reading B")
    return {
        "format": "langalpha-book-package/v1",
        "source_revision": "revision-1",
        "content_nodes": [
            {
                "node_key": "unit-1",
                "parent_key": None,
                "node_type": "unit",
                "label": None,
                "position": 1,
                "title": "Sports and Fitness",
                "summary": "Unit overview",
                "source_refs": [{"char_start": 0, "char_end": len(MARKDOWN)}],
            },
            {
                "node_key": "unit-1-reading-a",
                "parent_key": "unit-1",
                "node_type": "reading",
                "label": "Reading A",
                "position": 1,
                "title": "The World's Game",
                "summary": "Reading overview",
                "source_refs": [
                    {
                        "char_start": reading_start,
                        "char_end": reading_end,
                        "quote": "model quote that intentionally differs",
                        "source_id": "source-1",
                    }
                ],
            },
            {
                "node_key": "unit-1-project",
                "parent_key": "unit-1",
                "node_type": "project",
                "label": None,
                "position": 2,
                "title": "Unit project",
                "summary": "",
                "source_refs": [],
            },
        ],
        "knowledge_points": [
            {
                "candidate_key": "unit-1-reading-a-kp-1",
                "node_key": "unit-1-reading-a",
                "point_type": "concept",
                "title": "Why football became global",
                "summary": "The reading explains football's global reach.",
                "source_refs": [
                    {
                        "char_start": MARKDOWN.index("The world's"),
                        "char_end": MARKDOWN.index("\n", MARKDOWN.index("The world's")),
                        "quote": "also intentionally stale",
                    }
                ],
                "confidence": 0.92,
            }
        ],
        "assets": [
            {
                "node_key": "unit-1-reading-a",
                "kind": "knowledge",
                "path": "outputs/chapters/unit-1-reading-a/knowledge.md",
            }
        ],
    }


def test_preserves_generic_hierarchy_and_derives_canonical_quotes() -> None:
    package, warnings = validate_book_package(_candidate(), markdown=MARKDOWN)

    assert package["content_nodes"][1]["parent_key"] == "unit-1"
    assert package["knowledge_points"][0]["node_key"] == "unit-1-reading-a"
    reading_ref = package["content_nodes"][1]["source_refs"][0]
    assert reading_ref["quote"] == MARKDOWN[reading_ref["start"] : reading_ref["end"]]
    assert reading_ref["quote"] != "model quote that intentionally differs"
    assert reading_ref["source_id"] == "source-1"
    assert package["knowledge_points"][0]["source_refs"][0]["quote"] == (
        "The world's game is global."
    )
    assert "unknown_node_type" in warnings
    assert "source_refs_missing" in warnings
    assert package["content_nodes"][2]["node_type"] == "project"


def test_unknown_open_node_and_point_types_are_preserved_with_warnings() -> None:
    candidate = _candidate()
    candidate["content_nodes"][2]["node_type"] = "  Project_Workspace  "
    candidate["knowledge_points"][0]["point_type"] = "  Argument_Analysis  "

    package, warnings = validate_book_package(candidate, markdown=MARKDOWN)

    assert package["content_nodes"][2]["node_type"] == "project_workspace"
    assert package["knowledge_points"][0]["point_type"] == "argument_analysis"
    assert "unknown_node_type" in warnings
    assert "unknown_point_type" in warnings


def test_open_node_and_point_types_reject_control_characters() -> None:
    node_candidate = _candidate()
    node_candidate["content_nodes"][2]["node_type"] = "project\u0000workspace"
    with pytest.raises(BookPackageValidationError):
        validate_book_package(node_candidate, markdown=MARKDOWN)

    point_candidate = _candidate()
    point_candidate["knowledge_points"][0]["point_type"] = "concept\nvariant"
    with pytest.raises(BookPackageValidationError):
        validate_book_package(point_candidate, markdown=MARKDOWN)


def test_char_range_is_authoritative_and_quote_is_ignored() -> None:
    candidate = _candidate()
    ref = candidate["knowledge_points"][0]["source_refs"][0]
    ref["quote"] = "completely wrong"

    package, _ = validate_book_package(candidate, markdown=MARKDOWN)

    normalized = package["knowledge_points"][0]["source_refs"][0]
    assert normalized["quote"] == "The world's game is global."
    assert normalized["start"] == ref["char_start"]
    assert normalized["end"] == ref["char_end"]


def test_legacy_markdown_accepts_only_fixed_compatibility_source_id() -> None:
    candidate = _candidate()
    candidate["content_nodes"][1]["source_refs"][0]["source_id"] = "source-1"
    validate_book_package(candidate, markdown=MARKDOWN)

    candidate = _candidate()
    candidate["content_nodes"][1]["source_refs"][0]["source_id"] = "invented-source"
    with pytest.raises(BookPackageValidationError, match="compatibility source"):
        validate_book_package(candidate, markdown=MARKDOWN)


def test_char_only_package_does_not_build_line_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    constructed = False

    def forbidden_init(self, *args, **kwargs):
        nonlocal constructed
        constructed = True
        raise AssertionError("line index must not be constructed")

    monkeypatch.setattr(
        education_book_package._LineIndex,
        "__init__",
        forbidden_init,
    )

    validate_book_package(_candidate(), markdown=MARKDOWN)
    validate_book_package(
        {
            "format": "langalpha-book-package/v1",
            "source_revision": "empty",
            "content_nodes": [],
            "knowledge_points": [],
            "assets": [],
        },
        markdown="x" * 1024,
    )

    assert constructed is False


def test_line_range_is_one_based_and_end_exclusive() -> None:
    candidate = _candidate()
    candidate["content_nodes"][1]["source_refs"] = [{"line_start": 7, "line_end": 8}]

    package, _ = validate_book_package(candidate, markdown=MARKDOWN)
    source_ref = package["content_nodes"][1]["source_refs"][0]

    expected = "The world's game is global.\n"
    assert source_ref["quote"] == expected
    assert source_ref["line_start"] == 7
    assert source_ref["line_end"] == 8


@pytest.mark.parametrize(
    "source_ref",
    [
        "raw quote",
        {"quote": "The world's game is global."},
        {"source_id": "source-1"},
        {"char_start": 0},
        {"line_start": 1},
    ],
)
def test_rejects_source_refs_without_a_complete_range(source_ref: object) -> None:
    candidate = _candidate()
    candidate["content_nodes"][1]["source_refs"] = [source_ref]

    with pytest.raises(BookPackageValidationError, match="source reference"):
        validate_book_package(candidate, markdown=MARKDOWN)


@pytest.mark.parametrize(
    "source_ref",
    [
        {
            "char_start": 0,
            "char_end": 10,
            "line_start": 1,
            "line_end": 2,
        },
        {
            "char_start": 0,
            "char_end": 10,
            "line_start": 1,
        },
        {
            "line_start": 1,
            "line_end": 2,
            "char_start": 0,
        },
        {
            "char_start": 0,
            "char_end": 10,
            "line_start": 1,
            "line_end": 10_000,
        },
    ],
)
def test_rejects_mixed_or_overlapping_range_families(source_ref: dict) -> None:
    candidate = _candidate()
    candidate["content_nodes"][1]["source_refs"] = [source_ref]

    with pytest.raises(BookPackageValidationError, match="exactly one"):
        validate_book_package(candidate, markdown=MARKDOWN)


def test_rejects_out_of_bounds_and_cross_node_ranges() -> None:
    candidate = _candidate()
    candidate["content_nodes"][1]["source_refs"] = [
        {"char_start": len(MARKDOWN) - 2, "char_end": len(MARKDOWN) + 1}
    ]
    with pytest.raises(BookPackageValidationError, match="outside"):
        validate_book_package(candidate, markdown=MARKDOWN)

    candidate = _candidate()
    candidate["content_nodes"][1]["source_refs"] = [{"line_start": 0, "line_end": 2}]
    with pytest.raises(BookPackageValidationError, match="line range"):
        validate_book_package(candidate, markdown=MARKDOWN)

    candidate = _candidate()
    candidate["content_nodes"][0]["source_refs"] = [{"char_start": 0, "char_end": 120}]
    candidate["content_nodes"][1]["source_refs"] = [
        {"char_start": 0, "char_end": 10},
        {"char_start": 90, "char_end": 100},
    ]
    candidate["knowledge_points"][0]["source_refs"] = [
        {"char_start": 45, "char_end": 55}
    ]
    with pytest.raises(BookPackageValidationError, match="node source ref"):
        validate_book_package(candidate, markdown="x" * 120)


def test_empty_source_refs_are_warning_only() -> None:
    package, warnings = validate_book_package(_candidate(), markdown=MARKDOWN)

    assert package["content_nodes"][2]["source_refs"] == []
    assert "source_refs_missing" in warnings


def test_missing_or_null_source_refs_emit_missing_warning() -> None:
    for value in (None,):
        candidate = _candidate()
        candidate["content_nodes"][2].pop("source_refs")
        _, missing_warnings = validate_book_package(candidate, markdown=MARKDOWN)

        candidate = _candidate()
        candidate["content_nodes"][2]["source_refs"] = value
        _, null_warnings = validate_book_package(candidate, markdown=MARKDOWN)

        assert "source_refs_missing" in missing_warnings
        assert "source_refs_missing" in null_warnings


def test_parents_cycles_and_duplicate_keys_remain_hard_failures() -> None:
    candidate = _candidate()
    candidate["content_nodes"][1]["parent_key"] = "missing-parent"
    with pytest.raises(BookPackageValidationError, match="parent"):
        validate_book_package(candidate, markdown=MARKDOWN)

    candidate = _candidate()
    candidate["content_nodes"][0]["parent_key"] = "unit-1-project"
    with pytest.raises(BookPackageValidationError, match="cycle"):
        validate_book_package(candidate, markdown=MARKDOWN)

    candidate = _candidate()
    candidate["content_nodes"].append(copy.deepcopy(candidate["content_nodes"][2]))
    with pytest.raises(BookPackageValidationError, match="node key"):
        validate_book_package(candidate, markdown=MARKDOWN)


def test_missing_position_uses_next_unused_sibling_position() -> None:
    candidate = _candidate()
    candidate["content_nodes"][1].pop("position")
    candidate["content_nodes"][2]["position"] = 2

    package, warnings = validate_book_package(candidate, markdown=MARKDOWN)

    assert package["content_nodes"][1]["position"] == 1
    assert package["content_nodes"][2]["position"] == 2
    assert "node_position_defaulted" in warnings


@pytest.mark.parametrize(
    ("confidence", "expected", "warning"),
    [
        (None, 1.0, "knowledge_point_confidence_missing"),
        ("0.5", 1.0, "knowledge_point_confidence_defaulted"),
        (float("nan"), 1.0, "knowledge_point_confidence_defaulted"),
        (-0.01, 0.0, "knowledge_point_confidence_clamped"),
        (1.01, 1.0, "knowledge_point_confidence_clamped"),
    ],
)
def test_confidence_warning_policy_is_preserved(
    confidence: object,
    expected: float,
    warning: str,
) -> None:
    candidate = _candidate()
    candidate["knowledge_points"][0]["confidence"] = confidence

    package, warnings = validate_book_package(candidate, markdown=MARKDOWN)

    assert package["knowledge_points"][0]["confidence"] == expected
    assert math.isfinite(package["knowledge_points"][0]["confidence"])
    assert warning in warnings


@pytest.mark.parametrize("position", [0, -1, 1.5, "1", 2_147_483_648])
def test_invalid_positions_are_hard_failures(position: object) -> None:
    candidate = _candidate()
    candidate["content_nodes"][1]["position"] = position

    with pytest.raises(BookPackageValidationError, match="position"):
        validate_book_package(candidate, markdown=MARKDOWN)


@pytest.mark.parametrize("size_bytes", [-1, 1.5, 2_147_483_648])
def test_invalid_asset_sizes_are_hard_failures(size_bytes: object) -> None:
    candidate = _candidate()
    candidate["assets"][0]["size_bytes"] = size_bytes

    with pytest.raises(BookPackageValidationError, match="size_bytes"):
        validate_book_package(candidate, markdown=MARKDOWN)


def test_asset_size_postgres_integer_boundary_is_explicit() -> None:
    candidate = _candidate()
    candidate["assets"][0]["size_bytes"] = education_book_package.POSTGRES_INTEGER_MAX
    package, _warnings = validate_book_package(candidate, markdown=MARKDOWN)
    assert package["assets"][0]["size_bytes"] == (
        education_book_package.POSTGRES_INTEGER_MAX
    )

    candidate["assets"][0]["size_bytes"] = (
        education_book_package.POSTGRES_INTEGER_MAX + 1
    )
    with pytest.raises(BookPackageValidationError, match="size_bytes"):
        validate_book_package(candidate, markdown=MARKDOWN)


@pytest.mark.parametrize(
    "path",
    [
        "../outside.md",
        "/absolute.md",
        "/outputs/absolute.md",
        "a\\b.md",
        "inputs/manifest.md",
        ".agents/skills/example.md",
        ".langalpha/progress.jsonl",
        "outputs",
        "archive.bin",
        "outputs/archive.bin",
        "outputs/content",
        "outputs/../outside.md",
        "outputs/\x00bad.md",
        "outputs/bad\rname.md",
        "outputs/bad\nname.md",
        "outputs/bad\tname.md",
        "\toutputs/bad.md",
        "outputs/bad.md\t",
    ],
)
def test_unsafe_asset_paths_are_rejected(path: str) -> None:
    candidate = _candidate()
    candidate["assets"][0]["path"] = path

    with pytest.raises(BookPackageValidationError, match="path"):
        validate_book_package(candidate, markdown=MARKDOWN)


@pytest.mark.parametrize(
    "path",
    [
        "outputs/knowledge.md",
        "outputs/data.json",
        "outputs/notes.txt",
        "outputs/table.csv",
        "outputs/figure.png",
        "outputs/photo.jpg",
        "outputs/photo.jpeg",
        "outputs/diagram.webp",
        "outputs/diagram.svg",
    ],
)
def test_supported_asset_paths_are_allowed(path: str) -> None:
    candidate = _candidate()
    candidate["assets"][0]["path"] = path

    package, _ = validate_book_package(candidate, markdown=MARKDOWN)

    assert package["assets"][0]["path"] == path


@pytest.mark.parametrize("nul_location", ["source_revision", "title", "metadata"])
def test_nul_is_rejected_in_normalized_json(nul_location: str) -> None:
    candidate = _candidate()
    if nul_location == "source_revision":
        candidate["source_revision"] = "revision\x00bad"
    elif nul_location == "title":
        candidate["content_nodes"][0]["title"] = "Bad\x00Title"
    else:
        candidate["content_nodes"][0]["metadata"] = {"bad\x00key": "bad\x00value"}

    with pytest.raises(BookPackageValidationError, match="NUL"):
        validate_book_package(candidate, markdown=MARKDOWN)


def test_utf8_size_and_nonstandard_empty_package_are_preserved() -> None:
    candidate = _candidate()
    candidate["content_nodes"][0]["title"] = "\ud800"
    with pytest.raises(BookPackageValidationError, match="UTF-8"):
        validate_book_package(candidate, markdown=MARKDOWN)

    package, warnings = validate_book_package(
        {
            "format": "langalpha-book-package/v1",
            "source_revision": "empty",
            "content_nodes": [],
            "knowledge_points": [],
            "assets": [],
        },
        markdown=MARKDOWN,
    )
    assert package["content_nodes"] == []
    assert "no_child_nodes" in warnings
    assert "no_knowledge_points" in warnings
    assert "no_reading_nodes" in warnings


def test_oversized_package_is_rejected() -> None:
    candidate = _candidate()
    candidate["content_nodes"][0]["summary"] = "x" * (16 * 1024 * 1024)

    with pytest.raises(BookPackageValidationError, match="size limit"):
        validate_book_package(candidate, markdown=MARKDOWN)


def test_multi_source_ranges_and_quotes_follow_their_source() -> None:
    second_reading = MARKDOWN_SECOND.index("# Reading C")
    candidate = {
        "format": "langalpha-book-package/v1",
        "source_revision": "multi-source-revision",
        "content_nodes": [
            {
                "node_key": "unit-1",
                "parent_key": None,
                "node_type": "unit",
                "position": 1,
                "title": "Unit 1",
                "summary": "",
                "source_refs": [
                    {
                        "source_id": "source-1",
                        "char_start": 0,
                        "char_end": len(MARKDOWN),
                    }
                ],
            },
            {
                "node_key": "reading-c",
                "parent_key": "unit-1",
                "node_type": "reading",
                "position": 1,
                "title": "Reading C",
                "summary": "",
                "source_refs": [
                    {
                        "source_id": "source-2",
                        "line_start": MARKDOWN_SECOND[
                            :second_reading
                        ].count("\n")
                        + 1,
                        "line_end": MARKDOWN_SECOND.count("\n") + 1,
                    }
                ],
            },
        ],
        "knowledge_points": [
            {
                "candidate_key": "reading-c-kp-1",
                "node_key": "reading-c",
                "point_type": "concept",
                "title": "Triangle angle sum",
                "summary": "",
                "source_refs": [
                    {
                        "source_id": "source-2",
                        "char_start": MARKDOWN_SECOND.index("Triangles"),
                        "char_end": len(MARKDOWN_SECOND),
                    }
                ],
            }
        ],
        "assets": [],
    }

    package, _warnings = validate_book_package(
        candidate,
        markdown_by_source={
            "source-1": MARKDOWN,
            "source-2": MARKDOWN_SECOND,
        },
    )

    assert package["content_nodes"][0]["source_refs"][0]["quote"].startswith(
        "# Unit 1"
    )
    assert package["content_nodes"][1]["source_refs"][0]["quote"].startswith(
        "# Reading C"
    )
    assert package["knowledge_points"][0]["source_refs"][0]["quote"].startswith(
        "Triangles have"
    )


def test_single_multi_source_defaults_missing_source_id_with_warning() -> None:
    candidate = _candidate()
    candidate["content_nodes"][0]["source_refs"][0].pop("source_id", None)
    candidate["content_nodes"][1]["source_refs"][0].pop("source_id", None)
    candidate["knowledge_points"][0]["source_refs"][0].pop("source_id", None)

    package, warnings = validate_book_package(
        candidate,
        markdown_by_source={"source-1": MARKDOWN},
    )

    assert package["content_nodes"][0]["source_refs"][0]["source_id"] == "source-1"
    assert "source_id_defaulted" in warnings


@pytest.mark.parametrize("mode", ["missing", "unknown"])
def test_multi_source_requires_resolvable_source_id(mode: str) -> None:
    candidate = _candidate()
    reference = candidate["content_nodes"][1]["source_refs"][0]
    if mode == "missing":
        reference.pop("source_id", None)
    else:
        reference["source_id"] = "source-missing"

    with pytest.raises(BookPackageValidationError, match="source_id"):
        validate_book_package(
            candidate,
            markdown_by_source={
                "source-1": MARKDOWN,
                "source-2": MARKDOWN_SECOND,
            },
        )


def test_multi_source_knowledge_point_cannot_cross_node_source() -> None:
    candidate = _candidate()
    candidate["content_nodes"][0]["source_refs"][0]["source_id"] = "source-1"
    candidate["content_nodes"][1]["source_refs"] = [
        {
            "source_id": "source-2",
            "char_start": 0,
            "char_end": len(MARKDOWN_SECOND),
        }
    ]
    candidate["knowledge_points"][0]["source_refs"] = [
        {
            "source_id": "source-1",
            "char_start": 0,
            "char_end": 10,
        }
    ]

    with pytest.raises(BookPackageValidationError, match="node source ref"):
        validate_book_package(
            candidate,
            markdown_by_source={
                "source-1": MARKDOWN,
                "source-2": MARKDOWN_SECOND,
            },
        )


def test_multi_source_ranges_use_the_selected_source_bounds() -> None:
    candidate = _candidate()
    candidate["content_nodes"][0]["source_refs"][0]["source_id"] = "source-1"
    candidate["content_nodes"][1]["source_refs"] = [
        {
            "source_id": "source-2",
            "char_start": len(MARKDOWN_SECOND) - 2,
            "char_end": len(MARKDOWN_SECOND) + 1,
        }
    ]

    with pytest.raises(BookPackageValidationError, match="outside"):
        validate_book_package(
            candidate,
            markdown_by_source={
                "source-1": MARKDOWN,
                "source-2": MARKDOWN_SECOND,
            },
        )
