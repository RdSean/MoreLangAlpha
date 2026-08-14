"""Sandbox staging and private archive contracts for teaching packages."""

import json
from unittest.mock import AsyncMock

import pytest

from src.server.services import education_teaching_storage
from src.server.services.education_teaching_assets import expected_teaching_asset_paths


def _job() -> dict:
    return {
        "job_id": "5e3a0b43-8378-4b6c-926f-0f053577501d",
        "household_id": "household-1",
        "slug": "english-2",
        "content_version_sequence": 1,
        "teaching_package_sequence": 2,
        "chapters": [
            {
                "content_chapter_id": "f5761267-11d1-4977-8107-e2671c99a2f0",
                "position": 1,
                "slug": "01-overview",
                "title": "导读",
                "markdown": "# 导读\n\n教材正文。",
            }
        ],
        "sources": [{"storage_key": "education/household-1/secret.pdf"}],
    }


@pytest.mark.asyncio
async def test_stage_teaching_inputs_uploads_only_safe_manifest_and_frozen_chapters():
    sandbox = AsyncMock(spec=["aupload_file_bytes"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)

    frozen = await education_teaching_storage.stage_teaching_inputs(_job(), sandbox)

    uploaded = [
        (call.args[0], call.args[1])
        for call in sandbox.aupload_file_bytes.await_args_list
    ]
    paths = [path for path, _ in uploaded]
    bodies = [body.decode("utf-8") for _, body in uploaded]
    root = "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/"
    assert all(path.startswith(root) for path in paths)
    assert {
        f"{root}inputs/manifest.json",
        f"{root}inputs/chapters/01-01-overview.md",
        f"{root}work/knowledge-skill/.keep",
        f"{root}outputs/knowledge/.keep",
        f"{root}outputs/chapters/.keep",
    } == set(paths)
    assert all("storage_key" not in body for body in bodies)
    assert frozen["chapters"][0]["content_sha256"]
    manifest = json.loads(next(body for path, body in uploaded if path.endswith("manifest.json")))
    assert manifest["chapters"][0]["content_chapter_id"] == _job()["chapters"][0]["content_chapter_id"]


@pytest.mark.asyncio
async def test_stage_teaching_inputs_precreates_the_fixed_v2_output_directories():
    sandbox = AsyncMock(spec=["aupload_file_bytes"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)

    await education_teaching_storage.stage_teaching_inputs(_job(), sandbox)

    uploaded = {
        call.args[0]: call.args[1]
        for call in sandbox.aupload_file_bytes.await_args_list
    }
    root = "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/"
    assert uploaded[f"{root}work/knowledge-skill/.keep"] == b""
    assert uploaded[f"{root}outputs/knowledge/.keep"] == b""
    assert uploaded[f"{root}outputs/chapters/.keep"] == b""


@pytest.mark.asyncio
async def test_stage_managed_teaching_skills_stages_complete_static_builtin_skill_catalogs():
    sandbox = AsyncMock(spec=["aupload_file_bytes"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)

    await education_teaching_storage.stage_managed_teaching_skills(_job()["job_id"], sandbox)

    root = "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/.agents/skills/"
    paths = {call.args[0] for call in sandbox.aupload_file_bytes.await_args_list}
    assert f"{root}book-to-skill/SKILL.md" in paths
    assert f"{root}book-to-skill/reference/coverage-audit-template.md" in paths
    assert f"{root}book-to-skill/reference/practice-template.md" in paths
    assert f"{root}the-knowledge-guy/SKILL.md" in paths
    assert f"{root}the-knowledge-guy/design-system/layouts.md" in paths
    assert all("/scripts/" not in path for path in paths)


@pytest.mark.asyncio
async def test_staged_managed_skill_contracts_describe_only_v2_service_derived_outputs():
    sandbox = AsyncMock(spec=["aupload_file_bytes"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)

    await education_teaching_storage.stage_managed_teaching_skills(_job()["job_id"], sandbox)

    contracts = [
        call.args[1].decode("utf-8")
        for call in sandbox.aupload_file_bytes.await_args_list
        if call.args[0].endswith("reference/managed-textbook-contract.md")
    ]
    assert len(contracts) == 2
    for contract in contracts:
        assert "outputs/knowledge/concept-index.json" in contract
        assert "outputs/knowledge/coverage-audit.json" in contract
        assert "-knowledge.json" in contract
        assert "-toolkit.md" in contract
        assert "-practice.json" in contract
        assert "outputs/book-skill-manifest.json" not in contract


@pytest.mark.asyncio
async def test_staging_fails_closed_when_a_sandbox_upload_is_rejected():
    sandbox = AsyncMock(spec=["aupload_file_bytes"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=False)

    with pytest.raises(education_teaching_storage.TeachingPackageStorageError):
        await education_teaching_storage.stage_teaching_inputs(_job(), sandbox)


@pytest.mark.asyncio
async def test_download_teaching_output_uses_the_single_fixed_candidate_path():
    sandbox = AsyncMock()
    sandbox.adownload_file_bytes.return_value = b'{"format":"langalpha-managed-teaching-package/v1","chapters":[]}'

    output = await education_teaching_storage.download_teaching_output(
        "5e3a0b43-8378-4b6c-926f-0f053577501d", sandbox
    )

    assert output["chapters"] == []
    sandbox.adownload_file_bytes.assert_awaited_once_with(
        "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/outputs/teaching-package.json"
    )


@pytest.mark.asyncio
async def test_download_complete_teaching_outputs_uses_only_all_service_derived_paths():
    sandbox = AsyncMock()
    paths = expected_teaching_asset_paths(education_teaching_storage.freeze_teaching_input(_job()))
    sandbox.adownload_file_bytes.side_effect = [b"{}"] * len(paths.all_paths)

    outputs = await education_teaching_storage.download_teaching_asset_outputs(
        _job()["job_id"], education_teaching_storage.freeze_teaching_input(_job()), sandbox
    )

    root = "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/"
    requested = {call.args[0] for call in sandbox.adownload_file_bytes.await_args_list}
    assert requested == {f"{root}{path}" for path in paths.all_paths}
    assert outputs == {path: b"{}" for path in paths.all_paths}


@pytest.mark.asyncio
async def test_write_teaching_asset_bundle_uses_only_service_generated_education_keys(monkeypatch):
    uploads: list[tuple[str, bytes]] = []

    async def put(key: str, content: bytes, _content_type: str) -> None:
        uploads.append((key, content))

    monkeypatch.setattr(education_teaching_storage, "_put", put)
    frozen = education_teaching_storage.freeze_teaching_input(_job())
    paths = expected_teaching_asset_paths(frozen)
    outputs = {path: b"{}" for path in paths.all_paths}
    manifest = {
        "format": "langalpha-family-teaching-assets/v2",
        "concept_index": {"sha256": "a" * 64, "size_bytes": 2, "concept_count": 1},
        "coverage_audit": {"sha256": "b" * 64, "size_bytes": 2, "status": "complete"},
        "chapters": [],
    }

    prefix = await education_teaching_storage.write_teaching_asset_bundle(_job(), manifest, outputs)

    assert prefix == "education/household-1/english-2/v1/teaching/v2"
    assert all(key.startswith(prefix + "/") for key, _ in uploads)
    stored_manifest = json.loads(next(content for key, content in uploads if key.endswith("manifest.json")))
    assert "education/" not in json.dumps(stored_manifest)
    assert "storage_key" not in json.dumps(stored_manifest)
    assert f"{prefix}/knowledge/concept-index.json" in {key for key, _ in uploads}
    assert f"{prefix}/chapters/01-01-overview-knowledge.json" in {key for key, _ in uploads}


@pytest.mark.asyncio
async def test_write_teaching_package_bundle_uses_server_generated_education_keys(monkeypatch):
    uploads: list[tuple[str, bytes]] = []

    async def put(key: str, content: bytes, _content_type: str) -> None:
        uploads.append((key, content))

    monkeypatch.setattr(education_teaching_storage, "_put", put)
    package = {
        "format": "langalpha-managed-teaching-package/v1",
        "chapters": [
            {
                "content_chapter_id": _job()["chapters"][0]["content_chapter_id"],
                "content_sha256": "a" * 64,
                "learning_objectives": ["掌握内容"],
                "knowledge_points": ["核心概念"],
                "key_difficulties": ["难点"],
                "prerequisites": [],
                "teaching_material": "# 导读\n\n中文教学材料",
                "questions": [
                    {
                        "position": 1,
                        "prompt": "选择正确答案",
                        "options": {"A": "正确", "B": "错误"},
                        "correct_option": "A",
                        "explanation": "解释",
                        "knowledge_point": "核心概念",
                    }
                ],
            }
        ],
    }

    prefix = await education_teaching_storage.write_teaching_package_bundle(
        _job(), package
    )

    assert prefix == "education/household-1/english-2/v1/teaching/v2"
    assert all(key.startswith(prefix + "/") for key, _ in uploads)
    manifest = json.loads(next(content for key, content in uploads if key.endswith("manifest.json")))
    assert "storage_key" not in json.dumps(manifest)
    assert manifest["chapters"][0]["material_path"] == "chapters/01-01-overview-material.md"
