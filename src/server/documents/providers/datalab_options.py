"""Per-request knobs for the Datalab conversion.

The wizard writes these into the parse job's ``parser_options``; the executor
hands that blob to the provider as ``ParseRequest.options``. So this model is
the boundary in both directions: it validates what an honest client sends, and
it is the thing that decides what a stale blob means.

Kept in its own module rather than in the provider so the wizard's field set and
the validation rules sit in one readable place — and so a future contract
export can describe it without importing a parser.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


DatalabMode = Literal["fast", "balanced", "accurate"]

# "0-5,10,15-20" — the shape Datalab documents. Kept permissive about
# whitespace because humans type it, strict about everything else.
_PAGE_RANGE_RE = re.compile(r"^\d+(?:-\d+)?(?:,\s*\d+(?:-\d+)?)*$")


class DatalabConversionOptions(BaseModel):
    """What the user may tune per conversion.

    Defaults deliberately mirror the pipeline this integration replaced
    (``balanced`` + ``paginate``), so switching from that pipeline to
    ``client.convert()`` does not silently change what a parse produces.
    """

    output_format: Literal["markdown"] = "markdown"
    """Fixed. The document library's primary artifact is markdown, and every
    existing provider writes exactly one such file; exposing html/json would
    mean widening the artifact model, which is separate work."""

    mode: DatalabMode = "balanced"
    paginate: bool = True

    page_range: str | None = None
    max_pages: int | None = Field(default=None, gt=0)
    skip_cache: bool = False

    disable_image_extraction: bool = False
    """Off by default: images are extracted, published and previewed.

    This was ``True`` while the markdown's image references had nothing behind
    them — extracting produced a document whose pictures could not resolve, so
    skipping extraction was the only honest default. Images are now published
    as their own artifacts and the preview resolves the references, which was
    the whole condition for flipping this back.
    """

    disable_image_captions: bool = True
    """On by default, also unlike Datalab's own default.

    A caption is model-written prose about a picture, placed next to the text
    we are trying to extract from a scanned worksheet; it competes with that
    text rather than helping it. The wizard exposes the switch, so asking for
    captions is a deliberate choice rather than something that arrives with
    every conversion.
    """

    token_efficient_markdown: bool = False
    extras: str | None = None

    @model_validator(mode="after")
    def _check_shape(self) -> DatalabConversionOptions:
        if self.page_range is not None:
            if not _PAGE_RANGE_RE.match(self.page_range):
                raise ValueError("page_range must look like '0-5,10,15-20'")
            if self.max_pages is not None:
                raise ValueError("page_range and max_pages are mutually exclusive")
        return self

    @classmethod
    def from_stored(cls, raw: Mapping[str, Any] | None) -> DatalabConversionOptions:
        """Interpret a stored ``parser_options`` blob.

        All-or-nothing on purpose. A blob with one good field and one bad one
        falls back to *defaults entirely*, because half-applying is the quietly
        dangerous outcome: ``mode`` applied while ``page_range`` was dropped
        would convert a different set of pages than the user asked for, and
        nothing downstream would say so. Unknown keys are ignored — that is a
        newer client, not a broken one.
        """
        if not raw:
            return cls()
        try:
            return cls.model_validate(dict(raw))
        except Exception:  # noqa: BLE001 - any validation failure means defaults
            return cls()
