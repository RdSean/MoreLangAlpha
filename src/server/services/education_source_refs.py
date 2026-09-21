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


_WHITESPACE = re.compile(r"\s+")
_PAGE_MARKER = re.compile(r"^\{(\d+)\}-+$", re.MULTILINE)


def locate_page_markers(markdown: str) -> list[tuple[int, int]]:
    """Return (start, end) offsets of the extraction's page delimiters."""
    return [(match.start(), match.end()) for match in _PAGE_MARKER.finditer(markdown)]


def surrounding_section_range(
    markdown: str,
    start: int,
    end: int,
    *,
    pad: int = 16,
    max_chars: int | None = None,
) -> tuple[int, int]:
    """Expand a located span to the extraction page (or heading) containing it.

    Markdown headings are the primary boundary because they match the book's
    own sectioning; ``{n}-----`` PDF page delimiters are the fallback for
    extracts that lost their heading structure.
    """
    if not markdown:
        return start, end
    headings = [
        (match.start(), len(match.group(1)))
        for match in re.finditer(r"^(#{1,6})\s+\S", markdown, re.MULTILINE)
    ]
    previous = [item for item in headings if item[0] <= start]
    section_start = 0
    section_end = len(markdown)
    if previous:
        heading_start, level = previous[-1]
        following = [
            item[0] for item in headings if item[0] >= end and item[1] <= level
        ]
        # A heading is a complete section opener; do not pad backwards past it
        # or the preview starts mid-way through the previous section.
        section_start = heading_start
        if following:
            # Keep the next section's heading line readable as the boundary
            # marker instead of cutting it off mid-title.
            line_end = markdown.find("\n", following[0]) if following else -1
            section_end = line_end if line_end != -1 else following[0]
        else:
            section_end = len(markdown)
    else:
        markers = locate_page_markers(markdown)
        previous_markers = [item for item in markers if item[1] <= start]
        following_markers = [item for item in markers if item[1] >= end]
        section_start = (
            previous_markers[-1][1] if previous_markers else max(0, start - pad)
        )
        section_end = (
            following_markers[0][0] if following_markers else len(markdown)
        )
        section_end = min(len(markdown), max(section_end, end) + pad)
    if max_chars is None or section_end - section_start <= max_chars:
        return section_start, section_end
    # Oversized section: prefer reading it from the start, but never let the
    # located quote fall outside the window.
    window_start = section_start
    window_end = min(section_end, window_start + max_chars)
    if start < window_start or end > window_end:
        window_start = max(section_start, start - 400)
        window_end = min(section_end, window_start + max_chars)
    return window_start, window_end


def locate_quote_approximately(
    markdown: str, quote: str, *, window_pad: int = 8
) -> tuple[int, int] | None:
    """Locate a quote despite Markdown markers and PDF line wrapping.

    Offsets are approximate: the quote's leading words are matched with
    whitespace tolerated, then a window the size of the quote (plus a small
    pad) is returned. Used as a best-effort fallback when exact and
    whitespace-normalized resolution both fail.
    """
    words = [word for word in _WHITESPACE.split(quote) if word]
    if not words or not markdown:
        return None
    for length in (6, 5, 4, 3, 2, 1):
        prefix = " ".join(words[:length])
        pattern = re.compile(
            r"\s+".join(re.escape(word) for word in prefix.split()),
            re.IGNORECASE,
        )
        match = pattern.search(markdown)
        if match:
            end = min(len(markdown), match.start() + len(quote) + window_pad)
            return match.start(), end
    return None


def resolve_quote_range(
    markdown: str,
    quote: str,
    *,
    source_id: str | None = None,
    default_slice: int = 6_000,
) -> dict[str, Any]:
    """Resolve a quote to a usable range, never failing the caller.

    Tries the structured resolver first, then an approximate locator that
    tolerates Markdown markers and line wrapping, then falls back to a bounded
    leading slice of the source so downstream generation always has content.
    """
    try:
        resolved = resolve_source_ref(
            sources={str(source_id): markdown} if source_id else {"": markdown},
            source_id=str(source_id) if source_id else None,
            quote=quote,
        )
    except SourceReferenceResolutionError:
        resolved = {}
    start = resolved.get("start")
    end = resolved.get("end")
    if isinstance(start, int) and isinstance(end, int) and 0 <= start < end <= len(markdown):
        return {
            "start": start,
            "end": end,
            "resolution_status": str(resolved.get("resolution_status") or "resolved"),
        }
    if quote.strip():
        located = locate_quote_approximately(markdown, quote)
        if located:
            return {
                "start": located[0],
                "end": located[1],
                "resolution_status": "approximate",
            }
    end = min(len(markdown), max(1, default_slice))
    return {
        "start": 0,
        "end": end,
        "resolution_status": "document_prefix",
    }
