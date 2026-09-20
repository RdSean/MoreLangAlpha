"""Managed chapter asset job contracts."""

import pytest

from src.server.services import education_book_asset_jobs
from src.server.services.education_book_assets import BOOK_ASSET_FORMAT


MANIFEST = {
    "format": BOOK_ASSET_FORMAT,
    "chapter_files": ["chapters/ch01-overview.md"],
    "support_files": ["glossary.md"],
}


@pytest.mark.asyncio
async def test_queue_book_assets_creates_assets_job(monkeypatch):
    captured: dict[str, object] = {}

    async def get_structure(**_kwargs):
        return {
            "structure_id": "structure-1",
            "version_id": "version-1",
            "status": "accepted",
        }

    async def create_job(**kwargs):
        captured.update(kwargs)
        return {
            "generation_job_id": "generation-assets-1",
            "scope": "assets",
            "status": "queued",
        }

    monkeypatch.setattr(
        education_book_asset_jobs,
        "get_textbook_structure_for_parent",
        get_structure,
    )
    monkeypatch.setattr(
        education_book_asset_jobs,
        "create_generation_job",
        create_job,
    )

    queued = await education_book_asset_jobs.queue_book_assets_for_parent(
        parent_user_id="parent-1",
        structure_id="structure-1",
    )

    assert queued["generation_job_id"] == "generation-assets-1"
    assert captured["scope"] == "assets"
    assert captured["structure_id"] == "structure-1"
    assert captured["knowledge_point_id"] is None


@pytest.mark.asyncio
async def test_finalize_book_assets_archives_manifest(monkeypatch):
    stored: dict[str, object] = {}
    outputs = {"chapters/ch01-overview.md": b"# Overview\n", "glossary.md": b"# Terms\n"}

    async def download(_job_id, _sandbox):
        return MANIFEST, outputs

    async def write_bundle(job, manifest, files):
        stored["job"] = job
        stored["manifest"] = manifest
        stored["files"] = files
        return "education/household/textbook/v1/structures/v1/book-assets", {
            "format": BOOK_ASSET_FORMAT,
            "files": [],
        }

    async def complete(**kwargs):
        stored["complete"] = kwargs
        return {"structure_id": kwargs["structure_id"], "status": "completed"}

    monkeypatch.setattr(
        education_book_asset_jobs,
        "download_book_asset_outputs",
        download,
    )
    monkeypatch.setattr(
        education_book_asset_jobs,
        "write_book_asset_bundle",
        write_bundle,
    )
    monkeypatch.setattr(
        education_book_asset_jobs,
        "complete_book_asset_generation",
        complete,
    )

    result = await education_book_asset_jobs.finalize_book_asset_generation(
        job={
            "generation_job_id": "generation-assets-1",
            "structure_id": "structure-1",
            "content_version_sequence": 1,
            "structure_sequence": 1,
            "household_id": "household-1",
            "slug": "textbook",
        },
        attempt_id="attempt-1",
        root_run_id="run-1",
        sandbox=object(),
        terminal_status="completed",
        terminal_error=None,
    )

    assert result["status"] == "completed"
    assert stored["files"] == outputs
    assert stored["complete"]["bundle_prefix"].endswith("/book-assets")


def test_book_asset_prompt_is_separate_from_structure_and_lessons() -> None:
    prompt = education_book_asset_jobs.managed_book_assets_prompt(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    assert "chapters_manifest.json" in prompt
    assert "glossary.md" in prompt
    assert "不要生成 structure.json" in prompt
    assert "lesson.md" in prompt
