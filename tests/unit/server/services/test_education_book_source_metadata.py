import pytest

from src.server.services.education_book_source_metadata import original_page_count


@pytest.mark.parametrize("value", [None, True, False, "24", 0, -1, 2.5, {}, []])
def test_missing_or_invalid_pages_are_not_fabricated(value):
    assert original_page_count(value, "application/pdf") is None


def test_only_original_pdf_page_count_is_used():
    assert original_page_count(24, "application/pdf; charset=binary") == 24
    assert original_page_count(24, "text/markdown") is None
