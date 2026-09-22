"""Real PostgreSQL contracts for generated knowledge-point review."""

from __future__ import annotations

import asyncio
import hashlib
from uuid import uuid4

import psycopg
import pytest

from src.server.database import education_textbooks
from src.server.services import education_lesson_jobs
from src.server.services import education_teaching_storage


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def _seed_candidate_structure(
    db_conn: psycopg.AsyncConnection,
) -> tuple[str, str, str]:
    parent_user_id = f"candidate-parent-{uuid4()}"
    household_id = str(uuid4())
    textbook_id = str(uuid4())
    version_id = str(uuid4())
    structure_id = str(uuid4())
    node_id = str(uuid4())
    async with db_conn.transaction():
        async with db_conn.cursor() as cur:
            await cur.execute(
                "INSERT INTO users (user_id, name) VALUES (%s, %s)",
                (parent_user_id, "Candidate parent"),
            )
            await cur.execute(
                """
                INSERT INTO education_households (
                    household_id, name, model_owner_user_id
                ) VALUES (%s, %s, %s)
                """,
                (household_id, "Candidate household", parent_user_id),
            )
            await cur.execute(
                """
                INSERT INTO education_memberships (
                    household_id, user_id, role, display_name
                ) VALUES (%s, %s, 'parent', %s)
                """,
                (household_id, parent_user_id, "Parent"),
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
                    "Candidate textbook",
                    f"candidate-{uuid4().hex}",
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
            await cur.execute(
                """
                INSERT INTO education_textbook_structures (
                    structure_id, version_id, sequence, status, schema_version,
                    processing_profile_sha256, input_manifest_sha256,
                    source_revision, created_by_user_id
                ) VALUES (
                    %s, %s, 1, 'review', 'langalpha-book-content-tree/v1',
                    %s, %s, %s, %s
                )
                """,
                (
                    structure_id,
                    version_id,
                    "a" * 64,
                    "b" * 64,
                    "revision-1",
                    parent_user_id,
                ),
            )
            await cur.execute(
                """
                INSERT INTO education_content_nodes (
                    node_id, structure_id, parent_node_id, node_key, node_type,
                    label, position, slug, title, summary, source_refs, metadata
                ) VALUES (
                    %s, %s, NULL, 'unit-1', 'unit', NULL, 1, 'unit-1',
                    'Unit 1', '', '[]'::jsonb, '{}'::jsonb
                )
                """,
                (node_id, structure_id),
            )
    return parent_user_id, structure_id, node_id


async def _insert_candidate(
    db_conn: psycopg.AsyncConnection,
    *,
    structure_id: str,
    node_id: str,
    candidate_key: str,
    title: str,
    position: int = 1,
) -> str:
    candidate_id = str(uuid4())
    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO education_structure_knowledge_points (
                knowledge_point_id, unit_id, content_structure_id,
                content_node_id, candidate_key, point_type, origin,
                candidate_status, position, slug, title, summary,
                source_refs, confidence, status
            ) VALUES (
                %s, NULL, %s, %s, %s, 'concept', 'generated',
                'pending', %s, %s, %s, '', '[]'::jsonb, 0.9, 'review'
            )
            """,
            (
                candidate_id,
                structure_id,
                node_id,
                candidate_key,
                position,
                candidate_key,
                title,
            ),
        )
    return candidate_id


async def _insert_node_asset(
    db_conn: psycopg.AsyncConnection,
    *,
    structure_id: str,
    node_id: str,
    content_key: str,
    asset_type: str = "knowledge",
) -> str:
    asset_id = str(uuid4())
    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO education_content_assets (
                asset_id, structure_id, node_id, asset_type, content_key,
                content_sha256, size_bytes, metadata
            ) VALUES (
                %s, %s, %s, %s, %s, %s, 12, '{}'::jsonb
            )
            """,
            (
                asset_id,
                structure_id,
                node_id,
                asset_type,
                content_key,
                "c" * 64,
            ),
        )
    return asset_id


async def _insert_managed_runtime(
    db_conn: psycopg.AsyncConnection,
    *,
    parent_user_id: str,
    label: str,
) -> tuple[str, str]:
    workspace_id = str(uuid4())
    thread_id = str(uuid4())
    async with db_conn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO workspaces (workspace_id, user_id, name, status)
            VALUES (%s, %s, %s, 'running')
            """,
            (workspace_id, parent_user_id, f"{label} workspace"),
        )
        await cur.execute(
            """
            INSERT INTO conversation_threads (
                conversation_thread_id, workspace_id, msg_type,
                current_status, thread_index, title, platform
            ) VALUES (
                %s, %s, 'ptc', 'completed', 1, %s, 'education'
            )
            """,
            (thread_id, workspace_id, f"{label} thread"),
        )
    return workspace_id, thread_id


@pytest.mark.asyncio
async def test_concurrent_replacement_claim_and_stale_reclaim_keep_valid_chain(
    patched_get_db_connection,
) -> None:
    async with patched_get_db_connection() as db_conn:
        parent_user_id, structure_id, node_id = await _seed_candidate_structure(db_conn)
        candidate_id = await _insert_candidate(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            candidate_key="claim-chain-lesson",
            title="Claim chain lesson",
        )
        await _insert_node_asset(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            content_key=(
                f"education/household/book/v1/book-packages/{uuid4()}/"
                "assets/chapters/unit-1/knowledge.md"
            ),
        )
    await education_textbooks.accept_knowledge_point_candidates_for_parent(
        parent_user_id=parent_user_id,
        candidate_ids=[candidate_id],
    )
    queued = await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
        parent_user_id=parent_user_id,
        knowledge_point_id=candidate_id,
    )
    generation_job_id = str(queued["generation_job_id"])
    await education_textbooks.claim_lesson_launch(
        parent_user_id=parent_user_id,
        generation_job_id=generation_job_id,
    )
    async with patched_get_db_connection() as db_conn:
        old_workspace_id, old_thread_id = await _insert_managed_runtime(
            db_conn,
            parent_user_id=parent_user_id,
            label="Claim chain old",
        )
    old_attempt = await education_textbooks.claim_generation_job(
        generation_job_id=generation_job_id,
        managed_workspace_id=old_workspace_id,
        managed_thread_id=old_thread_id,
        expected_job_status="preparing",
    )
    assert old_attempt is not None
    async with patched_get_db_connection() as db_conn:
        replacement_workspace_id, replacement_thread_id = await _insert_managed_runtime(
            db_conn,
            parent_user_id=parent_user_id,
            label="Claim chain replacement",
        )
    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE education_generation_jobs
                SET updated_at = NOW() - INTERVAL '6 minutes'
                WHERE generation_job_id = %s
                """,
                (generation_job_id,),
            )
            await cur.execute(
                """
                UPDATE education_generation_attempts
                SET started_at = NOW() - INTERVAL '6 minutes',
                    heartbeat_at = NOW() - INTERVAL '6 minutes'
                WHERE attempt_id = %s
                """,
                (old_attempt["attempt_id"],),
            )

    replacement, reclaimed = await asyncio.wait_for(
        asyncio.gather(
            education_textbooks.claim_generation_job(
                generation_job_id=generation_job_id,
                managed_workspace_id=replacement_workspace_id,
                managed_thread_id=replacement_thread_id,
                expected_job_status="preparing",
            ),
            education_textbooks.claim_lesson_launch(
                parent_user_id=parent_user_id,
                generation_job_id=generation_job_id,
            ),
        ),
        timeout=10,
    )
    assert reclaimed is not None

    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                SELECT generation_job_id, status, latest_attempt_id,
                       attempt_count
                FROM education_generation_jobs
                WHERE generation_job_id = %s
                """,
                (generation_job_id,),
            )
            job = await cur.fetchone()
            await cur.execute(
                """
                SELECT attempt_id, previous_attempt_id, status, root_run_id
                FROM education_generation_attempts
                WHERE generation_job_id = %s
                ORDER BY started_at, attempt_id
                """,
                (generation_job_id,),
            )
            attempts = [dict(row) for row in await cur.fetchall()]

    assert job["status"] == "preparing"
    assert attempts[0]["status"] == "worker_lost"
    assert attempts[0]["root_run_id"] is None
    assert len(attempts) in {1, 2}
    if replacement is not None:
        assert len(attempts) == 2
        assert str(job["latest_attempt_id"]) == str(replacement["attempt_id"])
        assert str(replacement["previous_attempt_id"]) == str(old_attempt["attempt_id"])
        assert str(attempts[1]["previous_attempt_id"]) == str(old_attempt["attempt_id"])
    else:
        assert len(attempts) == 1
        assert str(job["latest_attempt_id"]) == str(old_attempt["attempt_id"])


@pytest.mark.asyncio
async def test_lesson_gate_requires_accepted_generic_candidate_with_node_asset(
    patched_get_db_connection,
) -> None:
    async with patched_get_db_connection() as db_conn:
        parent_user_id, structure_id, node_id = await _seed_candidate_structure(db_conn)
        candidate_id = await _insert_candidate(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            candidate_key="lesson-gate-kp",
            title="Lesson gate candidate",
        )
        asset_id = await _insert_node_asset(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            content_key=(
                "education/household/book/v1/book-packages/job/"
                "assets/chapters/unit-1/knowledge.md"
            ),
        )

    with pytest.raises(LookupError, match="accepted knowledge point"):
        await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
            parent_user_id=parent_user_id,
            knowledge_point_id=candidate_id,
        )

    accepted = await education_textbooks.accept_knowledge_point_candidates_for_parent(
        parent_user_id=parent_user_id,
        candidate_ids=[candidate_id],
    )
    assert accepted is not None
    context = await education_textbooks.get_knowledge_point_for_parent(
        parent_user_id=parent_user_id,
        knowledge_point_id=candidate_id,
    )
    assert context is not None
    assert context["candidate_status"] == "accepted"
    assert str(context["content_node_id"]) == node_id
    assert str(context["content_asset_id"]) == asset_id

    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM education_content_assets WHERE asset_id = %s",
                (asset_id,),
            )
    with pytest.raises(LookupError, match="content asset"):
        await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
            parent_user_id=parent_user_id,
            knowledge_point_id=candidate_id,
        )
    async with patched_get_db_connection() as db_conn:
        await _insert_node_asset(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            asset_type="practice",
            content_key=(
                "education/household/book/v1/book-packages/job/"
                "assets/chapters/unit-1/practice.md"
            ),
        )
    with pytest.raises(LookupError, match="content asset"):
        await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
            parent_user_id=parent_user_id,
            knowledge_point_id=candidate_id,
        )
    async with patched_get_db_connection() as db_conn:
        await _insert_node_asset(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            content_key=(
                f"education/household/book/v1/book-packages/{uuid4()}/"
                "assets/chapters/unit-1/knowledge.md"
            ),
        )

    queued = await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
        parent_user_id=parent_user_id,
        knowledge_point_id=candidate_id,
        auto_grading=True,
    )
    assert queued["scope"] == "lesson"
    assert queued["status"] == "queued"

    async with patched_get_db_connection() as db_conn:
        other_parent_id, _, _ = await _seed_candidate_structure(db_conn)
    with pytest.raises(LookupError):
        await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
            parent_user_id=other_parent_id,
            knowledge_point_id=candidate_id,
        )


@pytest.mark.asyncio
async def test_generic_lesson_projection_uses_content_node_metadata(
    patched_get_db_connection,
) -> None:
    async with patched_get_db_connection() as db_conn:
        parent_user_id, structure_id, node_id = await _seed_candidate_structure(db_conn)
        candidate_id = await _insert_candidate(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            candidate_key="generic-lesson-kp",
            title="Generic lesson candidate",
        )
    await education_textbooks.accept_knowledge_point_candidates_for_parent(
        parent_user_id=parent_user_id,
        candidate_ids=[candidate_id],
    )

    lesson_id = str(uuid4())
    revision_id = str(uuid4())
    content_key = (
        "education/household/book/v1/structures/v1/"
        f"content-nodes/{node_id}/knowledge-points/generic-lesson-kp/"
        f"lessons/job-{uuid4()}/lesson.md"
    )
    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO education_kp_lessons (
                    lesson_id, knowledge_point_id, status, latest_revision_id
                ) VALUES (%s, %s, 'review', NULL)
                """,
                (lesson_id, candidate_id),
            )
            await cur.execute(
                """
                INSERT INTO education_kp_lesson_revisions (
                    revision_id, lesson_id, revision, format, content_key,
                    content_sha256, size_bytes, processing_profile_sha256,
                    generation_job_id
                ) VALUES (
                    %s, %s, 1, 'markdown', %s, %s, 12, %s, NULL
                )
                """,
                (
                    revision_id,
                    lesson_id,
                    content_key,
                    "d" * 64,
                    "e" * 64,
                ),
            )
            await cur.execute(
                """
                UPDATE education_kp_lessons
                SET latest_revision_id = %s
                WHERE lesson_id = %s
                """,
                (revision_id, lesson_id),
            )

    lesson = await education_textbooks.get_kp_lesson_for_parent(
        parent_user_id=parent_user_id,
        lesson_id=lesson_id,
    )
    assert lesson is not None
    assert str(lesson["unit_id"]) == node_id
    assert lesson["unit_title"] == "Unit 1"
    assert str(lesson["content_node_id"]) == node_id
    assert lesson["candidate_key"] == "generic-lesson-kp"
    assert lesson["revisions"][0]["content_key"] == content_key

    by_point = await education_textbooks.get_kp_lesson_by_knowledge_point_for_parent(
        parent_user_id=parent_user_id,
        knowledge_point_id=candidate_id,
    )
    assert by_point is not None
    assert str(by_point["lesson_id"]) == lesson_id
    assert str(by_point["content_node_id"]) == node_id


@pytest.mark.asyncio
async def test_long_generic_candidate_keys_create_distinct_lesson_revisions(
    patched_get_db_connection,
) -> None:
    async with patched_get_db_connection() as db_conn:
        parent_user_id, structure_id, node_id = await _seed_candidate_structure(db_conn)
        candidate_ids = [
            await _insert_candidate(
                db_conn,
                structure_id=structure_id,
                node_id=node_id,
                candidate_key="x" * 81 + suffix,
                title=f"Long key {suffix}",
                position=position,
            )
            for position, suffix in enumerate(("A", "B"), start=1)
        ]
    await education_textbooks.accept_knowledge_point_candidates_for_parent(
        parent_user_id=parent_user_id,
        candidate_ids=candidate_ids,
    )

    content_keys: list[str] = []
    revision_ids: list[str] = []
    for candidate_id, candidate_key in zip(
        candidate_ids,
        ("x" * 81 + "A", "x" * 81 + "B"),
        strict=True,
    ):
        job = {
            "household_id": "household-1",
            "slug": "generic-textbook",
            "content_version_sequence": 1,
            "structure_sequence": 1,
            "generation_job_id": str(uuid4()),
            "content_node_id": node_id,
            "knowledge_point_id": candidate_id,
            "candidate_key": candidate_key,
        }
        content_sha256 = ("a" if candidate_key.endswith("A") else "b") * 64
        content_key = education_teaching_storage.kp_lesson_content_key(
            job,
            content_sha256=content_sha256,
        )
        revision = await education_textbooks.create_kp_lesson_revision(
            knowledge_point_id=candidate_id,
            content_key=content_key,
            content_sha256=content_sha256,
            size_bytes=12,
            processing_profile_sha256="e" * 64,
            generation_job_id=None,
        )
        assert revision is not None
        content_keys.append(content_key)
        revision_ids.append(str(revision["revision_id"]))

    assert content_keys[0] != content_keys[1]
    assert revision_ids[0] != revision_ids[1]
    repeated = await education_textbooks.create_kp_lesson_revision(
        knowledge_point_id=candidate_ids[0],
        content_key=content_keys[0],
        content_sha256=("a" * 64),
        size_bytes=12,
        processing_profile_sha256="e" * 64,
        generation_job_id=None,
    )
    assert repeated is not None
    assert str(repeated["revision_id"]) == revision_ids[0]
    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                SELECT COUNT(*) AS count
                FROM education_kp_lesson_revisions
                WHERE revision_id = ANY(%s::uuid[])
                """,
                (revision_ids,),
            )
            row = await cur.fetchone()
    assert row["count"] == 2


@pytest.mark.asyncio
async def test_existing_content_revision_repoints_lesson_latest(
    patched_get_db_connection,
    monkeypatch,
) -> None:
    async with patched_get_db_connection() as db_conn:
        parent_user_id, structure_id, node_id = await _seed_candidate_structure(db_conn)
        candidate_id = await _insert_candidate(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            candidate_key="repoint-lesson",
            title="Repoint lesson",
        )
    await education_textbooks.accept_knowledge_point_candidates_for_parent(
        parent_user_id=parent_user_id,
        candidate_ids=[candidate_id],
    )
    job = {
        "household_id": "household-1",
        "slug": "generic-textbook",
        "content_version_sequence": 1,
        "structure_sequence": 1,
        "generation_job_id": str(uuid4()),
        "content_node_id": node_id,
        "knowledge_point_id": candidate_id,
        "candidate_key": "repoint-lesson",
    }
    first_content = b"# Version 1\n"
    second_content = b"# Version 2\n"
    first_sha = hashlib.sha256(first_content).hexdigest()
    second_sha = hashlib.sha256(second_content).hexdigest()
    first_key = education_teaching_storage.kp_lesson_content_key(
        job,
        content_sha256=first_sha,
    )
    second_key = education_teaching_storage.kp_lesson_content_key(
        job,
        content_sha256=second_sha,
    )
    first = await education_textbooks.create_kp_lesson_revision(
        knowledge_point_id=candidate_id,
        content_key=first_key,
        content_sha256=first_sha,
        size_bytes=len(first_content),
        processing_profile_sha256="e" * 64,
        generation_job_id=None,
    )
    second = await education_textbooks.create_kp_lesson_revision(
        knowledge_point_id=candidate_id,
        content_key=second_key,
        content_sha256=second_sha,
        size_bytes=len(second_content),
        processing_profile_sha256="e" * 64,
        generation_job_id=None,
    )
    assert first is not None and second is not None
    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE education_kp_lessons
                SET latest_revision_id = %s, status = 'approved',
                    reviewed_at = NOW()
                WHERE lesson_id = %s
                """,
                (second["revision_id"], second["lesson_id"]),
            )

    repeated = await education_textbooks.create_kp_lesson_revision(
        knowledge_point_id=candidate_id,
        content_key=first_key,
        content_sha256=first_sha,
        size_bytes=len(first_content),
        processing_profile_sha256="e" * 64,
        generation_job_id=None,
    )
    assert repeated is not None
    assert str(repeated["revision_id"]) == str(first["revision_id"])
    assert str(repeated["latest_revision_id"]) == str(first["revision_id"])
    assert repeated["status"] == "review"

    lesson = await education_textbooks.get_kp_lesson_for_parent(
        parent_user_id=parent_user_id,
        lesson_id=str(first["lesson_id"]),
    )
    assert lesson is not None
    assert str(lesson["latest_revision_id"]) == str(first["revision_id"])
    assert lesson["status"] == "review"
    assert lesson["reviewed_at"] is None

    monkeypatch.setattr(
        education_teaching_storage,
        "get_bytes",
        lambda key: first_content if key == first_key else None,
    )
    content = await education_teaching_storage.read_kp_lesson_revision(
        first_key,
        expected_sha256=first_sha,
        expected_size=len(first_content),
    )
    assert content == first_content


@pytest.mark.asyncio
async def test_concurrent_generic_lesson_queue_reuses_one_active_job(
    patched_get_db_connection,
) -> None:
    async with patched_get_db_connection() as db_conn:
        parent_user_id, structure_id, node_id = await _seed_candidate_structure(db_conn)
        candidate_id = await _insert_candidate(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            candidate_key="concurrent-generic-lesson",
            title="Concurrent lesson candidate",
        )
        await _insert_node_asset(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            content_key=(
                "education/household/book/v1/book-packages/job/"
                "assets/chapters/unit-1/knowledge.md"
            ),
        )
    await education_textbooks.accept_knowledge_point_candidates_for_parent(
        parent_user_id=parent_user_id,
        candidate_ids=[candidate_id],
    )

    first, second = await asyncio.gather(
        education_lesson_jobs.queue_kp_lesson_generation_for_parent(
            parent_user_id=parent_user_id,
            knowledge_point_id=candidate_id,
        ),
        education_lesson_jobs.queue_kp_lesson_generation_for_parent(
            parent_user_id=parent_user_id,
            knowledge_point_id=candidate_id,
        ),
    )

    assert first["generation_job_id"] == second["generation_job_id"]
    assert sorted(
        bool(item.get("reused_existing_job")) for item in (first, second)
    ) == [False, True]
    with pytest.raises(
        education_lesson_jobs.TextbookTransitionError,
        match="different auto-grading",
    ):
        await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
            parent_user_id=parent_user_id,
            knowledge_point_id=candidate_id,
            auto_grading=True,
        )
    job = await education_textbooks.get_generation_job_for_parent(
        parent_user_id=parent_user_id,
        generation_job_id=str(first["generation_job_id"]),
    )
    assert job is not None
    assert job["content_node_source_refs"] == []
    context, warnings = education_lesson_jobs.build_lesson_source_context(
        job,
        {"sources": []},
        [],
        content_node_markdown="# Node asset fallback\n",
    )
    assert warnings == []
    assert context == "## Unit 1\n# Node asset fallback"
    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                SELECT COUNT(*) AS count
                FROM education_generation_jobs
                WHERE knowledge_point_id = %s AND scope = 'lesson'
                """,
                (candidate_id,),
            )
            row = await cur.fetchone()
    assert row["count"] == 1


@pytest.mark.asyncio
async def test_lesson_launch_claim_has_one_winner_and_recovers_after_failure(
    patched_get_db_connection,
) -> None:
    async with patched_get_db_connection() as db_conn:
        parent_user_id, structure_id, node_id = await _seed_candidate_structure(db_conn)
        candidate_id = await _insert_candidate(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            candidate_key="launch-claim-lesson",
            title="Launch claim lesson",
        )
        await _insert_node_asset(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            content_key=(
                f"education/household/book/v1/book-packages/{uuid4()}/"
                "assets/chapters/unit-1/knowledge.md"
            ),
        )
    await education_textbooks.accept_knowledge_point_candidates_for_parent(
        parent_user_id=parent_user_id,
        candidate_ids=[candidate_id],
    )
    queued = await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
        parent_user_id=parent_user_id,
        knowledge_point_id=candidate_id,
    )
    generation_job_id = str(queued["generation_job_id"])

    claims = await asyncio.gather(
        education_textbooks.claim_lesson_launch(
            parent_user_id=parent_user_id,
            generation_job_id=generation_job_id,
        ),
        education_textbooks.claim_lesson_launch(
            parent_user_id=parent_user_id,
            generation_job_id=generation_job_id,
        ),
    )
    assert sum(claim is not None for claim in claims) == 1

    failed = await education_textbooks.fail_claimed_lesson_launch(
        generation_job_id=generation_job_id,
        expected_latest_attempt_id=None,
        error_code="managed_lesson_launch_failed",
        error_message="launch failed before attempt",
    )
    assert failed is not None
    assert failed["status"] == "failed"

    replacement = await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
        parent_user_id=parent_user_id,
        knowledge_point_id=candidate_id,
    )
    assert replacement["generation_job_id"] != generation_job_id
    assert replacement["reused_existing_job"] is False

    replacement_job_id = str(replacement["generation_job_id"])
    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE education_generation_jobs
                SET status = 'preparing', latest_attempt_id = NULL,
                    updated_at = NOW()
                WHERE generation_job_id = %s
                """,
                (replacement_job_id,),
            )
    assert (
        await education_textbooks.claim_lesson_launch(
            parent_user_id=parent_user_id,
            generation_job_id=replacement_job_id,
        )
        is None
    )

    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE education_generation_jobs
                SET updated_at = NOW() - INTERVAL '6 minutes'
                WHERE generation_job_id = %s
                """,
                (replacement_job_id,),
            )
    claims = await asyncio.gather(
        education_textbooks.claim_lesson_launch(
            parent_user_id=parent_user_id,
            generation_job_id=replacement_job_id,
        ),
        education_textbooks.claim_lesson_launch(
            parent_user_id=parent_user_id,
            generation_job_id=replacement_job_id,
        ),
    )
    assert sum(claim is not None for claim in claims) == 1

    workspace_id = str(uuid4())
    thread_id = str(uuid4())
    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO workspaces (workspace_id, user_id, name, status)
                VALUES (%s, %s, 'Lesson recovery workspace', 'running')
                """,
                (workspace_id, parent_user_id),
            )
            await cur.execute(
                """
                INSERT INTO conversation_threads (
                    conversation_thread_id, workspace_id, msg_type,
                    current_status, thread_index, title, platform
                ) VALUES (
                    %s, %s, 'ptc', 'completed', 1,
                    'Lesson recovery thread', 'education'
                )
                """,
                (thread_id, workspace_id),
            )
    attempt = await education_textbooks.claim_generation_job(
        generation_job_id=replacement_job_id,
        managed_workspace_id=workspace_id,
        managed_thread_id=thread_id,
        expected_job_status="preparing",
    )
    assert attempt is not None
    settled = await education_textbooks.settle_generation_job(
        generation_job_id=replacement_job_id,
        attempt_id=str(attempt["attempt_id"]),
        status="completed",
    )
    assert settled is not None
    assert settled["status"] == "completed"


@pytest.mark.asyncio
async def test_stale_lesson_attempt_is_fenced_and_reclaimed(
    patched_get_db_connection,
) -> None:
    async with patched_get_db_connection() as db_conn:
        parent_user_id, structure_id, node_id = await _seed_candidate_structure(db_conn)
        candidate_id = await _insert_candidate(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            candidate_key="attempt-recovery-lesson",
            title="Attempt recovery lesson",
        )
        await _insert_node_asset(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            content_key=(
                f"education/household/book/v1/book-packages/{uuid4()}/"
                "assets/chapters/unit-1/knowledge.md"
            ),
        )
    await education_textbooks.accept_knowledge_point_candidates_for_parent(
        parent_user_id=parent_user_id,
        candidate_ids=[candidate_id],
    )
    queued = await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
        parent_user_id=parent_user_id,
        knowledge_point_id=candidate_id,
    )
    generation_job_id = str(queued["generation_job_id"])
    assert (
        await education_textbooks.claim_lesson_launch(
            parent_user_id=parent_user_id,
            generation_job_id=generation_job_id,
        )
        is not None
    )

    workspace_id = str(uuid4())
    thread_id = str(uuid4())
    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO workspaces (workspace_id, user_id, name, status)
                VALUES (%s, %s, 'Attempt recovery workspace', 'running')
                """,
                (workspace_id, parent_user_id),
            )
            await cur.execute(
                """
                INSERT INTO conversation_threads (
                    conversation_thread_id, workspace_id, msg_type,
                    current_status, thread_index, title, platform
                ) VALUES (
                    %s, %s, 'ptc', 'completed', 1,
                    'Attempt recovery thread', 'education'
                )
                """,
                (thread_id, workspace_id),
            )
    old_attempt = await education_textbooks.claim_generation_job(
        generation_job_id=generation_job_id,
        managed_workspace_id=workspace_id,
        managed_thread_id=thread_id,
        expected_job_status="preparing",
    )
    assert old_attempt is not None
    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE education_generation_jobs
                SET updated_at = NOW() - INTERVAL '6 minutes'
                WHERE generation_job_id = %s
                """,
                (generation_job_id,),
            )
            await cur.execute(
                """
                UPDATE education_generation_attempts
                SET started_at = NOW() - INTERVAL '6 minutes',
                    heartbeat_at = NOW() - INTERVAL '6 minutes'
                WHERE attempt_id = %s
                """,
                (old_attempt["attempt_id"],),
            )

    claims = await asyncio.gather(
        education_textbooks.claim_lesson_launch(
            parent_user_id=parent_user_id,
            generation_job_id=generation_job_id,
        ),
        education_textbooks.claim_lesson_launch(
            parent_user_id=parent_user_id,
            generation_job_id=generation_job_id,
        ),
    )
    assert sum(claim is not None for claim in claims) == 1

    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                SELECT status, error_code, completed_at
                FROM education_generation_attempts
                WHERE attempt_id = %s
                """,
                (old_attempt["attempt_id"],),
            )
            fenced = await cur.fetchone()
    assert fenced["status"] == "worker_lost"
    assert fenced["error_code"] == "launch_abandoned"
    assert fenced["completed_at"] is not None

    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE education_generation_jobs
                SET updated_at = NOW() - INTERVAL '6 minutes'
                WHERE generation_job_id = %s
                """,
                (generation_job_id,),
            )
    second_claims = await asyncio.gather(
        education_textbooks.claim_lesson_launch(
            parent_user_id=parent_user_id,
            generation_job_id=generation_job_id,
        ),
        education_textbooks.claim_lesson_launch(
            parent_user_id=parent_user_id,
            generation_job_id=generation_job_id,
        ),
    )
    assert sum(claim is not None for claim in second_claims) == 1
    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                SELECT status, error_code
                FROM education_generation_attempts
                WHERE attempt_id = %s
                """,
                (old_attempt["attempt_id"],),
            )
            still_fenced = await cur.fetchone()
    assert still_fenced["status"] == "worker_lost"
    assert still_fenced["error_code"] == "launch_abandoned"

    replacement_workspace_id = str(uuid4())
    replacement_thread_id = str(uuid4())
    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO workspaces (workspace_id, user_id, name, status)
                VALUES (%s, %s, 'Attempt recovery retry workspace', 'running')
                """,
                (replacement_workspace_id, parent_user_id),
            )
            await cur.execute(
                """
                INSERT INTO conversation_threads (
                    conversation_thread_id, workspace_id, msg_type,
                    current_status, thread_index, title, platform
                ) VALUES (
                    %s, %s, 'ptc', 'completed', 1,
                    'Attempt recovery retry thread', 'education'
                )
                """,
                (replacement_thread_id, replacement_workspace_id),
            )
    new_attempt = await education_textbooks.claim_generation_job(
        generation_job_id=generation_job_id,
        managed_workspace_id=replacement_workspace_id,
        managed_thread_id=replacement_thread_id,
        expected_job_status="preparing",
    )
    assert new_attempt is not None
    assert str(new_attempt["previous_attempt_id"]) == str(old_attempt["attempt_id"])
    settled = await education_textbooks.settle_generation_job(
        generation_job_id=generation_job_id,
        attempt_id=str(new_attempt["attempt_id"]),
        status="completed",
    )
    assert settled is not None
    assert settled["status"] == "completed"


@pytest.mark.asyncio
async def test_reclaim_and_mark_running_use_consistent_lock_order(
    patched_get_db_connection,
) -> None:
    async with patched_get_db_connection() as db_conn:
        parent_user_id, structure_id, node_id = await _seed_candidate_structure(db_conn)
        candidate_id = await _insert_candidate(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            candidate_key="lock-order-lesson",
            title="Lock order lesson",
        )
        await _insert_node_asset(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            content_key=(
                f"education/household/book/v1/book-packages/{uuid4()}/"
                "assets/chapters/unit-1/knowledge.md"
            ),
        )
    await education_textbooks.accept_knowledge_point_candidates_for_parent(
        parent_user_id=parent_user_id,
        candidate_ids=[candidate_id],
    )
    queued = await education_lesson_jobs.queue_kp_lesson_generation_for_parent(
        parent_user_id=parent_user_id,
        knowledge_point_id=candidate_id,
    )
    generation_job_id = str(queued["generation_job_id"])
    assert (
        await education_textbooks.claim_lesson_launch(
            parent_user_id=parent_user_id,
            generation_job_id=generation_job_id,
        )
        is not None
    )

    workspace_id = str(uuid4())
    thread_id = str(uuid4())
    root_run_id = str(uuid4())
    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO workspaces (workspace_id, user_id, name, status)
                VALUES (%s, %s, 'Lock order workspace', 'running')
                """,
                (workspace_id, parent_user_id),
            )
            await cur.execute(
                """
                INSERT INTO conversation_threads (
                    conversation_thread_id, workspace_id, msg_type,
                    current_status, thread_index, title, platform
                ) VALUES (
                    %s, %s, 'ptc', 'completed', 1,
                    'Lock order thread', 'education'
                )
                """,
                (thread_id, workspace_id),
            )
            await cur.execute(
                """
                INSERT INTO conversation_responses (
                    conversation_response_id, conversation_thread_id,
                    turn_index, status, created_at
                ) VALUES (%s, %s, 1, 'in_progress', NOW())
                """,
                (root_run_id, thread_id),
            )
    old_attempt = await education_textbooks.claim_generation_job(
        generation_job_id=generation_job_id,
        managed_workspace_id=workspace_id,
        managed_thread_id=thread_id,
        expected_job_status="preparing",
    )
    assert old_attempt is not None
    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                UPDATE education_generation_jobs
                SET updated_at = NOW() - INTERVAL '6 minutes'
                WHERE generation_job_id = %s
                """,
                (generation_job_id,),
            )
            await cur.execute(
                """
                UPDATE education_generation_attempts
                SET started_at = NOW() - INTERVAL '6 minutes',
                    heartbeat_at = NOW() - INTERVAL '6 minutes'
                WHERE attempt_id = %s
                """,
                (old_attempt["attempt_id"],),
            )

    mark_result, reclaim_result = await asyncio.wait_for(
        asyncio.gather(
            education_textbooks.mark_generation_attempt_running(
                generation_job_id=generation_job_id,
                attempt_id=str(old_attempt["attempt_id"]),
                root_run_id=root_run_id,
            ),
            education_textbooks.claim_lesson_launch(
                parent_user_id=parent_user_id,
                generation_job_id=generation_job_id,
            ),
        ),
        timeout=10,
    )
    assert sum(result is not None for result in (mark_result, reclaim_result)) == 1

    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                SELECT jobs.status AS job_status,
                       attempts.status AS attempt_status,
                       attempts.root_run_id
                FROM education_generation_jobs AS jobs
                JOIN education_generation_attempts AS attempts
                  ON attempts.attempt_id = jobs.latest_attempt_id
                WHERE jobs.generation_job_id = %s
                """,
                (generation_job_id,),
            )
            final_state = await cur.fetchone()

    if mark_result is not None:
        assert final_state["job_status"] == "running"
        assert final_state["attempt_status"] == "running"
        assert str(final_state["root_run_id"]) == root_run_id
    else:
        assert final_state["job_status"] == "preparing"
        assert final_state["attempt_status"] == "worker_lost"
        assert final_state["root_run_id"] is None


@pytest.mark.asyncio
async def test_candidate_review_transitions_are_owned_and_idempotent(
    patched_get_db_connection,
) -> None:
    async with patched_get_db_connection() as db_conn:
        parent_user_id, structure_id, node_id = await _seed_candidate_structure(db_conn)
        candidate_id = await _insert_candidate(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            candidate_key="unit-1-kp-1",
            title="世界运动",
        )
        reject_candidate_id = await _insert_candidate(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            candidate_key="unit-1-kp-2",
            title="足球词汇",
        )

    pending = await education_textbooks.list_knowledge_point_candidates_for_parent(
        parent_user_id=parent_user_id,
        structure_id=structure_id,
    )
    assert pending is not None
    assert pending["nodes"][0]["candidates"][0]["candidate_status"] == "pending"

    updated = await education_textbooks.update_knowledge_point_candidate_for_parent(
        parent_user_id=parent_user_id,
        candidate_id=candidate_id,
        title="足球运动",
        summary="新的摘要",
        point_type="reading_skill",
    )
    assert updated is not None
    assert updated["title"] == "足球运动"
    assert updated["point_type"] == "reading_skill"

    accepted = await education_textbooks.accept_knowledge_point_candidates_for_parent(
        parent_user_id=parent_user_id,
        candidate_ids=[candidate_id],
    )
    assert accepted is not None
    assert accepted[0]["candidate_status"] == "accepted"

    repeated = await education_textbooks.accept_knowledge_point_candidates_for_parent(
        parent_user_id=parent_user_id,
        candidate_ids=[candidate_id],
    )
    assert repeated is not None
    assert repeated[0]["candidate_status"] == "accepted"

    rejected = await education_textbooks.reject_knowledge_point_candidates_for_parent(
        parent_user_id=parent_user_id,
        candidate_ids=[reject_candidate_id],
    )
    assert rejected is not None
    assert rejected[0]["candidate_status"] == "rejected"
    rejected_again = (
        await education_textbooks.reject_knowledge_point_candidates_for_parent(
            parent_user_id=parent_user_id,
            candidate_ids=[reject_candidate_id],
        )
    )
    assert rejected_again is not None
    assert rejected_again[0]["candidate_status"] == "rejected"

    with pytest.raises(ValueError, match="candidate transition"):
        await education_textbooks.reject_knowledge_point_candidates_for_parent(
            parent_user_id=parent_user_id,
            candidate_ids=[candidate_id],
        )

    async with patched_get_db_connection() as db_conn:
        other_parent_id, _, _ = await _seed_candidate_structure(db_conn)
    assert other_parent_id != parent_user_id
    assert (
        await education_textbooks.list_knowledge_point_candidates_for_parent(
            parent_user_id=other_parent_id,
            structure_id=structure_id,
        )
        is None
    )
    with pytest.raises(education_textbooks.KnowledgePointCandidateNotFoundError):
        await education_textbooks.accept_knowledge_point_candidates_for_parent(
            parent_user_id=other_parent_id,
            candidate_ids=[candidate_id],
        )


@pytest.mark.asyncio
async def test_merge_and_split_are_atomic_and_preserve_ownership(
    patched_get_db_connection,
) -> None:
    async with patched_get_db_connection() as db_conn:
        parent_user_id, structure_id, node_id = await _seed_candidate_structure(db_conn)
        first_id = await _insert_candidate(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            candidate_key="unit-1-kp-1",
            title="世界运动",
        )
        second_id = await _insert_candidate(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            candidate_key="unit-1-kp-2",
            title="足球",
        )
        split_source_id = await _insert_candidate(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            candidate_key="unit-1-kp-3",
            title="足球文化",
        )

    merged = await education_textbooks.merge_knowledge_point_candidates_for_parent(
        parent_user_id=parent_user_id,
        source_ids=[first_id, second_id],
        target_id=first_id,
        title="足球运动",
        summary="",
        point_type="reading_skill",
        accept=True,
    )
    assert merged is not None
    by_id = {str(item["knowledge_point_id"]): item for item in merged}
    assert by_id[first_id]["candidate_status"] == "accepted"
    assert by_id[first_id]["point_type"] == "reading_skill"
    assert by_id[second_id]["candidate_status"] == "merged"

    split = await education_textbooks.split_knowledge_point_candidate_for_parent(
        parent_user_id=parent_user_id,
        candidate_id=split_source_id,
        items=[
            {"title": "足球起源", "summary": "", "point_type": "concept"},
            {"title": "足球传播", "summary": "", "point_type": "concept"},
        ],
    )
    assert split is not None
    assert split[0]["candidate_status"] == "split"
    assert [item["candidate_status"] for item in split[1:]] == [
        "pending",
        "pending",
    ]
    assert len({item["candidate_key"] for item in split}) == 3

    with pytest.raises(ValueError, match="Only a pending"):
        await education_textbooks.split_knowledge_point_candidate_for_parent(
            parent_user_id=parent_user_id,
            candidate_id=split_source_id,
            items=[
                {"title": "重复拆分一", "summary": "", "point_type": "concept"},
                {"title": "重复拆分二", "summary": "", "point_type": "concept"},
            ],
        )


@pytest.mark.asyncio
async def test_split_keeps_generated_keys_within_database_limit(
    patched_get_db_connection,
) -> None:
    async with patched_get_db_connection() as db_conn:
        parent_user_id, structure_id, node_id = await _seed_candidate_structure(db_conn)
        source_key = "k" * 255
        candidate_id = await _insert_candidate(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            candidate_key=source_key,
            title="长篇候选",
        )

    split = await education_textbooks.split_knowledge_point_candidate_for_parent(
        parent_user_id=parent_user_id,
        candidate_id=candidate_id,
        items=[
            {"title": "拆分一", "summary": "", "point_type": "concept"},
            {"title": "拆分二", "summary": "", "point_type": "concept"},
        ],
    )

    assert split is not None
    generated_keys = [str(item["candidate_key"]) for item in split[1:]]
    assert all(len(key) <= 255 for key in generated_keys)
    assert len(set(generated_keys)) == 2
    assert all(key.startswith("k") for key in generated_keys)


@pytest.mark.asyncio
async def test_split_database_failure_rolls_back_source_and_partial_items(
    patched_get_db_connection,
) -> None:
    async with patched_get_db_connection() as db_conn:
        parent_user_id, structure_id, node_id = await _seed_candidate_structure(db_conn)
        candidate_id = await _insert_candidate(
            db_conn,
            structure_id=structure_id,
            node_id=node_id,
            candidate_key="rollback-source",
            title="回滚候选",
        )

    with pytest.raises(psycopg.errors.StringDataRightTruncation):
        await education_textbooks.split_knowledge_point_candidate_for_parent(
            parent_user_id=parent_user_id,
            candidate_id=candidate_id,
            items=[
                {"title": "先写入", "summary": "", "point_type": "concept"},
                {"title": "触发失败", "summary": "", "point_type": "x" * 65},
            ],
        )

    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                SELECT candidate_status
                FROM education_structure_knowledge_points
                WHERE knowledge_point_id = %s
                """,
                (candidate_id,),
            )
            source = await cur.fetchone()
            await cur.execute(
                """
                SELECT COUNT(*) AS count
                FROM education_structure_knowledge_points
                WHERE content_node_id = %s
                """,
                (node_id,),
            )
            count = await cur.fetchone()

    assert source["candidate_status"] == "pending"
    assert count["count"] == 1


@pytest.mark.asyncio
async def test_concurrent_merge_and_split_serialize_node_positions(
    patched_get_db_connection,
) -> None:
    async with patched_get_db_connection() as db_conn:
        parent_user_id, structure_id, node_id = await _seed_candidate_structure(db_conn)
        candidate_ids = [
            await _insert_candidate(
                db_conn,
                structure_id=structure_id,
                node_id=node_id,
                candidate_key=f"concurrent-{position}",
                title=f"并发候选 {position}",
                position=position,
            )
            for position in range(1, 9)
        ]

    async with patched_get_db_connection() as blocker:
        async with blocker.transaction():
            async with blocker.cursor() as cur:
                await cur.execute(
                    """
                    SELECT node_id
                    FROM education_content_nodes
                    WHERE node_id = %s
                    FOR UPDATE
                    """,
                    (node_id,),
                )
            merge_task = asyncio.create_task(
                education_textbooks.merge_knowledge_point_candidates_for_parent(
                    parent_user_id=parent_user_id,
                    source_ids=candidate_ids[:2],
                    target_id=candidate_ids[0],
                    title="并发合并",
                    summary="",
                    point_type="concept",
                    accept=False,
                )
            )
            split_tasks = [
                asyncio.create_task(
                    education_textbooks.split_knowledge_point_candidate_for_parent(
                        parent_user_id=parent_user_id,
                        candidate_id=candidate_id,
                        items=[
                            {
                                "title": "拆分一",
                                "summary": "",
                                "point_type": "concept",
                            },
                            {
                                "title": "拆分二",
                                "summary": "",
                                "point_type": "concept",
                            },
                        ],
                    )
                )
                for candidate_id in candidate_ids[2:]
            ]
            await asyncio.sleep(0.2)
            assert merge_task.done() is False
            assert all(task.done() is False for task in split_tasks)

    results = await asyncio.gather(merge_task, *split_tasks)

    assert len(results) == 7
    async with patched_get_db_connection() as db_conn:
        async with db_conn.cursor() as cur:
            await cur.execute(
                """
                SELECT ARRAY_AGG(position ORDER BY position) AS positions,
                       COUNT(*) AS count
                FROM education_structure_knowledge_points
                WHERE content_node_id = %s
                """,
                (node_id,),
            )
            row = await cur.fetchone()

    assert row["count"] == 20
    assert row["positions"] == list(range(1, 21))
