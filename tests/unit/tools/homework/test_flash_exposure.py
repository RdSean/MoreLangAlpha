"""Flash carries the homework tool too.

Flash is the agent a quick question lands on, so "最近我有哪些作业要做" has to
work there — not only in PTC. This is a deliberate widening of Flash's tool
surface, which used to be documented as external-only.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from ptc_agent.config import AgentConfig, LLMConfig
from ptc_agent.config.core import (
    DaytonaConfig,
    FilesystemConfig,
    LoggingConfig,
    MCPConfig,
    SandboxConfig,
    SecurityConfig,
)


def _flash_config() -> AgentConfig:
    return AgentConfig(
        llm=LLMConfig(name="flash-model", flash="flash-model"),
        security=SecurityConfig(),
        logging=LoggingConfig(),
        sandbox=SandboxConfig(daytona=DaytonaConfig(api_key="test-key")),
        mcp=MCPConfig(),
        filesystem=FilesystemConfig(),
    )


def _flash_tool_names() -> set[str]:
    from ptc_agent.agent.flash.agent import FlashAgent

    with (
        patch("src.llms.llm.ensure_model_in_manifest", return_value=None),
        patch("src.llms.create_llm", return_value=MagicMock(name="flash-llm")),
    ):
        agent = FlashAgent(_flash_config())
    return {tool.name for tool in agent._build_tools()}


def test_flash_can_answer_the_homework_question() -> None:
    assert "get_homework_schedule" in _flash_tool_names()


def test_flash_keeps_the_tools_it_already_had() -> None:
    names = _flash_tool_names()
    assert {"get_sec_filing", "get_quote", "get_company_overview"} <= names
