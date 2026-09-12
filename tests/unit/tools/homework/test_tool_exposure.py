"""Which agents may see the homework tool.

Registration used to be implicit — a list built inline in `create_agent` and
gated by a single `managed_policy is None`, with nothing to assert against
except a full agent-construction harness. `build_domain_tools` names the set
instead, so the interesting properties are checkable directly.
"""

from __future__ import annotations

from types import SimpleNamespace

from ptc_agent.agent.agent import build_domain_tools, build_finance_tools


def _config(*, market_watch: bool = False) -> SimpleNamespace:
    return SimpleNamespace(feature_enabled=lambda key: key == "market_watch" and market_watch)


def _names(**kwargs) -> set[str]:
    return {tool.name for tool in build_domain_tools(_config(**kwargs))}


def _finance_names(**kwargs) -> set[str]:
    return {tool.name for tool in build_finance_tools(_config(**kwargs))}


def test_an_ordinary_account_gets_the_homework_tool() -> None:
    assert "get_homework_schedule" in _names()


def test_the_finance_tools_still_come_along() -> None:
    # This set predates the homework tool; the refactor must not have dropped
    # anything on the way through.
    assert {
        "get_sec_filing",
        "get_quote",
        "get_daily_prices",
        "get_company_overview",
        "get_market_overview",
        "get_options_chain",
        "screen_stocks",
    } <= _names()


def test_market_watch_stays_feature_gated() -> None:
    assert "watch_market" not in _names()
    assert "watch_market" in _names(market_watch=True)


def test_the_finance_set_does_not_gain_the_household_read() -> None:
    # `finance` is a tool set the built-in subagents declare by name, so adding
    # a household read to it would silently widen what an analyst subagent can
    # reach. The homework tool belongs to the top-level set only.
    assert "get_homework_schedule" not in _finance_names()
    assert "get_homework_schedule" in _names()
