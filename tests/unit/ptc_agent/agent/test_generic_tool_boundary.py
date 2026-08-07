"""Regression boundaries for the generic Agent runtime."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml

from ptc_agent.agent import agent as ptc_agent_module
from ptc_agent.agent.flash.agent import FlashAgent
from ptc_agent.agent.middleware.skills.registry import get_skill_registry
from ptc_agent.agent.subagents.builtins import BUILTIN_SUBAGENTS
from ptc_agent.core.sandbox._defaults import DEFAULT_DEPENDENCIES


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

FINANCE_SKILLS = {
    "user-profile",
    "onboarding",
    "chart-annotation",
    "market-watch",
    "comps-analysis",
    "dcf-model",
    "earnings-preview",
    "idea-generation",
    "check-model",
    "morning-note",
    "catalyst-calendar",
    "check-deck",
    "thesis-tracker",
    "model-update",
    "3-statements",
    "earnings-analysis",
    "sector-overview",
    "competitive-analysis",
    "interactive-dashboard",
    "initiating-coverage",
    "ui-design",
}

RETAINED_GENERIC_SKILLS = {
    "automation",
    "html-report",
    "inline-widget",
    "run-workflow",
    "secretary",
    "self-improve",
    "x-api",
    "xlsx",
}

RETIRED_FINANCE_RUNTIME_PATHS = (
    "src/server/database/market_insight.py",
    "src/server/models/market_insight.py",
    "src/utils/market_hours.py",
)


def _tool_name(tool: object) -> str:
    return str(getattr(tool, "name", getattr(tool, "__name__", "")))


def test_ptc_runtime_module_has_no_finance_native_tool_dependencies():
    """PTC keeps its generic execution tools, but not finance tool imports."""
    exposed_symbols = set(vars(ptc_agent_module))

    assert not (FINANCE_NATIVE_TOOL_SYMBOLS & exposed_symbols)


def test_ptc_runtime_does_not_mount_financial_user_data_files():
    """Portfolio and watchlist virtual files must not reach generic sandboxes."""
    source = Path(ptc_agent_module.__file__).read_text()

    assert "UserDataBackend" not in source
    assert "USER_PROFILE_DATA_DIR" not in source


def test_financial_user_data_implementation_is_retired():
    """The generic runtime must not retain a dormant portfolio DB adapter."""
    project_root = Path(__file__).parents[4]

    assert not (project_root / "src/ptc_agent/agent/backends/user_data.py").exists()
    assert not (project_root / "src/server/services/user_data_io.py").exists()


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


def test_default_skill_registry_has_no_finance_capabilities():
    """Retired finance Skills must not be discoverable by PTC or Flash."""
    assert not (FINANCE_SKILLS & set(get_skill_registry()))


def test_retired_finance_skill_templates_are_not_shipped():
    """Removed Skills must not remain available for a later accidental re-registration."""
    skills_root = Path(__file__).parents[4] / "skills"

    assert not [
        skill_name
        for skill_name in FINANCE_SKILLS
        if (skills_root / skill_name / "SKILL.md").exists()
    ]


def test_retained_skill_guidance_is_domain_neutral():
    """Generic Skills must not inherit finance-only examples or dependencies."""
    skills_root = Path(__file__).parents[4] / "skills"
    skill_text = "\n".join(
        (skills_root / skill_name / "SKILL.md").read_text()
        for skill_name in RETAINED_GENERIC_SKILLS
    ).lower()

    for retired_concept in (
        "financial",
        "investment",
        "portfolio",
        "watchlist",
        "ticker",
        "stock",
        "equity",
        "earnings",
        "valuation",
        "market data",
    ):
        assert retired_concept not in skill_text
    assert "ui-design" not in skill_text
    assert "interactive-dashboard" not in skill_text


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
            "components/user_profile.md.j2",
            "components/workspace_paths.md.j2",
            "components/memory.md.j2",
            "components/flash_identity.md.j2",
            "components/plan_mode.md.j2",
            "subagents/roles/data_prep.md.j2",
        )
    )

    for retired_tool in FINANCE_NATIVE_TOOL_SYMBOLS:
        assert retired_tool not in prompt_text
    assert "Financial Tools" not in prompt_text
    for retired_concept in (
        "financial",
        "investment",
        "portfolio",
        "watchlist",
        "ticker",
        "stock",
        "SEC filing",
        "market data",
    ):
        assert retired_concept.lower() not in prompt_text.lower()


def test_prompt_defaults_have_no_market_watch_toggle():
    """A removed runtime feature must not survive as a misleading prompt default."""
    config_path = (
        Path(__file__).parents[4] / "src/ptc_agent/agent/prompts/config/prompts.yaml"
    )
    config = yaml.safe_load(config_path.read_text())

    assert "market_watch_enabled" not in config["defaults"]


def test_generic_runtime_has_no_finance_only_modules_or_user_contracts():
    """Removed finance surfaces cannot remain as orphaned importable modules."""
    project_root = Path(__file__).parents[4]

    assert not [
        relative_path
        for relative_path in RETIRED_FINANCE_RUNTIME_PATHS
        if (project_root / relative_path).exists()
    ]

    user_models = (project_root / "src/server/models/user.py").read_text()
    for retired_contract in (
        "AlertSettings",
        "Watchlist",
        "PortfolioHolding",
        "PortfolioResponse",
        "normalize_symbol",
        "KNOWN_INSTRUMENT_TYPES",
    ):
        assert retired_contract not in user_models


def test_default_sandbox_has_no_financial_dependencies_or_token_channel():
    """Generic sandboxes must not install or provision finance-only integrations."""
    project_root = Path(__file__).parents[4]

    assert "yfinance" not in DEFAULT_DEPENDENCIES
    for relative_path in (
        "src/config/env.py",
        "src/config/settings.py",
        "src/ptc_agent/core/sandbox/ptc_sandbox.py",
        "src/ptc_agent/core/sandbox/assets.py",
        "src/server/services/workspace_manager.py",
        "src/ptc_agent/core/sandbox/providers/daytona.py",
        "Dockerfile.sandbox",
    ):
        source = (project_root / relative_path).read_text().lower()
        assert "ginlix_data" not in source
        assert "yfinance" not in source
        assert "polymarket" not in source


def test_default_prompts_and_public_docs_describe_a_generic_agent_platform():
    """Public entry points cannot advertise capabilities removed from runtime."""
    project_root = Path(__file__).parents[4]
    source = "\n".join(
        (project_root / relative_path).read_text().lower()
        for relative_path in (
            "README.md",
            "AGENTS.md",
            "web/README.md",
            "src/ptc_agent/agent/prompts/templates/components/workspace_context.md.j2",
            "src/ptc_agent/agent/middleware/compaction/utils.py",
        )
    )

    for retired_term in (
        "financial research",
        "market data",
        "tradingview",
        "price-triggered",
        "sec filing",
        "yfinance",
        "fmp",
        "portfolio",
        "watchlist",
    ):
        assert retired_term not in source
