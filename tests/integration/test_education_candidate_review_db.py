"""Real PostgreSQL contracts for generated knowledge-point review."""

from __future__ import annotations

import asyncio
from uuid import uuid4

import psycopg
import pytest

from src.server.database import education_textbooks


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
