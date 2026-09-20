import pytest

from src.server.services.education_book_assets import (
    BOOK_ASSET_FORMAT,
    BookAssetValidationError,
    expected_book_asset_files,
    validate_book_asset_content,
    validate_book_asset_manifest,
)


def test_accepts_safe_book_asset_manifest() -> None:
    manifest = validate_book_asset_manifest(
        {
            "format": BOOK_ASSET_FORMAT,
            "chapter_files": ["chapters/ch01-overview.md"],
            "support_files": ["glossary.md", "cheatsheet.md"],
        }
    )

    assert manifest["chapter_files"] == ["chapters/ch01-overview.md"]
    assert manifest["support_files"] == ["cheatsheet.md", "glossary.md"]


def test_builds_hashes_for_downloaded_assets() -> None:
    manifest = validate_book_asset_manifest(
        {
            "format": BOOK_ASSET_FORMAT,
            "chapter_files": ["chapters/ch01-overview.md"],
        }
    )

    validated = validate_book_asset_content(
        manifest,
        {"chapters/ch01-overview.md": b"# Chapter 1\n"},
    )

    assert validated["files"][0]["path"] == "chapters/ch01-overview.md"
    assert len(validated["files"][0]["sha256"]) == 64


@pytest.mark.parametrize(
    "chapter_file",
    [
        "../escape.md",
        "/absolute.md",
        "chapters/../escape.md",
        "chapters/ch01-overview.txt",
    ],
)
def test_rejects_unsafe_chapter_paths(chapter_file: str) -> None:
    with pytest.raises(BookAssetValidationError):
        validate_book_asset_manifest(
            {
                "format": BOOK_ASSET_FORMAT,
                "chapter_files": [chapter_file],
            }
        )


def test_rejects_missing_asset_content() -> None:
    manifest = validate_book_asset_manifest(
        {
            "format": BOOK_ASSET_FORMAT,
            "chapter_files": ["chapters/ch01-overview.md"],
        }
    )

    with pytest.raises(BookAssetValidationError):
        validate_book_asset_content(manifest, {})


def test_expected_files_keep_manifest_order() -> None:
    manifest = validate_book_asset_manifest(
        {
            "format": BOOK_ASSET_FORMAT,
            "chapter_files": ["chapters/ch02-b.md", "chapters/ch01-a.md"],
            "support_files": ["glossary.md"],
        }
    )

    assert expected_book_asset_files(manifest) == (
        "chapters/ch01-a.md",
        "chapters/ch02-b.md",
        "glossary.md",
    )
