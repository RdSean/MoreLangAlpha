"""Reading-scope validation for the canonical book-to-skill structure."""

import pytest

from src.server.services.education_structure_scope_validation import (
    ScopeValidationError,
    validate_structure_scopes,
)


SOURCE = "\n".join(f"line {number}" for number in range(1, 101)) + "\n"


def _payload(**overrides):
    payload = {
        "format": "langalpha-managed-textbook-structure/v2",
        "units": [
            {
                "unit": 1,
                "theme": "Unit One",
                "line_start": 10,
                "line_end": 60,
                "readings": [
                    {
                        "slot": "reading_a",
                        "title": "Reading A",
                        "line_start": 12,
                        "line_end": 30,
                    },
                    {
                        "slot": "reading_b",
                        "title": "Reading B",
                        "line_start": 31,
                        "line_end": 50,
                    },
                ],
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_scope_validation_accepts_a_well_formed_document():
    scopes = validate_structure_scopes(_payload(), markdown=SOURCE)

    assert [scope["slot"] for scope in scopes] == ["reading_a", "reading_b"]
    assert scopes[0]["char_start"] < scopes[0]["char_end"]
    assert SOURCE[scopes[0]["char_start"] : scopes[0]["char_end"]].startswith(
        "line 12"
    )
    assert SOURCE[scopes[1]["char_start"] : scopes[1]["char_end"]].startswith(
        "line 31"
    )


def test_scope_validation_rejects_readings_that_escape_their_unit():
    payload = _payload()
    payload["units"][0]["readings"][0]["line_start"] = 5

    with pytest.raises(ScopeValidationError, match="escapes its unit range"):
        validate_structure_scopes(payload, markdown=SOURCE)


def test_scope_validation_rejects_overlapping_readings():
    payload = _payload()
    payload["units"][0]["readings"][1]["line_start"] = 25

    with pytest.raises(ScopeValidationError, match="overlaps the previous reading"):
        validate_structure_scopes(payload, markdown=SOURCE)


def test_scope_validation_rejects_ranges_past_the_source():
    payload = _payload()
    payload["units"][0]["line_end"] = 100_000

    with pytest.raises(ScopeValidationError, match="past the end"):
        validate_structure_scopes(payload, markdown=SOURCE)


def test_scope_validation_rejects_an_unknown_slot():
    payload = _payload()
    payload["units"][0]["readings"][0]["slot"] = "reading_c"

    with pytest.raises(ScopeValidationError, match="slot must be one of"):
        validate_structure_scopes(payload, markdown=SOURCE)


def test_scope_validation_rejects_the_legacy_format():
    payload = _payload(format="langalpha-managed-textbook-structure/v1")

    with pytest.raises(ScopeValidationError, match="format must be"):
        validate_structure_scopes(payload, markdown=SOURCE)
