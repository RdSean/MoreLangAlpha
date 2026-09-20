"""Best-effort resolution of source quotes into frozen Markdown offsets."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any


class SourceReferenceResolutionError(ValueError):
    """A source reference cannot be represented safely at all."""


def _quoted_whitespace_pattern(quote: str) -> str:
    parts = [part for part in quote.split() if part]
    if not parts:
        raise SourceReferenceResolutionError("Source quote must not be empty")
    return r"\s+".join(re.escape(part) for part in parts)


def resolve_source_ref(
    *,
    sources: Mapping[str, str],
    source_id: str | None,
    quote: str,
    occurrence: int = 1,
) -> dict[str, Any]:
    """Resolve one quote without turning evidence issues into hard failures.

    Exact matches are preferred. Whitespace-normalized matches are accepted
    because Markdown extraction frequently changes line wrapping. Ambiguous
    quotes use the requested occurrence and remain reviewable with a warning.
    """
    if not isinstance(quote, str) or not quote.strip():
        raise SourceReferenceResolutionError("Source quote must be a non-empty string")
    if isinstance(occurrence, bool) or not isinstance(occurrence, int) or occurrence <= 0:
        raise SourceReferenceResolutionError("Source occurrence must be positive")

    warnings: list[str] = []
    normalized_source_id = str(source_id or "").strip()
    selected_source_id = normalized_source_id
    markdown: str | None = None

    if normalized_source_id in sources:
        markdown = sources[normalized_source_id]
    elif len(sources) == 1:
        selected_source_id = next(iter(sources))
        markdown = sources[selected_source_id]
        warnings.append(
            "source_id_defaulted" if not normalized_source_id else "source_id_reassigned"
        )
    else:
        warnings.append("source_id_unresolved")

    if markdown is None:
        warnings.append("source_quote_unresolved")
        return {
            "source_id": selected_source_id or normalized_source_id or None,
            "quote": quote,
            "start": None,
            "end": None,
            "resolution_status": "unresolved",
            "warnings": warnings,
        }

    exact_matches = list(re.finditer(re.escape(quote), markdown))
    if exact_matches:
        selected = exact_matches[min(occurrence, len(exact_matches)) - 1]
        if len(exact_matches) > 1:
            warnings.append("source_quote_ambiguous_first_match_used")
        return {
            "source_id": selected_source_id,
            "quote": quote,
            "start": selected.start(),
            "end": selected.end(),
            "resolution_status": "resolved",
            "warnings": warnings,
        }

    normalized_matches = list(
        re.finditer(_quoted_whitespace_pattern(quote), markdown)
    )
    if normalized_matches:
        selected = normalized_matches[min(occurrence, len(normalized_matches)) - 1]
        if len(normalized_matches) > 1:
            warnings.append("source_quote_ambiguous_first_match_used")
        warnings.append("source_quote_whitespace_normalized")
        return {
            "source_id": selected_source_id,
            "quote": markdown[selected.start() : selected.end()],
            "start": selected.start(),
            "end": selected.end(),
            "resolution_status": "normalized",
            "warnings": warnings,
        }

    warnings.append("source_quote_unresolved")
    return {
        "source_id": selected_source_id,
        "quote": quote,
        "start": None,
        "end": None,
        "resolution_status": "unresolved",
        "warnings": warnings,
    }
