"""Delete derived objects for explicitly selected current or legacy textbooks.

Each prefix must identify one textbook. The script intentionally does not
accept ``education/`` or a household prefix because homework attachments share
that namespace.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.utils.storage import delete_object, list_object_keys


_TEXTBOOK_PREFIX_RE = re.compile(
    r"^education/[0-9A-Za-z][0-9A-Za-z.-]*/"
    r"(?:textbooks/)?[0-9A-Za-z][0-9A-Za-z._-]*/$"
)
_TEXTBOOK_OBJECT_RE = re.compile(
    r"^education/[0-9A-Za-z][0-9A-Za-z.-]*/(?:"
    r"textbooks/[0-9A-Za-z][0-9A-Za-z._-]*/(?:source|materials|supplementary)/"
    r"|[0-9A-Za-z][0-9A-Za-z._-]*/(?:v[0-9]+/|source-bundles/))"
)


class PurgeSafetyError(RuntimeError):
    """An object-store response violated the purge allow-list."""


def _is_textbook_object(key: str) -> bool:
    return bool(_TEXTBOOK_OBJECT_RE.match(key))


def _normalize_prefix(prefix: str) -> str:
    normalized = prefix.rstrip("/") + "/"
    if (
        not _TEXTBOOK_PREFIX_RE.fullmatch(normalized)
        or normalized.split("/")[-2] == "textbooks"
    ):
        raise PurgeSafetyError(
            "Prefix must match education/<household>/textbooks/<textbook>/ "
            "or legacy education/<household>/<textbook>/"
        )
    return normalized


def purge_education_textbook_prefixes(
    *,
    prefixes: Iterable[str],
    apply: bool,
    list_keys: Callable[[str], Iterable[str]],
    delete_key: Callable[[str], bool],
) -> dict[str, int]:
    """Return counts while deleting only allow-listed textbook derived keys."""
    normalized_prefixes = sorted({_normalize_prefix(prefix) for prefix in prefixes})
    if not normalized_prefixes:
        raise PurgeSafetyError("At least one textbook prefix is required")
    keys = [key for prefix in normalized_prefixes for key in list_keys(prefix)]
    selected = [
        key
        for key in keys
        if _is_textbook_object(key)
        and any(key.startswith(prefix) for prefix in normalized_prefixes)
    ]
    skipped = len(keys) - len(selected)
    deleted = 0
    if apply:
        for key in selected:
            if not _is_textbook_object(key):
                raise PurgeSafetyError("Refusing to delete a non-textbook key")
            if not key.startswith("education/"):
                raise PurgeSafetyError("Refusing to delete a key outside education/")
            if not delete_key(key):
                raise PurgeSafetyError(f"Could not delete textbook object: {key}")
            deleted += 1
    return {
        "scanned": len(keys),
        "selected": len(selected),
        "skipped": skipped,
        "deleted": deleted,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--prefix",
        action="append",
        required=True,
        help="Exact education/<household>/textbooks/<textbook>/ prefix (or legacy slug prefix). Repeat for each textbook.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete selected objects. Default is dry-run.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = purge_education_textbook_prefixes(
            prefixes=args.prefix,
            apply=args.apply,
            list_keys=list_object_keys,
            delete_key=delete_object,
        )
    except PurgeSafetyError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    mode = "applied" if args.apply else "dry-run"
    print(
        f"{mode}: scanned={result['scanned']} selected={result['selected']} "
        f"skipped={result['skipped']} deleted={result['deleted']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
