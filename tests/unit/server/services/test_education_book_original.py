from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.server.services import education_book_original as original
from src.server.services.education_textbooks import TextbookNotFoundError
from src.server.services.education_textbook_snapshot_reads import (
    TextbookSnapshotReadError,
)


@pytest.mark.parametrize(
    "parser,text,line,page",
    [
        ("datalab-online", "{0}----\ncover\n{11}----\nchapter\n{14}----\nend", 4, 12),
        ("datalab-online", "{0}----\ncover\n{11}----\nchapter", 1, 1),
        ("datalab-online", "preface\n{11}----\nchapter", 1, None),
        ("datalab-online", "{11}----\nchapter\n{10}----\nwrong", 4, None),
        ("datalab-online", "{11}----\nchapter\n{11}----\nwrong", 2, None),
        ("datalab-online", "{11}----\n```\n{12}----\n```\nbody", 5, 12),
        ("legacy-pdf-text", "--- Page 12 ---\nchapter\n--- Page 15 ---\nend", 2, 12),
        ("unknown", "{11}----\nchapter", 2, None),
        ("datalab-online", "no markers", 1, None),
        ("datalab-online", "{11}----\nchapter", 3, None),
    ],
)
def test_pdf_page_uses_parser_coordinates_and_start_line(parser, text, line, page):
    assert original.pdf_page_for_line(text, parser_id=parser, start_line=line) == page


@pytest.mark.asyncio
async def test_original_checks_textbook_parent_before_opening_library(monkeypatch):
    monkeypatch.setattr(
        original, "get_managed_textbook_for_parent", AsyncMock(return_value=None)
    )
    library = SimpleNamespace(open_source_download=AsyncMock())
    with pytest.raises(TextbookNotFoundError):
        await original.open_book_original(
            parent_user_id="student", textbook_id="book", library=library
        )
    library.open_source_download.assert_not_awaited()


@pytest.mark.asyncio
async def test_original_reuses_exact_document_and_uploader_after_household_gate(
    monkeypatch,
):
    monkeypatch.setattr(
        original,
        "get_managed_textbook_for_parent",
        AsyncMock(
            return_value={
                "document_id": "doc-book",
                "source_owner_user_id": "uploading-parent",
            }
        ),
    )
    download = object()
    library = SimpleNamespace(open_source_download=AsyncMock(return_value=download))
    assert (
        await original.open_book_original(
            parent_user_id="other-parent", textbook_id="book", library=library
        )
        is download
    )
    library.open_source_download.assert_awaited_once_with(
        owner_user_id="uploading-parent", document_id="doc-book"
    )


@pytest.mark.asyncio
async def test_original_missing_document_has_clear_not_found(monkeypatch):
    monkeypatch.setattr(
        original,
        "get_managed_textbook_for_parent",
        AsyncMock(
            return_value={
                "document_id": "doc-book",
                "source_owner_user_id": "parent",
            }
        ),
    )
    with pytest.raises(TextbookNotFoundError):
        await original.open_book_original(
            parent_user_id="parent",
            textbook_id="book",
            library=SimpleNamespace(open_source_download=AsyncMock(return_value=None)),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", [False, True])
async def test_location_uses_frozen_text_and_unknown_does_not_block_original(
    monkeypatch, missing
):
    monkeypatch.setattr(
        original,
        "get_managed_textbook_for_parent",
        AsyncMock(return_value={"parser_id": "datalab-online"}),
    )
    monkeypatch.setattr(
        original,
        "get_managed_source_for_user",
        AsyncMock(
            return_value={
                "source_status": "ready",
                "source_snapshot_prefix": "education/book/source/",
                "source_markdown_key": "education/book/source/artifacts/book.md",
                "source_content_sha256": "a" * 64,
                "source_size_bytes": 100,
            }
        ),
    )
    read = AsyncMock(
        return_value=(b"{0}----\ncover\n{11}----\nchapter", "key"),
        side_effect=TextbookSnapshotReadError("missing") if missing else None,
    )
    monkeypatch.setattr(original, "read_snapshot_artifact_bytes", read)
    assert await original.get_book_original_location(
        parent_user_id="parent", textbook_id="book", start_line=4
    ) == {"page": None if missing else 12}
    assert read.await_args.kwargs["expected_sha256"] == "a" * 64
