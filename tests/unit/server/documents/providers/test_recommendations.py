from __future__ import annotations

import pytest

from src.server.documents.providers.registry import build_default_provider_registry


@pytest.mark.parametrize(
    ("classification", "expected_ids", "recommended_id"),
    [
        (
            "text_based",
            ("anydoc-local", "legacy-pdf-text", "datalab-online"),
            "anydoc-local",
        ),
        # Non-text classifications now recommend the hosted parser. It is the
        # only one that can read a scan; the legacy extractor remains in the
        # list for anyone who wants it, and is still what a deployment without
        # a Datalab key will actually get recommended (see the registry's own
        # policy tests, which drive that case with explicit descriptors).
        (
            "mixed",
            ("datalab-online", "legacy-pdf-text"),
            "datalab-online",
        ),
        (
            "scanned",
            ("datalab-online", "legacy-pdf-text"),
            "datalab-online",
        ),
        (
            "image_based",
            ("datalab-online", "legacy-pdf-text"),
            "datalab-online",
        ),
        (
            "unknown",
            ("datalab-online", "legacy-pdf-text"),
            "datalab-online",
        ),
    ],
)
def test_parser_options_follow_classification_matrix(
    classification: str,
    expected_ids: tuple[str, ...],
    recommended_id: str,
) -> None:
    options = build_default_provider_registry().parser_options(
        document_format="pdf",
        classification=classification,
    )

    assert tuple(option.parser_id for option in options) == expected_ids
    assert [option.parser_id for option in options if option.recommended] == [
        recommended_id
    ]


def test_the_ocr_placeholder_is_retired() -> None:
    """It stood in for OCR capability that the hosted parser now provides.

    Leaving a permanently unavailable entry in the picker beside a parser that
    does the same job is worse than removing it: it reads as a broken option
    rather than an absent one.
    """
    options = build_default_provider_registry().parser_options(
        document_format="pdf",
        classification="scanned",
    )

    assert all(option.parser_id != "ocr-document" for option in options)


@pytest.mark.parametrize(
    "classification",
    ["text_based", "mixed", "scanned", "image_based", "unknown"],
)
def test_every_option_has_one_sentence_reason_and_availability(
    classification: str,
) -> None:
    options = build_default_provider_registry().parser_options(
        document_format="pdf",
        classification=classification,
    )

    assert options
    for option in options:
        assert isinstance(option.available, bool)
        assert option.reason.endswith(".")
        assert "\n" not in option.reason


@pytest.mark.parametrize(
    "classification", ["mixed", "scanned", "image_based", "unknown"]
)
def test_non_text_legacy_option_includes_quality_warning(classification: str) -> None:
    options = build_default_provider_registry().parser_options(
        document_format="pdf",
        classification=classification,
    )

    legacy = next(option for option in options if option.parser_id == "legacy-pdf-text")
    assert (
        legacy.warning == "Pages without a usable text layer may be missing or empty."
    )
