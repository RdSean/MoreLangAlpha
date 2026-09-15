"""Token counting remains available when tiktoken cannot download its BPE file."""

from __future__ import annotations

from langchain_core.messages import HumanMessage

from ptc_agent.agent.middleware.compaction import utils


def test_count_tokens_retries_when_tiktoken_initialization_fails(monkeypatch):
    calls = 0

    def fail_to_load(_name):
        nonlocal calls
        calls += 1
        raise OSError("network unavailable")

    monkeypatch.setattr(utils, "_tiktoken_encoder", None)
    monkeypatch.setattr(utils.tiktoken, "get_encoding", fail_to_load)

    count = utils.count_tokens_tiktoken([HumanMessage(content="你好 hello")])

    assert count > 0
    # The fallback is not cached, so a repaired tokenizer can recover in-process.
    utils.count_tokens_tiktoken([HumanMessage(content="再试一次")])
    assert calls == 2


def test_approximate_encoder_handles_empty_text():
    encoder = utils._ApproximateTokenEncoder()

    assert len(encoder.encode("")) == 1
    assert len(encoder.encode("中文")) == 2
