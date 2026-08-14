"""Sandbox staging and private archive contracts for teaching packages."""

import json
from unittest.mock import AsyncMock

import pytest

from src.server.services import education_teaching_storage


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
    assert all(
        path.startswith(
            "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/inputs/"
        )
        for path in paths
    )
    assert all("storage_key" not in body for body in bodies)
    assert frozen["chapters"][0]["content_sha256"]
    manifest = json.loads(next(body for path, body in uploaded if path.endswith("manifest.json")))
    assert manifest["chapters"][0]["content_chapter_id"] == _job()["chapters"][0]["content_chapter_id"]


@pytest.mark.asyncio
async def test_stage_managed_teaching_skills_stages_only_fixed_managed_contracts():
    sandbox = AsyncMock(spec=["aupload_file_bytes"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)

    await education_teaching_storage.stage_managed_teaching_skills(_job()["job_id"], sandbox)

    paths = [call.args[0] for call in sandbox.aupload_file_bytes.await_args_list]
    assert paths == [
        "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/.agents/skills/book-to-skill/reference/managed-textbook-contract.md",
        "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/.agents/skills/the-knowledge-guy/reference/managed-textbook-contract.md",
    ]


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
