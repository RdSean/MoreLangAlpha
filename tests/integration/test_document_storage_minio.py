"""Opt-in real MinIO coverage for document sources and artifact bundles."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import pytest


pytestmark = pytest.mark.integration


def _require_document_minio() -> None:
    if os.getenv("RUN_DOCUMENT_MINIO_TESTS") != "1":
        pytest.skip("set RUN_DOCUMENT_MINIO_TESTS=1 for the configured development MinIO")

    from src.utils.storage.s3_compatible import StorageConfig

    endpoint = StorageConfig.ENDPOINT_URL
    host = urlparse(endpoint or "").hostname
    if host not in {"127.0.0.1", "localhost", "minio", "192.168.3.164"}:
        pytest.fail("document storage integration tests require an approved development MinIO")
    if not all(
        (
            StorageConfig.BUCKET_NAME,
            StorageConfig.ACCESS_KEY_ID,
            StorageConfig.SECRET_ACCESS_KEY,
        )
    ):
        pytest.fail("development MinIO credentials are not configured")


def test_minio_round_trips_document_source_and_artifact_bundle(tmp_path: Path) -> None:
    _require_document_minio()
    from src.utils.storage.s3_compatible import (
        delete_object,
        download_to_file,
        open_download_stream,
        upload_file,
    )

    key_root = f"documents/test-{uuid4().hex}/"
    payloads = {
        "source.pdf": b"%PDF-1.7\nreal document source\n%%EOF\n",
        "artifacts/document.md": b"# Parsed document\n",
        "artifacts/document.json": b'{"title":"Parsed document"}\n',
        "artifacts/images/page-1.png": b"\x89PNG\r\n\x1a\nfixture",
        "artifacts/manifest.json": b'{"artifacts":4}\n',
    }
    content_types = {
        "source.pdf": "application/pdf",
        "artifacts/document.md": "text/markdown",
        "artifacts/document.json": "application/json",
        "artifacts/images/page-1.png": "image/png",
        "artifacts/manifest.json": "application/json",
    }
    created_keys: list[str] = []

    try:
        for relative_path, content in payloads.items():
            source = tmp_path / "upload" / relative_path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(content)
            key = f"{key_root}{relative_path}"
            assert upload_file(
                key,
                str(source),
                content_types[relative_path],
                max_bytes=1024 * 1024,
            )
            created_keys.append(key)

        for relative_path, expected in payloads.items():
            destination = tmp_path / "download" / relative_path
            written = download_to_file(
                f"{key_root}{relative_path}",
                destination,
                max_bytes=1024 * 1024,
            )
            assert written == len(expected)
            assert destination.read_bytes() == expected

        streamed = open_download_stream(f"{key_root}artifacts/document.md")
        assert streamed.content_length == len(payloads["artifacts/document.md"])
        assert b"".join(streamed.chunks) == payloads["artifacts/document.md"]
    finally:
        for key in reversed(created_keys):
            # Every key is explicit, unique to this test, and below documents/test-*.
            assert delete_object(key)
