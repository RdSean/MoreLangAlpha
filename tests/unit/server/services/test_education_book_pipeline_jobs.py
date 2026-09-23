"""Managed unified book-pipeline job contracts."""

import asyncio
import hashlib
import json
from unittest.mock import AsyncMock

import pytest

from src.server.services import education_book_pipeline_jobs
from src.server.services import education_teaching_storage
from src.server.services.education_textbooks import (
    TextbookNotFoundError,
    TextbookTransitionError,
)

CHECKPOINT_PREFIX = (
    "education/household/textbook/v1/book-pipeline-checkpoints/"
    "4d0112f8-0e00-4f1f-990a-4bc1b1cc20f3/"
    "6f3f2de2-5c58-4bc2-84bc-95e97acd37f6"
)


def _job(*, status: str = "queued", pause: bool = False) -> dict:
    return {
        "generation_job_id": "4d0112f8-0e00-4f1f-990a-4bc1b1cc20f3",
        "version_id": "a8e02f20-b0d8-4f85-9282-d87a3aa54c83",
        "scope": "book_pipeline",
        "structure_id": None,
        "knowledge_point_id": None,
        "status": status,
        "attempt_count": 0,
        "pause_after_chapter_analysis": pause,
        "checkpoint_bundle_prefix": None,
        "error_code": None,
        "error_message": None,
        "created_at": None,
        "updated_at": None,
        "latest_attempt_id": None,
        "root_run_id": None,
        "started_at": None,
        "heartbeat_at": None,
        "processing_profile_sha256": "b" * 64,
    }


MARKDOWN = """\
# Unit 1

Football became a global sport through trade and media.

# Unit 2

Olympic athletes train with deliberate practice.
"""

MARKDOWN_SECOND = """\
# Unit 2

Geometry connects shapes, proofs, and measurements.

# Reading C

Triangles have three angles whose measures sum to 180 degrees.
"""


def _completed_pipeline_progress_events() -> list[dict]:
    return [
        {
            "generation_job_id": "4d0112f8-0e00-4f1f-990a-4bc1b1cc20f3",
            "attempt_id": "attempt-1",
            "sequence": sequence,
            "event_key": f"{stage}:completed:attempt-1",
            "stage": stage,
            "status": "completed",
        }
        for sequence, stage in enumerate(
            (
                "chapter_analysis",
                "content_processing",
                "knowledge_point_generation",
            ),
            start=1,
        )
    ]


def _book_package() -> dict:
    first_end = MARKDOWN.index("# Unit 2")
    return {
        "format": "langalpha-book-package/v1",
        "source_revision": "frozen-revision-1",
        "content_nodes": [
            {
                "node_key": f"node-{index:02d}",
                "parent_key": None if index == 1 else "node-01",
                "node_type": "unit" if index == 1 else "reading",
                "position": index,
                "title": f"Node {index}",
                "summary": "A source-backed content node.",
                "source_refs": [
                    {
                        "source_id": "source-1",
                        "char_start": 0 if index < 8 else first_end,
                        "char_end": first_end if index < 8 else len(MARKDOWN),
                    }
                ],
            }
            for index in range(1, 13)
        ],
        "knowledge_points": [
            {
                "candidate_key": "node-02-kp-1",
                "node_key": "node-02",
                "point_type": "theme",
                "title": "Football's global reach",
                "summary": "Trade and media connected the sport.",
                "source_refs": [
                    {
                        "source_id": "source-1",
                        "char_start": MARKDOWN.index("Football"),
                        "char_end": MARKDOWN.index("\n", MARKDOWN.index("Football")),
                    }
                ],
                "confidence": 0.9,
            }
        ],
        "assets": [
            {
                "node_key": "node-02",
                "kind": "knowledge",
                "path": "outputs/book-skill/chapters/node-02/knowledge.md",
                "content_sha256": hashlib.sha256(
                    b"# Knowledge\n\nFootball and media.\n"
                ).hexdigest(),
                "size_bytes": len(b"# Knowledge\n\nFootball and media.\n"),
            }
        ],
    }


class _PackageSandbox:
    def __init__(self, files: dict[str, bytes]) -> None:
        self.files = files
        self.downloads: list[str] = []

    async def adownload_file_bytes(self, path: str) -> bytes | None:
        self.downloads.append(path)
        return self.files.get(path)


@pytest.mark.asyncio
async def test_download_book_package_outputs_uses_manifest_declared_assets_only() -> (
    None
):
    package = _book_package()
    asset_path = package["assets"][0]["path"]
    asset_bytes = b"# Knowledge\n\nFootball and media.\n"
    package_bytes = json.dumps(package).encode()
    root = education_teaching_storage.managed_job_root(_job()["generation_job_id"])
    sandbox = _PackageSandbox(
        {
            f"{root}/outputs/book_package.json": package_bytes,
            f"{root}/outputs/content_tree.json": json.dumps(
                {
                    "format": "langalpha-content-tree/v1",
                    "content_nodes": package["content_nodes"],
                }
            ).encode(),
            f"{root}/outputs/knowledge_points.json": json.dumps(
                {
                    "format": "langalpha-knowledge-points/v1",
                    "knowledge_points": package["knowledge_points"],
                }
            ).encode(),
            f"{root}/outputs/assets_manifest.json": json.dumps(
                {
                    "format": "langalpha-assets-manifest/v1",
                    "assets": [
                        *package["assets"],
                        {
                            "node_key": "node-01",
                            "kind": "package",
                            "path": "outputs/book_package.json",
                            "content_sha256": hashlib.sha256(
                                package_bytes
                            ).hexdigest(),
                            "size_bytes": len(package_bytes),
                        },
                    ],
                }
            ).encode(),
            f"{root}/{asset_path}": asset_bytes,
            f"{root}/outputs/undeclared-secret.md": b"must not be read",
        }
    )

    downloaded = await education_teaching_storage.download_book_package_outputs(
        _job()["generation_job_id"],
        sandbox,
        markdown=MARKDOWN,
    )

    assert downloaded["package"]["content_nodes"][0]["node_key"] == "node-01"
    assert downloaded["asset_files"] == {asset_path: asset_bytes}
    assert sandbox.downloads == [
        f"{root}/outputs/book_package.json",
        f"{root}/outputs/content_tree.json",
        f"{root}/outputs/knowledge_points.json",
        f"{root}/outputs/assets_manifest.json",
        f"{root}/{asset_path}",
    ]


@pytest.mark.asyncio
async def test_download_book_package_outputs_rejects_asset_digest_mismatch() -> None:
    package = _book_package()
    asset_path = package["assets"][0]["path"]
    root = education_teaching_storage.managed_job_root(_job()["generation_job_id"])
    sandbox = _PackageSandbox(
        {
            f"{root}/outputs/book_package.json": json.dumps(package).encode(),
            f"{root}/outputs/content_tree.json": json.dumps(
                {
                    "format": package["format"],
                    "content_nodes": package["content_nodes"],
                }
            ).encode(),
            f"{root}/outputs/knowledge_points.json": json.dumps(
                {
                    "format": package["format"],
                    "knowledge_points": package["knowledge_points"],
                }
            ).encode(),
            f"{root}/outputs/assets_manifest.json": json.dumps(
                {
                    "format": "langalpha-assets-manifest/v1",
                    "assets": package["assets"],
                }
            ).encode(),
            f"{root}/{asset_path}": b"tampered",
        }
    )

    with pytest.raises(
        education_teaching_storage.TeachingPackageStorageError,
        match="digest",
    ):
        await education_teaching_storage.download_book_package_outputs(
            _job()["generation_job_id"],
            sandbox,
            markdown=MARKDOWN,
        )


@pytest.mark.asyncio
async def test_download_book_package_outputs_enforces_asset_size_boundary(
    monkeypatch,
) -> None:
    asset_path = "outputs/book-skill/chapters/node-02/knowledge.md"
    asset_bytes = b"1234"
    package = _book_package()
    package["assets"][0].update(
        {
            "path": asset_path,
            "size_bytes": len(asset_bytes),
            "content_sha256": hashlib.sha256(asset_bytes).hexdigest(),
        }
    )
    root = education_teaching_storage.managed_job_root(_job()["generation_job_id"])
    files = {
        f"{root}/outputs/book_package.json": json.dumps(package).encode(),
        f"{root}/outputs/content_tree.json": json.dumps(
            {
                "format": package["format"],
                "content_nodes": package["content_nodes"],
            }
        ).encode(),
        f"{root}/outputs/knowledge_points.json": json.dumps(
            {
                "format": package["format"],
                "knowledge_points": package["knowledge_points"],
            }
        ).encode(),
        f"{root}/outputs/assets_manifest.json": json.dumps(
            {
                "format": "langalpha-assets-manifest/v1",
                "assets": package["assets"],
            }
        ).encode(),
        f"{root}/{asset_path}": asset_bytes,
    }
    monkeypatch.setattr(
        education_teaching_storage,
        "_MAX_BOOK_PACKAGE_ASSET_BYTES",
        len(asset_bytes),
    )

    downloaded = await education_teaching_storage.download_book_package_outputs(
        _job()["generation_job_id"],
        _PackageSandbox(files),
        markdown=MARKDOWN,
    )
    assert downloaded["asset_files"][asset_path] == asset_bytes

    oversized = b"12345"
    package["assets"][0].update(
        {
            "size_bytes": len(oversized),
            "content_sha256": hashlib.sha256(oversized).hexdigest(),
        }
    )
    files[f"{root}/outputs/book_package.json"] = json.dumps(package).encode()
    files[f"{root}/outputs/content_tree.json"] = json.dumps(
        {"format": package["format"], "content_nodes": package["content_nodes"]}
    ).encode()
    files[f"{root}/outputs/knowledge_points.json"] = json.dumps(
        {
            "format": package["format"],
            "knowledge_points": package["knowledge_points"],
        }
    ).encode()
    files[f"{root}/outputs/assets_manifest.json"] = json.dumps(
        {"format": "langalpha-assets-manifest/v1", "assets": package["assets"]}
    ).encode()
    files[f"{root}/{asset_path}"] = oversized

    with pytest.raises(
        education_teaching_storage.TeachingPackageStorageError,
        match="too large",
    ):
        await education_teaching_storage.download_book_package_outputs(
            _job()["generation_job_id"],
            _PackageSandbox(files),
            markdown=MARKDOWN,
        )


@pytest.mark.asyncio
async def test_download_book_package_outputs_supports_multiple_sources() -> None:
    package = {
        "format": "langalpha-book-package/v1",
        "source_revision": "multi-source-revision",
        "content_nodes": [
            {
                "node_key": "source-one",
                "parent_key": None,
                "node_type": "unit",
                "position": 1,
                "title": "Source one",
                "summary": "",
                "source_refs": [
                    {
                        "source_id": "source-1",
                        "char_start": 0,
                        "char_end": len(MARKDOWN),
                    }
                ],
            },
            {
                "node_key": "source-two",
                "parent_key": "source-one",
                "node_type": "reading",
                "position": 1,
                "title": "Source two",
                "summary": "",
                "source_refs": [
                    {
                        "source_id": "source-2",
                        "char_start": 0,
                        "char_end": len(MARKDOWN_SECOND),
                    }
                ],
            },
        ],
        "knowledge_points": [],
        "assets": [],
    }
    root = education_teaching_storage.managed_job_root(_job()["generation_job_id"])
    sandbox = _PackageSandbox(
        {
            f"{root}/outputs/book_package.json": json.dumps(package).encode(),
            f"{root}/outputs/content_tree.json": json.dumps(
                {
                    "format": package["format"],
                    "content_nodes": package["content_nodes"],
                }
            ).encode(),
            f"{root}/outputs/knowledge_points.json": json.dumps(
                {
                    "format": package["format"],
                    "knowledge_points": [],
                }
            ).encode(),
            f"{root}/outputs/assets_manifest.json": json.dumps(
                {
                    "format": "langalpha-assets-manifest/v1",
                    "assets": [],
                }
            ).encode(),
        }
    )

    downloaded = await education_teaching_storage.download_book_package_outputs(
        _job()["generation_job_id"],
        sandbox,
        markdown_by_source={
            "source-1": MARKDOWN,
            "source-2": MARKDOWN_SECOND,
        },
    )

    assert downloaded["package"]["content_nodes"][0]["source_refs"][0][
        "quote"
    ].startswith("# Unit 1")
    assert downloaded["package"]["content_nodes"][1]["source_refs"][0][
        "quote"
    ].startswith("# Unit 2")


@pytest.mark.asyncio
async def test_write_book_package_bundle_archives_immutable_keys_and_hashes(
    monkeypatch,
) -> None:
    job = {
        **_job(),
        "household_id": "household",
        "slug": "textbook",
        "content_version_sequence": 2,
    }
    raw_files = {
        "outputs/book_package.json": b'{"format":"package"}',
        "outputs/content_tree.json": b'{"content_nodes":[]}',
        "outputs/knowledge_points.json": b'{"knowledge_points":[]}',
        "outputs/assets_manifest.json": b'{"assets":[]}',
    }
    asset_path = "outputs/book-skill/chapters/node-1/knowledge.md"
    asset_bytes = b"# Knowledge\n"
    written: list[tuple[str, bytes]] = []

    async def fake_put(key, content, _content_type):
        written.append((key, content))

    monkeypatch.setattr(
        education_teaching_storage,
        "_put",
        fake_put,
    )

    result = await education_teaching_storage.write_book_package_bundle(
        job,
        {
            "raw_files": raw_files,
            "asset_files": {asset_path: asset_bytes},
            "package": {
                "source_revision": "revision-2",
                "assets": [{"path": asset_path}],
            },
        },
    )

    expected_prefix = (
        f"education/household/textbook/v2/book-packages/{job['generation_job_id']}"
    )
    assert result["prefix"] == expected_prefix
    assert [key for key, _content in written] == [
        f"{expected_prefix}/book_package.json",
        f"{expected_prefix}/content_tree.json",
        f"{expected_prefix}/knowledge_points.json",
        f"{expected_prefix}/assets_manifest.json",
        f"{expected_prefix}/assets/book-skill/chapters/node-1/knowledge.md",
        f"{expected_prefix}/manifest.json",
    ]
    assert result["asset_content_keys"] == {
        asset_path: (
            f"{expected_prefix}/assets/book-skill/chapters/node-1/knowledge.md"
        )
    }
    for relative_path, content in raw_files.items():
        manifest_file = result["manifest"]["files"][relative_path]
        assert manifest_file["size_bytes"] == len(content)
        assert manifest_file["content_sha256"] == hashlib.sha256(content).hexdigest()
    assert result["manifest"]["assets"] == [
        {
            "path": asset_path,
            "content_key": (
                f"{expected_prefix}/assets/book-skill/chapters/node-1/knowledge.md"
            ),
            "content_sha256": hashlib.sha256(asset_bytes).hexdigest(),
            "size_bytes": len(asset_bytes),
        }
    ]


@pytest.mark.asyncio
async def test_import_book_package_persists_normalized_tree_candidates_and_assets(
    monkeypatch,
) -> None:
    downloaded = {
        "package": _book_package(),
        "raw_files": {
            "outputs/book_package.json": b"{}",
            "outputs/content_tree.json": b"{}",
            "outputs/knowledge_points.json": b"{}",
            "outputs/assets_manifest.json": b"{}",
        },
        "asset_files": {
            "outputs/book-skill/chapters/node-02/knowledge.md": (
                b"# Knowledge\n\nFootball and media.\n"
            )
        },
        "warnings": [],
    }
    stored: dict[str, object] = {}

    async def fake_download(*_args, **_kwargs):
        return downloaded

    async def fake_write(job, bundle):
        stored["write_job"] = job
        stored["write_bundle"] = bundle
        return {
            "prefix": "education/household/textbook/v1/book-packages/job-1",
            "manifest": {"format": "langalpha-book-package-bundle/v1"},
            "asset_content_keys": {
                "outputs/book-skill/chapters/node-02/knowledge.md": (
                    "education/household/textbook/v1/book-packages/job-1/"
                    "assets/book-skill/chapters/node-02/knowledge.md"
                )
            },
        }

    async def fake_complete(**kwargs):
        stored["complete"] = kwargs
        return {
            "structure_id": "structure-1",
            "node_count": len(kwargs["package"]["content_nodes"]),
            "knowledge_point_count": len(kwargs["package"]["knowledge_points"]),
            "asset_count": len(kwargs["package"]["assets"]),
            "status": "review",
        }

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "download_book_package_outputs",
        fake_download,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "write_book_package_bundle",
        fake_write,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "complete_book_pipeline_import",
        fake_complete,
    )

    result = await education_book_pipeline_jobs.import_book_package(
        {
            **_job(status="running"),
            "parent_user_id": "parent-1",
            "latest_attempt_id": "attempt-1",
            "attempt_id": "attempt-1",
            "frozen_input": {
                "sources": [
                    {
                        "source_id": "source-1",
                        "markdown": MARKDOWN,
                    }
                ]
            },
        },
        object(),
    )

    assert result["node_count"] == 12
    assert result["knowledge_point_count"] > 0
    assert result["asset_count"] > 0
    assert stored["complete"]["package"]["knowledge_points"][0]["origin"] == "generated"
    assert (
        stored["complete"]["package"]["knowledge_points"][0]["candidate_status"]
        == "pending"
    )


@pytest.mark.asyncio
async def test_import_book_package_uses_explicit_current_attempt(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_download(*_args, **_kwargs):
        return {
            "package": _book_package(),
            "raw_files": {},
            "asset_files": {},
            "warnings": [],
        }

    async def fake_write(_job, _bundle):
        return {
            "prefix": "education/household/textbook/v1/book-packages/job-1",
            "manifest": {"format": "langalpha-book-package-bundle/v1"},
            "asset_content_keys": {
                "outputs/book-skill/chapters/node-02/knowledge.md": "education/key"
            },
        }

    async def fake_complete(**kwargs):
        captured.update(kwargs)
        return {
            "structure_id": "structure-1",
            "node_count": len(kwargs["package"]["content_nodes"]),
            "knowledge_point_count": 1,
            "asset_count": 1,
            "status": "review",
        }

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "download_book_package_outputs",
        fake_download,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "write_book_package_bundle",
        fake_write,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "complete_book_pipeline_import",
        fake_complete,
    )

    await education_book_pipeline_jobs.import_book_package(
        {
            **_job(status="running"),
            "parent_user_id": "parent-1",
            "latest_attempt_id": "attempt-old-completed",
            "attempt_id": "attempt-new-running",
            "frozen_input": {
                "sources": [{"source_id": "source-1", "markdown": MARKDOWN}]
            },
        },
        object(),
    )

    assert captured["attempt_id"] == "attempt-new-running"


@pytest.mark.asyncio
async def test_finalize_book_pipeline_imports_and_completes(monkeypatch) -> None:
    imported: dict[str, object] = {}
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "list_generation_progress_events",
        AsyncMock(return_value=_completed_pipeline_progress_events()),
    )

    async def fake_import(job, sandbox, *, frozen_input=None):
        imported.update(
            {
                "job": job,
                "sandbox": sandbox,
                "frozen_input": frozen_input,
            }
        )
        return {
            "structure_id": "structure-1",
            "job_status": "completed",
            "node_count": 12,
            "knowledge_point_count": 3,
            "asset_count": 2,
        }

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "import_book_package",
        fake_import,
    )

    frozen_input = {"sources": [{"source_id": "source-1", "markdown": MARKDOWN}]}
    result = await education_book_pipeline_jobs.finalize_book_pipeline_generation(
        job={
            **_job(status="running"),
            "parent_user_id": "parent-1",
            "latest_attempt_id": "attempt-1",
            "attempt_id": "attempt-1",
        },
        frozen_input=frozen_input,
        attempt_id="attempt-1",
        root_run_id="run-1",
        sandbox=object(),
        terminal_status="completed",
        terminal_error=None,
    )

    assert result["status"] == "review"
    assert imported["job"]["attempt_id"] == "attempt-1"


@pytest.mark.asyncio
async def test_finalize_book_pipeline_failure_settles_failed_job(monkeypatch) -> None:
    settled: dict[str, object] = {}

    async def fake_settle(**kwargs):
        settled.update(kwargs)
        return {"status": kwargs["status"]}

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "settle_generation_job",
        fake_settle,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "import_book_package",
        AsyncMock(side_effect=AssertionError("must not import failed run")),
    )

    result = await education_book_pipeline_jobs.finalize_book_pipeline_generation(
        job=_job(status="running"),
        frozen_input={"sources": []},
        attempt_id="attempt-1",
        root_run_id="run-1",
        sandbox=object(),
        terminal_status="failed",
        terminal_error="model failed",
    )

    assert result["status"] == "failed"
    assert settled["error_code"] == "managed_book_pipeline_failed"
    assert settled["attempt_id"] == "attempt-1"


@pytest.mark.asyncio
async def test_finalize_book_pipeline_invalid_package_settles_invalid(
    monkeypatch,
) -> None:
    settled: dict[str, object] = {}

    async def fake_import(*_args, **_kwargs):
        raise education_teaching_storage.TeachingPackageStorageError("invalid package")

    async def fake_settle(**kwargs):
        settled.update(kwargs)
        return {"status": kwargs["status"]}

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "import_book_package",
        fake_import,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "list_generation_progress_events",
        AsyncMock(return_value=_completed_pipeline_progress_events()),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "settle_generation_job",
        fake_settle,
    )

    result = await education_book_pipeline_jobs.finalize_book_pipeline_generation(
        job=_job(status="running"),
        frozen_input={"sources": []},
        attempt_id="attempt-1",
        root_run_id="run-1",
        sandbox=object(),
        terminal_status="completed",
        terminal_error=None,
    )

    assert result["status"] == "failed"
    assert settled["error_code"] == "managed_book_pipeline_invalid"


@pytest.mark.asyncio
async def test_finalize_book_pipeline_requires_durable_completed_stages(
    monkeypatch,
) -> None:
    settled: dict[str, object] = {}
    events = _completed_pipeline_progress_events()
    events = [
        event
        for event in events
        if event["stage"] != "chapter_analysis"
    ]

    async def fake_settle(**kwargs):
        settled.update(kwargs)
        return {"status": kwargs["status"]}

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "list_generation_progress_events",
        AsyncMock(return_value=events),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "settle_generation_job",
        fake_settle,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "import_book_package",
        AsyncMock(side_effect=AssertionError("must not import missing stages")),
    )

    result = await education_book_pipeline_jobs.finalize_book_pipeline_generation(
        job=_job(status="running"),
        frozen_input={"sources": []},
        attempt_id="attempt-1",
        root_run_id="run-1",
        sandbox=object(),
        terminal_status="completed",
        terminal_error=None,
    )

    assert result["status"] == "failed"
    assert settled["error_code"] == "managed_book_pipeline_incomplete_progress"


@pytest.mark.asyncio
async def test_finalize_book_pipeline_rejects_parser_rejected_stage_events(
    monkeypatch,
) -> None:
    settled: dict[str, object] = {}
    events = _completed_pipeline_progress_events()
    for event in events:
        event["event_key"] = f"probe:noop:{event['stage']}"

    async def fake_settle(**kwargs):
        settled.update(kwargs)
        return {"status": kwargs["status"]}

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "list_generation_progress_events",
        AsyncMock(return_value=events),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "settle_generation_job",
        fake_settle,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "import_book_package",
        AsyncMock(side_effect=AssertionError("must not trust rejected rows")),
    )

    result = await education_book_pipeline_jobs.finalize_book_pipeline_generation(
        job=_job(status="running"),
        frozen_input={"sources": []},
        attempt_id="attempt-1",
        root_run_id="run-1",
        sandbox=object(),
        terminal_status="completed",
        terminal_error=None,
    )

    assert result["status"] == "failed"
    assert settled["error_code"] == "managed_book_pipeline_incomplete_progress"


@pytest.mark.asyncio
async def test_finalize_book_pipeline_requires_current_attempt_stage_events(
    monkeypatch,
) -> None:
    settled: dict[str, object] = {}
    events = _completed_pipeline_progress_events()
    for event in events:
        event["attempt_id"] = "attempt-old"

    async def fake_settle(**kwargs):
        settled.update(kwargs)
        return {"status": kwargs["status"]}

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "list_generation_progress_events",
        AsyncMock(return_value=events),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "settle_generation_job",
        fake_settle,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "import_book_package",
        AsyncMock(side_effect=AssertionError("must not trust old attempt rows")),
    )

    result = await education_book_pipeline_jobs.finalize_book_pipeline_generation(
        job=_job(status="running"),
        frozen_input={"sources": []},
        attempt_id="attempt-1",
        root_run_id="run-1",
        sandbox=object(),
        terminal_status="completed",
        terminal_error=None,
    )

    assert result["status"] == "failed"
    assert settled["error_code"] == "managed_book_pipeline_incomplete_progress"


@pytest.mark.asyncio
async def test_finalize_book_pipeline_continuation_uses_checkpoint_chapter_attempt(
    monkeypatch,
) -> None:
    checkpoint_attempt_id = CHECKPOINT_PREFIX.rsplit("/", 1)[-1]
    events = _completed_pipeline_progress_events()
    for event in events:
        event["attempt_id"] = (
            checkpoint_attempt_id
            if event["stage"] == "chapter_analysis"
            else "attempt-1"
        )
    import_package = AsyncMock(
        return_value={
            "status": "review",
            "job_status": "completed",
        }
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "list_generation_progress_events",
        AsyncMock(return_value=events),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "import_book_package",
        import_package,
    )

    result = await education_book_pipeline_jobs.finalize_book_pipeline_generation(
        job={
            **_job(status="running"),
            "checkpoint_bundle_prefix": CHECKPOINT_PREFIX,
        },
        frozen_input={"sources": []},
        attempt_id="attempt-1",
        root_run_id="run-1",
        sandbox=object(),
        terminal_status="completed",
        terminal_error=None,
    )

    assert result["status"] == "review"
    import_package.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_book_pipeline_rejects_unbound_checkpoint_chapter(
    monkeypatch,
) -> None:
    settled: dict[str, object] = {}
    events = _completed_pipeline_progress_events()
    events[0]["attempt_id"] = "unrelated-old-attempt"

    async def fake_settle(**kwargs):
        settled.update(kwargs)
        return {"status": kwargs["status"]}

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "list_generation_progress_events",
        AsyncMock(return_value=events),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "settle_generation_job",
        fake_settle,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "import_book_package",
        AsyncMock(side_effect=AssertionError("must not trust unrelated checkpoint")),
    )

    result = await education_book_pipeline_jobs.finalize_book_pipeline_generation(
        job={
            **_job(status="running"),
            "checkpoint_bundle_prefix": CHECKPOINT_PREFIX,
        },
        frozen_input={"sources": []},
        attempt_id="attempt-1",
        root_run_id="run-1",
        sandbox=object(),
        terminal_status="completed",
        terminal_error=None,
    )

    assert result["status"] == "failed"
    assert settled["error_code"] == "managed_book_pipeline_incomplete_progress"


@pytest.mark.asyncio
async def test_import_book_package_supports_multiple_sources(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_download(*_args, **kwargs):
        captured.update(kwargs)
        package = {
            **_book_package(),
            "content_nodes": [
                {
                    "node_key": "node-01",
                    "parent_key": None,
                    "node_type": "unit",
                    "position": 1,
                    "title": "Source one",
                    "summary": "",
                    "source_refs": [
                        {
                            "source_id": "source-1",
                            "char_start": 0,
                            "char_end": len(MARKDOWN),
                        }
                    ],
                },
                {
                    "node_key": "node-02",
                    "parent_key": "node-01",
                    "node_type": "reading",
                    "position": 1,
                    "title": "Source two",
                    "summary": "",
                    "source_refs": [
                        {
                            "source_id": "source-2",
                            "char_start": 0,
                            "char_end": len(MARKDOWN_SECOND),
                        }
                    ],
                },
            ],
            "knowledge_points": [],
            "assets": [],
        }
        return {
            "package": package,
            "raw_files": {},
            "asset_files": {},
            "warnings": [],
        }

    async def fake_write(job, _downloaded):
        return {
            "prefix": "education/household/textbook/v1/book-packages/job-1",
            "manifest": {"format": "langalpha-book-package-bundle/v1"},
            "asset_content_keys": {},
        }

    async def fake_complete(**kwargs):
        return {
            "structure_id": "structure-1",
            "node_count": len(kwargs["package"]["content_nodes"]),
            "knowledge_point_count": 0,
            "asset_count": 0,
            "status": "review",
        }

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "download_book_package_outputs",
        fake_download,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "write_book_package_bundle",
        fake_write,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "complete_book_pipeline_import",
        fake_complete,
    )
    result = await education_book_pipeline_jobs.import_book_package(
        {
            **_job(status="running"),
            "parent_user_id": "parent-1",
            "latest_attempt_id": "attempt-1",
            "attempt_id": "attempt-1",
        },
        object(),
        frozen_input={
            "sources": [
                {
                    "source_id": "source-1",
                    "content_chapter_id": "chapter-1",
                    "markdown": MARKDOWN,
                },
                {
                    "source_id": "source-2",
                    "content_chapter_id": "chapter-2",
                    "markdown": MARKDOWN_SECOND,
                },
            ]
        },
    )

    assert result["node_count"] == 2
    assert captured["markdown_by_source"] == {
        "source-1": MARKDOWN,
        "chapter-1": MARKDOWN,
        "source-2": MARKDOWN_SECOND,
        "chapter-2": MARKDOWN_SECOND,
    }


@pytest.mark.asyncio
async def test_enqueue_and_launch_book_pipeline_launches_new_job_once(
    monkeypatch,
) -> None:
    queued = {**_job(), "reused_existing_job": False}
    launched: list[str] = []
    projected = {**_job(status="running"), "reused_existing_job": False}

    async def fake_queue(**_kwargs):
        return queued

    async def fake_launch(**kwargs):
        launched.append(str(kwargs["generation_job_id"]))
        return {"root_run_id": "run-1"}

    async def fake_get(**_kwargs):
        return projected

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "queue_book_pipeline_for_parent",
        fake_queue,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "launch_book_pipeline_generation",
        fake_launch,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_book_pipeline_job_for_parent",
        fake_get,
    )

    result = (
        await education_book_pipeline_jobs.queue_and_launch_book_pipeline_for_parent(
            parent_user_id="parent-1",
            content_version_id=_job()["version_id"],
        )
    )

    assert result["status"] == "running"
    assert launched == [_job()["generation_job_id"]]


@pytest.mark.asyncio
async def test_enqueue_and_launch_reuses_active_job_without_second_launch(
    monkeypatch,
) -> None:
    reused = {**_job(status="running"), "reused_existing_job": True}

    async def fake_queue(**_kwargs):
        return reused

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "queue_book_pipeline_for_parent",
        fake_queue,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "launch_book_pipeline_generation",
        AsyncMock(side_effect=AssertionError("must not launch reused job")),
    )

    result = (
        await education_book_pipeline_jobs.queue_and_launch_book_pipeline_for_parent(
            parent_user_id="parent-1",
            content_version_id=_job()["version_id"],
        )
    )

    assert result is reused


@pytest.mark.asyncio
async def test_launch_book_pipeline_uses_shared_runtime_spine(monkeypatch) -> None:
    job = {
        **_job(),
        "parent_user_id": "parent-1",
        "processing_brief": "只提取学生活动页。",
        "content_version_sequence": 1,
        "household_id": "household-1",
        "slug": "textbook",
    }
    session = type("Session", (), {"sandbox": object()})()
    staged: dict[str, object] = {}
    started: dict[str, object] = {}
    graphed: dict[str, object] = {}
    executed: dict[str, object] = {}
    marked: dict[str, object] = {}
    captured: dict[str, object] = {}
    collectors: list[dict[str, object]] = []
    graph = object()

    class FakeProgressCollector:
        def __init__(self, **kwargs):
            collectors.append(kwargs)

    async def get_job(**_kwargs):
        return job

    async def create_workspace(**kwargs):
        return {"workspace_id": "workspace-1", **kwargs}

    async def create_thread(**kwargs):
        return {"conversation_thread_id": "thread-1", **kwargs}

    async def claim(**_kwargs):
        return {"attempt_id": "attempt-1"}

    class FakeWorkspaceManager:
        async def provision_managed_textbook_session(self, **kwargs):
            staged["session"] = kwargs
            return session

    class FakeRunCoordinator:
        async def start_run(self, **kwargs):
            started.update(kwargs)
            return type(
                "RunHandle",
                (),
                {
                    "run_id": kwargs["run_id"],
                    "turn_index": 1,
                    "guard": object(),
                    "checkpointer": object(),
                },
            )()

    class FakeExecutor:
        async def start_run(self, **kwargs):
            executed.update(kwargs)

    class FakeRunSSEProducer:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            captured["handler"] = kwargs

        async def stream_workflow(self, **_kwargs):
            if False:
                yield "unused"

    async def fake_build_graph(**kwargs):
        graphed.update(kwargs)
        return graph, {"messages": []}, {"configurable": {"thread_id": "thread-1"}}

    async def fake_mark_attempt(**kwargs):
        marked.update(kwargs)
        return {"status": "running", **kwargs}

    finalize = AsyncMock(return_value={"status": "review"})

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_generation_job_for_parent",
        get_job,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "_create_book_pipeline_workspace",
        create_workspace,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "_create_book_pipeline_thread",
        create_thread,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "claim_book_pipeline_launch",
        AsyncMock(return_value={**job, "status": "preparing"}),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "claim_generation_job",
        claim,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "resolve_managed_education_agent_config",
        AsyncMock(return_value=object()),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs.WorkspaceManager,
        "get_instance",
        classmethod(lambda cls: FakeWorkspaceManager()),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_teaching_input_for_parent",
        AsyncMock(
            return_value={"sources": [{"source_id": "source-1", "markdown": MARKDOWN}]}
        ),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "hydrate_source_asset_manifests",
        AsyncMock(
            side_effect=lambda frozen: {
                **frozen,
                "hydrated": True,
            }
        ),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "stage_managed_teaching_skills",
        AsyncMock(),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "stage_teaching_inputs",
        AsyncMock(),
    )
    stage_checkpoint = AsyncMock()
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "stage_book_pipeline_checkpoint_bundle",
        stage_checkpoint,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "build_managed_education_graph",
        fake_build_graph,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs.RunCoordinator,
        "get_instance",
        classmethod(lambda cls: FakeRunCoordinator()),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs.LocalRunExecutor,
        "get_instance",
        classmethod(lambda cls: FakeExecutor()),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "RunSSEProducer",
        FakeRunSSEProducer,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "mark_generation_attempt_running",
        fake_mark_attempt,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "ManagedProgressCollector",
        FakeProgressCollector,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "finalize_book_pipeline_generation",
        finalize,
    )

    result = await education_book_pipeline_jobs.launch_book_pipeline_generation(
        parent_user_id="parent-1",
        generation_job_id=job["generation_job_id"],
    )

    assert result == {"root_run_id": started["run_id"]}
    assert captured["handler"]["replay_profile"] == "education_compact"
    assert staged["session"]["policy"].purpose == "book_pipeline"
    assert graphed["policy"].purpose == "book_pipeline"
    assert graphed["managed_kind"] == "education_book_pipeline"
    assert graphed["prompt"] == started["query"].content
    assert "只提取学生活动页。" in str(graphed["prompt"])
    full_prompt = str(graphed["prompt"])
    assert full_prompt.partition("。")[0] == "managed mode=full-pipeline"
    assert "mode=mode" not in full_prompt
    assert started["thread_id"] == "thread-1"
    assert marked == {
        "generation_job_id": job["generation_job_id"],
        "attempt_id": "attempt-1",
        "root_run_id": started["run_id"],
    }
    assert collectors[0]["generation_job_id"] == job["generation_job_id"]
    assert collectors[0]["attempt_id"] == "attempt-1"
    assert collectors[0]["run_id"] == started["run_id"]
    assert executed["terminal_callback"].__name__ == "on_terminal"
    task_info = type("TaskInfo", (), {"error": None})()
    await executed["terminal_callback"](task_info, "completed")
    finalize.assert_awaited_once()
    assert finalize.await_args.kwargs["attempt_id"] == "attempt-1"
    assert finalize.await_args.kwargs["root_run_id"] == started["run_id"]
    stage_checkpoint.assert_not_awaited()

    job["checkpoint_bundle_prefix"] = CHECKPOINT_PREFIX
    await education_book_pipeline_jobs.launch_book_pipeline_generation(
        parent_user_id="parent-1",
        generation_job_id=job["generation_job_id"],
    )

    stage_checkpoint.assert_awaited_once()
    continuation_prompt = str(graphed["prompt"])
    assert (
        continuation_prompt.partition("。")[0]
        == "managed mode=full-pipeline-continuation"
    )
    assert "mode=mode" not in continuation_prompt
    assert "不要重新执行 Steps 0-3" in continuation_prompt


@pytest.mark.asyncio
async def test_launch_pipeline_loser_creates_no_runtime_resources(
    monkeypatch,
) -> None:
    job = {
        **_job(status="queued"),
        "parent_user_id": "parent-1",
        "content_version_sequence": 1,
        "household_id": "household-1",
        "slug": "textbook",
    }
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_generation_job_for_parent",
        AsyncMock(return_value=job),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "claim_book_pipeline_launch",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "_create_book_pipeline_workspace",
        AsyncMock(side_effect=AssertionError("loser must not create workspace")),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "_create_book_pipeline_thread",
        AsyncMock(side_effect=AssertionError("loser must not create thread")),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "claim_generation_job",
        AsyncMock(side_effect=AssertionError("loser must not claim attempt")),
    )

    result = await education_book_pipeline_jobs.launch_book_pipeline_generation(
        parent_user_id="parent-1",
        generation_job_id=job["generation_job_id"],
    )

    assert result == {"launch_claimed": False}


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_stage", ["workspace", "thread", "attempt"])
async def test_launch_pipeline_resource_failure_closes_launch_claim(
    monkeypatch,
    failed_stage: str,
) -> None:
    job = {
        **_job(status="queued"),
        "parent_user_id": "parent-1",
        "latest_attempt_id": "attempt-old",
        "content_version_sequence": 1,
        "household_id": "household-1",
        "slug": "textbook",
    }
    fenced: dict[str, object] = {}

    async def fake_fail(**kwargs):
        fenced.update(kwargs)
        return {"status": "failed"}

    async def fake_workspace(**_kwargs):
        if failed_stage == "workspace":
            raise RuntimeError("workspace failed")
        return {"workspace_id": "workspace-1"}

    async def fake_thread(**_kwargs):
        if failed_stage == "thread":
            raise RuntimeError("thread failed")
        return {"conversation_thread_id": "thread-1"}

    async def fake_claim(**_kwargs):
        if failed_stage == "attempt":
            return None
        return {"attempt_id": "attempt-new"}

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_generation_job_for_parent",
        AsyncMock(return_value=job),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "claim_book_pipeline_launch",
        AsyncMock(return_value={**job, "status": "preparing"}),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "fail_claimed_book_pipeline_launch",
        fake_fail,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "_create_book_pipeline_workspace",
        fake_workspace,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "_create_book_pipeline_thread",
        fake_thread,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "claim_generation_job",
        fake_claim,
    )

    with pytest.raises((RuntimeError, TextbookTransitionError)):
        await education_book_pipeline_jobs.launch_book_pipeline_generation(
            parent_user_id="parent-1",
            generation_job_id=job["generation_job_id"],
        )

    assert fenced["generation_job_id"] == job["generation_job_id"]
    assert fenced["expected_latest_attempt_id"] == "attempt-old"
    assert fenced["error_code"] == "managed_book_pipeline_start_failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_stage", ["read", "hydrate"])
async def test_launch_pipeline_preparing_failure_settles_current_attempt(
    monkeypatch,
    failed_stage: str,
) -> None:
    job = {
        **_job(status="queued"),
        "parent_user_id": "parent-1",
        "content_version_sequence": 1,
        "household_id": "household-1",
        "slug": "textbook",
    }
    session = type("Session", (), {"sandbox": object()})()
    settled: dict[str, object] = {}

    async def fake_claim(**_kwargs):
        return {"attempt_id": "attempt-1"}

    class FakeWorkspaceManager:
        async def provision_managed_textbook_session(self, **_kwargs):
            return session

    async def fake_settle(**kwargs):
        settled.update(kwargs)
        return {"status": kwargs["status"]}

    async def fake_get_input(**_kwargs):
        if failed_stage == "read":
            raise RuntimeError("read failed")
        return {"sources": [{"source_id": "source-1", "markdown": MARKDOWN}]}

    async def fake_hydrate(_frozen_input):
        raise RuntimeError("hydrate failed")

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_generation_job_for_parent",
        AsyncMock(return_value=job),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "claim_book_pipeline_launch",
        AsyncMock(return_value={**job, "status": "preparing"}),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "_create_book_pipeline_workspace",
        AsyncMock(return_value={"workspace_id": "workspace-1"}),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "_create_book_pipeline_thread",
        AsyncMock(return_value={"conversation_thread_id": "thread-1"}),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "claim_generation_job",
        fake_claim,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "resolve_managed_education_agent_config",
        AsyncMock(return_value=object()),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs.WorkspaceManager,
        "get_instance",
        classmethod(lambda cls: FakeWorkspaceManager()),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_teaching_input_for_parent",
        fake_get_input,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "hydrate_source_asset_manifests",
        fake_hydrate,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "settle_generation_job",
        fake_settle,
    )

    with pytest.raises(RuntimeError, match=failed_stage):
        await education_book_pipeline_jobs.launch_book_pipeline_generation(
            parent_user_id="parent-1",
            generation_job_id=job["generation_job_id"],
        )

    assert settled["generation_job_id"] == job["generation_job_id"]
    assert settled["attempt_id"] == "attempt-1"
    assert settled["status"] == "failed"


@pytest.mark.asyncio
async def test_processing_profile_hash_tracks_processing_brief(
    monkeypatch,
) -> None:
    hashes: list[str] = []

    async def parent(_parent_user_id):
        return {"household_id": "household-1"}

    async def queue(**kwargs):
        hashes.append(str(kwargs["processing_profile_sha256"]))
        return _job(pause=bool(kwargs["pause_after_chapter_analysis"]))

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        parent,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "queue_book_pipeline_job",
        queue,
    )

    await education_book_pipeline_jobs.queue_book_pipeline_for_parent(
        parent_user_id="parent-1",
        content_version_id=_job()["version_id"],
        processing_brief=" 只提取学生活动页。 ",
    )
    await education_book_pipeline_jobs.queue_book_pipeline_for_parent(
        parent_user_id="parent-1",
        content_version_id=_job()["version_id"],
        processing_brief=" 只提取学生活动页。 ",
    )
    await education_book_pipeline_jobs.queue_book_pipeline_for_parent(
        parent_user_id="parent-1",
        content_version_id=_job()["version_id"],
        processing_brief="忽略教师指导页。",
    )

    assert len(set(hashes)) == 2


@pytest.mark.asyncio
async def test_queue_book_pipeline_returns_persisted_queued_job(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def parent(_parent_user_id):
        return {"household_id": "household-1"}

    async def queue(**kwargs):
        captured.update(kwargs)
        return _job(pause=bool(kwargs["pause_after_chapter_analysis"]))

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        parent,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "queue_book_pipeline_job",
        queue,
    )

    job = await education_book_pipeline_jobs.queue_book_pipeline_for_parent(
        parent_user_id="parent-1",
        content_version_id=_job()["version_id"],
    )

    assert job["scope"] == "book_pipeline"
    assert job["status"] == "queued"
    assert job["pause_after_chapter_analysis"] is False
    assert captured["parent_user_id"] == "parent-1"
    assert captured["processing_brief"] == ""
    assert captured["request_id"] is None
    assert len(str(captured["processing_profile_sha256"])) == 64


@pytest.mark.asyncio
async def test_queue_book_pipeline_passes_brief_and_request_id(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def parent(_parent_user_id):
        return {"household_id": "household-1"}

    async def queue(**kwargs):
        captured.update(kwargs)
        return {**_job(), "reused_existing_job": True}

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        parent,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "queue_book_pipeline_job",
        queue,
    )

    job = await education_book_pipeline_jobs.queue_book_pipeline_for_parent(
        parent_user_id="parent-1",
        content_version_id=_job()["version_id"],
        processing_brief=" 数学教材，保留公式和例题顺序。 ",
        request_id="ba8a3e5c-c0b4-4a40-95ec-349310992445",
    )

    assert captured["processing_brief"] == "数学教材，保留公式和例题顺序。"
    assert captured["request_id"] == "ba8a3e5c-c0b4-4a40-95ec-349310992445"
    assert job["reused_existing_job"] is True


@pytest.mark.asyncio
async def test_pause_checkpoint_request_is_persisted_for_live_collector(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    async def parent(_parent_user_id):
        return {"household_id": "household-1"}

    async def queue(**kwargs):
        captured.update(kwargs)
        return _job(pause=True)

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        parent,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "queue_book_pipeline_job",
        queue,
    )

    job = await education_book_pipeline_jobs.queue_book_pipeline_for_parent(
        parent_user_id="parent-1",
        content_version_id=_job()["version_id"],
        pause_after_chapter_analysis=True,
    )

    assert captured["pause_after_chapter_analysis"] is True
    assert job["pause_after_chapter_analysis"] is True


@pytest.mark.asyncio
async def test_pause_checkpoint_closes_attempt_and_sets_awaiting_review(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    async def pause(**kwargs):
        captured.update(kwargs)
        return _job(status="awaiting_review", pause=True)

    async def parent(_parent_user_id):
        return {"household_id": "household-1"}

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        parent,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "pause_book_pipeline_for_chapter_review",
        pause,
    )

    job = await education_book_pipeline_jobs.pause_book_pipeline_for_parent(
        parent_user_id="parent-1",
        generation_job_id=_job()["generation_job_id"],
        attempt_id="attempt-1",
        checkpoint_bundle_prefix=CHECKPOINT_PREFIX,
    )

    assert job["status"] == "awaiting_review"
    assert captured == {
        "parent_user_id": "parent-1",
        "generation_job_id": _job()["generation_job_id"],
        "attempt_id": "attempt-1",
        "checkpoint_bundle_prefix": CHECKPOINT_PREFIX,
    }


@pytest.mark.asyncio
async def test_pause_checkpoint_requires_nonempty_bundle_prefix(monkeypatch) -> None:
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    pause_db = AsyncMock()
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "pause_book_pipeline_for_chapter_review",
        pause_db,
    )

    with pytest.raises(TextbookTransitionError, match="checkpoint bundle"):
        await education_book_pipeline_jobs.pause_book_pipeline_for_parent(
            parent_user_id="parent-1",
            generation_job_id=_job()["generation_job_id"],
            attempt_id="attempt-1",
            checkpoint_bundle_prefix="",
        )

    pause_db.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_book_pipeline_requeues_only_waiting_checkpoint(
    monkeypatch,
) -> None:
    waiting = {
        **_job(status="awaiting_review", pause=True),
        "checkpoint_bundle_prefix": CHECKPOINT_PREFIX,
    }
    resumed = {
        **_job(status="queued", pause=False),
        "checkpoint_bundle_prefix": CHECKPOINT_PREFIX,
    }
    state = {"status": "awaiting_review"}

    async def parent(_parent_user_id):
        return {"household_id": "household-1"}

    async def get_job(**_kwargs):
        return (
            {**waiting, "status": state["status"]}
            if state["status"] == "awaiting_review"
            else resumed
        )

    async def resume(**kwargs):
        assert kwargs == {
            "parent_user_id": "parent-1",
            "generation_job_id": waiting["generation_job_id"],
        }
        return resumed

    async def launch(**kwargs):
        assert kwargs == {
            "parent_user_id": "parent-1",
            "generation_job_id": waiting["generation_job_id"],
        }
        state["status"] = "queued"
        return {"root_run_id": "continuation-run"}

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        parent,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_generation_job_for_parent",
        get_job,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "resume_book_pipeline_job",
        resume,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "launch_book_pipeline_generation",
        launch,
    )

    job = await education_book_pipeline_jobs.resume_book_pipeline_for_parent(
        parent_user_id="parent-1",
        generation_job_id=waiting["generation_job_id"],
    )

    assert job["status"] == "queued"
    assert job["pause_after_chapter_analysis"] is False


@pytest.mark.asyncio
async def test_resume_checkpoint_rejects_missing_bundle_prefix(monkeypatch) -> None:
    waiting = _job(status="awaiting_review", pause=True)

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_generation_job_for_parent",
        AsyncMock(return_value=waiting),
    )
    resume_db = AsyncMock()
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "resume_book_pipeline_job",
        resume_db,
    )

    with pytest.raises(TextbookTransitionError, match="checkpoint bundle"):
        await education_book_pipeline_jobs.resume_book_pipeline_for_parent(
            parent_user_id="parent-1",
            generation_job_id=waiting["generation_job_id"],
        )

    resume_db.assert_not_awaited()


@pytest.mark.asyncio
async def test_continuation_launch_rejects_missing_bundle_prefix(
    monkeypatch,
) -> None:
    resumed_job = {
        **_job(status="queued", pause=False),
        "attempt_count": 1,
        "checkpoint_bundle_prefix": None,
    }
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_generation_job_for_parent",
        AsyncMock(return_value=resumed_job),
    )
    claim = AsyncMock()
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "claim_book_pipeline_launch",
        claim,
    )

    with pytest.raises(TextbookTransitionError, match="checkpoint bundle"):
        await education_book_pipeline_jobs.launch_book_pipeline_generation(
            parent_user_id="parent-1",
            generation_job_id=resumed_job["generation_job_id"],
        )

    claim.assert_not_awaited()


@pytest.mark.asyncio
async def test_continuation_checkpoint_corruption_is_transition_error(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "stage_book_pipeline_checkpoint_bundle",
        AsyncMock(
            side_effect=education_teaching_storage.TeachingPackageStorageError(
                "corrupt"
            )
        ),
    )

    with pytest.raises(TextbookTransitionError, match="checkpoint is corrupt"):
        await education_book_pipeline_jobs._stage_continuation_checkpoint_bundle(
            {
                **_job(status="queued"),
                "checkpoint_bundle_prefix": CHECKPOINT_PREFIX,
            },
            object(),
        )


@pytest.mark.asyncio
async def test_checkpoint_stop_never_imports_partial_book_package(
    monkeypatch,
) -> None:
    stopped = asyncio.Event()
    stopped.set()
    settle = AsyncMock()

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "import_book_package",
        AsyncMock(side_effect=AssertionError("partial package must not import")),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "_fail_book_pipeline_attempt",
        settle,
    )

    result = await education_book_pipeline_jobs.finalize_book_pipeline_generation(
        job={
            **_job(status="awaiting_review", pause=True),
            "parent_user_id": "parent-1",
            "checkpoint_bundle_prefix": CHECKPOINT_PREFIX,
        },
        frozen_input={},
        attempt_id="attempt-1",
        root_run_id="run-1",
        sandbox=object(),
        terminal_status="completed",
        terminal_error=None,
        checkpoint_stop_event=stopped,
    )

    assert result == {"status": "awaiting_review", "job_status": "awaiting_review"}
    settle.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_book_pipeline_rejects_non_waiting_job(monkeypatch) -> None:
    async def parent(_parent_user_id):
        return {"household_id": "household-1"}

    async def get_job(**_kwargs):
        return _job(status="running")

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        parent,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_generation_job_for_parent",
        get_job,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "resume_book_pipeline_job",
        AsyncMock(side_effect=AssertionError("must not requeue")),
    )

    with pytest.raises(TextbookTransitionError):
        await education_book_pipeline_jobs.resume_book_pipeline_for_parent(
            parent_user_id="parent-1",
            generation_job_id=_job()["generation_job_id"],
        )


@pytest.mark.asyncio
async def test_get_book_pipeline_rejects_another_scope(monkeypatch) -> None:
    async def parent(_parent_user_id):
        return {"household_id": "household-1"}

    async def get_job(**_kwargs):
        return {**_job(), "scope": "structure"}

    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        parent,
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_generation_job_for_parent",
        get_job,
    )

    with pytest.raises(TextbookNotFoundError):
        await education_book_pipeline_jobs.get_book_pipeline_job_for_parent(
            parent_user_id="parent-1",
            generation_job_id=_job()["generation_job_id"],
        )


@pytest.mark.asyncio
async def test_cancel_book_pipeline_returns_terminal_job_idempotently(
    monkeypatch,
) -> None:
    terminal = {
        **_job(status="completed"),
        "cancel_mode": "terminal",
    }
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "cancel_book_pipeline_without_run_for_parent",
        AsyncMock(return_value=terminal),
    )
    cancel_workflow = AsyncMock()
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "cancel_workflow",
        cancel_workflow,
    )

    result = await education_book_pipeline_jobs.cancel_book_pipeline_for_parent(
        parent_user_id="parent-1",
        generation_job_id=terminal["generation_job_id"],
    )

    assert result["status"] == "completed"
    assert "cancel_mode" not in result
    cancel_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_book_pipeline_cancels_queued_job_without_run(
    monkeypatch,
) -> None:
    cancelled = {
        **_job(status="cancelled"),
        "cancel_mode": "cancelled",
    }
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "cancel_book_pipeline_without_run_for_parent",
        AsyncMock(return_value=cancelled),
    )
    cancel_workflow = AsyncMock()
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "cancel_workflow",
        cancel_workflow,
    )

    result = await education_book_pipeline_jobs.cancel_book_pipeline_for_parent(
        parent_user_id="parent-1",
        generation_job_id=cancelled["generation_job_id"],
    )

    assert result["status"] == "cancelled"
    cancel_workflow.assert_not_awaited()


@pytest.mark.asyncio
async def test_cancel_book_pipeline_delegates_running_job_to_workflow_cancel(
    monkeypatch,
) -> None:
    running = {
        **_job(status="running"),
        "cancel_mode": "running",
        "managed_thread_id": "thread-1",
        "root_run_id": "run-1",
    }
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "household-1"}),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "cancel_book_pipeline_without_run_for_parent",
        AsyncMock(return_value=running),
    )
    cancel_workflow = AsyncMock(return_value={"cancelled": True})
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "cancel_workflow",
        cancel_workflow,
    )

    result = await education_book_pipeline_jobs.cancel_book_pipeline_for_parent(
        parent_user_id="parent-1",
        generation_job_id=running["generation_job_id"],
    )

    assert result["status"] == "running"
    assert result["root_run_id"] == "run-1"
    cancel_workflow.assert_awaited_once_with("thread-1", "run-1")


@pytest.mark.asyncio
async def test_cancel_book_pipeline_rejects_wrong_parent(monkeypatch) -> None:
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "get_household_context_for_parent",
        AsyncMock(return_value={"household_id": "parent-household"}),
    )
    monkeypatch.setattr(
        education_book_pipeline_jobs,
        "cancel_book_pipeline_without_run_for_parent",
        AsyncMock(return_value=None),
    )

    with pytest.raises(TextbookNotFoundError):
        await education_book_pipeline_jobs.cancel_book_pipeline_for_parent(
            parent_user_id="other-parent",
            generation_job_id=_job()["generation_job_id"],
        )
