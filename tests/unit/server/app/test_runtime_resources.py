from __future__ import annotations

from unittest.mock import patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from ptc_agent.tokenizer_resource import TokenizerResourceStatus
from tests.conftest import create_test_app


@pytest_asyncio.fixture
async def client():
    from src.server.app.runtime_resources import router

    app = create_test_app(router)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as value:
        yield value


@pytest.mark.asyncio
async def test_get_tokenizer_status_returns_safe_public_shape(client):
    status = TokenizerResourceStatus(
        encoding="cl100k_base",
        status="approximate",
        exact=False,
        error_code="vocabulary_unavailable",
    )
    with patch(
        "src.server.app.runtime_resources.get_tokenizer_resource_status",
        return_value=status,
    ):
        response = await client.get("/api/v1/runtime-resources/tokenizer")

    assert response.status_code == 200
    assert response.json() == {
        "encoding": "cl100k_base",
        "status": "approximate",
        "exact": False,
        "error_code": "vocabulary_unavailable",
    }
    assert "path" not in response.text


@pytest.mark.asyncio
async def test_retry_download_returns_ready_status(client):
    status = TokenizerResourceStatus(
        encoding="cl100k_base",
        status="ready",
        exact=True,
    )
    with patch(
        "src.server.app.runtime_resources.prepare_tokenizer_resource",
        return_value=status,
    ) as prepare:
        response = await client.post(
            "/api/v1/runtime-resources/tokenizer/download"
        )

    assert response.status_code == 200
    assert response.json()["exact"] is True
    prepare.assert_called_once_with(allow_download=True)


@pytest.mark.asyncio
async def test_retry_download_returns_503_when_approximation_remains(client):
    status = TokenizerResourceStatus(
        encoding="cl100k_base",
        status="approximate",
        exact=False,
        error_code="vocabulary_download_failed",
    )
    with patch(
        "src.server.app.runtime_resources.prepare_tokenizer_resource",
        return_value=status,
    ):
        response = await client.post(
            "/api/v1/runtime-resources/tokenizer/download"
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "tokenizer_vocabulary_unavailable",
            "resource_status": {
                "encoding": "cl100k_base",
                "status": "approximate",
                "exact": False,
                "error_code": "vocabulary_download_failed",
            },
        }
    }


@pytest.mark.asyncio
async def test_retry_download_does_not_expose_unexpected_error_details(client):
    with patch(
        "src.server.app.runtime_resources.prepare_tokenizer_resource",
        side_effect=RuntimeError("private filesystem detail"),
    ):
        response = await client.post(
            "/api/v1/runtime-resources/tokenizer/download"
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": {"code": "tokenizer_vocabulary_unavailable"}
    }
    assert "private filesystem detail" not in response.text
