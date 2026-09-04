"""Tests for src/utils/storage/s3_compatible.py timeout config."""

from __future__ import annotations

import importlib
from unittest.mock import MagicMock, patch

import pytest


def _reload_module():
    """Reimport the module so env-var-derived class attributes refresh."""
    import src.utils.storage.s3_compatible as mod
    importlib.reload(mod)
    return mod


def test_default_timeouts_applied_to_boto3_config():
    mod = _reload_module()
    mod._reset_client_for_test()
    captured: dict = {}

    def fake_client(*_args, **kwargs):
        captured["config"] = kwargs.get("config")
        return object()

    with patch.object(mod.boto3, "client", side_effect=fake_client):
        mod._get_client()

    cfg = captured["config"]
    assert cfg.connect_timeout == 5
    assert cfg.read_timeout == 30


def test_env_overrides_timeouts(monkeypatch):
    monkeypatch.setenv("STORAGE_CONNECT_TIMEOUT_S", "2")
    monkeypatch.setenv("STORAGE_READ_TIMEOUT_S", "11")
    mod = _reload_module()
    mod._reset_client_for_test()
    captured: dict = {}

    def fake_client(*_args, **kwargs):
        captured["config"] = kwargs.get("config")
        return object()

    with patch.object(mod.boto3, "client", side_effect=fake_client):
        mod._get_client()

    cfg = captured["config"]
    assert cfg.connect_timeout == 2
    assert cfg.read_timeout == 11


def test_default_addressing_style_is_virtual(monkeypatch):
    """Default addressing is virtual — most cloud S3-compatible providers need it,
    and it avoids boto3's path-style default doubling keys against the endpoint."""
    monkeypatch.delenv("STORAGE_ADDRESSING_STYLE", raising=False)
    mod = _reload_module()
    mod._reset_client_for_test()
    captured: dict = {}

    def fake_client(*_args, **kwargs):
        captured["config"] = kwargs.get("config")
        return object()

    with patch.object(mod.boto3, "client", side_effect=fake_client):
        mod._get_client()

    assert captured["config"].s3 == {"addressing_style": "virtual"}


def test_addressing_style_env_override(monkeypatch):
    """STORAGE_ADDRESSING_STYLE=path is honored (e.g. MinIO / path-only backends)."""
    monkeypatch.setenv("STORAGE_ADDRESSING_STYLE", "path")
    mod = _reload_module()
    mod._reset_client_for_test()
    captured: dict = {}

    def fake_client(*_args, **kwargs):
        captured["config"] = kwargs.get("config")
        return object()

    with patch.object(mod.boto3, "client", side_effect=fake_client):
        mod._get_client()

    assert captured["config"].s3 == {"addressing_style": "path"}


def test_addressing_style_trims_and_rejects_invalid(monkeypatch):
    """Whitespace is stripped; unrecognized values fall back to virtual."""

    def addressing_for(value):
        monkeypatch.setenv("STORAGE_ADDRESSING_STYLE", value)
        mod = _reload_module()
        mod._reset_client_for_test()
        captured: dict = {}

        def fake_client(*_args, **kwargs):
            captured["config"] = kwargs.get("config")
            return object()

        with patch.object(mod.boto3, "client", side_effect=fake_client):
            mod._get_client()
        return captured["config"].s3

    assert addressing_for("  path  ") == {"addressing_style": "path"}
    assert addressing_for("bogus") == {"addressing_style": "virtual"}


# --- E2E timeout → upload error mapping ----------------------------------
# The Config(...) wiring above is necessary but not sufficient. These tests
# go through the real upload_bytes() path so we verify both halves:
# 1. boto's ConnectTimeoutError / ReadTimeoutError get caught (they're
#    botocore Exception subclasses, so the bare `except Exception:` in
#    upload_bytes returns False instead of letting the exception escape).
# 2. False from upload_bytes maps to MemoBinaryUploadError at the
#    memo_binary_storage boundary, which the route then turns into 502.


def _patch_put_object_to_raise(mod, exc):
    """Wire boto3.client().put_object to raise the given exception."""
    from unittest.mock import MagicMock

    fake_client = MagicMock()
    fake_client.put_object.side_effect = exc
    mod._reset_client_for_test()
    return patch.object(mod.boto3, "client", return_value=fake_client)


def test_upload_bytes_returns_false_on_connect_timeout():
    """Boto ConnectTimeoutError is caught inside upload_bytes (returns False)."""
    from botocore.exceptions import ConnectTimeoutError

    mod = _reload_module()
    err = ConnectTimeoutError(endpoint_url="https://r2.example/")
    with _patch_put_object_to_raise(mod, err):
        # Force a configured state so upload_bytes doesn't short-circuit.
        with patch.object(mod.StorageConfig, "BUCKET_NAME", "test-bucket"):
            assert mod.upload_bytes("memo/u1/x.pdf", b"x", "application/pdf") is False


def test_upload_bytes_returns_false_on_read_timeout():
    """Boto ReadTimeoutError is caught inside upload_bytes (returns False)."""
    from botocore.exceptions import ReadTimeoutError

    mod = _reload_module()
    err = ReadTimeoutError(endpoint_url="https://r2.example/")
    with _patch_put_object_to_raise(mod, err):
        with patch.object(mod.StorageConfig, "BUCKET_NAME", "test-bucket"):
            assert mod.upload_bytes("memo/u1/x.pdf", b"x", "application/pdf") is False


@pytest.mark.asyncio
async def test_store_binary_raises_upload_error_when_put_times_out(monkeypatch):
    """A timing-out PUT goes upload_bytes→False→MemoBinaryUploadError."""
    from src.server.services import memo_binary_storage

    def fake_upload(*_a, **_k):  # mimics upload_bytes's catch-and-return-False
        return False

    monkeypatch.setattr(memo_binary_storage, "is_configured", lambda: True)
    monkeypatch.setattr(memo_binary_storage, "_storage_upload_bytes", fake_upload)
    with pytest.raises(memo_binary_storage.MemoBinaryUploadError):
        await memo_binary_storage.store_binary(
            user_id="u1", content=b"%PDF-1.4 x", content_type="application/pdf",
        )


def test_upload_file_accepts_explicit_cap_larger_than_global_default(
    tmp_path,
    monkeypatch,
):
    mod = _reload_module()
    source = tmp_path / "source.pdf"
    source.write_bytes(b"%PDF-1.4")
    client = MagicMock()

    monkeypatch.setattr(mod.StorageConfig, "MAX_UPLOAD_SIZE", 1)
    monkeypatch.setattr(mod, "_get_client", lambda: client)

    assert mod.upload_file(
        "documents/doc-A1b2C3d4E5f6/source",
        str(source),
        "application/pdf",
        max_bytes=source.stat().st_size,
    )
    client.put_object.assert_called_once()


class _StreamingBody:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0
        self.read_sizes: list[int] = []
        self.closed = False

    def read(self, size: int) -> bytes:
        self.read_sizes.append(size)
        chunk = self._data[self._offset:self._offset + size]
        self._offset += len(chunk)
        return chunk

    def close(self) -> None:
        self.closed = True


def test_download_to_file_streams_sized_chunks(tmp_path, monkeypatch):
    mod = _reload_module()
    body = _StreamingBody(b"abcdef")
    client = MagicMock()
    client.get_object.return_value = {"Body": body}
    monkeypatch.setattr(mod, "_get_client", lambda: client)
    destination = tmp_path / "download.bin"

    assert mod.download_to_file(
        "documents/doc-A1b2C3d4E5f6/source",
        destination,
        max_bytes=6,
    ) == 6
    assert destination.read_bytes() == b"abcdef"
    assert body.read_sizes
    assert all(size > 0 for size in body.read_sizes)
    assert body.closed


def test_download_to_file_stops_before_limit_is_exceeded(tmp_path, monkeypatch):
    mod = _reload_module()
    body = _StreamingBody(b"abcdef")
    client = MagicMock()
    client.get_object.return_value = {"Body": body}
    monkeypatch.setattr(mod, "_get_client", lambda: client)
    destination = tmp_path / "download.bin"

    with pytest.raises(ValueError, match="maximum size"):
        mod.download_to_file(
            "documents/doc-A1b2C3d4E5f6/source",
            destination,
            max_bytes=5,
        )

    assert not destination.exists()
    assert body.read_sizes
    assert all(size > 0 for size in body.read_sizes)
    assert body.closed


def test_presigned_download_uses_private_bucket_and_content_disposition(
    monkeypatch,
):
    mod = _reload_module()
    client = MagicMock()
    client.generate_presigned_url.return_value = "https://storage.example/signed"
    monkeypatch.setattr(mod.StorageConfig, "BUCKET_NAME", "private-documents")
    monkeypatch.setattr(mod, "_get_client", lambda: client)

    result = mod.create_presigned_download_url(
        "documents/doc-A1b2C3d4E5f6/artifacts/job-A1b2C3d4E5f6/document.md",
        expires_seconds=300,
        download_name="教材.md",
    )

    assert result == "https://storage.example/signed"
    _, kwargs = client.generate_presigned_url.call_args
    assert kwargs["ExpiresIn"] == 300
    assert kwargs["Params"]["Bucket"] == "private-documents"
    assert kwargs["Params"]["Key"].startswith("documents/")
    assert "ResponseContentDisposition" in kwargs["Params"]
