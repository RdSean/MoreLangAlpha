from __future__ import annotations

import pytest

from src.server.documents.contracts import ParserUnavailableError
from src.server.documents.providers.registry import build_default_provider_registry


@pytest.mark.parametrize(
    ("classification", "expected_ids", "recommended_id"),
    [
        ("text_based", ("anydoc-local", "legacy-pdf-text"), "anydoc-local"),
        ("mixed", ("legacy-pdf-text", "ocr-document"), "legacy-pdf-text"),
        ("scanned", ("legacy-pdf-text", "ocr-document"), "legacy-pdf-text"),
        ("image_based", ("legacy-pdf-text", "ocr-document"), "legacy-pdf-text"),
        ("unknown", ("legacy-pdf-text", "ocr-document"), "legacy-pdf-text"),
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


def test_ocr_document_is_visible_but_cannot_create_a_job() -> None:
    registry = build_default_provider_registry()
    options = registry.parser_options(
        document_format="pdf",
        classification="scanned",
    )

    ocr = next(option for option in options if option.parser_id == "ocr-document")
    assert not ocr.available
    assert ocr.reason == "OCR parser is not configured yet."
    with pytest.raises(ParserUnavailableError):
        registry.parser_for_selection(
            parser_id="ocr-document",
            document_format="pdf",
            classification="scanned",
        )


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


@pytest.mark.parametrize("classification", ["mixed", "scanned", "image_based", "unknown"])
def test_non_text_legacy_option_includes_quality_warning(classification: str) -> None:
    options = build_default_provider_registry().parser_options(
        document_format="pdf",
        classification=classification,
    )

    legacy = next(option for option in options if option.parser_id == "legacy-pdf-text")
    assert legacy.warning == "Pages without a usable text layer may be missing or empty."
