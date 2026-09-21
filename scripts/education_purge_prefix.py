"""Delete only versioned textbook objects from the configured object store.

The script intentionally does not purge the whole ``education/`` prefix:
homework attachments share that prefix. It targets only textbook content
versions (``education/<household>/<textbook>/v<N>/...``) and textbook source
bundles.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Callable, Iterable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.utils.storage import delete_object, list_object_keys


_TEXTBOOK_OBJECT_RE = re.compile(
    r"^education/[^/]+/(?:[^/]+/v[0-9]+/|[^/]+/source-bundles/)"
)


class PurgeSafetyError(RuntimeError):
    """An object-store response violated the purge allow-list."""


def _is_textbook_object(key: str) -> bool:
    return bool(_TEXTBOOK_OBJECT_RE.match(key))


def purge_education_textbook_objects(
    *,
    apply: bool,
    list_keys: Callable[[str], Iterable[str]],
    delete_key: Callable[[str], bool],
) -> dict[str, int]:
    """Return counts while deleting only canonical textbook object keys."""
    keys = list(list_keys("education/"))
    selected = [key for key in keys if _is_textbook_object(key)]
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
        "--apply",
        action="store_true",
        help="Delete selected objects. Default is dry-run.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        result = purge_education_textbook_objects(
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
