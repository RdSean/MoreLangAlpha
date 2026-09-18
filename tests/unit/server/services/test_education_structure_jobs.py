"""Managed structure-job orchestration contracts."""

import hashlib
import json

import pytest

from src.server.services import education_structure_jobs


FROZEN_INPUT = {
    "format": "langalpha-managed-textbook-input/v2",
    "job_id": "8a77d086-0b23-4a1e-89d0-f163fa23d5d1",
    "sources": [
        {
            "source_id": "source-1",
            "content_chapter_id": "f5761267-11d1-4977-8107-e2671c99a2f0",
            "position": 1,
            "slug": "reading-explorer",
            "title": "Reading Explorer",
            "content_sha256": hashlib.sha256(
                ("# Unit 1\n\n" + ("content " * 1_000)).encode("utf-8")
            ).hexdigest(),
            "path": "sources/01-reading-explorer.md",
            "markdown": "# Unit 1\n\n" + ("content " * 1_000),
        }
    ],
}


VALID_STRUCTURE = {
    "format": "langalpha-managed-textbook-structure/v1",
    "units": [
        {
            "position": 1,
            "slug": "unit-1-sports",
            "title": "Unit 1: Sports and Fitness",
            "summary": "Sports and fitness",
            "unit_type": "teaching",
            "confidence": 0.96,
            "source_refs": [
                {
                    "source_id": "source-1",
                    "start": 0,
                    "end": 50,
                    "quote": "Unit 1",
                }
            ],
            "knowledge_points": [
                {
                    "position": 1,
                    "slug": "world-game",
                    "title": "世界运动：足球的历史与流行原因",
                    "summary": "足球的历史与传播",
                    "confidence": 0.93,
                    "source_refs": [
                        {
                            "source_id": "source-1",
                            "start": 0,
                            "end": 40,
                        }
                    ],
                }
            ],
        },
        {
            "position": 2,
            "slug": "front-matter",
            "title": "Front Matter",
            "summary": "",
            "unit_type": "front_matter",
            "confidence": 0.9,
            "source_refs": [
                {
                    "source_id": "source-1",
                    "start": 50,
                    "end": 60,
                }
            ],
            "knowledge_points": [],
        },
    ],
}


def test_managed_structure_prompt_uses_one_output_and_forbids_forced_points() -> None:
    prompt = education_structure_jobs.managed_structure_prompt(
        "8a77d086-0b23-4a1e-89d0-f163fa23d5d1"
    )

    assert "outputs/structure.json" in prompt
    assert "book-to-skill/SKILL.md" in prompt
    assert "非教学" in prompt
    assert "不得为了满足数量" in prompt
    assert "不要生成课程、练习或教学包" in prompt


@pytest.mark.asyncio
async def test_queue_structure_generation_persists_frozen_hashes(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def fake_get_teaching_input(**kwargs):
        return dict(FROZEN_INPUT)

    async def fake_queue_textbook_structure(**kwargs):
        captured.update(kwargs)
        return {
            "structure_id": kwargs.get("structure_id", "structure-1"),
            "generation_job_id": kwargs["generation_job_id"],
            "status": "queued",
        }

    monkeypatch.setattr(
        education_structure_jobs,
        "get_teaching_input_for_parent",
        fake_get_teaching_input,
    )
    monkeypatch.setattr(
        education_structure_jobs,
        "queue_textbook_structure",
        fake_queue_textbook_structure,
    )
    monkeypatch.setattr(
        education_structure_jobs,
        "_managed_skill_hash",
        lambda _name: "c" * 64,
    )

    queued = await education_structure_jobs.queue_structure_generation_for_parent(
        parent_user_id="parent-1",
        content_version_id="version-1",
    )

    assert queued["status"] == "queued"
    assert len(captured["input_manifest_sha256"]) == 64
    assert captured["source_revision"] == captured["input_manifest_sha256"]
    assert len(captured["processing_profile_sha256"]) == 64


@pytest.mark.asyncio
async def test_finalize_structure_generation_validates_and_enters_review(
    monkeypatch,
) -> None:
    stored: dict[str, object] = {}

    async def fake_download(job_id, sandbox):
        return VALID_STRUCTURE

    async def fake_write_bundle(job, structure):
        stored["job"] = job
        stored["structure"] = structure
        return "education/household/textbook/v1/structures/v1"

    async def fake_replace(**kwargs):
        stored["replace"] = kwargs
        return []

    async def fake_complete(**kwargs):
        stored["complete"] = kwargs
        return {"structure_id": kwargs["structure_id"], "status": "review"}

    monkeypatch.setattr(
        education_structure_jobs,
        "download_structure_output",
        fake_download,
    )
    monkeypatch.setattr(
        education_structure_jobs,
        "write_structure_bundle",
        fake_write_bundle,
    )
    monkeypatch.setattr(
        education_structure_jobs,
        "replace_structure_contents",
        fake_replace,
    )
    monkeypatch.setattr(
        education_structure_jobs,
        "complete_structure_generation",
        fake_complete,
    )

    result = await education_structure_jobs.finalize_structure_generation(
        job={
            "generation_job_id": "generation-1",
            "structure_id": "structure-1",
            "household_id": "household-1",
            "slug": "textbook",
            "content_version_sequence": 1,
            "structure_sequence": 1,
        },
        frozen_input=FROZEN_INPUT,
        attempt_id="attempt-1",
        root_run_id="run-1",
        sandbox=object(),
        terminal_status="completed",
        terminal_error=None,
    )

    assert result["status"] == "review"
    assert stored["structure"]["units"][1]["knowledge_points"] == []
    assert stored["complete"]["bundle_prefix"].endswith("/structures/v1")


@pytest.mark.asyncio
async def test_finalize_structure_generation_fails_only_the_structure_job(
    monkeypatch,
) -> None:
    failed: dict[str, object] = {}
    invalid = json.loads(json.dumps(VALID_STRUCTURE))
    invalid["units"][0]["source_refs"] = []

    async def fake_download(job_id, sandbox):
        return invalid

    async def fake_fail(**kwargs):
        failed.update(kwargs)
        return {"status": kwargs["status"]}

    monkeypatch.setattr(
        education_structure_jobs,
        "download_structure_output",
        fake_download,
    )
    monkeypatch.setattr(
        education_structure_jobs,
        "fail_structure_generation",
        fake_fail,
    )
    monkeypatch.setattr(
        education_structure_jobs,
        "write_structure_bundle",
        lambda *_args, **_kwargs: None,
    )

    result = await education_structure_jobs.finalize_structure_generation(
        job={
            "generation_job_id": "generation-1",
            "structure_id": "structure-1",
        },
        frozen_input=FROZEN_INPUT,
        attempt_id="attempt-1",
        root_run_id="run-1",
        sandbox=object(),
        terminal_status="completed",
        terminal_error=None,
    )

    assert result["status"] == "failed"
    assert failed["error_code"] == "managed_structure_invalid"
    assert "结构" in failed["error_message"]
