"""Service contracts for managed textbook item execution."""

from __future__ import annotations

import hashlib
import inspect
import json
from unittest.mock import AsyncMock, Mock
from uuid import UUID

import pytest


def test_book_infrastructure_error_classification():
    import psycopg

    from ptc_agent.core.sandbox.runtime import (
        SandboxGoneError,
        SandboxTransientError,
    )
    from src.server.services import education_book_jobs
    from src.server.services.education_book_storage import BookStorageError

    assert education_book_jobs._is_book_infrastructure_error(
        BookStorageError("storage unavailable")
    )
    assert education_book_jobs._is_book_infrastructure_error(
        SandboxTransientError("transport unavailable")
    )
    assert education_book_jobs._is_book_infrastructure_error(
        SandboxGoneError("sandbox-1")
    )
    assert education_book_jobs._is_book_infrastructure_error(
        psycopg.OperationalError("database unavailable")
    )
    assert not education_book_jobs._is_book_infrastructure_error(
        ValueError("generated schema is invalid")
    )
    assert not education_book_jobs._is_book_infrastructure_error(
        RuntimeError("managed run did not produce the required output")
    )


CLAIMED = {
    "textbook_id": UUID("2d08d9e6-73e4-40d3-aa6c-8111ae754fea"),
    "job_id": UUID("9998bb1a-687a-4d45-815d-5b1dd6ed2f17"),
    "item_id": UUID("86f03a73-7604-4097-905b-768e6ad0f644"),
    "execution_id": UUID("8a77d086-0b23-4a1e-89d0-f163fa23d5d1"),
    "attempt_token": UUID("d5c87e74-fb75-4624-bb25-a36ec73a89ce"),
    "attempt": 1,
    "slug": "sample-book",
    "source_markdown_key": "education/h/textbooks/t/source/document.md",
    "source_blocks_key": "education/h/textbooks/t/source/blocks.json",
    "source_report_key": "education/h/textbooks/t/source/report.json",
    "source_asset_manifest": [],
    "source_content_sha256": "a" * 64,
    "more_to_skills_version": "2.1.0",
    "skill_sha256": "b" * 64,
    "schema_sha256": "c" * 64,
}


@pytest.fixture(autouse=True)
def _default_no_pending_book_cancellations(monkeypatch):
    from src.server.services import education_book_recovery

    monkeypatch.setattr(
        education_book_recovery,
        "list_book_jobs_pending_cancellation",
        AsyncMock(return_value=[]),
        raising=False,
    )


@pytest.mark.asyncio
async def test_failure_lock_resolves_and_locks_job_before_item_mutation():
    from src.server.database import education_book_jobs

    cursor = AsyncMock()
    cursor.fetchone.return_value = {"job_id": CLAIMED["job_id"]}

    job_id = await education_book_jobs._lock_book_job_for_item(
        cursor, item_id=CLAIMED["item_id"]
    )

    sql = cursor.execute.await_args.args[0]
    assert "JOIN education_book_job_items" in sql
    assert "FOR UPDATE OF jobs" in sql
    assert job_id == CLAIMED["job_id"]


def test_success_finalizers_lock_job_before_item_or_textbook_rows():
    from src.server.database.education_book_jobs import (
        finalize_material,
        finalize_supplementary,
    )
    from src.server.database.education_books import commit_book_structure

    for finalizer in (finalize_material, finalize_supplementary):
        source = inspect.getsource(finalizer)
        assert source.index("_lock_book_job_for_item") < source.index(
            "FROM education_book_job_items"
        )

    structure_source = inspect.getsource(commit_book_structure)
    assert structure_source.index("_lock_structure_job") < structure_source.index(
        "FROM education_book_job_items"
    )


def test_start_item_attempt_locks_job_before_updating_item():
    from src.server.database.education_book_jobs import start_item_attempt

    source = inspect.getsource(start_item_attempt)

    assert source.index("_lock_book_job_for_item") < source.index(
        "UPDATE education_book_job_items"
    )


def test_structure_execution_task_uses_structure_only_and_explicit_ids():
    from src.server.services.education_book_jobs import build_execution_task

    task = build_execution_task(
        {**CLAIMED, "operation": "structure", "kind": "structure"}
    )

    assert task["mode"] == "structure_only"
    assert task["textbook_id"] == str(CLAIMED["textbook_id"])
    assert task["job_id"] == str(CLAIMED["job_id"])
    assert task["item_id"] == str(CLAIMED["item_id"])
    assert task["execution_id"] == str(CLAIMED["execution_id"])
    assert task["attempt_token"] == str(CLAIMED["attempt_token"])
    assert task["progress"] == {
        "tool": "report_progress",
        "allowed_actions": {},
        "allowed_stages": [
            "structure_reading",
            "structure_organizing",
            "structure_splitting",
            "structure_validating",
        ],
    }
    assert task["output"]["structure"] == "outputs/sample-book/book-structure.json"
    assert "knowledge_point" not in task


def test_material_execution_task_contains_exactly_one_target_without_predecessor_gate():
    from src.server.services.education_book_jobs import build_execution_task

    task = build_execution_task(
        {
            **CLAIMED,
            "operation": "material",
            "kind": "material",
            "knowledge_point_id": UUID("9aac142f-a124-44aa-a17b-37ff8630c0a5"),
            "skill_kp_id": "u02-k03",
            "knowledge_point_json": {
                "id": "u02-k03",
                "title": "A single target",
                "anchor": {"start_line": 40, "end_line": 61},
            },
            "depth": "lesson",
            "requirements": "Include worked examples.",
        }
    )

    assert task["mode"] == "reading_material_only"
    assert task["requires_previous_material"] is False
    assert task["knowledge_point"] == {
        "knowledge_point_id": "9aac142f-a124-44aa-a17b-37ff8630c0a5",
        "skill_kp_id": "u02-k03",
        "value": {
            "id": "u02-k03",
            "title": "A single target",
            "anchor": {"start_line": 40, "end_line": 61},
        },
    }
    assert task["output"]["material"] == "outputs/sample-book/chapters/u02-k03.md"
    assert task["progress"]["allowed_stages"] == [
        "material_reading",
        "material_organizing",
        "material_writing",
        "material_validating",
    ]


def test_supplementary_item_is_explicit_and_has_a_fixed_output_set():
    from src.server.services.education_book_jobs import build_execution_task

    task = build_execution_task(
        {
            **CLAIMED,
            "operation": "material",
            "kind": "supplementary",
            "depth": "lesson",
            "requirements": "Generate all supporting files.",
        }
    )

    assert task["mode"] == "reading_material_only"
    assert task["supplementary"] is True
    assert "knowledge_point" not in task
    assert task["output"]["supplementary"] == [
        "outputs/sample-book/glossary.md",
        "outputs/sample-book/patterns.md",
        "outputs/sample-book/cheatsheet.md",
    ]
    assert task["progress"]["allowed_stages"] == [
        "supplementary_reading",
        "supplementary_organizing",
        "supplementary_validating",
    ]


def test_book_execution_rejects_a_changed_more_to_skills_identity(monkeypatch):
    from src.server.services import education_book_jobs
    from src.server.services.education_book_structure import MoreToSkillsIdentity

    monkeypatch.setattr(
        education_book_jobs,
        "get_more_to_skills_identity",
        lambda: MoreToSkillsIdentity(
            version="2.1.1",
            skill_sha256="d" * 64,
            schema_sha256="e" * 64,
        ),
    )

    with pytest.raises(RuntimeError, match="identity changed"):
        education_book_jobs._validate_book_execution_identity(CLAIMED)


def test_managed_item_prompt_exposes_only_execution_id():
    from src.server.services.education_book_jobs import managed_item_prompt

    prompt = managed_item_prompt(
        {**CLAIMED, "operation": "material", "kind": "material"}
    )

    assert str(CLAIMED["execution_id"]) in prompt
    assert str(CLAIMED["job_id"]) not in prompt
    assert str(CLAIMED["item_id"]) not in prompt
    assert str(CLAIMED["attempt_token"]) not in prompt
    assert "Reading Material Only" in prompt
    assert "progress.allowed_stages" in prompt
    assert "report_progress" in prompt
    assert "does not replace" in prompt
    assert "separate short tool-only turn" in prompt
    assert "Do not retrospectively report" in prompt


@pytest.mark.asyncio
async def test_cancel_book_job_stamps_runtime_intent_and_cross_worker_nudge(
    monkeypatch,
):
    from src.server.services import education_book_jobs

    context = {
        "job_id": CLAIMED["job_id"],
        "item_id": CLAIMED["item_id"],
        "attempt_token": CLAIMED["attempt_token"],
        "thread_id": "1e0d57be-2b7e-4ed2-8daf-246c408d09ec",
        "run_id": "e21b6198-85c6-41e2-b22b-2662851bc782",
    }
    raced_context = {
        "item_id": UUID("b50b797c-4eeb-488a-a9d8-b24d35d8c459"),
        "attempt_token": UUID("c1a93833-b1f0-4ab4-a110-d237e659d61a"),
        "thread_id": "728f5d3f-76ea-460f-a2ef-af2a725b681e",
        "run_id": "a2f48629-8adc-43a5-9ccd-46325200f7aa",
    }
    get_context = AsyncMock(return_value=context)
    events = []
    request_cancel = AsyncMock(
        side_effect=lambda *_args, **_kwargs: events.append("request")
        or {"state": "requested"}
    )
    nudge = AsyncMock(side_effect=lambda *_args: events.append("nudge"))
    signal = AsyncMock(side_effect=lambda *_args: events.append("signal") or True)
    publish_activity = AsyncMock(side_effect=lambda *_args: events.append("activity"))
    mark_cancelled = AsyncMock(
        side_effect=lambda **_kwargs: events.append("mark")
        or {
            "status": "cancelled",
            "high_water_seq": 5,
            "runtime_contexts": [raced_context],
        }
    )
    monkeypatch.setattr(education_book_jobs, "request_book_job_cancel", get_context)
    monkeypatch.setattr(education_book_jobs, "request_run_cancel", request_cancel)
    monkeypatch.setattr(education_book_jobs, "publish_cancel_nudge", nudge)
    monkeypatch.setattr(
        education_book_jobs.LocalRunExecutor,
        "get_instance",
        lambda: type("Executor", (), {"signal_cancel": signal})(),
    )
    monkeypatch.setattr(education_book_jobs, "mark_book_job_cancelled", mark_cancelled)
    monkeypatch.setattr(
        education_book_jobs, "publish_book_activity_hint", publish_activity
    )

    result = await education_book_jobs.cancel_book_job(job_id=str(CLAIMED["job_id"]))

    assert request_cancel.await_count == 2
    request_cancel.assert_any_await(context["run_id"], thread_id=context["thread_id"])
    request_cancel.assert_any_await(
        raced_context["run_id"], thread_id=raced_context["thread_id"]
    )
    assert signal.await_count == 2
    signal.assert_any_await(context["thread_id"], context["run_id"])
    signal.assert_any_await(raced_context["thread_id"], raced_context["run_id"])
    assert nudge.await_count == 2
    nudge.assert_any_await(context["thread_id"], context["run_id"])
    nudge.assert_any_await(raced_context["thread_id"], raced_context["run_id"])
    mark_cancelled.assert_awaited_once_with(
        job_id=CLAIMED["job_id"],
        item_id=CLAIMED["item_id"],
        attempt_token=CLAIMED["attempt_token"],
    )
    assert events.index("mark") < events.index("signal")
    assert events.index("mark") < events.index("nudge")
    assert events.index("mark") < events.index("activity") < events.index("signal")
    publish_activity.assert_awaited_once_with(CLAIMED["job_id"], 5)
    assert result == {"status": "cancelled", "high_water_seq": 5}


@pytest.mark.asyncio
async def test_cancel_book_job_signals_runtime_when_terminal_activity_write_fails(
    monkeypatch,
):
    from src.server.database.education_book_activity import BookActivityWriteError
    from src.server.services import education_book_jobs

    context = {
        "job_id": CLAIMED["job_id"],
        "item_id": CLAIMED["item_id"],
        "attempt_token": CLAIMED["attempt_token"],
        "thread_id": "1e0d57be-2b7e-4ed2-8daf-246c408d09ec",
        "run_id": "e21b6198-85c6-41e2-b22b-2662851bc782",
    }
    request_cancel = AsyncMock(return_value={"state": "requested"})
    signal = AsyncMock(return_value=True)
    nudge = AsyncMock()
    activity_error = BookActivityWriteError("activity unavailable")
    monkeypatch.setattr(
        education_book_jobs,
        "request_book_job_cancel",
        AsyncMock(return_value=context),
    )
    monkeypatch.setattr(education_book_jobs, "request_run_cancel", request_cancel)
    monkeypatch.setattr(education_book_jobs, "publish_cancel_nudge", nudge)
    monkeypatch.setattr(
        education_book_jobs.LocalRunExecutor,
        "get_instance",
        lambda: type("Executor", (), {"signal_cancel": signal})(),
    )
    monkeypatch.setattr(
        education_book_jobs,
        "mark_book_job_cancelled",
        AsyncMock(side_effect=activity_error),
    )

    with pytest.raises(BookActivityWriteError, match="activity unavailable"):
        await education_book_jobs.cancel_book_job(job_id=str(CLAIMED["job_id"]))

    request_cancel.assert_awaited_once_with(
        context["run_id"], thread_id=context["thread_id"]
    )
    signal.assert_awaited_once_with(context["thread_id"], context["run_id"])
    nudge.assert_awaited_once_with(context["thread_id"], context["run_id"])


@pytest.mark.asyncio
async def test_finalize_material_reads_and_stores_only_the_declared_target(
    monkeypatch,
):
    from src.server.services import education_book_jobs

    item = {
        **CLAIMED,
        "operation": "material",
        "kind": "material",
        "knowledge_point_id": UUID("9aac142f-a124-44aa-a17b-37ff8630c0a5"),
        "skill_kp_id": "u02-k03",
        "knowledge_point_json": {
            "id": "u02-k03",
            "title": "A single target",
            "anchor": {"start_line": 40, "end_line": 61},
        },
        "depth": "lesson",
        "requirements": None,
    }
    task = education_book_jobs.build_execution_task(item)
    sandbox = type(
        "Sandbox",
        (),
        {"adownload_file_bytes": AsyncMock(return_value=b"# Material")},
    )()
    store = AsyncMock(return_value={"material_id": "material-1"})
    monkeypatch.setattr(education_book_jobs, "store_material", store)

    result = await education_book_jobs.finalize_book_item(
        item=item,
        task=task,
        sandbox=sandbox,
    )

    sandbox.adownload_file_bytes.assert_awaited_once_with(
        f"/managed/textbook-job/{CLAIMED['execution_id']}/"
        "outputs/sample-book/chapters/u02-k03.md"
    )
    store.assert_awaited_once_with(
        item_id=CLAIMED["item_id"],
        attempt_token=CLAIMED["attempt_token"],
        markdown=b"# Material",
        generation_params={
            "depth": "lesson",
            "requirements": None,
            "execution_id": str(CLAIMED["execution_id"]),
        },
    )
    assert result == {"material_id": "material-1"}


@pytest.mark.asyncio
async def test_finalize_supplementary_archives_only_the_fixed_output_set(monkeypatch):
    from src.server.services import education_book_jobs

    item = {
        **CLAIMED,
        "operation": "material",
        "kind": "supplementary",
        "depth": "lesson",
        "requirements": "Generate all supporting files.",
    }
    task = education_book_jobs.build_execution_task(item)
    sandbox = type(
        "Sandbox",
        (),
        {
            "adownload_file_bytes": AsyncMock(
                side_effect=[b"# Glossary", b"# Patterns", b"# Cheatsheet"]
            )
        },
    )()
    store = AsyncMock(
        return_value={"files": ["glossary.md", "patterns.md", "cheatsheet.md"]}
    )
    monkeypatch.setattr(education_book_jobs, "store_supplementary", store)

    result = await education_book_jobs.finalize_book_item(
        item=item,
        task=task,
        sandbox=sandbox,
    )

    root = f"/managed/textbook-job/{CLAIMED['execution_id']}"
    assert [call.args[0] for call in sandbox.adownload_file_bytes.await_args_list] == [
        f"{root}/outputs/sample-book/glossary.md",
        f"{root}/outputs/sample-book/patterns.md",
        f"{root}/outputs/sample-book/cheatsheet.md",
    ]
    store.assert_awaited_once_with(
        item_id=CLAIMED["item_id"],
        attempt_token=CLAIMED["attempt_token"],
        files={
            "glossary.md": b"# Glossary",
            "patterns.md": b"# Patterns",
            "cheatsheet.md": b"# Cheatsheet",
        },
    )
    assert result["files"] == ["glossary.md", "patterns.md", "cheatsheet.md"]


@pytest.mark.asyncio
async def test_finalize_structure_uses_service_identity_and_source_coordinates(
    monkeypatch,
):
    from src.server.services import education_book_jobs

    item = {
        **CLAIMED,
        "operation": "structure",
        "kind": "structure",
        "source_filename": "sample.md",
        "source_format": "pdf",
        "source_total_lines": 120,
    }
    task = education_book_jobs.build_execution_task(item)
    sandbox = type(
        "Sandbox",
        (),
        {"adownload_file_bytes": AsyncMock(return_value=b'{"schema_version":"2.1.0"}')},
    )()
    parsed = object()
    parse = Mock(return_value=parsed)
    commit = AsyncMock(return_value={"structure_id": "structure-1"})
    monkeypatch.setattr(education_book_jobs, "parse_book_structure", parse)
    monkeypatch.setattr(education_book_jobs, "commit_book_structure", commit)

    result = await education_book_jobs.finalize_book_item(
        item=item,
        task=task,
        sandbox=sandbox,
    )

    parse.assert_called_once()
    source = parse.call_args.kwargs["trusted_source"]
    assert source.path == "inputs/source/document.md"
    assert source.filename == "sample.md"
    assert source.format == "pdf"
    assert source.total_lines == 120
    assert source.anchor_mode == "source_lines"
    assert source.line_offset == 0
    assert parse.call_args.kwargs["allowed_output_paths"] == ()
    commit.assert_awaited_once()
    assert commit.await_args.kwargs["validated_identity"].version == "2.1.0"
    assert result == {"structure_id": "structure-1"}


@pytest.mark.asyncio
async def test_finalize_structure_validates_real_parser_with_unmodified_source(
    monkeypatch,
):
    from src.server.services import education_book_jobs

    item = {
        **CLAIMED,
        "operation": "structure",
        "kind": "structure",
        "source_filename": "sample.pdf",
        "source_format": "pdf",
        "source_total_lines": 10,
    }
    candidate = {
        "schema_version": "2.1.0",
        "generator": {
            "name": "more-to-skills",
            "version": "2.1.0",
            "generated_at": "2026-10-02T12:00:00Z",
        },
        "book": {"title": "Sample", "title_source": "normalized"},
        "source": {},
        "level_names": ["chapter"],
        "nodes": [
            {
                "id": "ch1",
                "title": "Chapter",
                "anchor": {
                    "start_line": 1,
                    "end_line": 10,
                },
            }
        ],
        "knowledge_points": [
            {
                "id": "kp1",
                "title": "Concept",
                "unit": "ch1",
                "nodes": ["ch1"],
                "anchor": {"start_line": 1, "end_line": 10},
            }
        ],
        "coverage": {
            "scope": "Complete book",
            "excluded": [],
            "omitted": [],
            "gaps": [],
        },
    }
    sandbox = type(
        "Sandbox",
        (),
        {
            "adownload_file_bytes": AsyncMock(
                return_value=json.dumps(candidate).encode()
            ),
        },
    )()
    commit = AsyncMock(return_value={"structure_id": "structure-1"})
    monkeypatch.setattr(education_book_jobs, "commit_book_structure", commit)

    await education_book_jobs.finalize_book_item(
        item=item,
        task=education_book_jobs.build_execution_task(item),
        sandbox=sandbox,
    )

    parsed = commit.await_args.kwargs["parsed"]
    assert parsed.document["source"]["line_offset"] == 0
    assert parsed.knowledge_points[0]["start_line"] == 1
    assert parsed.knowledge_points[0]["end_line"] == 10


@pytest.mark.asyncio
async def test_stage_execution_reads_only_declared_snapshot_objects_and_seals_inputs(
    monkeypatch,
):
    from src.server.services import education_book_jobs

    source = b"# One\n\n![figure](images/figure.png)\n"
    blocks = b'{"blocks":[]}'
    report = b'{"ok":true}'
    image = b"png-bytes"
    prefix = "education/house/textbooks/book/source/"
    item = {
        **CLAIMED,
        "operation": "material",
        "kind": "material",
        "knowledge_point_id": UUID("9aac142f-a124-44aa-a17b-37ff8630c0a5"),
        "skill_kp_id": "u02-k03",
        "knowledge_point_json": {
            "id": "u02-k03",
            "title": "Target",
            "anchor": {"start_line": 1, "end_line": 3},
        },
        "depth": "lesson",
        "requirements": None,
        "source_snapshot_prefix": prefix,
        "source_markdown_key": f"{prefix}artifacts/document.md",
        "source_blocks_key": f"{prefix}artifacts/blocks.json",
        "source_report_key": f"{prefix}artifacts/report.json",
        "source_content_sha256": hashlib.sha256(source).hexdigest(),
        "source_asset_manifest": [
            {
                "relative_path": "images/figure.png",
                "sha256": hashlib.sha256(image).hexdigest(),
            }
        ],
        "structure_json": {"schema_version": "2.1.0", "knowledge_points": []},
    }
    objects = {
        item["source_markdown_key"]: source,
        item["source_blocks_key"]: blocks,
        item["source_report_key"]: report,
        f"{prefix}artifacts/images/figure.png": image,
    }
    read_object = AsyncMock(side_effect=lambda key: objects.get(key))
    stage_skill = AsyncMock()
    monkeypatch.setattr(education_book_jobs, "_read_storage_object", read_object)
    monkeypatch.setattr(
        education_book_jobs,
        "get_projected_current_structure",
        AsyncMock(
            return_value={
                "structure_json": item["structure_json"],
                "knowledge_points": [
                    {
                        "knowledge_point_id": item["knowledge_point_id"],
                        "skill_kp_id": item["skill_kp_id"],
                        "position": 1,
                        "title": "Target",
                        "unit_skill_node_id": "u02",
                        "start_line": 1,
                        "end_line": 3,
                        "content_key": None,
                    }
                ],
            }
        ),
    )
    monkeypatch.setattr(education_book_jobs, "stage_book_skill", stage_skill)

    class Sandbox:
        def __init__(self):
            self.files = {}
            self.sealed = []

        async def aupload_file_bytes(self, path, content):
            self.files[path] = content
            return True

        async def seal_directory_read_only(self, path):
            self.sealed.append(path)

    sandbox = Sandbox()
    task = education_book_jobs.build_execution_task(item)

    staged = await education_book_jobs.stage_book_execution(
        item=item,
        task=task,
        sandbox=sandbox,
    )

    root = f"/managed/textbook-job/{CLAIMED['execution_id']}"
    stage_skill.assert_awaited_once_with(
        str(CLAIMED["execution_id"]),
        sandbox,
        expected_skill_sha256=CLAIMED["skill_sha256"],
        expected_schema_sha256=CLAIMED["schema_sha256"],
    )
    assert sandbox.files[f"{root}/inputs/source/document.md"] == source
    assert sandbox.files[f"{root}/inputs/source/blocks.json"] == blocks
    assert sandbox.files[f"{root}/inputs/source/report.json"] == report
    assert sandbox.files[f"{root}/inputs/source/images/figure.png"] == image
    assert f"{root}/inputs/book-structure.json" in sandbox.files
    assert f"{root}/inputs/task.json" in sandbox.files
    assert sandbox.sealed == [
        f"{root}/inputs",
        f"{root}/.agents/skills/more-to-skills",
    ]
    assert staged["source_total_lines"] == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("previous_material", [b"# Previous lesson", None])
async def test_stage_material_uses_projected_structure_and_previous_context_fallback(
    monkeypatch,
    previous_material,
):
    from src.server.services import education_book_jobs

    source = b"one\ntwo\nthree\nfour\nfive\nsix\n"
    prefix = "education/house/textbooks/book/source/"
    previous_key = "education/house/textbooks/book/materials/previous.md"
    previous_id = UUID("11111111-1111-4111-8111-111111111111")
    target_id = UUID("22222222-2222-4222-8222-222222222222")
    next_id = UUID("33333333-3333-4333-8333-333333333333")
    item = {
        **CLAIMED,
        "operation": "material",
        "kind": "material",
        "knowledge_point_id": target_id,
        "skill_kp_id": "u01-k02",
        "knowledge_point_json": {
            "id": "u01-k02",
            "title": "Target",
            "anchor": {"start_line": 3, "end_line": 4},
        },
        "depth": "lesson",
        "requirements": None,
        "source_snapshot_prefix": prefix,
        "source_markdown_key": f"{prefix}artifacts/document.md",
        "source_blocks_key": None,
        "source_report_key": None,
        "source_content_sha256": hashlib.sha256(source).hexdigest(),
        "source_asset_manifest": [],
        "structure_json": {"stale": True},
    }
    projected = {
        "structure_json": {
            "schema_version": "2.1.0",
            "knowledge_points": [
                {"id": "u01-k01", "content_file": "materials/previous.md"},
                {"id": "u01-k02"},
                {"id": "u01-k03"},
            ],
        },
        "knowledge_points": [
            {
                "knowledge_point_id": previous_id,
                "skill_kp_id": "u01-k01",
                "position": 1,
                "title": "Previous",
                "unit_skill_node_id": "u01",
                "start_line": 1,
                "end_line": 2,
                "content_key": previous_key,
            },
            {
                "knowledge_point_id": target_id,
                "skill_kp_id": "u01-k02",
                "position": 2,
                "title": "Target",
                "unit_skill_node_id": "u01",
                "start_line": 3,
                "end_line": 4,
                "content_key": None,
            },
            {
                "knowledge_point_id": next_id,
                "skill_kp_id": "u01-k03",
                "position": 3,
                "title": "Next",
                "unit_skill_node_id": "u01",
                "start_line": 5,
                "end_line": 6,
                "content_key": None,
            },
        ],
    }
    objects = {
        item["source_markdown_key"]: source,
        previous_key: previous_material,
    }
    monkeypatch.setattr(
        education_book_jobs,
        "_read_storage_object",
        AsyncMock(side_effect=lambda key: objects.get(key)),
    )
    projection = AsyncMock(return_value=projected)
    monkeypatch.setattr(
        education_book_jobs, "get_projected_current_structure", projection
    )
    monkeypatch.setattr(education_book_jobs, "stage_book_skill", AsyncMock())

    class Sandbox:
        def __init__(self):
            self.files = {}

        async def aupload_file_bytes(self, path, content):
            self.files[path] = content
            return True

        async def seal_directory_read_only(self, _path):
            return None

    sandbox = Sandbox()
    task = education_book_jobs.build_execution_task(item)

    await education_book_jobs.stage_book_execution(
        item=item,
        task=task,
        sandbox=sandbox,
    )

    root = f"/managed/textbook-job/{CLAIMED['execution_id']}"
    projection.assert_awaited_once_with(textbook_id=str(CLAIMED["textbook_id"]))
    assert (
        json.loads(sandbox.files[f"{root}/inputs/book-structure.json"])[
            "knowledge_points"
        ][0]["content_file"]
        == "materials/previous.md"
    )
    context = json.loads(sandbox.files[f"{root}/inputs/material-context.json"])
    assert context["target"]["skill_kp_id"] == "u01-k02"
    assert context["next"] == {"skill_kp_id": "u01-k03", "title": "Next"}
    assert context["unit_titles"] == ["Previous", "Target", "Next"]
    if previous_material is None:
        assert context["previous"]["source"] == "source_excerpt"
        assert context["previous"]["source_excerpt"] == "one\ntwo"
        assert f"{root}/inputs/context/previous-material.md" not in sandbox.files
    else:
        assert context["previous"]["source"] == "material"
        assert context["previous"]["material_path"] == (
            "inputs/context/previous-material.md"
        )
        assert (
            sandbox.files[f"{root}/inputs/context/previous-material.md"]
            == previous_material
        )


@pytest.mark.asyncio
async def test_stage_supplementary_uses_projected_structure_and_current_materials(
    monkeypatch,
):
    from src.server.services import education_book_jobs

    source = b"source\n"
    prefix = "education/house/textbooks/book/source/"
    material_id = UUID("11111111-1111-4111-8111-111111111111")
    material_key = "education/house/textbooks/book/materials/current.md"
    item = {
        **CLAIMED,
        "operation": "material",
        "kind": "supplementary",
        "depth": "lesson",
        "requirements": "Generate all supporting files.",
        "source_snapshot_prefix": prefix,
        "source_markdown_key": f"{prefix}artifacts/document.md",
        "source_blocks_key": None,
        "source_report_key": None,
        "source_content_sha256": hashlib.sha256(source).hexdigest(),
        "source_asset_manifest": [],
    }
    projected = {
        "structure_json": {
            "schema_version": "2.1.0",
            "knowledge_points": [
                {
                    "id": "u01-k01",
                    "content_file": f"materials/{material_id}.md",
                }
            ],
        },
        "knowledge_points": [
            {
                "knowledge_point_id": material_id,
                "skill_kp_id": "u01-k01",
                "content_key": material_key,
            }
        ],
    }
    objects = {
        item["source_markdown_key"]: source,
        material_key: b"# Current material",
    }
    monkeypatch.setattr(
        education_book_jobs,
        "_read_storage_object",
        AsyncMock(side_effect=lambda key: objects.get(key)),
    )
    monkeypatch.setattr(
        education_book_jobs,
        "get_projected_current_structure",
        AsyncMock(return_value=projected),
    )
    monkeypatch.setattr(education_book_jobs, "stage_book_skill", AsyncMock())

    class Sandbox:
        def __init__(self):
            self.files = {}

        async def aupload_file_bytes(self, path, content):
            self.files[path] = content
            return True

        async def seal_directory_read_only(self, _path):
            return None

    sandbox = Sandbox()

    await education_book_jobs.stage_book_execution(
        item=item,
        task=education_book_jobs.build_execution_task(item),
        sandbox=sandbox,
    )

    root = f"/managed/textbook-job/{CLAIMED['execution_id']}"
    assert (
        json.loads(sandbox.files[f"{root}/inputs/book-structure.json"])[
            "knowledge_points"
        ][0]["content_file"]
        == f"materials/{material_id}.md"
    )
    assert sandbox.files[f"{root}/inputs/materials/{material_id}.md"] == (
        b"# Current material"
    )


@pytest.mark.asyncio
async def test_launch_book_item_binds_normal_root_run_and_finalizes_from_terminal_callback(
    monkeypatch,
):
    from src.server.services import education_book_jobs

    item = {
        **CLAIMED,
        "operation": "structure",
        "kind": "structure",
        "requested_by_user_id": "parent-1",
        "source_filename": "sample.md",
        "source_format": "pdf",
    }
    workspace_id = "743b2b72-f79c-45e8-aafd-b6941e1cbbc1"
    thread_id = "1e0d57be-2b7e-4ed2-8daf-246c408d09ec"
    run_id = "e21b6198-85c6-41e2-b22b-2662851bc782"
    create_workspace = AsyncMock(return_value={"workspace_id": workspace_id})
    create_thread = AsyncMock(return_value={"conversation_thread_id": thread_id})
    resolve_config = AsyncMock(return_value=object())
    sandbox = object()
    provision = AsyncMock(return_value=type("Session", (), {"sandbox": sandbox})())
    stage = AsyncMock(return_value={"source_total_lines": 120})
    run_handle = type(
        "RunHandle",
        (),
        {"run_id": run_id, "turn_index": 1, "checkpointer": None, "guard": None},
    )()
    start_root = AsyncMock(return_value=run_handle)
    bind = AsyncMock()
    graph = object()
    build_graph = AsyncMock(return_value=(graph, {"messages": []}, {"metadata": {}}))
    workflow = object()
    handler_kwargs = {}

    class Handler:
        def __init__(self, **kwargs):
            handler_kwargs.update(kwargs)

        def stream_workflow(self, **_kwargs):
            return workflow

    started = {}

    async def start_executor(**kwargs):
        started.update(kwargs)

    finalize = AsyncMock(return_value={"structure_id": "structure-1"})
    fail = AsyncMock(return_value={"high_water_seq": 7})
    publish_activity = AsyncMock()
    observer = type("Observer", (), {"report_service_stage": AsyncMock()})()
    observer_factory = Mock(return_value=observer)
    cleanup_candidates = AsyncMock()
    cleanup_runtime = AsyncMock()
    identity = Mock(
        return_value=education_book_jobs.MoreToSkillsIdentity(
            version=CLAIMED["more_to_skills_version"],
            skill_sha256=CLAIMED["skill_sha256"],
            schema_sha256=CLAIMED["schema_sha256"],
        )
    )
    monkeypatch.setattr(education_book_jobs, "create_workspace", create_workspace)
    monkeypatch.setattr(education_book_jobs, "create_thread", create_thread)
    monkeypatch.setattr(
        education_book_jobs, "resolve_managed_education_agent_config", resolve_config
    )
    monkeypatch.setattr(
        education_book_jobs.WorkspaceManager,
        "get_instance",
        lambda: type(
            "WorkspaceManager",
            (),
            {"provision_managed_textbook_session": provision},
        )(),
    )
    monkeypatch.setattr(education_book_jobs, "stage_book_execution", stage)
    monkeypatch.setattr(
        education_book_jobs.RunCoordinator,
        "get_instance",
        lambda: type(
            "Coordinator",
            (),
            {
                "start_run": staticmethod(start_root),
                "fail_open_run": staticmethod(AsyncMock()),
            },
        )(),
    )
    monkeypatch.setattr(education_book_jobs, "bind_book_item_runtime", bind)
    monkeypatch.setattr(
        education_book_jobs, "build_managed_education_graph", build_graph
    )
    monkeypatch.setattr(education_book_jobs, "RunSSEProducer", Handler)
    monkeypatch.setattr(
        education_book_jobs,
        "BookActivityObserver",
        observer_factory,
        raising=False,
    )
    monkeypatch.setattr(
        education_book_jobs,
        "publish_book_activity_hint",
        publish_activity,
        raising=False,
    )
    monkeypatch.setattr(
        education_book_jobs.LocalRunExecutor,
        "get_instance",
        lambda: type("Executor", (), {"start_run": staticmethod(start_executor)})(),
    )
    monkeypatch.setattr(education_book_jobs, "finalize_book_item", finalize)
    monkeypatch.setattr(education_book_jobs, "fail_book_item", fail)
    monkeypatch.setattr(
        education_book_jobs,
        "cleanup_book_item_candidates",
        cleanup_candidates,
    )
    monkeypatch.setattr(
        education_book_jobs,
        "cleanup_managed_book_runtime",
        cleanup_runtime,
    )
    monkeypatch.setattr(education_book_jobs, "get_more_to_skills_identity", identity)
    monkeypatch.setattr(education_book_jobs, "uuid4", lambda: UUID(run_id))

    launched = await education_book_jobs.launch_book_item(
        item=item,
        capacity_reservation="reservation-1",
    )

    bind.assert_awaited_once_with(
        item_id=CLAIMED["item_id"],
        attempt_token=CLAIMED["attempt_token"],
        workspace_id=workspace_id,
        thread_id=thread_id,
        run_id=run_id,
    )
    assert build_graph.await_args.kwargs["operation"] == "structure"
    assert build_graph.await_args.kwargs["execution_id"] == str(CLAIMED["execution_id"])
    observer.report_service_stage.assert_awaited_once_with("service_preparing")
    assert started["workflow_generator"] is workflow
    assert started["graph"] is graph
    assert started["capacity_reservation"] == "reservation-1"
    observer_factory.assert_called_once_with(
        job_id=CLAIMED["job_id"],
        item_id=CLAIMED["item_id"],
        attempt_token=CLAIMED["attempt_token"],
        item_kind="structure",
    )
    assert handler_kwargs["event_observer"] is observer
    assert launched == {
        "workspace_id": workspace_id,
        "thread_id": thread_id,
        "run_id": run_id,
    }
    identity.assert_called_once_with()

    await started["terminal_callback"](
        type("TaskInfo", (), {"error": None})(), "completed"
    )
    finalize.assert_awaited_once()
    publish_activity.assert_awaited_once_with(CLAIMED["job_id"], None)
    assert finalize.await_args.kwargs["item"]["source_total_lines"] == 120
    fail.assert_not_awaited()
    cleanup_candidates.assert_awaited_with(
        item_id=CLAIMED["item_id"],
        attempt_token=CLAIMED["attempt_token"],
    )
    cleanup_runtime.assert_awaited_with(
        workspace_id=workspace_id,
        thread_id=thread_id,
    )

    await started["terminal_callback"](
        type("TaskInfo", (), {"error": "provider unavailable"})(), "error"
    )
    assert fail.await_args.kwargs["stop_remaining"] is True
    publish_activity.assert_awaited_with(CLAIMED["job_id"], 7)

    fail.reset_mock()
    await started["terminal_callback"](
        type(
            "TaskInfo",
            (),
            {
                "error": "recursion limit reached",
                "metadata": {
                    "terminal_error_type": "langgraph.errors.GraphRecursionError"
                },
            },
        )(),
        "error",
    )
    assert fail.await_args.kwargs["stop_remaining"] is False

    fail.reset_mock()
    finalize.side_effect = ValueError("generated schema is invalid")
    await started["terminal_callback"](
        type("TaskInfo", (), {"error": None})(), "completed"
    )
    assert fail.await_args.kwargs["stop_remaining"] is False

    from src.server.services.education_book_storage import BookStorageError

    fail.reset_mock()
    finalize.side_effect = BookStorageError("storage unavailable")
    await started["terminal_callback"](
        type("TaskInfo", (), {"error": None})(), "completed"
    )
    assert fail.await_args.kwargs["stop_remaining"] is True

    from src.server.database.education_book_activity import BookActivityWriteError

    fail.reset_mock()
    cleanup_candidates.reset_mock()
    cleanup_runtime.reset_mock()
    finalize.side_effect = BookActivityWriteError("activity unavailable")
    await started["terminal_callback"](
        type("TaskInfo", (), {"error": None})(), "completed"
    )
    fail.assert_not_awaited()
    cleanup_candidates.assert_not_awaited()
    cleanup_runtime.assert_not_awaited()

    stage.side_effect = RuntimeError("staging failed")
    fail.reset_mock()
    publish_activity.reset_mock()
    cleanup_candidates.reset_mock()
    cleanup_runtime.reset_mock()

    with pytest.raises(RuntimeError, match="staging failed"):
        await education_book_jobs.launch_book_item(
            item=item,
            capacity_reservation="reservation-2",
        )

    fail.assert_awaited_once_with(
        item_id=CLAIMED["item_id"],
        attempt_token=CLAIMED["attempt_token"],
        safe_error="Managed textbook execution could not start",
        stop_remaining=True,
    )
    publish_activity.assert_awaited_once_with(CLAIMED["job_id"], 7)
    cleanup_candidates.assert_awaited_once_with(
        item_id=CLAIMED["item_id"],
        attempt_token=CLAIMED["attempt_token"],
    )
    cleanup_runtime.assert_awaited_once_with(
        workspace_id=workspace_id,
        thread_id=thread_id,
    )


@pytest.mark.asyncio
async def test_recovery_renews_live_runtime_without_restarting_the_item(monkeypatch):
    from src.server.services import education_book_recovery

    item = {**CLAIMED, "run_id": UUID("e21b6198-85c6-41e2-b22b-2662851bc782")}
    monkeypatch.setattr(
        education_book_recovery,
        "list_book_items_for_recovery",
        AsyncMock(return_value=[item]),
    )
    monkeypatch.setattr(
        education_book_recovery,
        "get_run",
        AsyncMock(return_value={"status": "in_progress"}),
    )
    renew = AsyncMock(return_value=True)
    recover = AsyncMock()
    fail = AsyncMock(return_value={"high_water_seq": 8})
    monkeypatch.setattr(education_book_recovery, "renew_book_item_lease", renew)
    monkeypatch.setattr(education_book_recovery, "recover_completed_book_item", recover)
    monkeypatch.setattr(education_book_recovery, "fail_book_item", fail)

    reconciled = await education_book_recovery.reconcile_book_jobs_once(
        worker_id="recovery-a", lease_seconds=60
    )

    assert reconciled == 0
    renew.assert_awaited_once_with(
        item_id=CLAIMED["item_id"],
        attempt_token=CLAIMED["attempt_token"],
        worker_id="recovery-a",
        lease_seconds=60,
    )
    recover.assert_not_awaited()
    fail.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovery_finalizes_completed_runtime_from_persisted_identity(
    monkeypatch,
):
    from src.server.services import education_book_recovery

    item = {**CLAIMED, "run_id": UUID("e21b6198-85c6-41e2-b22b-2662851bc782")}
    monkeypatch.setattr(
        education_book_recovery,
        "list_book_items_for_recovery",
        AsyncMock(return_value=[item]),
    )
    monkeypatch.setattr(
        education_book_recovery,
        "get_run",
        AsyncMock(return_value={"status": "completed"}),
    )
    recover = AsyncMock(return_value={"material_id": "material-1"})
    publish_activity = AsyncMock()
    monkeypatch.setattr(education_book_recovery, "recover_completed_book_item", recover)
    monkeypatch.setattr(education_book_recovery, "renew_book_item_lease", AsyncMock())
    monkeypatch.setattr(education_book_recovery, "fail_book_item", AsyncMock())
    monkeypatch.setattr(
        education_book_recovery,
        "publish_book_activity_hint",
        publish_activity,
        raising=False,
    )

    reconciled = await education_book_recovery.reconcile_book_jobs_once(
        worker_id="recovery-a", lease_seconds=60
    )

    assert reconciled == 1
    recover.assert_awaited_once_with(item)
    publish_activity.assert_awaited_once_with(CLAIMED["job_id"], None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "finalization_error",
    [
        ValueError("generated schema is invalid"),
        RuntimeError("managed run did not produce the required output"),
    ],
)
async def test_recovery_keeps_queue_running_after_completed_item_content_error(
    monkeypatch,
    finalization_error,
):
    from src.server.services import education_book_recovery

    item = {**CLAIMED, "run_id": UUID("e21b6198-85c6-41e2-b22b-2662851bc782")}
    monkeypatch.setattr(
        education_book_recovery,
        "list_book_items_for_recovery",
        AsyncMock(return_value=[item]),
    )
    monkeypatch.setattr(
        education_book_recovery,
        "get_run",
        AsyncMock(return_value={"status": "completed"}),
    )
    monkeypatch.setattr(
        education_book_recovery,
        "recover_completed_book_item",
        AsyncMock(side_effect=finalization_error),
    )
    fail = AsyncMock(return_value={"high_water_seq": 8})
    publish_activity = AsyncMock()
    monkeypatch.setattr(education_book_recovery, "fail_book_item", fail)
    monkeypatch.setattr(
        education_book_recovery,
        "publish_book_activity_hint",
        publish_activity,
    )

    reconciled = await education_book_recovery.reconcile_book_jobs_once(
        worker_id="recovery-a", lease_seconds=60
    )

    assert reconciled == 1
    assert fail.await_args.kwargs["stop_remaining"] is False
    publish_activity.assert_awaited_once_with(CLAIMED["job_id"], 8)


@pytest.mark.asyncio
async def test_recovery_stops_queue_after_completed_item_storage_error(monkeypatch):
    from src.server.services import education_book_recovery
    from src.server.services.education_book_storage import BookStorageError

    item = {**CLAIMED, "run_id": UUID("e21b6198-85c6-41e2-b22b-2662851bc782")}
    monkeypatch.setattr(
        education_book_recovery,
        "list_book_items_for_recovery",
        AsyncMock(return_value=[item]),
    )
    monkeypatch.setattr(
        education_book_recovery,
        "get_run",
        AsyncMock(return_value={"status": "completed"}),
    )
    monkeypatch.setattr(
        education_book_recovery,
        "recover_completed_book_item",
        AsyncMock(side_effect=BookStorageError("storage unavailable")),
    )
    fail = AsyncMock(return_value={"high_water_seq": 8})
    publish_activity = AsyncMock()
    monkeypatch.setattr(education_book_recovery, "fail_book_item", fail)
    monkeypatch.setattr(
        education_book_recovery,
        "publish_book_activity_hint",
        publish_activity,
    )

    reconciled = await education_book_recovery.reconcile_book_jobs_once(
        worker_id="recovery-a", lease_seconds=60
    )

    assert reconciled == 1
    assert fail.await_args.kwargs["stop_remaining"] is True
    publish_activity.assert_awaited_once_with(CLAIMED["job_id"], 8)


@pytest.mark.asyncio
async def test_recovery_defers_when_terminal_activity_storage_is_unavailable(
    monkeypatch,
):
    from src.server.database.education_book_activity import BookActivityWriteError
    from src.server.services import education_book_recovery

    item = {**CLAIMED, "run_id": UUID("e21b6198-85c6-41e2-b22b-2662851bc782")}
    monkeypatch.setattr(
        education_book_recovery,
        "list_book_items_for_recovery",
        AsyncMock(return_value=[item]),
    )
    monkeypatch.setattr(
        education_book_recovery,
        "get_run",
        AsyncMock(return_value={"status": "completed"}),
    )
    recover = AsyncMock(side_effect=BookActivityWriteError("activity unavailable"))
    fail = AsyncMock()
    monkeypatch.setattr(education_book_recovery, "recover_completed_book_item", recover)
    monkeypatch.setattr(education_book_recovery, "fail_book_item", fail)

    reconciled = await education_book_recovery.reconcile_book_jobs_once(
        worker_id="recovery-a", lease_seconds=60
    )

    assert reconciled == 0
    fail.assert_not_awaited()


@pytest.mark.asyncio
async def test_recovery_marks_runtime_failure_retriable_and_stops_remainder(
    monkeypatch,
):
    from src.server.services import education_book_recovery

    item = {**CLAIMED, "run_id": UUID("e21b6198-85c6-41e2-b22b-2662851bc782")}
    monkeypatch.setattr(
        education_book_recovery,
        "list_book_items_for_recovery",
        AsyncMock(return_value=[item]),
    )
    monkeypatch.setattr(
        education_book_recovery,
        "get_run",
        AsyncMock(return_value={"status": "error"}),
    )
    fail = AsyncMock(return_value={"high_water_seq": 8})
    publish_activity = AsyncMock()
    monkeypatch.setattr(education_book_recovery, "fail_book_item", fail)
    monkeypatch.setattr(education_book_recovery, "renew_book_item_lease", AsyncMock())
    monkeypatch.setattr(
        education_book_recovery, "recover_completed_book_item", AsyncMock()
    )
    monkeypatch.setattr(
        education_book_recovery,
        "publish_book_activity_hint",
        publish_activity,
        raising=False,
    )

    reconciled = await education_book_recovery.reconcile_book_jobs_once(
        worker_id="recovery-a", lease_seconds=60
    )

    assert reconciled == 1
    fail.assert_awaited_once_with(
        item_id=CLAIMED["item_id"],
        attempt_token=CLAIMED["attempt_token"],
        safe_error="Managed textbook runtime ended before business commit",
        stop_remaining=True,
    )
    publish_activity.assert_awaited_once_with(CLAIMED["job_id"], 8)


@pytest.mark.asyncio
async def test_recovery_keeps_queue_running_after_item_recursion_limit(monkeypatch):
    from src.server.services import education_book_recovery

    item = {**CLAIMED, "run_id": UUID("e21b6198-85c6-41e2-b22b-2662851bc782")}
    monkeypatch.setattr(
        education_book_recovery,
        "list_book_items_for_recovery",
        AsyncMock(return_value=[item]),
    )
    monkeypatch.setattr(
        education_book_recovery,
        "get_run",
        AsyncMock(
            return_value={
                "status": "error",
                "metadata": {
                    "terminal_error_type": "langgraph.errors.GraphRecursionError"
                },
            }
        ),
    )
    fail = AsyncMock(return_value={"high_water_seq": 8})
    monkeypatch.setattr(education_book_recovery, "fail_book_item", fail)

    reconciled = await education_book_recovery.reconcile_book_jobs_once(
        worker_id="recovery-a", lease_seconds=60
    )

    assert reconciled == 1
    assert fail.await_args.kwargs["stop_remaining"] is False


@pytest.mark.asyncio
async def test_recovery_preserves_durable_user_cancellation(monkeypatch):
    from src.server.services import education_book_recovery

    item = {**CLAIMED, "run_id": UUID("e21b6198-85c6-41e2-b22b-2662851bc782")}
    monkeypatch.setattr(
        education_book_recovery,
        "list_book_items_for_recovery",
        AsyncMock(return_value=[item]),
    )
    monkeypatch.setattr(
        education_book_recovery,
        "get_run",
        AsyncMock(
            return_value={"status": "cancelled", "cancel_requested_at": object()}
        ),
    )
    cancel = AsyncMock(return_value={"status": "cancelled", "high_water_seq": 9})
    fail = AsyncMock()
    publish_activity = AsyncMock()
    monkeypatch.setattr(education_book_recovery, "mark_book_job_cancelled", cancel)
    monkeypatch.setattr(education_book_recovery, "fail_book_item", fail)
    monkeypatch.setattr(
        education_book_recovery,
        "publish_book_activity_hint",
        publish_activity,
        raising=False,
    )

    reconciled = await education_book_recovery.reconcile_book_jobs_once(
        worker_id="recovery-a", lease_seconds=60
    )

    assert reconciled == 1
    cancel.assert_awaited_once_with(
        job_id=CLAIMED["job_id"],
        item_id=CLAIMED["item_id"],
        attempt_token=CLAIMED["attempt_token"],
    )
    fail.assert_not_awaited()
    publish_activity.assert_awaited_once_with(CLAIMED["job_id"], 9)


@pytest.mark.asyncio
async def test_recovery_settles_queued_job_with_durable_cancel_intent(monkeypatch):
    from src.server.services import education_book_recovery

    pending = {
        "job_id": CLAIMED["job_id"],
        "item_id": None,
        "attempt_token": None,
    }
    monkeypatch.setattr(
        education_book_recovery,
        "list_book_jobs_pending_cancellation",
        AsyncMock(return_value=[pending]),
        raising=False,
    )
    monkeypatch.setattr(
        education_book_recovery,
        "list_book_items_for_recovery",
        AsyncMock(return_value=[]),
    )
    cancel = AsyncMock(return_value={"status": "cancelled", "high_water_seq": 3})
    publish_activity = AsyncMock()
    monkeypatch.setattr(education_book_recovery, "mark_book_job_cancelled", cancel)
    monkeypatch.setattr(
        education_book_recovery,
        "publish_book_activity_hint",
        publish_activity,
    )

    reconciled = await education_book_recovery.reconcile_book_jobs_once(
        worker_id="recovery-a", lease_seconds=60
    )

    assert reconciled == 1
    cancel.assert_awaited_once_with(
        job_id=CLAIMED["job_id"],
        item_id=None,
        attempt_token=None,
    )
    publish_activity.assert_awaited_once_with(CLAIMED["job_id"], 3)


@pytest.mark.asyncio
async def test_recovery_replays_runtime_signal_for_durable_cancel_intent(monkeypatch):
    from src.server.services import education_book_recovery

    pending = {
        "job_id": CLAIMED["job_id"],
        "item_id": CLAIMED["item_id"],
        "attempt_token": CLAIMED["attempt_token"],
        "thread_id": "1e0d57be-2b7e-4ed2-8daf-246c408d09ec",
        "run_id": "e21b6198-85c6-41e2-b22b-2662851bc782",
    }
    monkeypatch.setattr(
        education_book_recovery,
        "list_book_jobs_pending_cancellation",
        AsyncMock(return_value=[pending]),
    )
    monkeypatch.setattr(
        education_book_recovery,
        "list_book_items_for_recovery",
        AsyncMock(return_value=[]),
    )
    request_cancel = AsyncMock(return_value={"state": "requested"})
    signal = AsyncMock(return_value=True)
    nudge = AsyncMock()
    monkeypatch.setattr(
        education_book_recovery, "request_run_cancel", request_cancel, raising=False
    )
    monkeypatch.setattr(
        education_book_recovery.LocalRunExecutor,
        "get_instance",
        lambda: type("Executor", (), {"signal_cancel": signal})(),
        raising=False,
    )
    monkeypatch.setattr(
        education_book_recovery, "publish_cancel_nudge", nudge, raising=False
    )
    monkeypatch.setattr(
        education_book_recovery,
        "mark_book_job_cancelled",
        AsyncMock(
            return_value={
                "status": "cancelled",
                "high_water_seq": 3,
                "runtime_contexts": [pending],
            }
        ),
    )
    monkeypatch.setattr(
        education_book_recovery, "publish_book_activity_hint", AsyncMock()
    )

    reconciled = await education_book_recovery.reconcile_book_jobs_once(
        worker_id="recovery-a", lease_seconds=60
    )

    assert reconciled == 1
    request_cancel.assert_awaited_once_with(
        pending["run_id"], thread_id=pending["thread_id"]
    )
    signal.assert_awaited_once_with(pending["thread_id"], pending["run_id"])
    nudge.assert_awaited_once_with(pending["thread_id"], pending["run_id"])


@pytest.mark.asyncio
async def test_settled_item_cleanup_retries_candidates_and_managed_runtime(monkeypatch):
    from src.server.services import education_book_jobs

    cleanup_item = {
        "item_id": CLAIMED["item_id"],
        "attempt_token": CLAIMED["attempt_token"],
        "managed_workspace_id": UUID("743b2b72-f79c-45e8-aafd-b6941e1cbbc1"),
        "managed_thread_id": UUID("1e0d57be-2b7e-4ed2-8daf-246c408d09ec"),
    }
    list_items = AsyncMock(return_value=[cleanup_item])
    cleanup_candidates = AsyncMock(return_value=1)
    cleanup_runtime = AsyncMock()
    monkeypatch.setattr(
        education_book_jobs,
        "list_book_items_for_terminal_cleanup",
        list_items,
    )
    monkeypatch.setattr(
        education_book_jobs,
        "cleanup_book_item_candidates",
        cleanup_candidates,
    )
    monkeypatch.setattr(
        education_book_jobs,
        "cleanup_managed_book_runtime",
        cleanup_runtime,
    )

    cleaned = await education_book_jobs.cleanup_settled_book_items_once(limit=25)

    assert cleaned == 1
    list_items.assert_awaited_once_with(limit=25)
    cleanup_candidates.assert_awaited_once_with(
        item_id=CLAIMED["item_id"],
        attempt_token=CLAIMED["attempt_token"],
    )
    cleanup_runtime.assert_awaited_once_with(
        workspace_id=str(cleanup_item["managed_workspace_id"]),
        thread_id=str(cleanup_item["managed_thread_id"]),
    )


@pytest.mark.asyncio
async def test_failed_launch_cleanup_survives_ledger_and_item_failures(monkeypatch):
    from src.server.services import education_book_jobs

    fail_open = AsyncMock(side_effect=RuntimeError("ledger unavailable"))
    fail_item = AsyncMock(side_effect=RuntimeError("database unavailable"))
    cleanup_candidates = AsyncMock()
    cleanup_runtime = AsyncMock()
    monkeypatch.setattr(
        education_book_jobs.RunCoordinator,
        "get_instance",
        lambda: type("Coordinator", (), {"fail_open_run": staticmethod(fail_open)})(),
    )
    monkeypatch.setattr(education_book_jobs, "fail_book_item", fail_item)
    monkeypatch.setattr(
        education_book_jobs, "cleanup_book_item_candidates", cleanup_candidates
    )
    monkeypatch.setattr(
        education_book_jobs, "cleanup_managed_book_runtime", cleanup_runtime
    )

    await education_book_jobs._settle_failed_book_launch(
        item=CLAIMED,
        identity=education_book_jobs._managed_identity(
            {**CLAIMED, "operation": "structure"}
        ),
        workspace_id="workspace-1",
        thread_id="thread-1",
        run_handle=object(),
        error=RuntimeError("staging failed"),
    )

    cleanup_candidates.assert_awaited_once()
    cleanup_runtime.assert_awaited_once_with(
        workspace_id="workspace-1", thread_id="thread-1"
    )


@pytest.mark.asyncio
async def test_managed_runtime_cleanup_skips_workspace_file_backup(monkeypatch):
    from src.server.services import education_book_jobs

    archive = AsyncMock()
    delete = AsyncMock()
    monkeypatch.setattr(education_book_jobs, "update_thread_fields", archive)
    monkeypatch.setattr(
        education_book_jobs.WorkspaceManager,
        "get_instance",
        lambda: type("WorkspaceManager", (), {"delete_workspace": delete})(),
    )

    await education_book_jobs.cleanup_managed_book_runtime(
        workspace_id="workspace-1", thread_id="thread-1"
    )

    archive.assert_awaited_once_with("thread-1", archived=True)
    delete.assert_awaited_once_with("workspace-1", backup_files=False)


@pytest.mark.asyncio
async def test_queue_service_reconciles_then_claims_one_persisted_item(monkeypatch):
    from src.server.services import education_book_jobs

    reconcile = AsyncMock(return_value=0)
    cleanup = AsyncMock(return_value=0)
    reserve = AsyncMock(return_value="reservation-1")
    release = AsyncMock()
    claim = AsyncMock(return_value={**CLAIMED, "operation": "structure"})
    renew = AsyncMock(return_value=True)
    launch = AsyncMock()
    monkeypatch.setattr(
        "src.server.services.education_book_recovery.reconcile_book_jobs_once",
        reconcile,
    )
    monkeypatch.setattr(education_book_jobs, "claim_next_book_item", claim)
    monkeypatch.setattr(education_book_jobs, "cleanup_settled_book_items_once", cleanup)
    monkeypatch.setattr(
        education_book_jobs.LocalRunExecutor,
        "get_instance",
        lambda: type(
            "Executor",
            (),
            {
                "reserve_capacity": reserve,
                "release_capacity_reservation": release,
            },
        )(),
    )
    monkeypatch.setattr(education_book_jobs, "renew_book_item_lease", renew)
    monkeypatch.setattr(education_book_jobs, "launch_book_item", launch)
    service = education_book_jobs.EducationBookJobService(
        worker_id="book-worker-a",
        lease_seconds=60,
        poll_interval=1,
    )

    processed = await service.scan_once()

    reconcile.assert_awaited_once_with(
        worker_id="book-worker-a",
        lease_seconds=60,
    )
    cleanup.assert_awaited_once_with()
    claim.assert_awaited_once_with(
        worker_id="book-worker-a",
        lease_seconds=60,
    )
    renew.assert_awaited_once_with(
        item_id=CLAIMED["item_id"],
        attempt_token=CLAIMED["attempt_token"],
        worker_id="book-worker-a",
        lease_seconds=60,
    )
    launch.assert_awaited_once_with(
        item=claim.return_value,
        capacity_reservation="reservation-1",
    )
    release.assert_awaited_once_with("reservation-1")
    assert processed == 1


@pytest.mark.asyncio
async def test_queue_service_does_not_claim_or_allocate_when_executor_is_full(
    monkeypatch,
):
    from src.server.services import education_book_jobs

    reconcile = AsyncMock(return_value=0)
    cleanup = AsyncMock(return_value=0)
    claim = AsyncMock()
    reserve = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "src.server.services.education_book_recovery.reconcile_book_jobs_once",
        reconcile,
    )
    monkeypatch.setattr(education_book_jobs, "cleanup_settled_book_items_once", cleanup)
    monkeypatch.setattr(education_book_jobs, "claim_next_book_item", claim)
    monkeypatch.setattr(
        education_book_jobs.LocalRunExecutor,
        "get_instance",
        lambda: type("Executor", (), {"reserve_capacity": reserve})(),
    )
    service = education_book_jobs.EducationBookJobService(
        worker_id="book-worker-a",
        lease_seconds=60,
        poll_interval=1,
    )

    processed = await service.scan_once()

    assert processed == 0
    claim.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_service_renews_claim_while_launch_is_still_staging(monkeypatch):
    import asyncio

    from src.server.services import education_book_jobs

    reconcile = AsyncMock(return_value=0)
    cleanup = AsyncMock(return_value=0)
    reserve = AsyncMock(return_value="reservation-1")
    release = AsyncMock()
    claim = AsyncMock(return_value={**CLAIMED, "operation": "structure"})
    second_renewal = asyncio.Event()
    renew_calls = []

    async def renew(**kwargs):
        renew_calls.append(kwargs)
        if len(renew_calls) == 2:
            second_renewal.set()
        return True

    async def launch(*, item, capacity_reservation):
        assert item is claim.return_value
        assert capacity_reservation == "reservation-1"
        await asyncio.wait_for(second_renewal.wait(), timeout=1)

    monkeypatch.setattr(
        "src.server.services.education_book_recovery.reconcile_book_jobs_once",
        reconcile,
    )
    monkeypatch.setattr(education_book_jobs, "claim_next_book_item", claim)
    monkeypatch.setattr(education_book_jobs, "cleanup_settled_book_items_once", cleanup)
    monkeypatch.setattr(
        education_book_jobs.LocalRunExecutor,
        "get_instance",
        lambda: type(
            "Executor",
            (),
            {
                "reserve_capacity": reserve,
                "release_capacity_reservation": release,
            },
        )(),
    )
    monkeypatch.setattr(education_book_jobs, "renew_book_item_lease", renew)
    monkeypatch.setattr(education_book_jobs, "launch_book_item", launch)
    service = education_book_jobs.EducationBookJobService(
        worker_id="book-worker-a",
        lease_seconds=0.03,
        poll_interval=1,
    )

    processed = await service.scan_once()
    renew_count_after_launch = len(renew_calls)
    await asyncio.sleep(0.04)

    assert processed == 1
    assert renew_count_after_launch >= 2
    assert len(renew_calls) == renew_count_after_launch
    assert renew_calls[0] == {
        "item_id": CLAIMED["item_id"],
        "attempt_token": CLAIMED["attempt_token"],
        "worker_id": "book-worker-a",
        "lease_seconds": 0.03,
    }
