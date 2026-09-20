"""Source quote resolution favors usable evidence over strict failure."""

import pytest

from src.server.services.education_source_refs import (
    SourceReferenceResolutionError,
    resolve_source_ref,
)


def test_exact_quote_resolves_character_offsets() -> None:
    resolved = resolve_source_ref(
        sources={"source-1": "Before. Exact quote. After."},
        source_id="source-1",
        quote="Exact quote.",
    )

    assert resolved == {
        "source_id": "source-1",
        "quote": "Exact quote.",
        "start": 8,
        "end": 20,
        "resolution_status": "resolved",
        "warnings": [],
    }


def test_whitespace_normalized_quote_resolves_markdown_line_wrapping() -> None:
    resolved = resolve_source_ref(
        sources={"source-1": "A sentence split\nacross lines."},
        source_id="source-1",
        quote="A sentence split across lines.",
    )

    assert resolved["resolution_status"] == "normalized"
    assert resolved["start"] == 0
    assert resolved["end"] == 30
    assert resolved["warnings"] == ["source_quote_whitespace_normalized"]


def test_duplicate_quote_uses_first_match_and_keeps_warning() -> None:
    resolved = resolve_source_ref(
        sources={"source-1": "Repeated. Other. Repeated."},
        source_id="source-1",
        quote="Repeated.",
    )

    assert resolved["start"] == 0
    assert resolved["end"] == 9
    assert resolved["warnings"] == [
        "source_quote_ambiguous_first_match_used"
    ]


def test_missing_quote_is_retained_as_unresolved() -> None:
    resolved = resolve_source_ref(
        sources={"source-1": "Only this text."},
        source_id="source-1",
        quote="Not in the source.",
    )

    assert resolved == {
        "source_id": "source-1",
        "quote": "Not in the source.",
        "start": None,
        "end": None,
        "resolution_status": "unresolved",
        "warnings": ["source_quote_unresolved"],
    }


def test_single_source_is_used_when_source_id_is_missing_or_unknown() -> None:
    for source_id in (None, "unknown"):
        resolved = resolve_source_ref(
            sources={"source-1": "Quote here."},
            source_id=source_id,
            quote="Quote here.",
        )

        assert resolved["source_id"] == "source-1"
        assert resolved["start"] == 0
        assert resolved["warnings"] == [
            "source_id_defaulted" if source_id is None else "source_id_reassigned"
        ]


def test_unknown_source_with_multiple_candidates_remains_reviewable() -> None:
    resolved = resolve_source_ref(
        sources={"source-1": "One.", "source-2": "Two."},
        source_id="unknown",
        quote="Missing",
    )

    assert resolved["resolution_status"] == "unresolved"
    assert resolved["warnings"] == [
        "source_id_unresolved",
        "source_quote_unresolved",
    ]


def test_empty_quote_is_rejected() -> None:
    with pytest.raises(SourceReferenceResolutionError):
        resolve_source_ref(
            sources={"source-1": "Text."},
            source_id="source-1",
            quote=" ",
        )
