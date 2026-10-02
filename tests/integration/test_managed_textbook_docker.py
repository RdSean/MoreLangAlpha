"""Real Docker smoke coverage for the managed textbook execution envelope."""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from uuid import uuid4

from langchain_core.messages import ToolMessage
from PIL import Image
import pytest

from ptc_agent.agent.managed_execution import (
    education_book_policy,
    managed_core_config,
)
from ptc_agent.agent.middleware.file_operations.multimodal import (
    MultimodalMiddleware,
)
from ptc_agent.config import ConfigContext, load_from_files
from ptc_agent.core.sandbox.ptc_sandbox import PTCSandbox
from src.server.services.education_book_structure import (
    TrustedBookSource,
    parse_book_structure,
)


pytestmark = [pytest.mark.integration, pytest.mark.provider_docker, pytest.mark.asyncio]


def _candidate() -> dict[str, object]:
    return {
        "schema_version": "2.1.0",
        "generator": {
            "name": "more-to-skills",
            "version": "2.1.0",
            "generated_at": "2026-10-02T00:00:00+09:00",
        },
        "book": {"title": "Docker Smoke", "title_source": "normalized"},
        "source": {
            "path": "inputs/source/document.md",
            "filename": "document.md",
            "format": "markdown",
            "total_lines": 3,
            "anchor_mode": "source_lines",
            "line_offset": 0,
        },
        "level_names": ["unit"],
        "nodes": [
            {
                "id": "unit-1",
                "title": "Unit 1",
                "anchor": {"start_line": 1, "end_line": 3},
                "children": [],
            }
        ],
        "knowledge_points": [
            {
                "id": "unit-1-k1",
                "title": "Smoke point",
                "anchor": {"start_line": 1, "end_line": 3},
                "unit": "unit-1",
                "nodes": ["unit-1"],
            }
        ],
        "coverage": {"scope": "Complete", "excluded": [], "omitted": [], "gaps": []},
    }


async def test_managed_textbook_real_docker_capabilities_and_boundaries() -> None:
    agent_config = await load_from_files(context=ConfigContext.SDK)
    if agent_config.sandbox.provider != "docker":
        pytest.skip("Docker sandbox provider is not selected")
    execution_id = str(uuid4())
    policy = education_book_policy(execution_id)
    sandbox = PTCSandbox(managed_core_config(agent_config.to_core_config(), policy))
    root = policy.filesystem_root
    try:
        await sandbox.setup_managed_textbook_job(policy)
        await sandbox.ensure_directories(
            [f"{root}/inputs/source", f"{root}/.agents/skills/more-to-skills/scripts"]
        )
        assert await sandbox.aupload_file_bytes(
            f"{root}/inputs/source/document.md", b"one\ntwo\nthree\n"
        )
        assert await sandbox.aupload_file_bytes(
            f"{root}/.agents/skills/more-to-skills/scripts/probe.py",
            b"print('ORIGINAL')\n",
        )
        assert await sandbox.aupload_file_bytes(
            f"{root}/work/build.py",
            b"from pathlib import Path\nPath('outputs/bash.txt').write_text('bash-ok')\n",
        )
        image_buffer = io.BytesIO()
        Image.new("RGB", (2, 2), color=(255, 0, 0)).save(image_buffer, format="PNG")
        assert await sandbox.aupload_file_bytes(
            f"{root}/inputs/source/red.png", image_buffer.getvalue()
        )
        await sandbox.seal_directory_read_only(f"{root}/inputs")
        await sandbox.seal_directory_read_only(f"{root}/.agents/skills")

        bash = await sandbox.execute_bash_command(
            "python work/build.py && "
            "cp .agents/skills/more-to-skills/scripts/probe.py work/probe.py && "
            "sed -i 's/ORIGINAL/MODIFIED/' work/probe.py && python work/probe.py",
            working_dir=root,
        )
        assert bash["success"] is True
        assert "MODIFIED" in bash["stdout"]
        assert await sandbox.aread_file_text(f"{root}/outputs/bash.txt") == "bash-ok"

        execute_code = await sandbox.execute(
            "from pathlib import Path\n"
            "Path('outputs/execute-code.txt').write_text('execute-code-ok')\n"
            "print(Path('inputs/source/document.md').read_text().splitlines()[1])",
        )
        assert execute_code.success is True
        assert "two" in execute_code.stdout
        assert (
            await sandbox.aread_file_text(f"{root}/outputs/execute-code.txt")
            == "execute-code-ok"
        )

        denied = await sandbox.execute_bash_command(
            "printf changed >> inputs/source/document.md; "
            "printf changed >> .agents/skills/more-to-skills/scripts/probe.py",
            working_dir=root,
        )
        assert denied["success"] is False

        middleware = MultimodalMiddleware(sandbox=sandbox)
        request = SimpleNamespace(
            tool_call={
                "name": "Read",
                "args": {"file_path": "inputs/source/red.png"},
                "id": "image-read",
            }
        )

        async def read_ack(_request):
            return ToolMessage(content="read", tool_call_id="image-read")

        image_result = await middleware.awrap_tool_call(request, read_ack)
        assert image_result.content[-1]["type"] == "image_url"
        assert image_result.content[-1]["image_url"]["url"].startswith(
            "data:image/png;base64,"
        )

        candidate_path = f"{root}/outputs/book-structure.json"
        assert await sandbox.aupload_file_bytes(
            candidate_path,
            json.dumps(_candidate()).encode("utf-8"),
        )
        raw_candidate = await sandbox.adownload_file_bytes(candidate_path)
        parsed = parse_book_structure(
            trusted_source=TrustedBookSource(
                path="inputs/source/document.md",
                filename="document.md",
                format="markdown",
                total_lines=3,
                anchor_mode="source_lines",
                line_offset=0,
            ),
            raw_json=raw_candidate or b"",
            allowed_output_paths=(),
        )
        assert parsed.knowledge_points[0]["skill_kp_id"] == "unit-1-k1"
    finally:
        await sandbox.cleanup()
