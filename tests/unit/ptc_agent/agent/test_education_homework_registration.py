"""The shared host homework tool is available in both chat agent modes."""

from types import SimpleNamespace

from ptc_agent.agent import agent as ptc_agent_module
from ptc_agent.agent.flash.agent import FlashAgent
from src.tools.education import education_create_homework


def _names(tools):
    return [getattr(tool, "name", "") for tool in tools]


def test_ptc_source_registers_homework_tool_only_for_normal_builds():
    source = open(ptc_agent_module.__file__, encoding="utf-8").read()
    assert "education_create_homework" in source
    assert "managed_policy is None" in source


def test_flash_default_tools_include_shared_homework_tool(monkeypatch):
    agent = object.__new__(FlashAgent)
    agent.config = SimpleNamespace(
        search_api=None,
        search_depth=None,
    )
    monkeypatch.setattr(
        "ptc_agent.agent.flash.agent.get_web_search_tool",
        lambda **_: SimpleNamespace(name="web_search"),
    )
    monkeypatch.setattr(
        "ptc_agent.agent.flash.agent.web_fetch_tool",
        SimpleNamespace(name="web_fetch"),
    )
    monkeypatch.setattr("src.tools.secretary.SECRETARY_TOOLS", [])

    tools = agent._build_tools()
    assert education_create_homework in tools
    assert _names(tools).count("education_create_homework") == 1
