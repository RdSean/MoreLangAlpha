"""Regression boundaries for the generic Agent runtime."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from ptc_agent.agent import agent as ptc_agent_module
from ptc_agent.agent.flash.agent import FlashAgent
from ptc_agent.agent.subagents.builtins import BUILTIN_SUBAGENTS


FINANCE_NATIVE_TOOL_SYMBOLS = {
    "get_sec_filing",
    "get_quote",
    "get_daily_prices",
    "get_company_overview",
    "get_market_overview",
    "get_options_chain",
    "screen_stocks",
    "watch_market",
}

FINANCE_MCP_SERVERS = {
    "price_data",
    "fundamentals",
    "macro",
    "options",
    "yf_price",
    "yf_fundamentals",
    "yf_analysis",
    "yf_market",
    "alphavantage",
}


def _tool_name(tool: object) -> str:
    return str(getattr(tool, "name", getattr(tool, "__name__", "")))


def test_ptc_runtime_module_has_no_finance_native_tool_dependencies():
    """PTC keeps its generic execution tools, but not finance tool imports."""
    exposed_symbols = set(vars(ptc_agent_module))

    assert not (FINANCE_NATIVE_TOOL_SYMBOLS & exposed_symbols)


def test_flash_default_tools_are_generic(monkeypatch):
    """Flash remains a web-capable assistant without finance lookup tools."""
    import ptc_agent.agent.flash.agent as flash_agent_module
    import src.tools.secretary as secretary_module

    web_search = SimpleNamespace(name="web_search")
    web_fetch = SimpleNamespace(name="web_fetch")
    secretary = SimpleNamespace(name="delegate_to_worker")
    monkeypatch.setattr(flash_agent_module, "get_web_search_tool", lambda **_: web_search)
    monkeypatch.setattr(flash_agent_module, "web_fetch_tool", web_fetch)
    monkeypatch.setattr(secretary_module, "SECRETARY_TOOLS", [secretary])

    agent = object.__new__(FlashAgent)
    agent.config = SimpleNamespace(search_api="test", search_depth="basic")

    tool_names = {_tool_name(tool) for tool in agent._build_tools()}

    assert {"web_search", "web_fetch", "delegate_to_worker"} <= tool_names
    assert not (FINANCE_NATIVE_TOOL_SYMBOLS & tool_names)


def test_default_mcp_configuration_has_no_finance_servers():
    """Finance providers must be opt-in workspace extensions, never defaults."""
    config_path = Path(__file__).parents[4] / "agent_config.yaml"
    config = yaml.safe_load(config_path.read_text())
    configured_names = {entry["name"] for entry in config["mcp"]["servers"]}

    assert not (FINANCE_MCP_SERVERS & configured_names)


def test_builtin_subagents_have_no_finance_tool_set_or_finance_role():
    """Default specialist roles must compile from generic tool groups only."""
    assert "equity-analyst" not in BUILTIN_SUBAGENTS
    assert "analyst" in BUILTIN_SUBAGENTS
    assert all("finance" not in definition.tools for definition in BUILTIN_SUBAGENTS.values())


def test_default_agent_prompts_do_not_advertise_retired_finance_tools():
    """A generic runtime cannot instruct models to call tools it no longer has."""
    template_root = (
        Path(__file__).parents[4] / "src/ptc_agent/agent/prompts/templates"
    )
    prompt_text = "\n".join(
        (template_root / relative_path).read_text()
        for relative_path in (
            "system.md.j2",
            "flash_system.md.j2",
            "components/tool_guide.md.j2",
        )
    )

    for retired_tool in FINANCE_NATIVE_TOOL_SYMBOLS:
        assert retired_tool not in prompt_text
    assert "Financial Tools" not in prompt_text


def test_prompt_defaults_have_no_market_watch_toggle():
    """A removed runtime feature must not survive as a misleading prompt default."""
    config_path = (
        Path(__file__).parents[4] / "src/ptc_agent/agent/prompts/config/prompts.yaml"
    )
    config = yaml.safe_load(config_path.read_text())

    assert "market_watch_enabled" not in config["defaults"]
