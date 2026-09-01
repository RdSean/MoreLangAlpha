from __future__ import annotations

import logging
import threading

import pytest

from ptc_agent.tokenizer_resource import TokenizerResourceStatus


@pytest.mark.asyncio
async def test_prepare_tokenizer_at_startup_is_non_fatal(monkeypatch, caplog):
    from src.server.app import setup

    caller_thread = threading.get_ident()
    preparation_threads: list[int] = []

    def prepare(*, allow_download: bool):
        assert allow_download is True
        preparation_threads.append(threading.get_ident())
        return TokenizerResourceStatus(
            encoding="cl100k_base",
            status="approximate",
            exact=False,
            error_code="vocabulary_download_failed",
        )

    monkeypatch.setattr(
        "ptc_agent.tokenizer_resource.prepare_tokenizer_resource",
        prepare,
    )

    with caplog.at_level(logging.ERROR):
        await setup._prepare_tokenizer_resource_at_startup()

    assert preparation_threads
    assert preparation_threads[0] != caller_thread
    assert "vocabulary_download_failed" in caplog.text


@pytest.mark.asyncio
async def test_unexpected_tokenizer_startup_error_does_not_abort(monkeypatch, caplog):
    from src.server.app import setup

    def fail(*, allow_download: bool):
        assert allow_download is True
        raise RuntimeError("private filesystem detail")

    monkeypatch.setattr(
        "ptc_agent.tokenizer_resource.prepare_tokenizer_resource",
        fail,
    )

    with caplog.at_level(logging.ERROR):
        await setup._prepare_tokenizer_resource_at_startup()

    assert "tokenizer_preparation_failed" in caplog.text
    assert "private filesystem detail" not in caplog.text
