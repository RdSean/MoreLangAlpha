"""Per-request options for the Datalab conversion.

These travel from the wizard through the job's ``parser_options`` JSONB into
``ParseRequest.options``, so the model has two jobs: validate what an honest
client sends, and degrade rather than explode when a stored blob predates the
current shape.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.server.documents.providers.datalab_options import DatalabConversionOptions


class TestDefaults:
    def test_match_the_pipeline_this_replaced(self) -> None:
        options = DatalabConversionOptions()
        assert options.mode == "balanced"
        assert options.paginate is True

    def test_image_extraction_is_on_by_default(self) -> None:
        """Extraction earns its default now that the pictures can be shown.

        It was off while the markdown's references had nothing behind them:
        extracting only produced a document with broken pictures. Images are
        published as artifacts and resolved at render time, so a picture-heavy
        worksheet no longer needs the user to know to ask for its figures.
        """
        assert DatalabConversionOptions().disable_image_extraction is False

    def test_output_format_is_fixed_to_markdown(self) -> None:
        # A literal rather than an omitted field, so the constraint is visible
        # in the model instead of only in the provider's implementation.
        assert DatalabConversionOptions().output_format == "markdown"

    def test_image_captions_are_off_by_default(self) -> None:
        """Datalab captions images by default; we ask it not to.

        Captions are model-written prose about a picture, and the picture here
        is usually a scanned worksheet — the caption competes with the text we
        actually want, so the wizard ships the switch on. The flag is negative,
        which is why the default is ``True`` and the checkbox reads "skip".
        """
        assert DatalabConversionOptions().disable_image_captions is True


class TestValidation:
    def test_accepts_a_page_range(self) -> None:
        assert DatalabConversionOptions(page_range="0-5,10").page_range == "0-5,10"

    def test_rejects_an_unknown_mode(self) -> None:
        with pytest.raises(ValidationError):
            DatalabConversionOptions(mode="turbo")

    def test_rejects_page_range_together_with_max_pages(self) -> None:
        # Datalab documents these as mutually exclusive; catching it here gives
        # the user a validation error instead of a failed parse job.
        with pytest.raises(ValidationError):
            DatalabConversionOptions(page_range="0-5", max_pages=10)

    @pytest.mark.parametrize("page_range", ["", "abc", "1-", "-3", "1--2", "0-5;7"])
    def test_rejects_a_malformed_page_range(self, page_range: str) -> None:
        with pytest.raises(ValidationError):
            DatalabConversionOptions(page_range=page_range)

    def test_rejects_a_non_positive_max_pages(self) -> None:
        with pytest.raises(ValidationError):
            DatalabConversionOptions(max_pages=0)


class TestFromStored:
    """Reading a blob a possibly older client wrote."""

    def test_an_empty_blob_yields_defaults(self) -> None:
        assert DatalabConversionOptions.from_stored({}) == DatalabConversionOptions()

    def test_known_keys_are_applied(self) -> None:
        options = DatalabConversionOptions.from_stored(
            {"mode": "accurate", "page_range": "0-5"}
        )
        assert options.mode == "accurate"
        assert options.page_range == "0-5"

    def test_unknown_keys_are_ignored(self) -> None:
        """A newer wizard must not break an older server."""
        options = DatalabConversionOptions.from_stored({"invented_later": True})
        assert options == DatalabConversionOptions()

    def test_an_invalid_blob_degrades_instead_of_failing_the_job(self) -> None:
        """Stale options are not worth failing a conversion over.

        The document still gets parsed, on defaults, rather than the job dying
        because a field's allowed values changed between releases.
        """
        options = DatalabConversionOptions.from_stored(
            {"mode": "turbo", "page_range": "nonsense"}
        )
        assert options == DatalabConversionOptions()

    def test_a_partially_valid_blob_keeps_nothing_rather_than_guessing(self) -> None:
        """All-or-nothing, so a rejected blob cannot half-apply.

        Half-applying is the dangerous outcome: `mode` applied while
        `page_range` silently vanished would parse a different set of pages than
        the user asked for, and nothing would say so.
        """
        options = DatalabConversionOptions.from_stored(
            {"mode": "accurate", "page_range": "nonsense"}
        )
        assert options == DatalabConversionOptions()
