"""Approximate quote location and section expansion."""

from src.server.services import education_source_refs


def test_surrounding_section_uses_headings_and_stops_at_same_level():
    markdown = (
        "# Book\n\n"
        "### BEFORE YOU READ\n\nintro text\n\n"
        "### THE WORLD'S GAME\n\n"
        "passage body that mentions soccer.\n\n"
        "### SOCCER WITHOUT BORDERS\n\n"
        "the next reading\n"
    )
    quote_start = markdown.index("passage body")
    quote_end = quote_start + len("passage body")

    start, end = education_source_refs.surrounding_section_range(
        markdown, quote_start, quote_end
    )

    section = markdown[start:end]
    assert "THE WORLD'S GAME" in section
    assert "passage body that mentions soccer." in section
    assert "SOCCER WITHOUT BORDERS" in section
    assert "BEFORE YOU READ" not in section


def test_surrounding_section_falls_back_to_page_markers():
    markdown = (
        "{1}----\n\nfirst page\n\n"
        "{2}----\n\nsecond page has the quote here\n\n"
        "{3}----\n\nthird page\n"
    )
    quote_start = markdown.index("quote here")
    quote_end = quote_start + len("quote here")

    start, end = education_source_refs.surrounding_section_range(
        markdown, quote_start, quote_end
    )

    section = markdown[start:end]
    assert "second page has the quote here" in section
    assert "first page" not in section


def test_surrounding_section_caps_oversized_sections_around_the_quote():
    markdown = "# Huge\n\n" + ("x" * 5_000) + "\n\nquote anchor\n\n" + ("y" * 5_000)
    quote_start = markdown.index("quote anchor")

    start, end = education_source_refs.surrounding_section_range(
        markdown, quote_start, quote_start + len("quote anchor"), max_chars=2_000
    )

    assert end - start <= 2_000
    assert start <= quote_start < quote_start + len("quote anchor") <= end
