"""Read original files for household parents and assigned textbook students."""

import re

from src.server.database.education_books import get_managed_source_for_user
from src.server.documents.contracts import DocumentDomainError
from src.server.documents.library import DocumentLibraryService, SourceDownload
from src.server.documents.storage import S3CompatibleDocumentStore
from src.server.services.education_textbook_snapshot_reads import (
    TextbookSnapshotReadError,
    read_snapshot_artifact_bytes,
)
from src.server.services.education_textbooks import (
    TextbookNotFoundError,
    TextbookProcessingError,
)


def pdf_page_for_line(text: str, *, parser_id: str, start_line: int) -> int | None:
    lines = text.splitlines()
    if not 1 <= start_line <= len(lines):
        return None
    if parser_id == "datalab-online":
        pattern = re.compile(r"^\s*\{(\d+)\}-{3,}\s*$")
        offset = 1
    elif parser_id == "legacy-pdf-text":
        pattern = re.compile(r"^--- Page (\d+) ---$")
        offset = 0
    else:
        return None
    page = None
    previous = 0
    fence: str | None = None
    for line_number, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if stripped.startswith(("```", "~~~")):
            marker = stripped[:3]
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            continue
        if fence is not None:
            continue
        match = pattern.fullmatch(line)
        if not match:
            continue
        current = int(match[1]) + offset
        if current <= previous:
            return None
        previous = current
        if line_number <= start_line:
            page = current
    return page


async def open_book_original(
    *,
    user_id: str,
    textbook_id: str,
    library: DocumentLibraryService | None = None,
) -> SourceDownload:
    row = await get_managed_source_for_user(user_id=user_id, textbook_id=textbook_id)
    if row is None:
        raise TextbookNotFoundError("Textbook not found")
    if not row.get("document_id") or not row.get("source_owner_user_id"):
        raise TextbookNotFoundError("Original file not found")
    library = library or DocumentLibraryService(
        object_store=S3CompatibleDocumentStore()
    )
    try:
        download = await library.open_source_download(
            owner_user_id=str(row["source_owner_user_id"]),
            document_id=str(row["document_id"]),
        )
    except DocumentDomainError as exc:
        raise TextbookProcessingError("Original file is unavailable") from exc
    if download is None:
        raise TextbookNotFoundError("Original file not found")
    return download


async def get_book_original_location(
    *, user_id: str, textbook_id: str, start_line: int
) -> dict[str, int | None]:
    source = await get_managed_source_for_user(user_id=user_id, textbook_id=textbook_id)
    if source is None:
        raise TextbookNotFoundError("Textbook not found")
    if source.get("source_status", "ready") != "ready":
        return {"page": None}
    prefix = str(source["source_snapshot_prefix"])
    key = str(source["source_markdown_key"])
    if not key.startswith(prefix):
        return {"page": None}
    try:
        content, _ = await read_snapshot_artifact_bytes(
            snapshot_prefix=prefix,
            relative_path=key.removeprefix(prefix),
            expected_sha256=str(source["source_content_sha256"]),
            max_bytes=int(source["source_size_bytes"]),
        )
        page = pdf_page_for_line(
            content.decode("utf-8"),
            parser_id=str(source.get("parser_id") or ""),
            start_line=start_line,
        )
    except (TextbookSnapshotReadError, UnicodeDecodeError):
        return {"page": None}
    page_count = source.get("page_count")
    if isinstance(page_count, int) and page is not None and page > page_count:
        page = None
    return {"page": page}
