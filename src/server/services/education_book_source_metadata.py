"""Original document metadata suitable for the textbook workbench."""

from typing import Any


def original_page_count(value: Any, media_type: str) -> int | None:
    if media_type.split(";", 1)[0].strip().lower() != "application/pdf":
        return None
    return value if type(value) is int and value > 0 else None
