"""Focused filesystem write validation contracts."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ptc_agent.agent.tools.file_ops import create_filesystem_tools


@pytest.mark.asyncio
async def test_write_validator_rejects_content_before_sandbox_storage():
    backend = SimpleNamespace(
        normalize_path=lambda path: path,
        filesystem_config=SimpleNamespace(enable_path_validation=True),
        validate_path=lambda _path: True,
        awrite_text=AsyncMock(return_value=True),
        virtualize_path=lambda path: path,
    )
    _read, write, _edit = create_filesystem_tools(
        backend,
        write_validator=lambda _path, _content: "candidate must be valid JSON",
    )

    result = await write.ainvoke(
        {"file_path": "/managed/job/outputs/teaching-package.json", "content": "bad"}
    )

    assert result == "ERROR: candidate must be valid JSON"
    backend.awrite_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_edit_validator_rejects_path_before_sandbox_storage():
    backend = SimpleNamespace(
        normalize_path=lambda path: path.strip(),
        filesystem_config=SimpleNamespace(enable_path_validation=True),
        validate_path=lambda _path: True,
        aedit_text=AsyncMock(return_value={"success": True}),
        aread_text=AsyncMock(return_value="content"),
    )
    _read, _write, edit = create_filesystem_tools(
        backend,
        edit_validator=lambda path: "path is not allowed" if path.endswith("\n") else None,
    )

    result = await edit.ainvoke(
        {
            "file_path": "inputs/source.md\n",
            "old_string": "a",
            "new_string": "b",
        }
    )

    assert result == "ERROR: path is not allowed"
    backend.aedit_text.assert_not_awaited()
