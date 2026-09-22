"""Real Markdown contract for the canonical Reading pipeline."""

from __future__ import annotations

import hashlib
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from src.server.database import education_tasks, education_textbooks
from src.server.database.conversation.threads_write import create_thread
from src.server.database.workspace import create_workspace
from src.server.services import education_candidate_review
from src.server.services import education_lesson_jobs
from src.server.services.education_book_package import validate_book_package
from src.server.services.education_lesson_jobs import build_lesson_source_context
from src.server.services.education_reading_assets import build_reading_asset_inputs
from src.server.services.education_structure_scope_validation import (
    validate_structure_scopes,
)
from src.server.services.education_structure_validation import normalize_v2_units


REAL_MARKDOWN = Path(
    os.environ.get(
        "LANGALPHA_REAL_TEXTBOOK_MARKDOWN",
        "/Users/seanlee/DevelopCode/MoreAlpha/LangAlpha/"
        "datalab-output-REX 3e SB3 Page1-50.pdf.md",
    )
)


def _line_number(lines: list[str], needle: str, *, start: int = 0) -> int:
    return (
        next(
            index
            for index, line in enumerate(lines[start:], start=start)
            if needle in line
        )
        + 1
    )


def _line_index(lines: list[str], needle: str, *, start: int = 0) -> int:
    return next(
        index for index, line in enumerate(lines[start:], start=start) if needle in line
    )


def _test_connection(conn: psycopg.AsyncConnection):
    @asynccontextmanager
    async def _connect():
        yield conn

    return _connect


def _rex3_candidate() -> tuple[dict, str, dict[str, bytes]]:
    markdown = REAL_MARKDOWN.read_text(encoding="utf-8")
    lines = markdown.splitlines()
    unit_index = _line_index(lines, "## SPORTS AND FITNESS")
    reading_a_index = _line_index(lines, "### BEFORE YOU READ", start=unit_index)
    reading_b_index = _line_index(
        lines,
        "### BEFORE YOU READ",
        start=reading_a_index + 1,
    )
    sport_climbing_index = _line_index(
        lines,
        "### SPORT CLIMBING",
        start=reading_b_index + 1,
    )
    skin_deep_index = _line_index(lines, "## SKIN DEEP", start=unit_index)
    world_game_index = _line_index(lines, "### THE WORLD'S GAME")
    olympic_index = _line_index(lines, "### WHAT MAKES AN OLYMPIC CHAMPION?")

    asset_files = {
        "outputs/book-skill/chapters/reading-a/knowledge.md": (
            "# The World's Game\n\nSoccer became a global sport.\n".encode()
        ),
        "outputs/book-skill/chapters/reading-b/knowledge.md": (
            "# Olympic Champions\n\nElite athletes combine training and biology.\n".encode()
        ),
    }
    package = {
        "format": "langalpha-book-package/v1",
        "source_revision": hashlib.sha256(markdown.encode()).hexdigest(),
        "content_nodes": [
            {
                "node_key": "unit-1-sports",
                "parent_key": None,
                "node_type": "unit",
                "position": 1,
                "title": "Unit 1: Sports and Fitness",
                "summary": "Sports, identity, and elite performance.",
                "source_refs": [
                    {
                        "source_id": "source-1",
                        "line_start": unit_index + 1,
                        "line_end": skin_deep_index + 1,
                    }
                ],
            },
            {
                "node_key": "reading-a-world-game",
                "parent_key": "unit-1-sports",
                "node_type": "reading",
                "position": 1,
                "title": "The World's Game",
                "summary": "Soccer's global history and local meaning.",
                "source_refs": [
                    {
                        "source_id": "source-1",
                        "line_start": reading_a_index + 1,
                        "line_end": reading_b_index + 1,
                    }
                ],
            },
            {
                "node_key": "reading-b-olympic-champion",
                "parent_key": "unit-1-sports",
                "node_type": "reading",
                "position": 2,
                "title": "What Makes an Olympic Champion?",
                "summary": "The traits and training of elite athletes.",
                "source_refs": [
                    {
                        "source_id": "source-1",
                        "line_start": reading_b_index + 1,
                        "line_end": sport_climbing_index + 1,
                    }
                ],
            },
        ],
        "knowledge_points": [
            {
                "candidate_key": "world-game-global-sport",
                "node_key": "reading-a-world-game",
                "point_type": "theme",
                "title": "Soccer as a global sport",
                "summary": "Trade, migration, and media connected the game worldwide.",
                "source_refs": [
                    {
                        "source_id": "source-1",
                        "line_start": world_game_index + 1,
                        "line_end": world_game_index + 3,
                    }
                ],
                "confidence": 0.94,
            },
            {
                "candidate_key": "olympic-training-biology",
                "node_key": "reading-b-olympic-champion",
                "point_type": "concept",
                "title": "Training and biology in elite performance",
                "summary": "Elite athletes combine inherited traits with deliberate training.",
                "source_refs": [
                    {
                        "source_id": "source-1",
                        "line_start": olympic_index + 1,
                        "line_end": olympic_index + 3,
                    }
                ],
                "confidence": 0.93,
            },
        ],
        "assets": [
            {
                "node_key": "reading-a-world-game",
                "kind": "knowledge",
                "path": ("outputs/book-skill/chapters/reading-a/knowledge.md"),
                "content_sha256": hashlib.sha256(
                    asset_files["outputs/book-skill/chapters/reading-a/knowledge.md"]
                ).hexdigest(),
                "size_bytes": len(
                    asset_files["outputs/book-skill/chapters/reading-a/knowledge.md"]
                ),
            },
            {
                "node_key": "reading-b-olympic-champion",
                "kind": "knowledge",
                "path": ("outputs/book-skill/chapters/reading-b/knowledge.md"),
                "content_sha256": hashlib.sha256(
                    asset_files["outputs/book-skill/chapters/reading-b/knowledge.md"]
                ).hexdigest(),
                "size_bytes": len(
                    asset_files["outputs/book-skill/chapters/reading-b/knowledge.md"]
                ),
            },
        ],
    }
    validated, warnings = validate_book_package(package, markdown=markdown)
    assert "no_reading_nodes" not in warnings
    assert "source_refs_missing" not in warnings
    return validated, markdown, asset_files


async def _seed_running_pipeline(
    db_conn: psycopg.AsyncConnection,
) -> tuple[str, str, str, str]:
    parent_user_id = f"canonical-parent-{uuid4()}"
    household_id = str(uuid4())
    textbook_id = str(uuid4())
    version_id = str(uuid4())
    generation_job_id = str(uuid4())
    attempt_id = str(uuid4())
    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO users (user_id, name) VALUES (%s, %s)",
                (parent_user_id, "Canonical parent"),
            )
            await cur.execute(
                """
                INSERT INTO education_households (
                    household_id, name, model_owner_user_id
                ) VALUES (%s, %s, %s)
                """,
                (household_id, "Canonical household", parent_user_id),
            )
            await cur.execute(
                """
                INSERT INTO education_memberships (
                    household_id, user_id, role, display_name
                ) VALUES (%s, %s, 'parent', %s)
                """,
                (household_id, parent_user_id, "Canonical parent"),
            )
            await cur.execute(
                """
                INSERT INTO education_textbooks (
                    textbook_id, household_id, title, slug, created_by_user_id
                ) VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    textbook_id,
                    household_id,
                    "Reading Explorer 3",
                    f"rex3-{uuid4().hex}",
                    parent_user_id,
                ),
            )
            await cur.execute(
                """
                INSERT INTO education_textbook_versions (
                    version_id, textbook_id, sequence, status, created_by_user_id
                ) VALUES (%s, %s, 1, 'review', %s)
                """,
                (version_id, textbook_id, parent_user_id),
            )
        workspace = await create_workspace(
            user_id=parent_user_id,
            name=f"Canonical workspace {uuid4()}",
            status="running",
            conn=db_conn,
        )
        thread = await create_thread(
            conversation_thread_id=str(uuid4()),
            workspace_id=str(workspace["workspace_id"]),
            current_status="completed",
            msg_type="ptc",
            conn=db_conn,
        )
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO education_generation_jobs (
                    generation_job_id, version_id, scope, status,
                    attempt_count, processing_profile_sha256
                ) VALUES (%s, %s, 'book_pipeline', 'running', 1, %s)
                """,
                (generation_job_id, version_id, "a" * 64),
            )
            await cur.execute(
                """
                INSERT INTO education_generation_attempts (
                    attempt_id, generation_job_id, managed_workspace_id,
                    managed_thread_id, status
                ) VALUES (%s, %s, %s, %s, 'running')
                """,
                (
                    attempt_id,
                    generation_job_id,
                    workspace["workspace_id"],
                    thread["conversation_thread_id"],
                ),
            )
            await cur.execute(
                """
                UPDATE education_generation_jobs
                SET latest_attempt_id = %s
                WHERE generation_job_id = %s
                """,
                (attempt_id, generation_job_id),
            )
    return parent_user_id, version_id, generation_job_id, attempt_id


@pytest.mark.integration
def test_pipeline_builds_reading_assets_from_real_markdown() -> None:
    if not REAL_MARKDOWN.is_file():
        pytest.skip("REX 3 real Markdown fixture is unavailable")
    markdown = REAL_MARKDOWN.read_text(encoding="utf-8")
    lines = markdown.splitlines()
    unit_start = _line_number(lines, "## SPORTS AND FITNESS")
    reading_a_start = _line_number(lines, "### BEFORE YOU READ", start=unit_start)
    reading_b_start = _line_number(
        lines,
        "### BEFORE YOU READ",
        start=reading_a_start,
    )
    sport_climbing = _line_number(lines, "### SPORT CLIMBING")
    skin_deep = _line_number(lines, "## SKIN DEEP")
    structure = {
        "format": "langalpha-managed-textbook-structure/v2",
        "units": [
            {
                "unit": 1,
                "theme": "Sports and Fitness",
                "line_start": unit_start,
                "line_end": skin_deep - 1,
                "readings": [
                    {
                        "slot": "reading_a",
                        "title": "The World's Game",
                        "line_start": reading_a_start,
                        "line_end": reading_b_start - 1,
                        "summary": "Soccer's global history and local meaning.",
                    },
                    {
                        "slot": "reading_b",
                        "title": "What Makes an Olympic Champion?",
                        "line_start": reading_b_start,
                        "line_end": sport_climbing - 1,
                        "summary": "The traits and training of elite athletes.",
                    },
                ],
            }
        ],
    }

    scopes = validate_structure_scopes(
        structure,
        markdown=markdown,
        source_id="source-1",
    )
    units = normalize_v2_units(structure)
    job = {
        "units": [
            {
                **units[0],
                "unit_id": "unit-1",
                "scopes": [{**scope, "unit_id": "unit-1"} for scope in scopes],
            }
        ]
    }
    built = build_reading_asset_inputs(
        job,
        {"sources": [{"source_id": "source-1", "markdown": markdown}]},
        job["units"][0]["scopes"],
    )

    reading_a = built["files"][
        "inputs/readings/01-unit-1-sports-and-fitness/reading_a.md"
    ]
    reading_b = built["files"][
        "inputs/readings/01-unit-1-sports-and-fitness/reading_b.md"
    ]
    assert reading_a.startswith(b"### BEFORE YOU READ")
    assert b"THE WORLD'S GAME" in reading_a
    assert b"WHAT MAKES AN OLYMPIC CHAMPION?" not in reading_a
    assert reading_b.startswith(b"### BEFORE YOU READ")
    assert b"WHAT MAKES AN OLYMPIC CHAMPION?" in reading_b
    assert b"THE WORLD'S GAME" not in reading_b

    lesson_scope = next(
        scope for scope in job["units"][0]["scopes"] if scope["slot"] == "reading_b"
    )
    context, warnings = build_lesson_source_context(
        {
            "knowledge_point_scope_slot": "reading_b",
            "knowledge_point_title": "Olympic champions",
        },
        {"sources": [{"source_id": "source-1", "markdown": markdown}]},
        job["units"][0]["scopes"],
    )
    assert warnings == []
    assert lesson_scope["title"] in context
    assert "WHAT MAKES AN OLYMPIC CHAMPION?" in context


@pytest.mark.integration
@pytest.mark.asyncio
async def test_real_rex3_package_import_persists_pending_candidates_and_gates_lessons(
    cleanup_tables,
    db_conn,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if not REAL_MARKDOWN.is_file():
        pytest.skip("REX 3 real Markdown fixture is unavailable")
    package, _markdown, asset_files = _rex3_candidate()
    assert package["content_nodes"]
    assert package["knowledge_points"]
    assert any(node["node_type"] == "reading" for node in package["content_nodes"])
    node_keys = {node["node_key"] for node in package["content_nodes"]}
    assert all(point["node_key"] in node_keys for point in package["knowledge_points"])
    assert all(
        reference["resolution_status"] == "resolved" and bool(reference["quote"])
        for item in (*package["content_nodes"], *package["knowledge_points"])
        for reference in item["source_refs"]
    )

    (
        parent_user_id,
        version_id,
        generation_job_id,
        attempt_id,
    ) = await _seed_running_pipeline(db_conn)
    test_connection = _test_connection(db_conn)
    monkeypatch.setattr(
        education_textbooks,
        "get_db_connection",
        test_connection,
    )
    monkeypatch.setattr(
        education_tasks,
        "get_db_connection",
        test_connection,
    )
    imported = await education_textbooks.complete_book_pipeline_import(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
        attempt_id=attempt_id,
        package=package,
        bundle_prefix=("education/canonical-household/rex3/v1/book-packages/rex3"),
        bundle_manifest={"format": "langalpha-book-package-bundle/v1"},
        asset_content_keys={
            path: (
                "education/canonical-household/rex3/v1/"
                f"book-packages/rex3/{path.removeprefix('outputs/')}"
            )
            for path in asset_files
        },
    )
    assert imported is not None
    assert imported["node_count"] == len(package["content_nodes"])
    assert imported["knowledge_point_count"] == len(package["knowledge_points"])
    assert imported["asset_count"] == len(asset_files)

    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT knowledge_point_id, candidate_key, origin, candidate_status,
                   content_structure_id, content_node_id,
                   nodes.node_key AS content_node_key
            FROM education_structure_knowledge_points AS knowledge_points
            JOIN education_content_nodes AS nodes
              ON nodes.structure_id = knowledge_points.content_structure_id
             AND nodes.node_id = knowledge_points.content_node_id
            WHERE knowledge_points.content_structure_id = %s
            ORDER BY knowledge_points.candidate_key
            """,
            (imported["structure_id"],),
        )
        candidates = await cur.fetchall()
        assert len(candidates) == 2
        assert {row["origin"] for row in candidates} == {"generated"}
        assert {row["candidate_status"] for row in candidates} == {"pending"}
        assert all(row["content_node_id"] for row in candidates)
        assert {
            row["candidate_key"]: row["content_node_key"] for row in candidates
        } == {
            "world-game-global-sport": "reading-a-world-game",
            "olympic-training-biology": "reading-b-olympic-champion",
        }
        assert {str(row["content_structure_id"]) for row in candidates} == {
            str(imported["structure_id"])
        }
        await cur.execute(
            "SELECT COUNT(*) AS count FROM education_content_assets WHERE structure_id = %s",
            (imported["structure_id"],),
        )
        assert (await cur.fetchone())["count"] == 2
        await cur.execute(
            """
            SELECT COUNT(*) AS count
            FROM education_generation_jobs
            WHERE version_id = %s AND scope = 'lesson'
            """,
            (version_id,),
        )
        assert (await cur.fetchone())["count"] == 0

    candidate_id = str(candidates[0]["knowledge_point_id"])
    with pytest.raises(LookupError, match="accepted knowledge point"):
        await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
            parent_user_id=parent_user_id,
            knowledge_point_id=candidate_id,
        )
    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            SELECT COUNT(*) AS count
            FROM education_generation_jobs
            WHERE version_id = %s AND scope = 'lesson'
            """,
            (version_id,),
        )
        assert (await cur.fetchone())["count"] == 0

    await education_candidate_review.accept_knowledge_point_candidates_for_parent(
        parent_user_id=parent_user_id,
        candidate_ids=[candidate_id],
    )
    lesson_job = await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
        parent_user_id=parent_user_id,
        knowledge_point_id=candidate_id,
    )
    assert lesson_job["scope"] == "lesson"
    assert lesson_job["status"] == "queued"
    assert str(lesson_job["knowledge_point_id"]) == candidate_id
