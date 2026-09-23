"""Sandbox staging and private archive contracts for teaching packages."""

import asyncio
import json
from hashlib import sha256
from pathlib import Path
import subprocess
import sys
from unittest.mock import AsyncMock

import pytest

from src.server.services import education_generation_progress
from src.server.services import education_teaching_storage


UNSAFE_PROGRESS_TEXT_CASES = (
    "OPENAI_API_KEY=opaque-value",
    "ANTHROPIC_ACCESS_TOKEN: opaque-value",
    "GITHUB_TOKEN opaque-value",
    "prefix_api_key=opaque-value",
    "access_key_id: opaque-value",
    "secret_key=opaque-value",
    "PASSWORD=opaque-value",
    "passwd_suffix: opaque-value",
    "TOKEN=opaque-value",
    "client_secret: opaque-value",
    '{"token":"opaque-value"}',
    "sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
    "ghp_abcdefghijklmnopqrstuvwxyz1234",
    "github_pat_11ABCDEFG0123456789_abcdefghijklmnopqrstuvwxyz",
    "AKIA1234567890ABCDEF",
    "ASIA1234567890ABCDEF",
    "/etc/passwd",
    "/foo",
    "path /foo",
    "见 /foo",
    "path: /foo",
    "path=/etc/passwd",
    "参见 /notes.md",
    "打开 /content/chapter.md",
    "/managed/textbook-job/secret",
    "/home/parent/book.md",
    "/tmp/progress.jsonl",
    r"C:\Users\parent\book.md",
    "C:/Users/parent/book.md",
    r"\\server\share\book.md",
    "s3://bucket/private",
    "file:///tmp/private",
    "https://user:password@example.com/book",
)

SAFE_PROGRESS_TEXT_CASES = (
    "private_key",
    "public_key",
    "token",
    "client_secret",
    "已完成 1 / 3 个文件",
    "Reading A / B",
    "TCP /IP",
    "1 /3",
    "Reading A /B",
)


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
    sandbox = AsyncMock(spec=["aupload_file_bytes", "ensure_directories"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)
    sandbox.ensure_directories = AsyncMock()

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
    sandbox.ensure_directories.assert_awaited_once_with(
        [f"{root}inputs"],
        mode=0o555,
    )


@pytest.mark.asyncio
async def test_stage_teaching_inputs_exposes_ordered_complete_source_bundles_without_storage_details():
    sandbox = AsyncMock(spec=["aupload_file_bytes", "ensure_directories"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)
    sandbox.ensure_directories = AsyncMock()
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
    sandbox = AsyncMock(spec=["aupload_file_bytes", "ensure_directories"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)
    sandbox.ensure_directories = AsyncMock()

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
    sandbox = AsyncMock(spec=["aupload_file_bytes", "ensure_directories"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)
    sandbox.ensure_directories = AsyncMock()

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
    sandbox = AsyncMock(spec=["aupload_file_bytes", "ensure_directories"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)
    sandbox.ensure_directories = AsyncMock()

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
    sandbox = AsyncMock(spec=["aupload_file_bytes", "ensure_directories"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)
    sandbox.ensure_directories = AsyncMock()

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
    sandbox = AsyncMock(spec=["aupload_file_bytes", "ensure_directories"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)
    sandbox.ensure_directories = AsyncMock()

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
    sandbox = AsyncMock(spec=["aupload_file_bytes", "ensure_directories"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)
    sandbox.ensure_directories = AsyncMock()

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
    sandbox = AsyncMock(spec=["aupload_file_bytes", "ensure_directories"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)
    sandbox.ensure_directories = AsyncMock()

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
    sandbox = AsyncMock(spec=["aupload_file_bytes", "ensure_directories"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)
    sandbox.ensure_directories = AsyncMock()

    with pytest.raises(
        education_teaching_storage.TeachingPackageStorageError,
        match="digest",
    ):
        await education_teaching_storage.stage_teaching_inputs(job, sandbox)


@pytest.mark.asyncio
async def test_stage_teaching_inputs_precreates_the_fixed_v2_output_directories():
    sandbox = AsyncMock(spec=["aupload_file_bytes", "ensure_directories"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)
    sandbox.ensure_directories = AsyncMock()

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
async def test_stage_reading_asset_inputs_uploads_only_fixed_reading_slices():
    sandbox = AsyncMock(spec=["aupload_file_bytes", "ensure_directories"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)
    sandbox.ensure_directories = AsyncMock()
    markdown = (
        "# Unit 1\n\n"
        "### THE WORLD'S GAME\n\n"
        "Soccer is global.\n\n"
        "### SOCCER WITHOUT BORDERS\n\n"
        "The game crosses borders.\n"
    )
    first = markdown.index("### THE WORLD'S GAME")
    second = markdown.index("### SOCCER WITHOUT BORDERS")
    job = {
        "job_id": _job()["job_id"],
        "generation_job_id": _job()["job_id"],
        "units": [
            {
                "unit_id": "unit-1",
                "position": 1,
                "slug": "unit-1-sports",
                "title": "Unit 1: Sports",
            }
        ],
    }
    frozen_input = {
        "sources": [{"source_id": "source-1", "markdown": markdown}],
    }
    scopes = [
        {
            "unit_id": "unit-1",
            "slot": "reading_a",
            "title": "The World's Game",
            "source_id": "source-1",
            "line_start": 3,
            "line_end": 5,
            "char_start": first,
            "char_end": second,
        }
    ]

    manifest = await education_teaching_storage.stage_reading_asset_inputs(
        job,
        frozen_input,
        scopes,
        sandbox,
    )

    root = "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/"
    uploaded = {
        call.args[0]: call.args[1]
        for call in sandbox.aupload_file_bytes.await_args_list
    }
    assert uploaded[
        f"{root}inputs/readings/01-unit-1-sports/reading_a.md"
    ].startswith(b"### THE WORLD'S GAME")
    assert manifest["readings"][0]["slot"] == "reading_a"


@pytest.mark.asyncio
async def test_stage_managed_teaching_skills_stages_complete_static_builtin_skill_catalogs():
    sandbox = AsyncMock(spec=["aupload_file_bytes", "ensure_directories"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)
    sandbox.ensure_directories = AsyncMock()

    await education_teaching_storage.stage_managed_teaching_skills(_job()["job_id"], sandbox)

    root = "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/.agents/skills/"
    paths = {call.args[0] for call in sandbox.aupload_file_bytes.await_args_list}
    assert f"{root}book-to-skill/SKILL.md" in paths
    # The canonical skill ships its extractor next to the SKILL.md, so helper
    # scripts are staged with it rather than excluded.
    assert f"{root}book-to-skill/scripts/extract.py" in paths
    assert f"{root}book-to-skill/book_to_skill/parsers/text.py" in paths
    assert all("the-knowledge-guy" not in path for path in paths)


@pytest.mark.asyncio
async def test_stage_managed_teaching_skills_stages_progress_helper():
    sandbox = AsyncMock(spec=["aupload_file_bytes", "ensure_directories"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)
    sandbox.ensure_directories = AsyncMock()

    await education_teaching_storage.stage_managed_teaching_skills(
        _job()["job_id"],
        sandbox,
        skill_names=("book-to-skill",),
    )

    uploaded = {
        call.args[0]: call.args[1]
        for call in sandbox.aupload_file_bytes.await_args_list
    }
    root = "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d"
    assert f"{root}/.langalpha/progress.py" in uploaded
    assert uploaded[f"{root}/.langalpha/progress.jsonl"] == b""
    assert str(education_generation_progress.MAX_METADATA_INTEGER).encode() in uploaded[
        f"{root}/.langalpha/progress.py"
    ]


def test_staged_progress_helper_appends_valid_events_and_never_rewrites(tmp_path: Path):
    helper = tmp_path / "progress.py"
    helper.write_bytes(education_teaching_storage.progress_helper_source())
    first = {
        "event_key": "chapter_analysis:running:chapter",
        "stage": "chapter_analysis",
        "status": "running",
        "label": "Chapter analysis",
    }

    for raw in (
        json.dumps(first, ensure_ascii=False),
        json.dumps(
            {
                "event_key": "chapter_analysis:completed:chapter",
                "stage": "chapter_analysis",
                "status": "completed",
                "label": "x" * 250,
            },
            ensure_ascii=False,
        ),
    ):
        result = subprocess.run(
            [sys.executable, str(helper), raw],
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    lines = (tmp_path / "progress.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["event_key"] == "chapter_analysis:running:chapter"
    assert json.loads(lines[1])["event_key"] == "chapter_analysis:completed:chapter"
    assert len(json.loads(lines[1])["label"]) == (
        education_generation_progress.MAX_LABEL_LENGTH
    )
    assert "\n" not in lines[0] and "\n" not in lines[1]


def test_staged_progress_helper_accepts_stdin_and_rejects_unsafe_input(tmp_path: Path):
    helper = tmp_path / "progress.py"
    helper.write_bytes(education_teaching_storage.progress_helper_source())
    valid = subprocess.run(
        [sys.executable, str(helper)],
        input=json.dumps(
            {
                "event_key": "content_processing:running:content",
                "stage": "content_processing",
                "status": "running",
            }
        ),
        capture_output=True,
        text=True,
        check=False,
    )
    assert valid.returncode == 0, valid.stderr
    output = tmp_path / "progress.jsonl"
    before = output.read_bytes()

    invalid_inputs = (
        json.dumps(["not", "an", "object"]),
        json.dumps(
            {
                "event_key": "invalid:stage",
                "stage": "unknown",
                "status": "running",
            }
        ),
        json.dumps(
            {
                "event_key": "invalid:status",
                "stage": "chapter_analysis",
                "status": "waiting",
            }
        ),
        json.dumps(
            {
                "event_key": "invalid:substage",
                "stage": "chapter_analysis",
                "status": "running",
                "substage": "../unsafe",
            }
        ),
        json.dumps(
            {
                "event_key": "invalid:control",
                "stage": "chapter_analysis",
                "status": "running",
                "label": "bad\x00label",
            }
        ),
        json.dumps(
            {
                "event_key": "invalid:format",
                "stage": "chapter_analysis",
                "status": "running",
                "label": "zero\u200bwidth",
            }
        ),
        json.dumps(
            {
                "event_key": "unsafe:path",
                "stage": "chapter_analysis",
                "status": "running",
                "label": "/managed/private",
            }
        ),
        json.dumps(
            {
                "event_key": "unsafe:secret",
                "stage": "chapter_analysis",
                "status": "running",
                "detail": "api_key=sk-live-abcdefghijklmnopqrstuvwxyz",
            }
        ),
        (
            '{"event_key":"first","event_key":"second",'
            '"stage":"chapter_analysis","status":"running"}'
        ),
    ) + tuple(
        json.dumps(
            {
                "event_key": f"unsafe:case-{index}",
                "stage": "chapter_analysis",
                "status": "running",
                "label": unsafe,
            }
        )
        for index, unsafe in enumerate(UNSAFE_PROGRESS_TEXT_CASES)
    )
    for invalid_input in invalid_inputs:
        invalid = subprocess.run(
            [sys.executable, str(helper)],
            input=invalid_input,
            capture_output=True,
            text=True,
            check=False,
        )
        assert invalid.returncode != 0
        assert output.read_bytes() == before


def test_staged_progress_helper_accepts_safe_domain_text(tmp_path: Path):
    helper = tmp_path / "progress.py"
    helper.write_bytes(education_teaching_storage.progress_helper_source())

    for index, label in enumerate(SAFE_PROGRESS_TEXT_CASES):
        result = subprocess.run(
            [sys.executable, str(helper)],
            input=json.dumps(
                {
                    "event_key": f"spaced:slash:{index}",
                    "stage": "chapter_analysis",
                    "status": "running",
                    "label": label,
                },
                ensure_ascii=False,
            ),
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    lines = (tmp_path / "progress.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["label"] for line in lines] == list(
        SAFE_PROGRESS_TEXT_CASES
    )


def test_staged_progress_helper_enforces_input_size_limits(tmp_path: Path):
    helper = tmp_path / "progress.py"
    helper.write_bytes(education_teaching_storage.progress_helper_source())
    output = tmp_path / "progress.jsonl"
    valid = json.dumps(
        {
            "event_key": "chapter_analysis:running:safe",
            "stage": "chapter_analysis",
            "status": "running",
        }
    )

    oversized_line = (
        " " * (education_generation_progress.MAX_PROGRESS_EVENT_BYTES + 1) + valid
    )
    oversized_string = json.dumps(
        {
            "event_key": "chapter_analysis:running:safe",
            "stage": "chapter_analysis",
            "status": "running",
            "label": "x"
            * (education_generation_progress.MAX_PROGRESS_STRING_BYTES + 1),
        }
    )
    for raw in (oversized_line, oversized_string):
        result = subprocess.run(
            [sys.executable, str(helper)],
            input=raw,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
        assert not output.exists()


@pytest.mark.asyncio
async def test_structure_staging_loads_only_book_to_skill():
    sandbox = AsyncMock(spec=["aupload_file_bytes", "ensure_directories"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)
    sandbox.ensure_directories = AsyncMock()

    await education_teaching_storage.stage_managed_teaching_skills(
        _job()["job_id"],
        sandbox,
        skill_names=("book-to-skill",),
    )

    root = "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/.agents/skills/"
    paths = {call.args[0] for call in sandbox.aupload_file_bytes.await_args_list}
    assert f"{root}book-to-skill/SKILL.md" in paths


@pytest.mark.asyncio
async def test_staging_fails_closed_when_a_sandbox_upload_is_rejected():
    sandbox = AsyncMock(spec=["aupload_file_bytes", "ensure_directories"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=False)

    with pytest.raises(education_teaching_storage.TeachingPackageStorageError):
        await education_teaching_storage.stage_teaching_inputs(_job(), sandbox)



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
        "generation_job_id": "5e3a0b43-8378-4b6c-926f-0f053577501d",
    }
    content = "# 世界运动\n\n课程内容。\n".encode()

    stored = await education_teaching_storage.write_kp_lesson_revision(
        job,
        content,
    )

    expected_key = (
        "education/household-1/english-2/v1/structures/v1/"
        "units/01-unit-1-sports/knowledge-points/02-world-game/"
        f"lessons/{sha256(content).hexdigest()}/lesson.md"
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
async def test_write_generic_kp_lesson_revision_uses_stable_content_node_path(
    monkeypatch,
) -> None:
    uploads: list[tuple[str, bytes, str]] = []

    async def put(key: str, content: bytes, content_type: str) -> None:
        uploads.append((key, content, content_type))

    monkeypatch.setattr(education_teaching_storage, "_put", put)
    node_id = "f5761267-11d1-4977-8107-e2671c99a2f0"
    job = {
        **_job(),
        "structure_sequence": 2,
        "content_node_id": node_id,
        "knowledge_point_id": "11111111-1111-4111-8111-111111111111",
        "candidate_key": "unit-1-reading-kp-1",
        "generation_job_id": "5e3a0b43-8378-4b6c-926f-0f053577501d",
    }
    content = "# Generic lesson\n\nNode-scoped content.\n".encode()

    content_sha256 = sha256(content).hexdigest()
    content_key = education_teaching_storage.kp_lesson_content_key(
        job,
        content_sha256=content_sha256,
    )
    stored = await education_teaching_storage.write_kp_lesson_revision(job, content)

    expected_key = (
        "education/household-1/english-2/v1/structures/v2/"
        f"content-nodes/{node_id}/knowledge-points/"
        "11111111-1111-4111-8111-111111111111-"
        f"{sha256(b'unit-1-reading-kp-1').hexdigest()}/"
        f"lessons/{content_sha256}/lesson.md"
    )
    assert content_key == expected_key
    assert stored == {
        "content_key": expected_key,
        "content_sha256": sha256(content).hexdigest(),
        "size_bytes": len(content),
    }
    assert uploads == [(expected_key, content, "text/markdown; charset=utf-8")]


@pytest.mark.asyncio
async def test_generic_lesson_keys_do_not_collide_for_long_candidate_keys(
    monkeypatch,
) -> None:
    uploads: list[tuple[str, bytes, str]] = []

    async def put(key: str, content: bytes, content_type: str) -> None:
        uploads.append((key, content, content_type))

    monkeypatch.setattr(education_teaching_storage, "_put", put)
    common = {
        **_job(),
        "structure_sequence": 2,
        "content_node_id": "f5761267-11d1-4977-8107-e2671c99a2f0",
        "generation_job_id": "5e3a0b43-8378-4b6c-926f-0f053577501d",
    }
    first_job = {
        **common,
        "knowledge_point_id": "11111111-1111-4111-8111-111111111111",
        "candidate_key": "x" * 81 + "A",
    }
    second_job = {
        **common,
        "knowledge_point_id": "22222222-2222-4222-8222-222222222222",
        "candidate_key": "x" * 81 + "B",
    }

    first_key = education_teaching_storage.kp_lesson_content_key(
        first_job,
        content_sha256=sha256(b"# First\n").hexdigest(),
    )
    second_key = education_teaching_storage.kp_lesson_content_key(
        second_job,
        content_sha256=sha256(b"# Second\n").hexdigest(),
    )
    assert first_key != second_key

    first, second = await asyncio.gather(
        education_teaching_storage.write_kp_lesson_revision(
            first_job,
            b"# First\n",
        ),
        education_teaching_storage.write_kp_lesson_revision(
            second_job,
            b"# Second\n",
        ),
    )

    assert first["content_key"] == first_key
    assert second["content_key"] == second_key
    assert len({key for key, _content, _content_type in uploads}) == 2


@pytest.mark.asyncio
async def test_write_generic_lesson_revision_reuses_duplicate_content(
    monkeypatch,
) -> None:
    objects: dict[str, bytes] = {}
    uploads: list[str] = []

    async def put(key: str, content: bytes, content_type: str) -> None:
        del content_type
        objects[key] = content
        uploads.append(key)

    monkeypatch.setattr(education_teaching_storage, "_put", put)
    monkeypatch.setattr(
        education_teaching_storage,
        "get_bytes",
        lambda key: objects.get(key),
    )
    job = {
        **_job(),
        "structure_sequence": 2,
        "content_node_id": "f5761267-11d1-4977-8107-e2671c99a2f0",
        "knowledge_point_id": "11111111-1111-4111-8111-111111111111",
        "candidate_key": "stable-content",
        "generation_job_id": "5e3a0b43-8378-4b6c-926f-0f053577501d",
    }
    content = b"# Stable lesson\n"

    first = await education_teaching_storage.write_kp_lesson_revision(job, content)
    second = await education_teaching_storage.write_kp_lesson_revision(job, content)

    assert first == second
    assert uploads == [first["content_key"]]


@pytest.mark.asyncio
async def test_stage_kp_lesson_inputs_contains_only_target_context():
    sandbox = AsyncMock(spec=["aupload_file_bytes", "ensure_directories"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)
    sandbox.ensure_directories = AsyncMock()

    await education_teaching_storage.stage_kp_lesson_inputs(
        {
            "generation_job_id": "5e3a0b43-8378-4b6c-926f-0f053577501d",
            "knowledge_point_id": "kp-1",
            "knowledge_point_title": "世界运动",
            "knowledge_point_scope_slot": "reading_a",
            "unit_title": "Unit 1",
            "auto_grading": False,
            "knowledge_point_source_refs": [
                {"source_id": "source-1", "start": 0, "end": 40}
            ],
        },
        "# Unit 1\n\nsource excerpt",
        "# Reading knowledge",
        sandbox,
    )

    uploaded = {
        call.args[0]: call.args[1]
        for call in sandbox.aupload_file_bytes.await_args_list
    }
    root = "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/"
    assert uploaded[f"{root}inputs/readings/reading_a.md"] == b"# Unit 1\n\nsource excerpt"
    assert uploaded[f"{root}inputs/chapters/reading_a-knowledge.md"] == b"# Reading knowledge"
    manifest = json.loads(uploaded[f"{root}inputs/manifest.json"])
    assert manifest["knowledge_point_id"] == "kp-1"
    assert manifest["scope_slot"] == "reading_a"
    assert manifest["auto_grading"] is False


@pytest.mark.asyncio
async def test_stage_generic_kp_lesson_uses_node_specific_paths():
    sandbox = AsyncMock(spec=["aupload_file_bytes", "ensure_directories"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)
    sandbox.ensure_directories = AsyncMock()
    node_id = "f5761267-11d1-4977-8107-e2671c99a2f0"

    await education_teaching_storage.stage_kp_lesson_inputs(
        {
            "generation_job_id": "5e3a0b43-8378-4b6c-926f-0f053577501d",
            "knowledge_point_id": "kp-1",
            "knowledge_point_title": "世界运动",
            "content_node_id": node_id,
            "content_node_title": "The World's Game",
            "auto_grading": False,
            "knowledge_point_source_refs": [
                {"source_id": "source-1", "char_start": 0, "char_end": 40}
            ],
        },
        "# The World's Game\n\nsource excerpt",
        "# Node knowledge",
        sandbox,
    )

    uploaded = {
        call.args[0]: call.args[1]
        for call in sandbox.aupload_file_bytes.await_args_list
    }
    root = "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/"
    assert uploaded[f"{root}inputs/content-nodes/{node_id}.md"] == (
        b"# The World's Game\n\nsource excerpt"
    )
    assert uploaded[f"{root}inputs/chapters/{node_id}-knowledge.md"] == (
        b"# Node knowledge"
    )
    manifest = json.loads(uploaded[f"{root}inputs/manifest.json"])
    assert manifest["format"] == "langalpha-managed-kp-lesson-input/v2"
    assert manifest["source_kind"] == "content_node"
    assert manifest["content_node_id"] == node_id
    assert "scope_slot" not in manifest


@pytest.mark.asyncio
async def test_stage_generic_kp_lesson_allows_missing_or_empty_source_refs():
    sandbox = AsyncMock(spec=["aupload_file_bytes", "ensure_directories"])
    sandbox.aupload_file_bytes = AsyncMock(return_value=True)
    sandbox.ensure_directories = AsyncMock()
    node_id = "f5761267-11d1-4977-8107-e2671c99a2f0"

    await education_teaching_storage.stage_kp_lesson_inputs(
        {
            "generation_job_id": "5e3a0b43-8378-4b6c-926f-0f053577501d",
            "knowledge_point_id": "kp-1",
            "knowledge_point_title": "世界运动",
            "content_node_id": node_id,
            "content_node_title": "The World's Game",
            "auto_grading": False,
        },
        "# Node source fallback",
        "# Node knowledge",
        sandbox,
    )

    uploaded = {
        call.args[0]: call.args[1]
        for call in sandbox.aupload_file_bytes.await_args_list
    }
    root = "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/"
    manifest = json.loads(uploaded[f"{root}inputs/manifest.json"])
    assert manifest["source_kind"] == "content_node"
    assert manifest["source_refs"] == []


@pytest.mark.asyncio
async def test_read_content_node_asset_verifies_hash_and_size(monkeypatch):
    async def to_thread(function, *args):
        return function(*args)

    content = b"# Node knowledge\n"
    monkeypatch.setattr(education_teaching_storage.asyncio, "to_thread", to_thread)
    monkeypatch.setattr(
        education_teaching_storage,
        "get_bytes",
        lambda _key: content,
    )

    loaded = await education_teaching_storage.read_content_node_asset(
        {
            "content_asset_key": (
                "education/household/book/v1/book-packages/job/"
                "assets/chapters/reading/knowledge.md"
            ),
            "content_asset_sha256": sha256(content).hexdigest(),
            "content_asset_size_bytes": len(content),
        }
    )

    assert loaded == "# Node knowledge\n"


@pytest.mark.asyncio
async def test_read_reading_asset_knowledge_verifies_manifest_hash(monkeypatch):
    content = b"# Reading knowledge\n"
    job = {
        "book_asset_prefix": "education/household/book/readings",
        "book_asset_manifest": {
            "format": "langalpha-managed-reading-assets/v2",
            "readings": [
                {
                    "unit_id": "unit-1",
                    "slot": "reading_a",
                    "title": "The World's Game",
                    "files": {
                        "knowledge": {
                            "path": "readings/01-unit/reading_a/knowledge.md",
                            "size_bytes": len(content),
                            "sha256": sha256(content).hexdigest(),
                        }
                    },
                }
            ],
        },
    }
    monkeypatch.setattr(
        education_teaching_storage,
        "get_bytes",
        lambda _key: content,
        raising=False,
    )

    loaded = await education_teaching_storage.read_reading_asset_knowledge(
        job,
        {"unit_id": "unit-1", "slot": "reading_a"},
    )

    assert loaded == "# Reading knowledge\n"


@pytest.mark.asyncio
async def test_read_kp_lesson_revision_accepts_only_private_lesson_keys(monkeypatch):
    async def to_thread(function, *args):
        return function(*args)

    monkeypatch.setattr(education_teaching_storage.asyncio, "to_thread", to_thread)
    monkeypatch.setattr(
        education_teaching_storage,
        "get_bytes",
        lambda _key: b"# Lesson\n",
    )

    content = await education_teaching_storage.read_kp_lesson_revision(
        "education/household/book/v1/structures/v1/content-nodes/"
        "f5761267-11d1-4977-8107-e2671c99a2f0/knowledge-points/"
        f"unit-1-kp-1/lessons/{sha256(b'# Lesson\n').hexdigest()}/lesson.md",
        expected_sha256=sha256(b"# Lesson\n").hexdigest(),
        expected_size=len(b"# Lesson\n"),
    )

    assert content == b"# Lesson\n"
    with pytest.raises(
        education_teaching_storage.TeachingPackageStorageError,
        match="hash mismatch",
    ):
        await education_teaching_storage.read_kp_lesson_revision(
            "education/household/book/v1/structures/v1/lessons/"
            f"{sha256(b'# Lesson\n').hexdigest()}/lesson.md",
            expected_sha256="a" * 64,
            expected_size=len(b"# Lesson\n"),
        )
    with pytest.raises(
        education_teaching_storage.TeachingPackageStorageError,
        match="size mismatch",
    ):
        await education_teaching_storage.read_kp_lesson_revision(
            "education/household/book/v1/structures/v1/lessons/"
            f"{sha256(b'# Lesson\n').hexdigest()}/lesson.md",
            expected_sha256=sha256(b"# Lesson\n").hexdigest(),
            expected_size=len(b"# Lesson\n") + 1,
        )
    with pytest.raises(education_teaching_storage.TeachingPackageStorageError):
        await education_teaching_storage.read_kp_lesson_revision(
            "education/../secret"
        )


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


@pytest.mark.asyncio
async def test_book_pipeline_checkpoint_bundle_archives_fixed_chapter_outputs(
    monkeypatch,
) -> None:
    job = {
        **_job(),
        "generation_job_id": "5e3a0b43-8378-4b6c-926f-0f053577501d",
        "version_id": "version-1",
        "latest_attempt_id": "6f3f2de2-5c58-4bc2-84bc-95e97acd37f6",
    }
    attempt_id = "6f3f2de2-5c58-4bc2-84bc-95e97acd37f6"
    sandbox = AsyncMock()
    sandbox.adownload_file_bytes.side_effect = [
        b'{"format":"langalpha-book-package/v1","content_nodes":[]}',
        b'{"format":"langalpha-book-package/v1","content_nodes":[]}',
        None,
        None,
    ]
    put = AsyncMock()
    monkeypatch.setattr(education_teaching_storage, "_put", put)

    bundle = await education_teaching_storage.write_book_pipeline_checkpoint_bundle(
        job,
        attempt_id,
        sandbox,
    )

    assert bundle["manifest"]["format"] == ("langalpha-book-pipeline-checkpoint/v1")
    assert bundle["manifest"]["generation_job_id"] == job["generation_job_id"]
    assert bundle["manifest"]["version_id"] == job["version_id"]
    assert bundle["manifest"]["attempt_id"] == attempt_id
    assert set(bundle["manifest"]["files"]) == {
        "outputs/book_package.json",
        "outputs/content_tree.json",
    }
    assert [call.args[0] for call in put.await_args_list][:2] == [
        f"{bundle['prefix']}/book_package.json",
        f"{bundle['prefix']}/content_tree.json",
    ]
    assert put.await_args_list[-1].args[0] == f"{bundle['prefix']}/manifest.json"


@pytest.mark.asyncio
async def test_book_pipeline_checkpoint_stage_restores_only_fixed_outputs(
    monkeypatch,
) -> None:
    job = {
        **_job(),
        "generation_job_id": "5e3a0b43-8378-4b6c-926f-0f053577501d",
        "version_id": "version-1",
        "latest_attempt_id": "6f3f2de2-5c58-4bc2-84bc-95e97acd37f6",
        "checkpoint_bundle_prefix": (
            "education/household-1/english-2/v1/book-pipeline-checkpoints/"
            "5e3a0b43-8378-4b6c-926f-0f053577501d/"
            "6f3f2de2-5c58-4bc2-84bc-95e97acd37f6"
        ),
    }
    files = {
        "outputs/book_package.json": b"{}",
        "outputs/content_tree.json": b"{}",
    }
    prefix = job["checkpoint_bundle_prefix"]
    objects = {
        f"{prefix}/{relative.removeprefix('outputs/')}": content
        for relative, content in files.items()
    }
    objects[f"{prefix}/manifest.json"] = json.dumps(
        {
            "format": "langalpha-book-pipeline-checkpoint/v1",
            "generation_job_id": job["generation_job_id"],
            "version_id": job["version_id"],
            "attempt_id": job["latest_attempt_id"],
            "files": {
                relative: {
                    "content_key": f"{prefix}/{relative.removeprefix('outputs/')}",
                    "content_sha256": sha256(content).hexdigest(),
                    "size_bytes": len(content),
                }
                for relative, content in files.items()
            },
        }
    ).encode()
    sandbox = AsyncMock()
    sandbox.aupload_file_bytes.return_value = True

    async def to_thread(function, *args):
        return function(*args)

    monkeypatch.setattr(education_teaching_storage.asyncio, "to_thread", to_thread)
    monkeypatch.setattr(education_teaching_storage, "get_bytes", objects.get)

    uploaded = await education_teaching_storage.stage_book_pipeline_checkpoint_bundle(
        job,
        sandbox,
    )

    assert uploaded == [
        "outputs/book_package.json",
        "outputs/content_tree.json",
    ]
    assert [call.args[0] for call in sandbox.aupload_file_bytes.await_args_list] == [
        (
            "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/"
            "outputs/book_package.json"
        ),
        (
            "/managed/textbook-job/5e3a0b43-8378-4b6c-926f-0f053577501d/"
            "outputs/content_tree.json"
        ),
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    ["wrong_job", "wrong_hash", "second_hash", "wrong_key"],
)
async def test_checkpoint_stage_rejects_corrupt_or_cross_job_manifest(
    monkeypatch,
    mutation: str,
) -> None:
    attempt_id = "6f3f2de2-5c58-4bc2-84bc-95e97acd37f6"
    prefix = (
        "education/household-1/english-2/v1/book-pipeline-checkpoints/"
        "5e3a0b43-8378-4b6c-926f-0f053577501d/"
        f"{attempt_id}"
    )
    job = {
        **_job(),
        "generation_job_id": "5e3a0b43-8378-4b6c-926f-0f053577501d",
        "version_id": "version-1",
        "latest_attempt_id": attempt_id,
        "checkpoint_bundle_prefix": prefix,
    }
    files = {
        "outputs/book_package.json": b"{}",
        "outputs/content_tree.json": b"{}",
    }
    manifest = {
        "format": "langalpha-book-pipeline-checkpoint/v1",
        "generation_job_id": job["generation_job_id"],
        "version_id": job["version_id"],
        "attempt_id": attempt_id,
        "files": {
            relative: {
                "content_key": f"{prefix}/{relative.removeprefix('outputs/')}",
                "content_sha256": sha256(content).hexdigest(),
                "size_bytes": len(content),
            }
            for relative, content in files.items()
        },
    }
    if mutation == "wrong_job":
        manifest["generation_job_id"] = "11111111-1111-1111-1111-111111111111"
    elif mutation == "wrong_hash":
        manifest["files"]["outputs/book_package.json"]["content_sha256"] = "0" * 64
    elif mutation == "second_hash":
        manifest["files"]["outputs/content_tree.json"]["content_sha256"] = "0" * 64
    else:
        manifest["files"]["outputs/book_package.json"]["content_key"] = (
            "education/other/book_package.json"
        )
    objects = {
        f"{prefix}/{relative.removeprefix('outputs/')}": content
        for relative, content in files.items()
    }
    objects[f"{prefix}/manifest.json"] = json.dumps(manifest).encode()
    sandbox = AsyncMock()
    sandbox.aupload_file_bytes.return_value = True

    async def to_thread(function, *args):
        return function(*args)

    monkeypatch.setattr(education_teaching_storage.asyncio, "to_thread", to_thread)
    monkeypatch.setattr(education_teaching_storage, "get_bytes", objects.get)

    with pytest.raises(education_teaching_storage.TeachingPackageStorageError):
        await education_teaching_storage.stage_book_pipeline_checkpoint_bundle(
            job,
            sandbox,
        )

    sandbox.aupload_file_bytes.assert_not_awaited()
