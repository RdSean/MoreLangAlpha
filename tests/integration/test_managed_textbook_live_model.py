"""Opt-in live-model proof that a managed PTC run can actually inspect an image."""

from __future__ import annotations

import io
from uuid import uuid4

from langchain_core.messages import ToolMessage
from PIL import Image
import pytest

from ptc_agent.agent.graph import build_ptc_graph_with_session
from ptc_agent.agent.managed_execution import (
    education_book_policy,
    managed_core_config,
)
from ptc_agent.config import ConfigContext, load_from_files
from ptc_agent.core.session import Session
from src.server.database.pool import get_or_create_pool
from src.server.services.education_managed_runs import (
    resolve_managed_education_agent_config,
)
from src.server.services.education_teaching_storage import (
    stage_managed_teaching_skills,
)


pytestmark = [
    pytest.mark.integration,
    pytest.mark.provider_docker,
    pytest.mark.regression,
    pytest.mark.asyncio,
]


async def test_managed_ptc_model_reads_staged_image(monkeypatch) -> None:
    agent_config = await load_from_files(context=ConfigContext.SDK)
    if agent_config.sandbox.provider != "docker":
        pytest.skip("Docker sandbox provider is not selected")
    pool = get_or_create_pool()
    await pool.open()
    async with pool.connection() as connection:
        row = await connection.execute(
            """
            SELECT users.user_id
            FROM users
            WHERE users.byok_enabled = TRUE
              AND EXISTS (
                  SELECT 1 FROM user_api_keys
                  WHERE user_api_keys.user_id = users.user_id
              )
            ORDER BY users.created_at
            LIMIT 1
            """
        )
        model_owner = await row.fetchone()
    if model_owner is None:
        await pool.close()
        pytest.skip("No local user has an enabled BYOK model")
    from src.server.app import setup

    previous_agent_config = setup.agent_config
    setup.agent_config = agent_config
    resolved_config = await resolve_managed_education_agent_config(
        parent_user_id=str(model_owner[0])
    )
    execution_id = str(uuid4())
    policy = education_book_policy(execution_id)
    session = Session(
        str(uuid4()),
        managed_core_config(agent_config.to_core_config(), policy),
    )
    monkeypatch.setattr(
        "ptc_agent.agent.graph._read_workspace_naming",
        lambda _workspace_id: _async_value(("Managed image smoke", "")),
    )
    try:
        await session.initialize_managed_textbook(policy)
        assert session.sandbox is not None
        await stage_managed_teaching_skills(
            execution_id,
            session.sandbox,
            skill_names=("more-to-skills",),
        )
        image_buffer = io.BytesIO()
        Image.new("RGB", (64, 64), color=(255, 0, 0)).save(image_buffer, format="PNG")
        image_path = f"{policy.filesystem_root}/inputs/source/red-square.png"
        assert await session.sandbox.aupload_file_bytes(
            image_path, image_buffer.getvalue()
        )
        await session.sandbox.seal_directory_read_only(
            f"{policy.filesystem_root}/inputs"
        )
        await session.sandbox.seal_directory_read_only(
            f"{policy.filesystem_root}/.agents/skills/more-to-skills"
        )
        graph = await build_ptc_graph_with_session(
            session=session,
            config=resolved_config,
            subagent_names=[],
            disable_subagents=True,
            thread_id=str(uuid4()),
            managed_policy=policy,
        )
        result = await graph.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "Use the Read tool on inputs/source/red-square.png. "
                            "Identify the predominant visible color from the image "
                            "itself, then answer with the single uppercase word RED."
                        ),
                    }
                ],
                "current_agent": "ptc",
            },
            {"recursion_limit": 20},
        )
        messages = result["messages"]
        assert any(
            isinstance(message, ToolMessage)
            and isinstance(message.content, list)
            and any(
                isinstance(block, dict) and block.get("type") == "image_url"
                for block in message.content
            )
            for message in messages
        )
        final_content = messages[-1].content
        final_text = (
            "".join(
                str(block.get("text") or "")
                for block in final_content
                if isinstance(block, dict) and block.get("type") == "text"
            )
            if isinstance(final_content, list)
            else str(final_content)
        )
        final_answer = final_text.strip().splitlines()[-1].strip("*_`")
        assert final_answer == "RED"
    finally:
        await session.cleanup()
        setup.agent_config = previous_agent_config
        await pool.close()


async def _async_value(value):
    return value
