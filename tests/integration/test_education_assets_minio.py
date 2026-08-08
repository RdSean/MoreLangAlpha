"""Opt-in smoke coverage for the Docker-local MinIO education bucket only."""

import os
from urllib.parse import urlparse
from uuid import uuid4

import pytest


pytestmark = pytest.mark.integration


def _require_local_minio() -> None:
    if os.getenv("RUN_EDUCATION_ASSET_MINIO_TESTS") != "1":
        pytest.skip("set RUN_EDUCATION_ASSET_MINIO_TESTS=1 after starting the local education-storage profile")

    from src.utils.storage.s3_compatible import StorageConfig

    endpoint = StorageConfig.ENDPOINT_URL
    host = urlparse(endpoint or "").hostname
    if host not in {"127.0.0.1", "localhost", "minio"}:
        pytest.skip("education asset smoke tests may only target the local MinIO profile")
    if not StorageConfig.BUCKET_NAME:
        pytest.skip("local MinIO storage bucket is not configured")


def test_local_minio_accepts_private_education_object_and_signs_it():
    _require_local_minio()
    from src.utils.storage.s3_compatible import delete_object, get_signed_url, upload_bytes

    key = f"education/integration-{uuid4()}/attachment.pdf"
    try:
        assert upload_bytes(key, b"%PDF-1.7 integration smoke", "application/pdf") is True
        assert get_signed_url(key, expires_in=60)
    finally:
        # This is the unique object created by this test, always under education/.
        delete_object(key)
