"""Managed textbook skills are repository-owned, frozen, and free of JSONL helpers."""

from unittest.mock import AsyncMock
from pathlib import Path
from uuid import uuid4

import pytest

from src.server.services import education_book_jobs
from src.server.services.education_book_structure import get_more_to_skills_identity


def test_student_material_guidance_keeps_line_anchors_out_of_reading_text():
    root = (
        Path(__file__).resolve().parents[4]
        / "plugins/langalpha_local/skills/more-to-skills"
    )
    skill = (root / "SKILL.md").read_text()
    material_rules = skill.split("## Step 7 — 逐条生成材料", 1)[1].split(
        "## Step 8 — 生成附加材料", 1
    )[0]
    language = (root / "reference/material-language.md").read_text()
    general = (root / "reference/material-general.md").read_text()

    assert "讲义不展示源文件行号" in material_rules
    assert "结构 JSON 的 anchor" in material_rules
    assert "在材料里注明出处行号" not in material_rules
    assert "并给行号" not in material_rules
    assert "源文件行：" not in material_rules + language + general
    assert "脚注编号" in language
    assert "粗体" in language
    assert "自然融入" in language


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
    skill_root = (
        Path(__file__).resolve().parents[4]
        / "plugins/langalpha_local/skills/more-to-skills"
    )
    for reference in (
        "material-math.md",
        "material-language.md",
        "material-general.md",
    ):
        destination = f"{root}/reference/{reference}"
        assert destination in files
        assert files[destination] == (skill_root / "reference" / reference).read_bytes()
    assert all(path.startswith(root + "/") for path in files)
    assert not any("skill-backups" in path for path in files)
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


@pytest.mark.asyncio
async def test_subject_reference_change_rejects_frozen_catalog_before_upload(
    monkeypatch, tmp_path
):
    from src.server.services import education_book_structure as structure

    root = tmp_path / "skill"
    (root / "schemas").mkdir(parents=True)
    (root / "reference").mkdir()
    (root / "SKILL.md").write_bytes(b"instructions")
    (root / "schemas/book-structure.schema.json").write_bytes(b"{}")
    reference = root / "reference/material-math.md"
    reference.write_bytes(b"original teaching guidance")
    monkeypatch.setattr(structure, "_SKILL_ROOT", root)
    identity = get_more_to_skills_identity()
    reference.write_bytes(b"changed teaching guidance")
    assert get_more_to_skills_identity().schema_sha256 == identity.schema_sha256
    sandbox = AsyncMock()
    with pytest.raises(ValueError, match="frozen identity"):
        await education_book_jobs.stage_book_skill(
            str(uuid4()),
            sandbox,
            expected_skill_sha256=identity.skill_sha256,
            expected_schema_sha256=identity.schema_sha256,
        )
    sandbox.aupload_file_bytes.assert_not_awaited()
