"""Durable teaching-package persistence contracts."""

from contextlib import asynccontextmanager

import pytest

from src.server.database import education_textbooks


@pytest.mark.asyncio
async def test_queue_teaching_package_freezes_a_parent_reviewable_content_version(
    mock_connection, mock_cursor, monkeypatch
):
    """Only a parent may queue a package for a content version ready for teaching."""

    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    mock_cursor.fetchone.side_effect = [
        {"version_id": "version-1", "household_id": "household-1"},
        {"sequence": 1},
        {
            "teaching_package_id": "package-1",
            "content_version_id": "version-1",
            "status": "queued",
            "sequence": 1,
        },
        {"job_id": "job-1", "teaching_package_id": "package-1", "status": "queued"},
    ]
    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    monkeypatch.setattr(education_textbooks, "uuid4", lambda: "generated-id")

    package = await education_textbooks.queue_teaching_package(
        parent_user_id="parent-1",
        content_version_id="version-1",
        hashes=education_textbooks.TeachingInputHashes(
            input_manifest_sha256="a" * 64,
            book_to_skill_sha256="b" * 64,
            knowledge_guy_sha256="c" * 64,
            adapter_prompt_sha256="d" * 64,
        ),
    )

    assert package == {
        "teaching_package_id": "package-1",
        "content_version_id": "version-1",
        "status": "queued",
        "sequence": 1,
        "job_id": "job-1",
    }
    version_lookup_sql = mock_cursor.execute.call_args_list[0].args[0]
    assert "memberships.role = 'parent'" in version_lookup_sql
    assert "versions.status = 'review'" in version_lookup_sql


@pytest.mark.asyncio
async def test_creating_teaching_attempt_binds_one_root_ptc_run_and_previous_attempt(
    mock_connection, mock_cursor, monkeypatch
):
    """A job attempt has explicit root-run and retry-chain identity."""

    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    mock_cursor.fetchone.side_effect = [
        {
            "job_id": "job-1",
            "teaching_package_id": "package-1",
            "attempt_count": 1,
            "previous_attempt_id": "attempt-1",
        },
        {
            "attempt_id": "attempt-2",
            "job_id": "job-1",
            "managed_workspace_id": "workspace-1",
            "managed_thread_id": "thread-1",
            "previous_attempt_id": "attempt-1",
        },
    ]
    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    monkeypatch.setattr(education_textbooks, "uuid4", lambda: "generated-id")

    attempt = await education_textbooks.create_teaching_attempt(
        job_id="job-1",
        managed_workspace_id="workspace-1",
        managed_thread_id="thread-1",
    )

    assert attempt["previous_attempt_id"] == "attempt-1"
    statements = [call.args[0] for call in mock_cursor.execute.call_args_list]
    attempt_insert_sql = next(
        sql for sql in statements if "INSERT INTO education_teaching_attempts" in sql
    )
    assert "previous_attempt_id" in attempt_insert_sql
    assert "root_run_id" in attempt_insert_sql
    assert any(
        "UPDATE education_teaching_packages" in sql and "'preparing'" in sql
        for sql in statements
    )


@pytest.mark.asyncio
async def test_settling_terminal_attempt_projects_failure_to_teaching_package(
    mock_connection, mock_cursor, monkeypatch
):
    """A failed root run cannot leave its package apparently processable."""

    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    mock_cursor.fetchone.side_effect = [
        {
            "attempt_id": "attempt-1",
            "job_id": "job-1",
            "root_run_id": "run-1",
            "status": "failed",
        }
    ]
    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)

    settled = await education_textbooks.settle_teaching_attempt(
        attempt_id="attempt-1",
        root_run_id="run-1",
        status="failed",
        error_code="managed_run_failed",
        error_message="已脱敏的失败信息",
    )

    assert settled == {
        "attempt_id": "attempt-1",
        "job_id": "job-1",
        "root_run_id": "run-1",
        "status": "failed",
    }
    statements = [call.args[0] for call in mock_cursor.execute.call_args_list]
    assert any(
        "UPDATE education_teaching_packages" in sql and "status = %s" in sql
        for sql in statements
    )


@pytest.mark.asyncio
async def test_recording_generation_progress_advances_the_package_phase(
    mock_connection, mock_cursor, monkeypatch
):
    """Only the safe managed phase projection advances the product state."""

    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    mock_cursor.fetchone.side_effect = [
        {"job_id": "job-1", "position": 1},
        {"sequence": 1},
    ]
    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    monkeypatch.setattr(education_textbooks, "uuid4", lambda: "event-1")

    await education_textbooks.record_teaching_event(
        attempt_id="attempt-1",
        phase="generating_teaching",
        chapter_id="11111111-1111-1111-1111-111111111111",
        summary="已完成第 1 章教学材料生成",
    )

    statements = [call.args[0] for call in mock_cursor.execute.call_args_list]
    package_update = next(
        call
        for call in mock_cursor.execute.call_args_list
        if "UPDATE education_teaching_packages" in call.args[0]
    )
    assert package_update.args[1][0] == "generating_teaching"


@pytest.mark.asyncio
async def test_parent_can_requeue_only_a_failed_or_cancelled_teaching_job(
    mock_connection, mock_cursor, monkeypatch
):
    """A resume preserves the prior attempt as the retry-chain predecessor."""

    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    mock_cursor.fetchone.side_effect = [
        {
            "job_id": "job-1",
            "teaching_package_id": "package-1",
            "latest_attempt_id": "attempt-1",
            "status": "queued",
        }
    ]
    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)

    resumed = await education_textbooks.requeue_teaching_job(
        parent_user_id="parent-1", job_id="job-1"
    )

    assert resumed == {
        "job_id": "job-1",
        "status": "queued",
        "latest_attempt_id": "attempt-1",
    }
    statements = [call.args[0] for call in mock_cursor.execute.call_args_list]
    assert any("jobs.status IN ('failed', 'cancelled')" in sql for sql in statements)
    assert any(
        "UPDATE education_teaching_packages" in sql and "status = 'queued'" in sql
        for sql in statements
    )


@pytest.mark.asyncio
async def test_failing_a_prepared_attempt_without_a_root_run_fails_job_and_package(
    mock_connection, mock_cursor, monkeypatch
):
    """Sandbox provisioning failure remains recoverable without inventing a run id."""

    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    mock_cursor.fetchone.side_effect = [
        {"attempt_id": "attempt-1", "job_id": "job-1", "status": "failed"},
    ]
    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)

    failed = await education_textbooks.fail_preparing_teaching_attempt(
        attempt_id="attempt-1",
        error_code="managed_sandbox_unavailable",
        error_message="教材教学加工环境无法启动，请重新运行。",
    )

    assert failed == {"attempt_id": "attempt-1", "status": "failed"}
    statements = [call.args[0] for call in mock_cursor.execute.call_args_list]
    assert any("root_run_id" not in sql for sql in statements if "UPDATE education_teaching_attempts" in sql)
    assert any("UPDATE education_teaching_jobs" in sql and "status = 'failed'" in sql for sql in statements)
    assert any("UPDATE education_teaching_packages" in sql and "status = 'failed'" in sql for sql in statements)


@pytest.mark.asyncio
async def test_recovered_terminal_root_marks_matching_running_teaching_attempt_retriable(
    mock_connection, mock_cursor, monkeypatch
):
    """A dead executor's terminal root run cannot strand product state in running."""

    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    mock_cursor.fetchone.side_effect = [
        {"attempt_id": "attempt-1", "job_id": "job-1", "status": "failed"},
    ]
    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)

    settled = await education_textbooks.settle_recovered_teaching_root_run(
        root_run_id="run-1",
        status="failed",
        error_code="managed_worker_lost",
        error_message="教材教学加工进程中断，请重新运行。",
    )

    assert settled == {"attempt_id": "attempt-1", "status": "failed"}
    statements = [call.args[0] for call in mock_cursor.execute.call_args_list]
    assert any("root_run_id = %s" in sql and "UPDATE education_teaching_attempts" in sql for sql in statements)
    assert any("UPDATE education_teaching_jobs" in sql and "status = %s" in sql for sql in statements)
    assert any("UPDATE education_teaching_packages" in sql and "status = %s" in sql for sql in statements)


@pytest.mark.asyncio
async def test_reconcile_terminal_roots_repairs_running_attempt_after_projection_failure(
    mock_connection, mock_cursor, monkeypatch
):
    """A later scanner pass repairs the root/product split without sandbox access."""

    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    mock_cursor.fetchall.return_value = [
        {"root_run_id": "run-1", "root_status": "error"},
    ]
    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    projected = []

    async def settle(**kwargs):
        projected.append(kwargs)
        return {"attempt_id": "attempt-1", "status": "failed"}

    monkeypatch.setattr(
        education_textbooks, "settle_recovered_teaching_root_run", settle
    )

    repaired = await education_textbooks.reconcile_terminal_teaching_root_runs()

    assert repaired == 1
    assert projected == [
        {
            "root_run_id": "run-1",
            "status": "failed",
            "error_code": "managed_terminal_unprojected",
            "error_message": "教材教学加工进程中断，请重新运行。",
        }
    ]


@pytest.mark.asyncio
async def test_parent_detail_selects_safe_teaching_package_projection(
    mock_connection, mock_cursor, monkeypatch
):
    """Teaching package summaries remain household-scoped and never select object keys."""

    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    mock_cursor.fetchone.side_effect = [
        {
            "textbook_id": "textbook-1",
            "household_id": "household-1",
            "title": "英语第二册",
            "slug": "english-2",
        }
    ]
    mock_cursor.fetchall.side_effect = [
        [
            {
                "version_id": "version-1",
                "sequence": 1,
                "status": "review",
                "chapter_count": 1,
                "publication_id": None,
                "is_published": False,
            }
        ],
        [],
        [],
        [
            {
                "teaching_package_id": "package-1",
                "sequence": 1,
                "status": "review",
                "chapter_count": 1,
                "question_count": 1,
            }
        ],
    ]
    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)

    detail = await education_textbooks.get_textbook_for_parent(
        parent_user_id="parent-1", textbook_id="textbook-1"
    )

    assert detail is not None
    assert detail["versions"][0]["teaching_packages"] == [
        {
            "teaching_package_id": "package-1",
            "sequence": 1,
            "status": "review",
            "chapter_count": 1,
            "question_count": 1,
        }
    ]
    package_select_sql = mock_cursor.execute.call_args_list[-1].args[0]
    assert "storage_key" not in package_select_sql
    assert "education_teaching_packages" in package_select_sql


@pytest.mark.asyncio
async def test_complete_teaching_attempt_writes_review_projection_atomically(
    mock_connection, mock_cursor, monkeypatch
):
    """A candidate becomes reviewable only with its root-run attempt and package rows."""

    @asynccontextmanager
    async def fake_connection():
        yield mock_connection

    mock_cursor.fetchone.side_effect = [
        {
            "attempt_id": "attempt-1",
            "job_id": "job-1",
            "teaching_package_id": "package-1",
            "root_run_id": "run-1",
        },
        {"package_chapter_id": "package-chapter-1"},
        {"attempt_id": "attempt-1", "status": "completed"},
    ]
    monkeypatch.setattr(education_textbooks, "get_db_connection", fake_connection)
    ids = iter(["chapter-row-1", "question-row-1"])
    monkeypatch.setattr(education_textbooks, "uuid4", lambda: next(ids))

    completed = await education_textbooks.complete_teaching_attempt(
        job_id="job-1",
        attempt_id="attempt-1",
        root_run_id="run-1",
        bundle_prefix="education/household/book/v1/teaching/v1",
        package={
            "chapters": [
                {
                    "content_chapter_id": "content-chapter-1",
                    "learning_objectives": ["目标"],
                    "knowledge_points": ["知识点"],
                    "key_difficulties": ["难点"],
                    "prerequisites": [],
                    "teaching_material": "# 教学材料",
                    "questions": [
                        {
                            "position": 1,
                            "prompt": "题目",
                            "options": {"A": "对", "B": "错"},
                            "correct_option": "A",
                            "explanation": "解释",
                            "knowledge_point": "知识点",
                        }
                    ],
                }
            ]
        },
    )

    assert completed == {"attempt_id": "attempt-1", "status": "completed"}
    statements = [call.args[0] for call in mock_cursor.execute.call_args_list]
    assert any("INSERT INTO education_teaching_package_chapters" in sql for sql in statements)
    assert any("INSERT INTO education_teaching_package_questions" in sql for sql in statements)
    assert any("status = 'review'" in sql for sql in statements)
    assert sum("status = 'completed'" in sql for sql in statements) == 2
