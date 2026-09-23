"""Managed generation contracts for one knowledge-point lesson."""

import hashlib
from unittest.mock import AsyncMock

import pytest

from src.server.services import education_lesson_jobs
from src.server.services.education_book_package import validate_book_package


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
            "content_sha256": "a" * 64,
            "path": "sources/01-reading-explorer.md",
            "markdown": (
                "# Unit 1\n\nThe first paragraph.\n\n"
                + ("filler sentence. " * 400)
                + "\n\nThe second paragraph.\n"
            ),
        }
    ],
}

GENERIC_NODE_ID = "f5761267-11d1-4977-8107-e2671c99a2f0"


LESSON_JOB = {
    "generation_job_id": "8a77d086-0b23-4a1e-89d0-f163fa23d5d1",
    "version_id": "version-1",
    "scope": "lesson",
    "knowledge_point_id": "kp-1",
    "knowledge_point_position": 2,
    "knowledge_point_slug": "world-game",
    "knowledge_point_title": "世界运动",
    "knowledge_point_scope_slot": "reading_a",
    "knowledge_point_source_refs": [
        {"source_id": "source-1", "start": 0, "end": 30}
    ],
    "unit_id": "unit-1",
    "unit_position": 1,
    "unit_slug": "unit-1-sports",
    "unit_title": "Unit 1: Sports and Fitness",
    "structure_id": "structure-1",
    "structure_sequence": 1,
    "household_id": "household-1",
    "slug": "english-2",
    "content_version_sequence": 1,
    "auto_grading": False,
    "processing_profile_sha256": "b" * 64,
}

GENERIC_LESSON_JOB = {
    **LESSON_JOB,
    "knowledge_point_id": "generic-kp-1",
    "knowledge_point_title": "足球成为全球运动的原因",
    "knowledge_point_scope_slot": None,
    "knowledge_point_source_refs": [
        {
            "source_id": "source-1",
            "char_start": 120,
            "char_end": 190,
        }
    ],
    "unit_id": None,
    "unit_position": None,
    "unit_slug": None,
    "unit_title": None,
    "origin": "generated",
    "candidate_status": "accepted",
    "content_structure_id": "structure-1",
    "content_node_id": GENERIC_NODE_ID,
    "content_node_key": "unit-1-reading",
    "content_node_type": "reading",
    "content_node_title": "The World's Game",
    "content_node_source_refs": [
        {
            "source_id": "source-1",
            "char_start": 120,
            "char_end": 190,
        }
    ],
    "content_asset_id": "asset-1",
    "content_asset_type": "knowledge",
    "content_asset_key": (
        "education/household-1/english-2/v1/book-packages/job-1/"
        "assets/book-skill/chapters/unit-1-reading/knowledge.md"
    ),
    "content_asset_sha256": "c" * 64,
    "content_asset_size_bytes": 128,
}


def test_managed_lesson_prompt_contains_only_target_contract() -> None:
    prompt = education_lesson_jobs.managed_lesson_prompt(
        LESSON_JOB,
        scope={"slot": "reading_a"},
        chapter_markdown="# Chapter knowledge\n",
    )

    assert "inputs/readings/reading_a.md" in prompt
    assert "inputs/chapters/reading_a-knowledge.md" in prompt
    assert "outputs/lesson.md" in prompt
    assert "outputs/practice.json" in prompt
    assert "世界运动" in prompt
    assert "不要读取整本书" in prompt
    assert "vocabulary.json" in prompt
    assert "evidence.json" in prompt


def test_generic_managed_lesson_prompt_does_not_require_reading_scope() -> None:
    prompt = education_lesson_jobs.managed_lesson_prompt(
        GENERIC_LESSON_JOB,
        chapter_markdown="# Node knowledge\n",
        attempt_id="attempt-1",
    )

    assert f"inputs/content-nodes/{GENERIC_NODE_ID}.md" in prompt
    assert "-knowledge.md" in prompt
    assert "所属内容节点是：The World's Game" in prompt
    assert "inputs/readings/" not in prompt


def test_managed_lesson_prompt_requires_semantic_progress_checkpoints() -> None:
    prompt = education_lesson_jobs.managed_lesson_prompt(
        LESSON_JOB,
        scope={"slot": "reading_a"},
        chapter_markdown="# Chapter knowledge\n",
        attempt_id="attempt-1",
    )

    assert ".langalpha/progress.py" in prompt
    assert "append-only" in prompt
    for substage in (
        "preparing",
        "extracting_source",
        "planning",
        "generating_explanation",
        "generating_practice",
        "validating",
        "completed",
    ):
        assert f"lesson_preparation/{substage}" in prompt
    assert LESSON_JOB["generation_job_id"] in prompt
    assert "attempt-1" in prompt
    assert '"status":"running"' in prompt
    assert '"status":"completed"' in prompt


def _scope(markdown: str, start: int, end: int) -> dict:
    return {
        "slot": "reading_a",
        "scope_title": "The World's Game",
        "source_id": "source-1",
        "line_start": 1,
        "line_end": 50,
        "char_start": start,
        "char_end": end,
    }


def test_build_lesson_source_context_slices_the_declared_scope() -> None:
    markdown = FROZEN_INPUT["sources"][0]["markdown"]
    quote_start = markdown.index("The second paragraph.")
    quote_end = quote_start + len("The second paragraph.")

    context, warnings = education_lesson_jobs.build_lesson_source_context(
        LESSON_JOB,
        FROZEN_INPUT,
        [_scope(markdown, quote_start, quote_end)],
    )

    assert warnings == []
    assert context.startswith("## The World's Game [1:50]")
    assert "The second paragraph." in context
    assert "The first paragraph." not in context


def test_build_lesson_source_context_uses_the_assigned_reading() -> None:
    markdown = FROZEN_INPUT["sources"][0]["markdown"]
    reading_a_start = markdown.index("The first paragraph.")
    reading_a_end = markdown.index("filler sentence.")
    reading_b_start = markdown.index("The second paragraph.")
    reading_b_end = reading_b_start + len("The second paragraph.")
    scopes = [
        {
            **_scope(markdown, reading_a_start, reading_a_end),
            "slot": "reading_a",
            "scope_title": "Reading A",
        },
        {
            **_scope(markdown, reading_b_start, reading_b_end),
            "slot": "reading_b",
            "scope_title": "Reading B",
        },
    ]

    context, warnings = education_lesson_jobs.build_lesson_source_context(
        {**LESSON_JOB, "knowledge_point_scope_slot": "reading_b"},
        FROZEN_INPUT,
        scopes,
    )

    assert warnings == []
    assert context.startswith("## Reading B [1:50]")
    assert "The second paragraph." in context
    assert "The first paragraph." not in context


def test_build_lesson_source_context_refuses_to_guess_without_a_scope() -> None:
    with pytest.raises(ValueError, match="scope is unavailable"):
        education_lesson_jobs.build_lesson_source_context(
            LESSON_JOB,
            FROZEN_INPUT,
            [],
        )


def test_build_lesson_source_context_rejects_an_empty_scope() -> None:
    with pytest.raises(ValueError, match="range is invalid"):
        education_lesson_jobs.build_lesson_source_context(
            LESSON_JOB,
            FROZEN_INPUT,
            [_scope(FROZEN_INPUT["sources"][0]["markdown"], 10, 10)],
        )


def test_build_lesson_source_context_uses_generic_node_source_range() -> None:
    markdown = FROZEN_INPUT["sources"][0]["markdown"]
    start = markdown.index("The first paragraph.")
    end = start + len("The first paragraph.")

    context, warnings = education_lesson_jobs.build_lesson_source_context(
        {
            **GENERIC_LESSON_JOB,
            "content_node_source_refs": [
                {"source_id": "source-1", "char_start": start, "char_end": end}
            ],
        },
        FROZEN_INPUT,
        [],
    )

    assert warnings == []
    assert context.startswith("## The World's Game")
    assert "The first paragraph." in context
    assert "filler sentence." not in context


def test_build_lesson_source_context_falls_back_to_generic_node_asset() -> None:
    context, warnings = education_lesson_jobs.build_lesson_source_context(
        {
            **GENERIC_LESSON_JOB,
            "content_node_source_refs": [],
        },
        FROZEN_INPUT,
        [],
        content_node_markdown="# Generated node knowledge\n\nTrusted node asset.",
    )

    assert warnings == []
    assert context.startswith("## The World's Game")
    assert "Trusted node asset." in context
    assert "filler sentence." not in context


def test_build_lesson_source_context_uses_validator_normalized_node_range() -> None:
    markdown = FROZEN_INPUT["sources"][0]["markdown"]
    start = markdown.index("The first paragraph.")
    end = start + len("The first paragraph.")
    package, _warnings = validate_book_package(
        {
            "format": "langalpha-book-package/v1",
            "source_revision": "revision-1",
            "content_nodes": [
                {
                    "node_key": "unit-1-reading",
                    "parent_key": None,
                    "node_type": "reading",
                    "label": None,
                    "position": 1,
                    "title": "The World's Game",
                    "summary": "Reading overview",
                    "source_refs": [
                        {"char_start": start, "char_end": end, "source_id": "source-1"}
                    ],
                }
            ],
            "knowledge_points": [],
            "assets": [],
        },
        markdown=markdown,
    )
    normalized_refs = package["content_nodes"][0]["source_refs"]
    assert normalized_refs == [
        {
            "start": start,
            "end": end,
            "quote": "The first paragraph.",
            "resolution_status": "resolved",
            "source_id": "source-1",
        }
    ]

    context, warnings = education_lesson_jobs.build_lesson_source_context(
        {
            **GENERIC_LESSON_JOB,
            "content_node_source_refs": normalized_refs,
        },
        FROZEN_INPUT,
        [],
        content_node_markdown="# Asset fallback must not be used\n",
    )

    assert warnings == []
    assert "The first paragraph." in context
    assert "Asset fallback must not be used" not in context


@pytest.mark.asyncio
async def test_queue_lesson_generation_creates_one_lesson_job(monkeypatch) -> None:
    captured: dict[str, object] = {}

    async def get_kp(**_kwargs):
        return dict(LESSON_JOB)

    async def create_job(**kwargs):
        captured.update(kwargs)
        return {
            "generation_job_id": "generation-1",
            "scope": "lesson",
            "status": "queued",
            "auto_grading": kwargs["auto_grading"],
        }

    async def get_scopes(**_kwargs):
        return [
            {
                "unit_id": "unit-1",
                "slot": "reading_a",
            }
        ]

    monkeypatch.setattr(
        education_lesson_jobs,
        "get_knowledge_point_for_parent",
        get_kp,
    )
    monkeypatch.setattr(
        education_lesson_jobs,
        "create_generation_job",
        create_job,
    )
    monkeypatch.setattr(
        education_lesson_jobs,
        "get_textbook_scopes_for_unit",
        get_scopes,
    )

    queued = await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
        parent_user_id="parent-1",
        knowledge_point_id="kp-1",
        auto_grading=False,
    )

    assert queued["scope"] == "lesson"
    assert captured["scope"] == "lesson"
    assert captured["knowledge_point_id"] == "kp-1"


@pytest.mark.asyncio
async def test_queue_lesson_generation_rejects_unassigned_reading(monkeypatch) -> None:
    async def get_kp(**_kwargs):
        return {
            **LESSON_JOB,
            "knowledge_point_scope_slot": None,
        }

    async def get_scopes(**_kwargs):
        return [
            {"unit_id": "unit-1", "slot": "reading_a"},
            {"unit_id": "unit-1", "slot": "reading_b"},
        ]

    monkeypatch.setattr(
        education_lesson_jobs,
        "get_knowledge_point_for_parent",
        get_kp,
    )
    monkeypatch.setattr(
        education_lesson_jobs,
        "get_textbook_scopes_for_unit",
        get_scopes,
    )

    with pytest.raises(LookupError, match="Reading scope"):
        await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
            parent_user_id="parent-1",
            knowledge_point_id="kp-1",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "candidate_status",
    ["pending", "rejected", "merged", "split"],
)
async def test_queue_lesson_generation_rejects_non_accepted_generic_candidate(
    monkeypatch,
    candidate_status: str,
) -> None:
    create_job = AsyncMock()

    async def get_kp(**_kwargs):
        return {
            **GENERIC_LESSON_JOB,
            "candidate_status": candidate_status,
        }

    monkeypatch.setattr(
        education_lesson_jobs,
        "get_knowledge_point_for_parent",
        get_kp,
    )
    monkeypatch.setattr(
        education_lesson_jobs,
        "create_generation_job",
        create_job,
    )

    with pytest.raises(LookupError, match="accepted knowledge point"):
        await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
            parent_user_id="parent-1",
            knowledge_point_id="generic-kp-1",
        )

    create_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_lesson_generation_rejects_generic_candidate_without_node(
    monkeypatch,
) -> None:
    create_job = AsyncMock()

    async def get_kp(**_kwargs):
        return {
            **GENERIC_LESSON_JOB,
            "content_node_id": None,
            "content_asset_id": None,
            "content_asset_key": None,
        }

    monkeypatch.setattr(
        education_lesson_jobs,
        "get_knowledge_point_for_parent",
        get_kp,
    )
    monkeypatch.setattr(
        education_lesson_jobs,
        "create_generation_job",
        create_job,
    )

    with pytest.raises(LookupError, match="content node"):
        await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
            parent_user_id="parent-1",
            knowledge_point_id="generic-kp-1",
        )

    create_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_lesson_generation_rejects_generic_candidate_without_asset(
    monkeypatch,
) -> None:
    create_job = AsyncMock()

    async def get_kp(**_kwargs):
        return {
            **GENERIC_LESSON_JOB,
            "content_asset_id": None,
            "content_asset_key": None,
        }

    monkeypatch.setattr(
        education_lesson_jobs,
        "get_knowledge_point_for_parent",
        get_kp,
    )
    monkeypatch.setattr(
        education_lesson_jobs,
        "create_generation_job",
        create_job,
    )

    with pytest.raises(LookupError, match="content asset"):
        await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
            parent_user_id="parent-1",
            knowledge_point_id="generic-kp-1",
        )

    create_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_lesson_generation_accepts_generic_candidate(monkeypatch) -> None:
    captured: dict[str, object] = {}
    scopes = AsyncMock()

    async def get_kp(**_kwargs):
        return dict(GENERIC_LESSON_JOB)

    async def create_job(**kwargs):
        captured.update(kwargs)
        return {
            "generation_job_id": "generation-generic-1",
            "scope": "lesson",
            "status": "queued",
            "auto_grading": kwargs["auto_grading"],
        }

    monkeypatch.setattr(
        education_lesson_jobs,
        "get_knowledge_point_for_parent",
        get_kp,
    )
    monkeypatch.setattr(
        education_lesson_jobs,
        "create_generation_job",
        create_job,
    )
    monkeypatch.setattr(
        education_lesson_jobs,
        "get_textbook_scopes_for_unit",
        scopes,
    )

    queued = await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
        parent_user_id="parent-1",
        knowledge_point_id="generic-kp-1",
        auto_grading=True,
    )

    assert queued["content_node_id"] == GENERIC_NODE_ID
    assert captured["knowledge_point_id"] == "generic-kp-1"
    assert captured["auto_grading"] is True
    scopes.assert_not_awaited()


@pytest.mark.asyncio
async def test_queue_lesson_generation_maps_auto_grading_conflict(monkeypatch) -> None:
    async def get_kp(**_kwargs):
        return dict(GENERIC_LESSON_JOB)

    async def conflict(**_kwargs):
        raise education_lesson_jobs.LessonGenerationConflictError(
            "Active lesson job uses different auto-grading settings"
        )

    monkeypatch.setattr(
        education_lesson_jobs,
        "get_knowledge_point_for_parent",
        get_kp,
    )
    monkeypatch.setattr(
        education_lesson_jobs,
        "create_generation_job",
        conflict,
    )

    with pytest.raises(
        education_lesson_jobs.TextbookTransitionError,
        match="different auto-grading",
    ):
        await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
            parent_user_id="parent-1",
            knowledge_point_id="kp-1",
            auto_grading=True,
        )


@pytest.mark.asyncio
async def test_finalize_lesson_generation_creates_immutable_revision(monkeypatch) -> None:
    stored: dict[str, object] = {}
    markdown = "# 世界运动\n\n课程内容。\n".encode()

    async def download(**_kwargs):
        return markdown, None

    async def write_revision(job, content):
        stored["write_job"] = job
        stored["content"] = content
        return {
            "content_key": "education/household-1/english-2/v1/lesson.md",
            "content_sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }

    async def create_revision(**kwargs):
        stored["create_revision"] = kwargs
        return {"lesson_id": "lesson-1", "revision_id": "revision-1"}

    async def settle(**kwargs):
        stored["settle"] = kwargs
        return {"status": kwargs["status"]}

    monkeypatch.setattr(education_lesson_jobs, "download_kp_lesson_outputs", download)
    monkeypatch.setattr(
        education_lesson_jobs,
        "write_kp_lesson_revision",
        write_revision,
    )
    monkeypatch.setattr(
        education_lesson_jobs,
        "create_kp_lesson_revision",
        create_revision,
    )
    monkeypatch.setattr(
        education_lesson_jobs,
        "settle_generation_job",
        settle,
    )

    result = await education_lesson_jobs.finalize_kp_lesson_generation(
        job=LESSON_JOB,
        attempt_id="attempt-1",
        root_run_id="run-1",
        sandbox=object(),
        terminal_status="completed",
        terminal_error=None,
    )

    assert result["lesson_id"] == "lesson-1"
    assert stored["content"] == markdown
    assert (
        stored["create_revision"]["generation_job_id"]
        == LESSON_JOB["generation_job_id"]
    )
    assert stored["settle"]["status"] == "completed"


@pytest.mark.asyncio
async def test_finalize_lesson_generation_fails_only_the_target_job(monkeypatch) -> None:
    settle_calls: list[dict[str, object]] = []

    async def download(**_kwargs):
        return b"", None

    async def settle(**kwargs):
        settle_calls.append(kwargs)
        return {"status": kwargs["status"]}

    monkeypatch.setattr(education_lesson_jobs, "download_kp_lesson_outputs", download)
    monkeypatch.setattr(education_lesson_jobs, "settle_generation_job", settle)

    result = await education_lesson_jobs.finalize_kp_lesson_generation(
        job=LESSON_JOB,
        attempt_id="attempt-1",
        root_run_id="run-1",
        sandbox=object(),
        terminal_status="completed",
        terminal_error=None,
    )

    assert result["status"] == "failed"
    assert settle_calls[0]["error_code"] == "managed_lesson_invalid"


@pytest.mark.asyncio
async def test_dispatch_lesson_starts_live_progress_collector(monkeypatch) -> None:
    job_id = LESSON_JOB["generation_job_id"]
    session = type("Session", (), {"sandbox": object()})()
    captured: dict[str, object] = {}
    collectors: list[dict[str, object]] = []
    graph = object()

    class FakeRunCoordinator:
        async def start_run(self, **kwargs):
            captured["run"] = kwargs
            return type(
                "RunHandle",
                (),
                {"run_id": kwargs["run_id"], "guard": object()},
            )()

    class FakeExecutor:
        async def start_run(self, **kwargs):
            captured["executor"] = kwargs

    class FakeRunSSEProducer:
        def __init__(self, **kwargs):
            captured["handler"] = kwargs

        async def stream_workflow(self, **_kwargs):
            if False:
                yield "unused"

    class FakeProgressCollector:
        def __init__(self, **kwargs):
            collectors.append(kwargs)

    async def build_graph(**_kwargs):
        return graph, {"messages": []}, {"configurable": {"thread_id": "thread-1"}}

    async def mark_running(**kwargs):
        return {"status": "running", **kwargs}

    monkeypatch.setattr(
        education_lesson_jobs,
        "stage_kp_lesson_inputs",
        AsyncMock(),
    )
    monkeypatch.setattr(
        education_lesson_jobs,
        "build_managed_education_graph",
        build_graph,
    )
    monkeypatch.setattr(
        education_lesson_jobs,
        "mark_generation_attempt_running",
        mark_running,
    )
    monkeypatch.setattr(
        education_lesson_jobs.RunCoordinator,
        "get_instance",
        classmethod(lambda cls: FakeRunCoordinator()),
    )
    monkeypatch.setattr(
        education_lesson_jobs.LocalRunExecutor,
        "get_instance",
        classmethod(lambda cls: FakeExecutor()),
    )
    monkeypatch.setattr(
        education_lesson_jobs,
        "RunSSEProducer",
        FakeRunSSEProducer,
    )
    monkeypatch.setattr(
        education_lesson_jobs,
        "ManagedProgressCollector",
        FakeProgressCollector,
    )

    result = await education_lesson_jobs._dispatch_kp_lesson_root_run(
        job=LESSON_JOB,
        source_context="# Source",
        scope={"slot": "reading_a"},
        chapter_markdown="# Chapter",
        attempt_id="attempt-1",
        session=session,
        workspace_id="workspace-1",
        thread_id="thread-1",
        agent_config=object(),
        parent_user_id="parent-1",
    )

    assert result == {"root_run_id": captured["run"]["run_id"]}
    assert captured["handler"]["replay_profile"] == "education_compact"
    assert collectors == [
        {
            "sandbox": session.sandbox,
            "generation_job_id": job_id,
            "attempt_id": "attempt-1",
            "run_id": captured["run"]["run_id"],
        }
    ]
    workflow = captured["executor"]["workflow_generator"]
    await workflow.aclose()


@pytest.mark.asyncio
async def test_launch_lesson_running_job_does_not_create_resources(monkeypatch) -> None:
    create_workspace = AsyncMock()

    async def get_job(**_kwargs):
        return {**LESSON_JOB, "status": "running", "latest_attempt_id": "attempt-1"}

    monkeypatch.setattr(education_lesson_jobs, "get_generation_job_for_parent", get_job)
    monkeypatch.setattr(
        education_lesson_jobs,
        "create_generation_workspace",
        create_workspace,
    )

    result = await education_lesson_jobs.launch_kp_lesson_generation(
        parent_user_id="parent-1",
        generation_job_id=LESSON_JOB["generation_job_id"],
    )

    assert result["launched"] == "false"
    assert result["status"] == "running"
    create_workspace.assert_not_awaited()


@pytest.mark.asyncio
async def test_launch_lesson_claim_loser_does_not_create_resources(monkeypatch) -> None:
    create_workspace = AsyncMock()
    projections = iter(
        (
            {**LESSON_JOB, "status": "queued", "latest_attempt_id": None},
            {**LESSON_JOB, "status": "preparing", "latest_attempt_id": None},
        )
    )

    async def get_job(**_kwargs):
        return next(projections)

    async def lose_claim(**_kwargs):
        return None

    monkeypatch.setattr(education_lesson_jobs, "get_generation_job_for_parent", get_job)
    monkeypatch.setattr(education_lesson_jobs, "claim_lesson_launch", lose_claim)
    monkeypatch.setattr(
        education_lesson_jobs,
        "create_generation_workspace",
        create_workspace,
    )

    result = await education_lesson_jobs.launch_kp_lesson_generation(
        parent_user_id="parent-1",
        generation_job_id=LESSON_JOB["generation_job_id"],
    )

    assert result["launched"] == "false"
    assert result["status"] == "preparing"
    create_workspace.assert_not_awaited()


@pytest.mark.asyncio
async def test_launch_lesson_attempt_claim_loser_does_not_create_resources(
    monkeypatch,
) -> None:
    create_workspace = AsyncMock()
    projections = iter(
        (
            {
                **LESSON_JOB,
                "status": "preparing",
                "latest_attempt_id": "attempt-1",
            },
            {
                **LESSON_JOB,
                "status": "preparing",
                "latest_attempt_id": "attempt-1",
            },
        )
    )

    async def get_job(**_kwargs):
        return next(projections)

    async def lose_claim(**_kwargs):
        return None

    monkeypatch.setattr(education_lesson_jobs, "get_generation_job_for_parent", get_job)
    monkeypatch.setattr(education_lesson_jobs, "claim_lesson_launch", lose_claim)
    monkeypatch.setattr(
        education_lesson_jobs,
        "create_generation_workspace",
        create_workspace,
    )

    result = await education_lesson_jobs.launch_kp_lesson_generation(
        parent_user_id="parent-1",
        generation_job_id=LESSON_JOB["generation_job_id"],
    )

    assert result["launched"] == "false"
    assert result["status"] == "preparing"
    create_workspace.assert_not_awaited()


@pytest.mark.asyncio
async def test_launch_lesson_pre_attempt_failure_marks_claim_failed(monkeypatch) -> None:
    failures: list[dict[str, object]] = []

    async def get_job(**_kwargs):
        return {**LESSON_JOB, "status": "queued", "latest_attempt_id": None}

    async def claim(**_kwargs):
        return {
            **LESSON_JOB,
            "status": "preparing",
            "latest_attempt_id": None,
        }

    async def fail_claim(**kwargs):
        failures.append(kwargs)
        return kwargs

    async def create_workspace(**_kwargs):
        raise RuntimeError("workspace unavailable")

    monkeypatch.setattr(education_lesson_jobs, "get_generation_job_for_parent", get_job)
    monkeypatch.setattr(education_lesson_jobs, "claim_lesson_launch", claim)
    monkeypatch.setattr(
        education_lesson_jobs,
        "fail_claimed_lesson_launch",
        fail_claim,
    )
    monkeypatch.setattr(
        education_lesson_jobs,
        "create_generation_workspace",
        create_workspace,
    )

    with pytest.raises(RuntimeError, match="workspace unavailable"):
        await education_lesson_jobs.launch_kp_lesson_generation(
            parent_user_id="parent-1",
            generation_job_id=LESSON_JOB["generation_job_id"],
        )

    assert failures == [
        {
            "generation_job_id": LESSON_JOB["generation_job_id"],
            "expected_latest_attempt_id": None,
            "error_code": "managed_lesson_launch_failed",
            "error_message": "单知识点课程生成无法启动，请稍后重试。",
        }
    ]
