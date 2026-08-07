"""Tests for the generic sandbox layout migration."""

import shlex
from unittest.mock import AsyncMock

import pytest

from ptc_agent.core.sandbox.migration import (
    CURRENT_LAYOUT_VERSION,
    migrate_layout_v1_to_v2,
    run_layout_migrations,
)


@pytest.fixture
def mock_runtime():
    runtime = AsyncMock()
    runtime.exec = AsyncMock(return_value="")
    return runtime


WORK_DIR = "/home/user/project"


@pytest.mark.asyncio
async def test_zero_cost_when_current(mock_runtime):
    result = await run_layout_migrations(
        mock_runtime, WORK_DIR, current_version=CURRENT_LAYOUT_VERSION
    )

    assert result == CURRENT_LAYOUT_VERSION
    mock_runtime.exec.assert_not_called()


@pytest.mark.asyncio
async def test_migration_v1_to_v2_moves_generic_workspace_directories(mock_runtime):
    await migrate_layout_v1_to_v2(mock_runtime, WORK_DIR)

    calls = [call.args[0] for call in mock_runtime.exec.call_args_list]
    assert any("mkdir -p" in call and ".agents/skills" in call for call in calls)
    assert any(".agent/threads" in call and ".agents/threads" in call for call in calls)
    assert any(
        ".agent/large_tool_results" in call
        and ".agents/large_tool_results" in call
        for call in calls
    )
    assert any("rmdir" in call and ".agent" in call for call in calls)
    assert any("rm -rf" in call and "/skills" in call for call in calls)


@pytest.mark.asyncio
async def test_migration_v1_to_v2_quotes_workspace_paths(mock_runtime):
    work_dir = "/home/user/my project"
    await migrate_layout_v1_to_v2(mock_runtime, work_dir)

    quoted_skills = shlex.quote(f"{work_dir}/.agents/skills")
    calls = [call.args[0] for call in mock_runtime.exec.call_args_list]
    assert any(quoted_skills in call for call in calls)


@pytest.mark.asyncio
async def test_run_layout_migrations_from_v1_runs_current_generic_migration(
    mock_runtime,
):
    result = await run_layout_migrations(mock_runtime, WORK_DIR, current_version=1)

    assert result == CURRENT_LAYOUT_VERSION
    calls = [call.args[0] for call in mock_runtime.exec.call_args_list]
    assert any(".agents/skills" in call for call in calls)
    assert any(".agent/threads" in call for call in calls)
