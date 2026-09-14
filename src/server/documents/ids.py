"""Compact public identifiers for document-domain entities."""

from __future__ import annotations

import secrets
import string
from collections.abc import Callable
from typing import Literal


PublicIdKind = Literal[
    "dataset",
    "document",
    "inspection",
    "job",
    "artifact",
    "tag",
    "usage",
]

_PREFIXES: dict[PublicIdKind, str] = {
    "dataset": "dts",
    "document": "doc",
    "inspection": "ins",
    "job": "job",
    "artifact": "art",
    "tag": "tag",
    "usage": "use",
}
_BASE62 = string.digits + string.ascii_uppercase + string.ascii_lowercase
_SUFFIX_LENGTH = 12


class PublicIdCollisionError(RuntimeError):
    """Raised when a bounded public-ID allocation cannot find a free value."""


def new_public_id(kind: PublicIdKind | str) -> str:
    """Return one opaque ID with a stable three-letter type prefix."""
    try:
        prefix = _PREFIXES[kind]  # type: ignore[index]
    except KeyError as exc:
        raise ValueError(f"Unsupported public ID kind: {kind!r}") from exc

    suffix = "".join(secrets.choice(_BASE62) for _ in range(_SUFFIX_LENGTH))
    return f"{prefix}-{suffix}"


def new_unique_public_id(
    kind: PublicIdKind,
    *,
    is_taken: Callable[[str], bool],
    max_attempts: int = 8,
) -> str:
    """Return an unused ID according to a caller-owned uniqueness check."""
    if max_attempts <= 0:
        raise ValueError("max_attempts must be positive")

    for _ in range(max_attempts):
        candidate = new_public_id(kind)
        if not is_taken(candidate):
            return candidate

    raise PublicIdCollisionError(
        f"Could not allocate a unique {kind} ID after {max_attempts} attempts"
    )
