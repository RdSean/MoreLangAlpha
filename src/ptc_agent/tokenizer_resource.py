"""Verified local resource management for LangAlpha's tiktoken vocabulary."""

from __future__ import annotations

import hashlib
import os
import shutil
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal
from urllib.error import URLError
from urllib.request import Request, urlopen

CL100K_BASE_ENCODING = "cl100k_base"
CL100K_BASE_URL = (
    "https://openaipublic.blob.core.windows.net/encodings/"
    "cl100k_base.tiktoken"
)
CL100K_BASE_SHA256 = (
    "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
)
# tiktoken uses SHA-1(url) as the filename inside TIKTOKEN_CACHE_DIR.
CL100K_BASE_CACHE_KEY = "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"
BUNDLED_VOCABULARY_PATH = (
    Path(__file__).resolve().parent
    / "resources"
    / "tiktoken"
    / "cl100k_base.tiktoken"
)

_DOWNLOAD_TIMEOUT_SECONDS = 20
_MAX_VOCABULARY_BYTES = 4 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class TokenizerResourceStatus:
    """Safe runtime state exposed to callers and the settings API."""

    encoding: str
    status: Literal["ready", "approximate"]
    exact: bool
    error_code: str | None = None

    def to_public_dict(self) -> dict[str, str | bool | None]:
        return asdict(self)


def _ready_status() -> TokenizerResourceStatus:
    return TokenizerResourceStatus(
        encoding=CL100K_BASE_ENCODING,
        status="ready",
        exact=True,
    )


def _approximate_status(error_code: str) -> TokenizerResourceStatus:
    return TokenizerResourceStatus(
        encoding=CL100K_BASE_ENCODING,
        status="approximate",
        exact=False,
        error_code=error_code,
    )


def resolve_tiktoken_cache_dir() -> Path:
    """Return the explicit cache override or LangAlpha's stable local default."""
    configured = os.getenv("TIKTOKEN_CACHE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    repository_root = Path(__file__).resolve().parents[2]
    return repository_root / "var" / "cache" / "tiktoken"


def _cache_vocabulary_path() -> Path:
    return resolve_tiktoken_cache_dir() / CL100K_BASE_CACHE_KEY


def _matches_expected_hash(path: Path) -> bool:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(128 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest() == CL100K_BASE_SHA256
    except OSError:
        return False


def _temporary_path(cache_path: Path) -> Path:
    return cache_path.with_name(f".{cache_path.name}.{uuid.uuid4().hex}.tmp")


def _install_bundled_vocabulary(cache_path: Path) -> None:
    temporary_path = _temporary_path(cache_path)
    try:
        shutil.copyfile(BUNDLED_VOCABULARY_PATH, temporary_path)
        if not _matches_expected_hash(temporary_path):
            raise ValueError("bundled vocabulary changed during copy")
        os.replace(temporary_path, cache_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _download_official_vocabulary(destination: Path) -> None:
    request = Request(
        CL100K_BASE_URL,
        headers={"User-Agent": "LangAlpha tokenizer resource manager"},
    )
    with (
        urlopen(request, timeout=_DOWNLOAD_TIMEOUT_SECONDS) as response,
        destination.open("xb") as output,
    ):
        total = 0
        while chunk := response.read(128 * 1024):
            total += len(chunk)
            if total > _MAX_VOCABULARY_BYTES:
                raise ValueError("vocabulary download exceeded size limit")
            output.write(chunk)


def get_tokenizer_resource_status() -> TokenizerResourceStatus:
    """Inspect the verified runtime cache without performing network I/O."""
    if _matches_expected_hash(_cache_vocabulary_path()):
        return _ready_status()
    return _approximate_status("vocabulary_unavailable")


def prepare_tokenizer_resource(
    *,
    allow_download: bool = True,
) -> TokenizerResourceStatus:
    """Prepare a verified cache entry without making tokenizer failure fatal."""
    cache_dir = resolve_tiktoken_cache_dir()
    os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(cache_dir))
    cache_path = cache_dir / CL100K_BASE_CACHE_KEY

    if _matches_expected_hash(cache_path):
        return _ready_status()

    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return _approximate_status("cache_unwritable")

    if _matches_expected_hash(BUNDLED_VOCABULARY_PATH):
        try:
            _install_bundled_vocabulary(cache_path)
        except OSError:
            return _approximate_status("cache_unwritable")
        except ValueError:
            return _approximate_status("vocabulary_hash_mismatch")
        return _ready_status()

    if not allow_download:
        return _approximate_status("vocabulary_unavailable")

    temporary_path = _temporary_path(cache_path)
    try:
        _download_official_vocabulary(temporary_path)
        if not _matches_expected_hash(temporary_path):
            return _approximate_status("vocabulary_hash_mismatch")
        os.replace(temporary_path, cache_path)
        return _ready_status()
    except URLError:
        return _approximate_status("vocabulary_download_failed")
    except PermissionError:
        return _approximate_status("cache_unwritable")
    except (OSError, ValueError):
        return _approximate_status("vocabulary_download_failed")
    finally:
        temporary_path.unlink(missing_ok=True)
