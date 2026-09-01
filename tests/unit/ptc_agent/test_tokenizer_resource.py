from __future__ import annotations

import hashlib
from pathlib import Path


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _configure_test_resource(monkeypatch, tmp_path: Path, payload: bytes):
    from ptc_agent import tokenizer_resource

    cache_dir = tmp_path / "cache"
    bundled_path = tmp_path / "bundled" / "cl100k_base.tiktoken"
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr(tokenizer_resource, "CL100K_BASE_SHA256", _sha256(payload))
    monkeypatch.setattr(
        tokenizer_resource,
        "BUNDLED_VOCABULARY_PATH",
        bundled_path,
    )
    return tokenizer_resource, cache_dir, bundled_path


def test_environment_cache_directory_overrides_repository_default(
    tmp_path: Path,
    monkeypatch,
):
    from ptc_agent.tokenizer_resource import resolve_tiktoken_cache_dir

    configured = tmp_path / "custom-cache"
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(configured))

    assert resolve_tiktoken_cache_dir() == configured


def test_valid_cache_is_reused_without_download(tmp_path: Path, monkeypatch):
    payload = b"verified-cache"
    tokenizer_resource, cache_dir, _ = _configure_test_resource(
        monkeypatch,
        tmp_path,
        payload,
    )
    cache_dir.mkdir(parents=True)
    cache_path = cache_dir / tokenizer_resource.CL100K_BASE_CACHE_KEY
    cache_path.write_bytes(payload)

    def unexpected_download(_destination: Path) -> None:
        raise AssertionError("valid cache must not trigger a download")

    monkeypatch.setattr(
        tokenizer_resource,
        "_download_official_vocabulary",
        unexpected_download,
    )

    status = tokenizer_resource.prepare_tokenizer_resource()

    assert status.exact is True
    assert status.status == "ready"
    assert status.error_code is None
    assert cache_path.read_bytes() == payload


def test_bundled_vocabulary_seeds_missing_cache_atomically(
    tmp_path: Path,
    monkeypatch,
):
    payload = b"verified-bundled-resource"
    tokenizer_resource, cache_dir, bundled_path = _configure_test_resource(
        monkeypatch,
        tmp_path,
        payload,
    )
    bundled_path.parent.mkdir(parents=True)
    bundled_path.write_bytes(payload)

    def unexpected_download(_destination: Path) -> None:
        raise AssertionError("valid bundled resource must not trigger a download")

    monkeypatch.setattr(
        tokenizer_resource,
        "_download_official_vocabulary",
        unexpected_download,
    )

    status = tokenizer_resource.prepare_tokenizer_resource()

    cache_path = cache_dir / tokenizer_resource.CL100K_BASE_CACHE_KEY
    assert status.exact is True
    assert cache_path.read_bytes() == payload
    assert list(cache_dir.glob("*.tmp")) == []


def test_missing_local_vocabulary_downloads_verified_official_copy(
    tmp_path: Path,
    monkeypatch,
):
    payload = b"verified-download"
    tokenizer_resource, cache_dir, _ = _configure_test_resource(
        monkeypatch,
        tmp_path,
        payload,
    )

    def download(destination: Path) -> None:
        destination.write_bytes(payload)

    monkeypatch.setattr(
        tokenizer_resource,
        "_download_official_vocabulary",
        download,
    )

    status = tokenizer_resource.prepare_tokenizer_resource()

    cache_path = cache_dir / tokenizer_resource.CL100K_BASE_CACHE_KEY
    assert status.exact is True
    assert cache_path.read_bytes() == payload
    assert list(cache_dir.glob("*.tmp")) == []


def test_hash_mismatch_returns_approximate_and_leaves_no_cache(
    tmp_path: Path,
    monkeypatch,
):
    expected_payload = b"expected"
    tokenizer_resource, cache_dir, _ = _configure_test_resource(
        monkeypatch,
        tmp_path,
        expected_payload,
    )

    def corrupt_download(destination: Path) -> None:
        destination.write_bytes(b"corrupt")

    monkeypatch.setattr(
        tokenizer_resource,
        "_download_official_vocabulary",
        corrupt_download,
    )

    status = tokenizer_resource.prepare_tokenizer_resource()

    assert status.exact is False
    assert status.status == "approximate"
    assert status.error_code == "vocabulary_hash_mismatch"
    assert not (cache_dir / tokenizer_resource.CL100K_BASE_CACHE_KEY).exists()
    assert list(cache_dir.glob("*.tmp")) == []


def test_public_status_does_not_expose_paths_or_internal_errors(
    tmp_path: Path,
    monkeypatch,
):
    tokenizer_resource, _, _ = _configure_test_resource(
        monkeypatch,
        tmp_path,
        b"missing",
    )

    status = tokenizer_resource.get_tokenizer_resource_status()

    assert status.to_public_dict() == {
        "encoding": "cl100k_base",
        "status": "approximate",
        "exact": False,
        "error_code": "vocabulary_unavailable",
    }
