"""Managed textbook skills are repository-owned, frozen, and free of JSONL helpers."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.server.services import education_book_jobs
from src.server.services.education_book_structure import get_more_to_skills_identity


def test_tool_script_change_invalidates_frozen_catalog(monkeypatch, tmp_path):
    from src.server.services import education_book_structure as structure

    root = tmp_path / "skill"
    (root / "schemas").mkdir(parents=True)
    (root / "tools").mkdir()
    (root / "SKILL.md").write_bytes(b"instructions")
    (root / "schemas/book-structure.schema.json").write_bytes(b"{}")
    tool = root / "tools/split_blocks.py"
    tool.write_bytes(b"original")
    monkeypatch.setattr(structure, "_SKILL_ROOT", root)
    monkeypatch.setattr(structure, "_SKILL_PATH", root / "SKILL.md")
    monkeypatch.setattr(
        structure, "_SCHEMA_PATH", root / "schemas/book-structure.schema.json"
    )
    identity = get_more_to_skills_identity()
    tool.write_bytes(b"changed")
    assert get_more_to_skills_identity().skill_sha256 != identity.skill_sha256
    with pytest.raises(ValueError, match="frozen identity"):
        structure.load_more_to_skills_files(
            expected_skill_sha256=identity.skill_sha256,
            expected_schema_sha256=identity.schema_sha256,
        )


@pytest.mark.asyncio
async def test_staging_ignores_personal_skill_catalog_and_does_not_stage_progress(
    monkeypatch,
):
    from ptc_agent.config import agent

    def forbidden_catalog():
        raise AssertionError("managed textbooks must not discover personal skills")

    monkeypatch.setattr(agent, "host_skill_dirs", forbidden_catalog)
    sandbox = AsyncMock()
    sandbox.aupload_file_bytes.return_value = True
    identity = get_more_to_skills_identity()
    execution_id = str(uuid4())
    await education_book_jobs.stage_book_skill(
        execution_id,
        sandbox,
        expected_skill_sha256=identity.skill_sha256,
        expected_schema_sha256=identity.schema_sha256,
    )
    files = {
        call.args[0]: call.args[1]
        for call in sandbox.aupload_file_bytes.await_args_list
    }
    root = f"/managed/textbook-job/{execution_id}/.agents/skills/more-to-skills"
    assert f"{root}/SKILL.md" in files
    assert f"{root}/schemas/book-structure.schema.json" in files
    assert f"{root}/tools/split_blocks.py" in files
    assert all(path.startswith(root + "/") for path in files)
    sandbox.seal_directory_read_only.assert_awaited_once_with(root)


@pytest.mark.asyncio
async def test_changed_frozen_skill_rejected_before_any_upload():
    sandbox = AsyncMock()
    identity = get_more_to_skills_identity()
    with pytest.raises(ValueError, match="frozen identity"):
        await education_book_jobs.stage_book_skill(
            str(uuid4()),
            sandbox,
            expected_skill_sha256="0" * 64,
            expected_schema_sha256=identity.schema_sha256,
        )
    sandbox.aupload_file_bytes.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_skill_upload_does_not_seal_incomplete_catalog():
    sandbox = AsyncMock()
    sandbox.aupload_file_bytes.return_value = False
    identity = get_more_to_skills_identity()
    with pytest.raises(RuntimeError, match="stage"):
        await education_book_jobs.stage_book_skill(
            str(uuid4()),
            sandbox,
            expected_skill_sha256=identity.skill_sha256,
            expected_schema_sha256=identity.schema_sha256,
        )
    sandbox.seal_directory_read_only.assert_not_awaited()
