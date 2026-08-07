"""Hash stability of the content-addressed body store on the frequent path.

The body handed to ``store_result_bodies`` is the canonical string that produced
``result_sha256``, after passing through ``_redact_body``. For clean web pages,
search results, and static documents, redaction is the identity and
``sha256(stored_body) == result_sha256`` exactly.

That equality is what both a post-hoc verifier and the content-addressed dedup
key rest on. The tests use an armed ``LeakDetectionMiddleware`` with configured
secret values that are absent from clean content, proving that normal content is
not modified by the redactor. A genuine secret is intentionally redacted, so its
stored body no longer hashes to the original raw-content hash.
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from ptc_agent.agent.middleware.provenance import ProvenanceMiddleware
from ptc_agent.agent.middleware.tool.leak_detection import LeakDetectionMiddleware
from ptc_agent.agent.provenance.types import RESULT_BODY_MAX_BYTES

_WRITER_PATH = (
    "ptc_agent.agent.middleware.provenance.middleware.get_stream_writer"
)
_STORE_PATH = "src.server.database.provenance_bodies.store_result_bodies"

_VAULT_SECRETS = {
    "EDUCATION_API_KEY": "fake-education-key-for-tests-only",
    "OPENAI_API_KEY": "fake-openai-key-for-tests-only",
    "GITHUB_TOKEN": "fake-github-token-for-tests-only",
}


def _armed_middleware() -> ProvenanceMiddleware:
    redactor = LeakDetectionMiddleware(vault_secrets=dict(_VAULT_SECRETS)).redact
    return ProvenanceMiddleware(redactor=redactor)


def _canonical(value) -> str:
    """Mirror of types._canonicalize for assertions."""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    return str(value)


def _make_request(name, args, tool_call_id="call-1"):
    return SimpleNamespace(
        tool_call={"name": name, "args": args, "id": tool_call_id}
    )


def _result(content="", artifact=None):
    return SimpleNamespace(content=content, artifact=artifact)


async def _run(middleware, request, result):
    """Run awrap_tool_call with patched writer + store; return (emitted, store)."""
    emitted: list = []
    store = AsyncMock()

    async def handler(_req):
        return result

    with patch(_WRITER_PATH, return_value=emitted.append), patch(
        _STORE_PATH, store
    ):
        await middleware.awrap_tool_call(request, handler)
        await middleware._drain_body_flushes()
    return emitted, store


def _stored(store):
    """[(sha, body, size, content_type), ...] handed to the batched store call."""
    return [
        item
        for call in store.await_args_list
        for item in (call.args[0] if call.args else [])
    ]


def _web_fetch_request(url: str, tool_call_id: str = "call-1"):
    return _make_request("WebFetch", {"url": url}, tool_call_id)


def _web_fetch_result(content: str, url: str):
    return _result(content, {"url": url, "provider": "test"})


_STUDY_GUIDE = (
    "A learner-centered study guide explains a concept, provides a worked "
    "example, and follows with practice questions and reflection prompts."
)
_STUDY_GUIDE_URL = "https://docs.example.test/study-guide"


# ---------------------------------------------------------------------------
# Clean frequent path: stored body hashes exactly to result_sha256.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_web_fetch_body_hashes_to_sha():
    _, store = await _run(
        _armed_middleware(),
        _web_fetch_request(_STUDY_GUIDE_URL),
        _web_fetch_result(_STUDY_GUIDE, _STUDY_GUIDE_URL),
    )

    calls = _stored(store)
    assert len(calls) == 1
    sha, body, size, content_type = calls[0]
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == sha
    assert size == len(body.encode("utf-8"))
    assert content_type == "text/plain; charset=utf-8"
    assert "[REDACTED" not in body


@pytest.mark.asyncio
async def test_large_web_fetch_full_body_hashes_to_sha():
    big_text = "Practice explanation. " * 4000
    assert len(big_text.encode("utf-8")) > RESULT_BODY_MAX_BYTES

    _, store = await _run(
        _armed_middleware(),
        _web_fetch_request(_STUDY_GUIDE_URL),
        _web_fetch_result(big_text, _STUDY_GUIDE_URL),
    )

    sha, body, size, _ = _stored(store)[0]
    assert len(body.encode("utf-8")) > RESULT_BODY_MAX_BYTES
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() == sha
    assert size == len(body.encode("utf-8"))


# ---------------------------------------------------------------------------
# Dedup-key stability: identical content -> identical sha -> one body row.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_same_static_document_dedups_to_one_sha_across_turns():
    _, first_store = await _run(
        _armed_middleware(),
        _web_fetch_request(_STUDY_GUIDE_URL, tool_call_id="turn-1"),
        _web_fetch_result(_STUDY_GUIDE, _STUDY_GUIDE_URL),
    )
    _, second_store = await _run(
        _armed_middleware(),
        _web_fetch_request(_STUDY_GUIDE_URL, tool_call_id="turn-2"),
        _web_fetch_result(_STUDY_GUIDE, _STUDY_GUIDE_URL),
    )

    sha1, body1, _, _ = _stored(first_store)[0]
    sha2, body2, _, _ = _stored(second_store)[0]
    assert sha1 == sha2
    assert body1 == body2


@pytest.mark.asyncio
async def test_different_content_gets_different_sha():
    _, first_store = await _run(
        _armed_middleware(),
        _web_fetch_request(_STUDY_GUIDE_URL),
        _web_fetch_result(_STUDY_GUIDE, _STUDY_GUIDE_URL),
    )
    _, second_store = await _run(
        _armed_middleware(),
        _web_fetch_request(_STUDY_GUIDE_URL),
        _web_fetch_result(_STUDY_GUIDE + " Include a review checklist.", _STUDY_GUIDE_URL),
    )

    assert _stored(first_store)[0][0] != _stored(second_store)[0][0]


@pytest.mark.asyncio
async def test_web_search_dict_key_order_does_not_change_sha():
    item = {
        "url": "https://docs.example.test/mathematics",
        "title": "Mathematics lesson",
        "snippet": "A lesson on fractions.",
        "metadata": {"grade": 4, "subject": "mathematics"},
    }
    shuffled = dict(reversed(list(item.items())))
    request = _make_request("WebSearch", {"query": "math lesson"})

    _, first_store = await _run(
        _armed_middleware(), request, _result(artifact={"results": [item]})
    )
    _, second_store = await _run(
        _armed_middleware(), request, _result(artifact={"results": [shuffled]})
    )

    assert _stored(first_store)[0][0] == _stored(second_store)[0][0]
    assert _stored(first_store)[0][1] == _canonical(item)


# ---------------------------------------------------------------------------
# Negative controls: a genuine leak is redacted and diverges from the raw hash.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sandbox_token_in_body_is_redacted_and_diverges():
    token = "gxsa_abc123DEF456ghi789"
    _, store = await _run(
        _armed_middleware(),
        _web_fetch_request(_STUDY_GUIDE_URL),
        _web_fetch_result(
            f"{_STUDY_GUIDE} Internal token={token}", _STUDY_GUIDE_URL
        ),
    )

    sha, body, _, _ = _stored(store)[0]
    assert token not in body
    assert "[REDACTED:SANDBOX_TOKEN]" in body
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() != sha


@pytest.mark.asyncio
async def test_configured_secret_value_in_body_is_redacted_and_diverges():
    secret = _VAULT_SECRETS["EDUCATION_API_KEY"]
    _, store = await _run(
        _armed_middleware(),
        _web_fetch_request(_STUDY_GUIDE_URL),
        _web_fetch_result(
            f"{_STUDY_GUIDE} Internal API key={secret}", _STUDY_GUIDE_URL
        ),
    )

    sha, body, _, _ = _stored(store)[0]
    assert secret not in body
    assert "[REDACTED:EDUCATION_API_KEY]" in body
    assert hashlib.sha256(body.encode("utf-8")).hexdigest() != sha
