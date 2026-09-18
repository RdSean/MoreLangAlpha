"""Sandbox staging and private archive contracts for teaching packages."""

import json
from hashlib import sha256
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


def _source_job() -> dict:
    first_markdown = "# Complete first source\n\nFirst body.\n"
    second_markdown = "# Complete second source\n\nSecond body.\n"
    return {
        "job_id": "5e3a0b43-8378-4b6c-926f-0f053577501d",
        "household_id": "household-1",
        "slug": "english-2",
        "content_version_sequence": 1,
        "teaching_package_sequence": 2,
        "sources": [
            {
                "source_id": "job-parse-1",
                "content_chapter_id": "f5761267-11d1-4977-8107-e2671c99a2f0",
                "document_id": "doc-1",
                "position": 1,
                "slug": "reading-explorer",
                "title": "reading-explorer.pdf",
                "content_sha256": sha256(first_markdown.encode()).hexdigest(),
                "markdown": first_markdown,
            },
            {
                "source_id": "job-parse-2",
                "content_chapter_id": "8a77d086-0b23-4a1e-89d0-f163fa23d5d1",
                "document_id": "doc-2",
                "position": 2,
                "slug": "workbook",
                "title": "workbook.pdf",
                "content_sha256": sha256(second_markdown.encode()).hexdigest(),
                "markdown": second_markdown,
            },
        ],
    }


def _source_asset_job(
    *,
    markdown: str,
    asset_sha256: str,
    relative_path: str = "images/figure.png",
) -> dict:
    job = _source_job()
    source = job["sources"][0]
    source["markdown"] = markdown
    source["content_sha256"] = sha256(markdown.encode()).hexdigest()
    source["snapshot_prefix"] = (
        "education/household-1/english-2/source-bundles/"
        "f5761267-11d1-4977-8107-e2671c99a2f0/01/"
    )
    source["asset_manifest"] = [
        {
            "artifact_id": "image-1",
            "artifact_kind": "embedded_image",
            "format": "png",
            "media_type": "image/png",
            "relative_path": relative_path,
            "sha256": asset_sha256,
        }
    ]
    job["sources"] = [source]
    return job


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
        f"{root}outputs/.keep",
        f"{root}outputs/knowledge/.keep",
        f"{root}outputs/chapters/.keep",
    } == set(paths)
    assert all("storage_key" not in body for body in bodies)
    assert frozen["chapters"][0]["content_sha256"]
    manifest = json.loads(next(body for path, body in uploaded if path.endswith("manifest.json")))
    assert manifest["chapters"][0]["content_chapter_id"] == _job()["chapters"][0]["content_chapter_id"]


@pytest.mark.asyncio
async def test_stage_teaching_inputs_exposes_ordered_complete_source_bundles_without_storage_details():
    sandbox = AsyncMock(spec=["aupload_file_bytes"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)
    job = _source_job()

    staged = await education_teaching_storage.stage_teaching_inputs(job, sandbox)

    uploaded = {
        call.args[0]: call.args[1]
        for call in sandbox.aupload_file_bytes.await_args_list
    }
    root = "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/"
    manifest = json.loads(uploaded[f"{root}inputs/manifest.json"])
    assert manifest["format"] == "langalpha-managed-textbook-input/v2"
    assert [source["position"] for source in manifest["sources"]] == [1, 2]
    assert [source["path"] for source in manifest["sources"]] == [
        "sources/01-reading-explorer.md",
        "sources/02-workbook.md",
    ]
    assert [source["content_sha256"] for source in manifest["sources"]] == [
        job["sources"][0]["content_sha256"],
        job["sources"][1]["content_sha256"],
    ]
    assert uploaded[f"{root}inputs/sources/01-reading-explorer.md"] == (
        job["sources"][0]["markdown"].encode()
    )
    assert uploaded[f"{root}inputs/sources/02-workbook.md"] == (
        job["sources"][1]["markdown"].encode()
    )
    serialized = json.dumps(manifest)
    for forbidden in (
        "storage_key",
        "https://",
        "http://",
        "education/",
        "/managed/",
    ):
        assert forbidden not in serialized
    assert [chapter["position"] for chapter in staged["chapters"]] == [1, 2]


@pytest.mark.asyncio
async def test_stage_teaching_inputs_resolves_exact_and_basename_asset_refs(monkeypatch):
    image = b"frozen-image-bytes"
    markdown = (
        "# Complete source\n\n"
        "![exact](images/figure.png)\n"
        '![angle](<images/figure.png> "title")\n'
        "![basename](figure.png)\n"
        "![external](https://example.test/figure.png)\n"
        "![data](data:image/png;base64,AAAA)\n"
        "![blob](blob:https://example.test/figure.png)\n"
    )
    job = _source_asset_job(
        markdown=markdown,
        asset_sha256=sha256(image).hexdigest(),
    )
    requested: list[str] = []

    def get_bytes(key: str) -> bytes:
        requested.append(key)
        return image

    monkeypatch.setattr(
        education_teaching_storage, "get_bytes", get_bytes, raising=False
    )
    sandbox = AsyncMock(spec=["aupload_file_bytes"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)

    await education_teaching_storage.stage_teaching_inputs(job, sandbox)

    uploaded = {
        call.args[0]: call.args[1]
        for call in sandbox.aupload_file_bytes.await_args_list
    }
    root = "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/"
    manifest = json.loads(uploaded[f"{root}inputs/manifest.json"])
    assert manifest["sources"][0]["asset_paths"] == ["assets/01/images/figure.png"]
    assert uploaded[f"{root}inputs/assets/01/images/figure.png"] == image
    assert requested == [
        "education/household-1/english-2/source-bundles/"
        "f5761267-11d1-4977-8107-e2671c99a2f0/01/artifacts/images/figure.png"
    ]
    serialized = json.dumps(manifest)
    assert "storage_key" not in serialized
    assert "https://" not in serialized
    assert "data:image" not in serialized


@pytest.mark.asyncio
async def test_stage_teaching_inputs_reads_legacy_root_image_layout(monkeypatch):
    image = b"legacy-root-image"
    markdown = "![figure](images/figure.png)\n"
    job = _source_asset_job(
        markdown=markdown,
        asset_sha256=sha256(image).hexdigest(),
    )
    prefix = job["sources"][0]["snapshot_prefix"]
    objects = {f"{prefix}images/figure.png": image}
    monkeypatch.setattr(education_teaching_storage, "get_bytes", objects.get)
    sandbox = AsyncMock(spec=["aupload_file_bytes"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)

    await education_teaching_storage.stage_teaching_inputs(job, sandbox)

    uploaded = {
        call.args[0]: call.args[1]
        for call in sandbox.aupload_file_bytes.await_args_list
    }
    root = "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/"
    assert uploaded[f"{root}inputs/assets/01/images/figure.png"] == image


@pytest.mark.asyncio
async def test_stage_teaching_inputs_backfills_empty_asset_manifest_from_snapshot(monkeypatch):
    image = b"backfilled-image"
    markdown = "![figure](images/figure.png)\n"
    job = _source_job()
    source = job["sources"][0]
    source["markdown"] = markdown
    source["content_sha256"] = sha256(markdown.encode()).hexdigest()
    source["snapshot_prefix"] = (
        "education/household-1/english-2/source-bundles/"
        "f5761267-11d1-4977-8107-e2671c99a2f0/01/"
    )
    source["asset_manifest"] = []
    prefix = source["snapshot_prefix"]
    root_manifest = {
        "format": "langalpha-textbook-source-snapshot/v1",
        "document_id": source["document_id"],
        "producer_job_id": source["source_id"],
        "primary_artifact_id": "primary-1",
        "artifacts": [
            {
                "artifact_id": "image-1",
                "artifact_kind": "embedded_image",
                "format": "png",
                "media_type": "image/png",
                "relative_path": "images/figure.png",
                "sha256": sha256(image).hexdigest(),
                "storage_key": "must-not-leak",
            }
        ],
    }
    objects = {
        f"{prefix}manifest.json": json.dumps(root_manifest).encode(),
        f"{prefix}images/figure.png": image,
    }
    monkeypatch.setattr(education_teaching_storage, "get_bytes", objects.get)
    sandbox = AsyncMock(spec=["aupload_file_bytes"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)

    await education_teaching_storage.stage_teaching_inputs(job, sandbox)

    uploaded = {
        call.args[0]: call.args[1]
        for call in sandbox.aupload_file_bytes.await_args_list
    }
    root = "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/"
    manifest = json.loads(uploaded[f"{root}inputs/manifest.json"])
    assert manifest["sources"][0]["asset_paths"] == ["assets/01/images/figure.png"]
    assert uploaded[f"{root}inputs/assets/01/images/figure.png"] == image
    assert "storage_key" not in json.dumps(manifest)
    assert "must-not-leak" not in json.dumps(manifest)


@pytest.mark.asyncio
async def test_stage_teaching_inputs_percent_decodes_image_references(monkeypatch):
    first_image = b"encoded-space"
    second_image = b"encoded-unicode"
    markdown = (
        "![encoded](images/my%20figure-%E5%9B%BE.png)\n"
        "![basename](%E5%9B%BE.png)\n"
    )
    job = _source_asset_job(
        markdown=markdown,
        asset_sha256=sha256(first_image).hexdigest(),
        relative_path="images/my figure-图.png",
    )
    job["sources"][0]["asset_manifest"].append(
        {
            "artifact_id": "image-2",
            "artifact_kind": "embedded_image",
            "format": "png",
            "media_type": "image/png",
            "relative_path": "covers/图.png",
            "sha256": sha256(second_image).hexdigest(),
        }
    )
    prefix = job["sources"][0]["snapshot_prefix"]

    def get_bytes(key: str) -> bytes | None:
        return {
            f"{prefix}artifacts/images/my figure-图.png": first_image,
            f"{prefix}artifacts/covers/图.png": second_image,
        }.get(key)

    monkeypatch.setattr(
        education_teaching_storage, "get_bytes", get_bytes, raising=False
    )
    sandbox = AsyncMock(spec=["aupload_file_bytes"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)

    await education_teaching_storage.stage_teaching_inputs(job, sandbox)

    uploaded = {
        call.args[0]: call.args[1]
        for call in sandbox.aupload_file_bytes.await_args_list
    }
    root = "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/"
    manifest = json.loads(uploaded[f"{root}inputs/manifest.json"])
    assert manifest["sources"][0]["asset_paths"] == [
        "assets/01/images/my figure-图.png",
        "assets/01/covers/图.png",
    ]
    assert uploaded[f"{root}inputs/assets/01/images/my figure-图.png"] == first_image
    assert uploaded[f"{root}inputs/assets/01/covers/图.png"] == second_image


@pytest.mark.asyncio
async def test_stage_teaching_inputs_rejects_encoded_traversal_reference():
    job = _source_asset_job(
        markdown="![unsafe](images/%2E%2E/secret.png)\n",
        asset_sha256=sha256(b"secret").hexdigest(),
        relative_path="images/secret.png",
    )
    sandbox = AsyncMock(spec=["aupload_file_bytes"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)

    with pytest.raises(education_teaching_storage.TeachingPackageStorageError):
        await education_teaching_storage.stage_teaching_inputs(job, sandbox)


@pytest.mark.asyncio
async def test_stage_teaching_inputs_ignores_unreferenced_asset_manifest_entries(
    monkeypatch,
):
    job = _source_asset_job(
        markdown="# Source\n\n![external](https://example.test/figure.png)\n",
        asset_sha256=sha256(b"not-staged").hexdigest(),
    )
    get_bytes = AsyncMock()
    monkeypatch.setattr(education_teaching_storage, "get_bytes", get_bytes)
    sandbox = AsyncMock(spec=["aupload_file_bytes"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)

    await education_teaching_storage.stage_teaching_inputs(job, sandbox)

    uploaded = {
        call.args[0]: call.args[1]
        for call in sandbox.aupload_file_bytes.await_args_list
    }
    root = "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/"
    manifest = json.loads(uploaded[f"{root}inputs/manifest.json"])
    assert manifest["sources"][0]["asset_paths"] == []
    get_bytes.assert_not_awaited()
    assert f"{root}inputs/assets/01/images/figure.png" not in uploaded


@pytest.mark.asyncio
async def test_stage_teaching_inputs_fails_closed_for_missing_referenced_asset():
    job = _source_asset_job(
        markdown="![missing](images/missing.png)\n",
        asset_sha256=sha256(b"other").hexdigest(),
        relative_path="images/other.png",
    )
    sandbox = AsyncMock(spec=["aupload_file_bytes"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)

    with pytest.raises(education_teaching_storage.TeachingPackageStorageError):
        await education_teaching_storage.stage_teaching_inputs(job, sandbox)


@pytest.mark.asyncio
async def test_stage_teaching_inputs_fails_closed_for_referenced_asset_digest_mismatch(
    monkeypatch,
):
    job = _source_asset_job(
        markdown="![figure](images/figure.png)\n",
        asset_sha256="a" * 64,
    )
    monkeypatch.setattr(
        education_teaching_storage,
        "get_bytes",
        lambda _key: b"different-bytes",
        raising=False,
    )
    sandbox = AsyncMock(spec=["aupload_file_bytes"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)

    with pytest.raises(
        education_teaching_storage.TeachingPackageStorageError,
        match="digest",
    ):
        await education_teaching_storage.stage_teaching_inputs(job, sandbox)


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
    assert uploaded[f"{root}outputs/.keep"] == b""
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
async def test_structure_staging_loads_only_book_to_skill():
    sandbox = AsyncMock(spec=["aupload_file_bytes"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)

    await education_teaching_storage.stage_managed_teaching_skills(
        _job()["job_id"],
        sandbox,
        skill_names=("book-to-skill",),
    )

    root = "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/.agents/skills/"
    paths = {call.args[0] for call in sandbox.aupload_file_bytes.await_args_list}
    assert f"{root}book-to-skill/SKILL.md" in paths
    assert f"{root}the-knowledge-guy/SKILL.md" not in paths


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
async def test_staged_skill_managed_modes_reference_v2_outputs_without_a_service_order():
    sandbox = AsyncMock(spec=["aupload_file_bytes"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)

    await education_teaching_storage.stage_managed_teaching_skills(_job()["job_id"], sandbox)

    modes = [
        call.args[1].decode("utf-8")
        for call in sandbox.aupload_file_bytes.await_args_list
        if call.args[0].endswith("/SKILL.md")
    ]
    assert len(modes) == 2
    for mode in modes:
        assert "outputs/knowledge/concept-index.json" in mode
        assert "outputs/book-skill-manifest.json" not in mode
        assert "Return control for the next service-owned stage" not in mode


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
async def test_download_structure_output_uses_only_the_fixed_structure_path():
    sandbox = AsyncMock()
    sandbox.adownload_file_bytes.return_value = (
        b'{"format":"langalpha-managed-textbook-structure/v1","units":[]}'
    )

    output = await education_teaching_storage.download_structure_output(
        "5e3a0b43-8378-4b6c-926f-0f053577501d",
        sandbox,
    )

    assert output["units"] == []
    sandbox.adownload_file_bytes.assert_awaited_once_with(
        "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/outputs/structure.json"
    )


@pytest.mark.asyncio
async def test_write_structure_bundle_uses_only_private_education_keys(monkeypatch):
    uploads: list[tuple[str, bytes]] = []

    async def put(key: str, content: bytes, _content_type: str) -> None:
        uploads.append((key, content))

    monkeypatch.setattr(education_teaching_storage, "_put", put)
    job = {
        **_job(),
        "structure_sequence": 1,
    }

    prefix = await education_teaching_storage.write_structure_bundle(
        job,
        {"format": "langalpha-managed-textbook-structure/v1", "units": []},
    )

    assert prefix == "education/household-1/english-2/v1/structures/v1"
    assert {key for key, _content in uploads} == {
        f"{prefix}/README.md",
        f"{prefix}/manifest.json",
        f"{prefix}/structure.json",
    }
    manifest = json.loads(
        next(content for key, content in uploads if key.endswith("manifest.json"))
    )
    assert "education/" not in json.dumps(manifest)
    assert manifest["structure_version"] == 1


@pytest.mark.asyncio
async def test_write_kp_lesson_revision_uses_private_revision_path(monkeypatch):
    uploads: list[tuple[str, bytes, str]] = []

    async def put(key: str, content: bytes, content_type: str) -> None:
        uploads.append((key, content, content_type))

    monkeypatch.setattr(education_teaching_storage, "_put", put)
    job = {
        **_job(),
        "structure_sequence": 1,
        "unit_position": 1,
        "unit_slug": "unit-1-sports",
        "knowledge_point_position": 2,
        "knowledge_point_slug": "world-game",
        "lesson_revision": 3,
    }
    content = "# 世界运动\n\n课程内容。\n".encode()

    stored = await education_teaching_storage.write_kp_lesson_revision(
        job,
        content,
    )

    expected_key = (
        "education/household-1/english-2/v1/structures/v1/"
        "units/01-unit-1-sports/knowledge-points/02-world-game/"
        "lessons/v3/lesson.md"
    )
    assert stored == {
        "content_key": expected_key,
        "content_sha256": sha256(content).hexdigest(),
        "size_bytes": len(content),
    }
    assert uploads == [
        (expected_key, content, "text/markdown; charset=utf-8")
    ]


@pytest.mark.asyncio
async def test_stage_kp_lesson_inputs_contains_only_target_context():
    sandbox = AsyncMock(spec=["aupload_file_bytes"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)

    await education_teaching_storage.stage_kp_lesson_inputs(
        {
            "job_id": "5e3a0b43-8378-4b6c-926f-0f053577501d",
            "knowledge_point_id": "kp-1",
            "knowledge_point_title": "世界运动",
            "unit_title": "Unit 1",
            "auto_grading": False,
            "source_refs": [{"source_id": "source-1", "start": 0, "end": 40}],
        },
        "# Unit 1\n\nsource excerpt",
        sandbox,
    )

    uploaded = {
        call.args[0]: call.args[1]
        for call in sandbox.aupload_file_bytes.await_args_list
    }
    root = "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/"
    assert uploaded[f"{root}inputs/lesson-context.md"] == b"# Unit 1\n\nsource excerpt"
    manifest = json.loads(uploaded[f"{root}inputs/manifest.json"])
    assert manifest["knowledge_point_id"] == "kp-1"
    assert manifest["auto_grading"] is False


@pytest.mark.asyncio
async def test_download_kp_lesson_outputs_uses_only_fixed_paths():
    sandbox = AsyncMock()
    sandbox.adownload_file_bytes.side_effect = [
        b"# lesson\n",
        None,
    ]

    lesson, practice = await education_teaching_storage.download_kp_lesson_outputs(
        "5e3a0b43-8378-4b6c-926f-0f053577501d",
        sandbox,
        auto_grading=False,
    )

    assert lesson == b"# lesson\n"
    assert practice is None
    assert [call.args[0] for call in sandbox.adownload_file_bytes.await_args_list] == [
        "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/outputs/lesson.md",
        "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/outputs/practice.json",
    ]


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
async def test_download_incomplete_teaching_outputs_reports_only_safe_relative_path():
    sandbox = AsyncMock()
    frozen = education_teaching_storage.freeze_teaching_input(_job())
    paths = expected_teaching_asset_paths(frozen)
    missing_path = paths.for_chapter(_job()["chapters"][0]["content_chapter_id"]).practice
    sandbox.adownload_file_bytes.side_effect = [
        None if path == missing_path else b"{}" for path in sorted(paths.all_paths)
    ]

    with pytest.raises(education_teaching_storage.TeachingPackageStorageError) as exc_info:
        await education_teaching_storage.download_teaching_asset_outputs(
            _job()["job_id"], frozen, sandbox
        )

    assert exc_info.value.relative_path == missing_path
    assert "/managed/" not in str(exc_info.value)


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
async def test_private_teaching_archive_retries_across_the_transient_storage_window(monkeypatch):
    attempts = 0
    delays: list[float] = []

    def upload(_key: str, _content: bytes, _content_type: str) -> bool:
        nonlocal attempts
        attempts += 1
        return attempts == 6

    async def to_thread(function, *args):
        return function(*args)

    async def sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(education_teaching_storage, "upload_bytes", upload)
    monkeypatch.setattr(education_teaching_storage.asyncio, "to_thread", to_thread)
    monkeypatch.setattr(education_teaching_storage.asyncio, "sleep", sleep)

    await education_teaching_storage._put(
        "education/household-1/english-2/v1/teaching/v2/manifest.json",
        b"{}",
        "application/json",
    )

    assert attempts == 6
    assert delays == [5, 10, 20, 40, 60]


def test_validated_teaching_archive_stage_round_trips_only_fixed_candidate_paths():
    frozen = education_teaching_storage.freeze_teaching_input(_job())
    paths = expected_teaching_asset_paths(frozen)
    outputs = {
        path: f"validated candidate: {path}".encode("utf-8")
        for path in paths.all_paths
    }

    staged = education_teaching_storage.encode_teaching_archive_stage(
        frozen, outputs
    )

    restored = education_teaching_storage.decode_teaching_archive_stage(
        frozen, staged
    )

    assert restored == outputs
    assert b"education/" not in staged
    assert b"storage_key" not in staged


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
