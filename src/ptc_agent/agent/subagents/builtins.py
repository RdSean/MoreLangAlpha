"""Built-in subagent definitions.

These are the default subagents shipped with the agent.  User-defined
definitions in ``agent_config.yaml`` can override any of these by name.
"""

from __future__ import annotations

from ptc_agent.agent.subagents.definition import SubagentDefinition

BUILTIN_SUBAGENTS: dict[str, SubagentDefinition] = {
    "research": SubagentDefinition(
        name="research",
        description=(
            "Delegate research to the sub-agent researcher. "
            "Give this researcher one specific topic or question at a time. "
            "The researcher will search the web and provide findings with citations."
        ),
        mode="ptc",
        role_prompt_template="roles/researcher.md.j2",
        tools=["web_search", "filesystem"],
        max_iterations=5,
        stateful=False,
        sections={
            "workspace_paths": False,
            "tool_guide": False,
            "data_processing": False,
            "visualizations": False,
        },
    ),
    "general-purpose": SubagentDefinition(
        name="general-purpose",
        description=(
            "Delegate complex tasks to the general-purpose sub-agent. "
            "This agent has access to all filesystem tools "
            "(read, write, edit, glob, grep, bash) and can execute Python "
            "code with MCP tools. Use for multi-step operations, data "
            "processing, file manipulation, or any task requiring full tool access."
        ),
        mode="ptc",
        role_prompt_template="roles/general.md.j2",
        tools=["execute_code", "filesystem", "bash", "web_search"],
        max_iterations=10,
        stateful=True,
        sections={
            "workspace_paths": True,
            "tool_guide": True,
            "data_processing": True,
            "visualizations": True,
        },
    ),
    "data-prep": SubagentDefinition(
        name="data-prep",
        description=(
            "Delegate data fetching and preparation to the data prep sub-agent. "
            "This agent gathers data from available MCP servers or approved web "
            "sources, cleans and transforms it, and saves structured datasets to "
            "files. Use for bulk data collection or preparing datasets for analysis. "
            "Can run multiple instances in parallel for different data needs."
        ),
        mode="ptc",
        role_prompt_template="roles/data_prep.md.j2",
        tools=["execute_code", "filesystem", "bash", "web_search"],
        max_iterations=10,
        stateful=True,
        sections={
            "workspace_paths": True,
            "tool_guide": True,
            "data_processing": True,
            "visualizations": False,
        },
    ),
    "analyst": SubagentDefinition(
        name="analyst",
        description=(
            "Delegate evidence-based analysis to the analyst sub-agent. This agent "
            "can search the web, execute Python code with MCP tools, and build "
            "models or charts. Use for structured research, comparison, synthesis, "
            "or other tasks requiring web research and programmatic analysis."
        ),
        mode="ptc",
        role_prompt_template="roles/analyst.md.j2",
        tools=["execute_code", "filesystem", "bash", "web_search"],
        max_iterations=15,
        stateful=True,
        sections={
            "workspace_paths": True,
            "tool_guide": True,
            "data_processing": True,
            "visualizations": True,
        },
    ),
    "report-builder": SubagentDefinition(
        name="report-builder",
        description=(
            "Delegate document creation to the report builder sub-agent. "
            "This agent specializes in producing polished DOCX reports, XLSX "
            "models, PPTX presentations, and PDF files. Give it the analysis "
            "results and desired output format. Loads the relevant format "
            "skill (xlsx/docx/pptx/pdf) as its first action."
        ),
        mode="ptc",
        role_prompt_template="roles/report_builder.md.j2",
        tools=["execute_code", "filesystem", "bash"],
        max_iterations=20,
        stateful=True,
        sections={
            "workspace_paths": True,
            "tool_guide": True,
            "data_processing": False,
            "visualizations": True,
        },
    ),
}
