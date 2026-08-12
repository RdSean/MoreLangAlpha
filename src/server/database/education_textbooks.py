"""Raw PostgreSQL persistence for versioned family textbook learning."""

from typing import Any
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Json

from src.server.database.pool import get_db_connection


async def create_textbook_record(
    *, household_id: str, parent_user_id: str, title: str, slug: str
) -> dict[str, Any]:
    textbook_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO education_textbooks (textbook_id, household_id, title, slug, created_by_user_id)
                SELECT %s, %s, %s, %s, %s
                WHERE EXISTS (
                    SELECT 1 FROM education_memberships
                    WHERE household_id = %s AND user_id = %s AND role = 'parent'
                )
                RETURNING textbook_id, household_id, title, slug, created_by_user_id, created_at
                """,
                (
                    textbook_id,
                    household_id,
                    title,
                    slug,
                    parent_user_id,
                    household_id,
                    parent_user_id,
                ),
            )
            row = await cur.fetchone()
    return dict(row) if row else {}


async def queue_textbook_processing(
    *,
    parent_user_id: str,
    household_id: str,
    textbook_id: str,
    source_asset_ids: list[str],
    extractor_name: str,
    extractor_version: str,
) -> dict[str, Any] | None:
    """Freeze eligible source assets into a fresh processing version and queue one job."""
    version_id = str(uuid4())
    job_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT textbook_id FROM education_textbooks
                    WHERE textbook_id = %s AND household_id = %s
                    FOR UPDATE
                    """,
                    (textbook_id, household_id),
                )
                if not await cur.fetchone():
                    return None
                await cur.execute(
                    """
                    SELECT COUNT(*) AS source_count FROM education_assets
                    WHERE household_id = %s AND asset_id = ANY(%s::uuid[])
                    """,
                    (household_id, source_asset_ids),
                )
                if (await cur.fetchone())["source_count"] != len(set(source_asset_ids)):
                    raise ValueError(
                        "One or more textbook sources are outside the household"
                    )
                await cur.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 AS sequence FROM education_textbook_versions WHERE textbook_id = %s",
                    (textbook_id,),
                )
                sequence = (await cur.fetchone())["sequence"]
                await cur.execute(
                    """
                    INSERT INTO education_textbook_versions (
                        version_id, textbook_id, sequence, status, extractor_name, extractor_version, created_by_user_id
                    ) VALUES (%s, %s, %s, 'processing', %s, %s, %s)
                    """,
                    (
                        version_id,
                        textbook_id,
                        sequence,
                        extractor_name,
                        extractor_version,
                        parent_user_id,
                    ),
                )
                await cur.executemany(
                    "INSERT INTO education_textbook_sources (version_id, asset_id, position) VALUES (%s, %s, %s)",
                    [
                        (version_id, asset_id, index)
                        for index, asset_id in enumerate(source_asset_ids, start=1)
                    ],
                )
                await cur.execute(
                    """
                    INSERT INTO education_processing_jobs (job_id, version_id, status)
                    VALUES (%s, %s, 'queued')
                    RETURNING job_id, version_id, status, attempt_count, created_at
                    """,
                    (job_id, version_id),
                )
                job = dict(await cur.fetchone())
    return job


async def claim_textbook_processing_job(*, job_id: str) -> dict[str, Any] | None:
    """Claim exactly one queued job with a row lock; a future PTC worker uses the same contract."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT jobs.job_id, jobs.version_id, versions.sequence AS version_sequence,
                           textbooks.textbook_id, textbooks.household_id, textbooks.title, textbooks.slug
                    FROM education_processing_jobs AS jobs
                    JOIN education_textbook_versions AS versions ON versions.version_id = jobs.version_id
                    JOIN education_textbooks AS textbooks ON textbooks.textbook_id = versions.textbook_id
                    WHERE jobs.job_id = %s AND jobs.status = 'queued'
                    FOR UPDATE SKIP LOCKED
                    """,
                    (job_id,),
                )
                job = await cur.fetchone()
                if not job:
                    return None
                await cur.execute(
                    """
                    UPDATE education_processing_jobs
                    SET status = 'processing', attempt_count = attempt_count + 1, claimed_at = NOW(), updated_at = NOW()
                    WHERE job_id = %s
                    """,
                    (job_id,),
                )
                await cur.execute(
                    """
                    SELECT assets.asset_id, assets.storage_key, assets.original_filename, assets.content_type, assets.size_bytes
                    FROM education_textbook_sources AS sources
                    JOIN education_assets AS assets ON assets.asset_id = sources.asset_id
                    WHERE sources.version_id = %s
                    ORDER BY sources.position
                    """,
                    (job["version_id"],),
                )
                sources = [dict(row) for row in await cur.fetchall()]
    result = dict(job)
    result["sources"] = sources
    return result


async def complete_textbook_processing_job(
    *, job_id: str, version_id: str, bundle_prefix: str, chapters: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Persist reviewed candidate material only while the claimed job is still processing."""
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT 1 FROM education_processing_jobs WHERE job_id = %s AND version_id = %s AND status = 'processing' FOR UPDATE",
                    (job_id, version_id),
                )
                if not await cur.fetchone():
                    return None
                for chapter in chapters:
                    chapter_id = str(uuid4())
                    await cur.execute(
                        """
                        INSERT INTO education_textbook_chapters (
                            chapter_id, version_id, position, slug, title, page_start, page_end, markdown,
                            teaching_material, markdown_key, teaching_material_key
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            chapter_id,
                            version_id,
                            chapter["position"],
                            chapter["slug"],
                            chapter["title"],
                            chapter.get("page_start"),
                            chapter.get("page_end"),
                            chapter["markdown"],
                            chapter["teaching_material"],
                            chapter["markdown_key"],
                            chapter["teaching_material_key"],
                        ),
                    )
                    for question in chapter["questions"]:
                        await cur.execute(
                            """
                            INSERT INTO education_chapter_questions (
                                question_id, chapter_id, position, prompt, options, correct_option, explanation, knowledge_point
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                str(uuid4()),
                                chapter_id,
                                question["position"],
                                question["prompt"],
                                Json(question["options"]),
                                question["correct_option"],
                                question["explanation"],
                                question["knowledge_point"],
                            ),
                        )
                await cur.execute(
                    """
                    UPDATE education_textbook_versions
                    SET status = 'review', bundle_prefix = %s, processing_error = NULL, reviewed_at = NOW()
                    WHERE version_id = %s AND status = 'processing'
                    """,
                    (bundle_prefix, version_id),
                )
                await cur.execute(
                    """
                    UPDATE education_processing_jobs
                    SET status = 'completed', completed_at = NOW(), updated_at = NOW(), error_message = NULL
                    WHERE job_id = %s
                    RETURNING job_id, version_id, status, attempt_count, completed_at
                    """,
                    (job_id,),
                )
                row = await cur.fetchone()
    return dict(row) if row else None


async def fail_textbook_processing_job(
    *, job_id: str, version_id: str, error_message: str
) -> None:
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor() as cur:
                await cur.execute(
                    """
                    UPDATE education_processing_jobs
                    SET status = 'failed', error_message = %s, updated_at = NOW()
                    WHERE job_id = %s AND version_id = %s AND status = 'processing'
                    """,
                    (error_message[:10_000], job_id, version_id),
                )
                await cur.execute(
                    """
                    UPDATE education_textbook_versions
                    SET status = 'failed', processing_error = %s
                    WHERE version_id = %s AND status = 'processing'
                    """,
                    (error_message[:10_000], version_id),
                )


async def list_textbooks_for_parent(user_id: str) -> list[dict[str, Any]]:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT textbooks.textbook_id, textbooks.household_id, textbooks.title, textbooks.slug,
                       textbooks.created_by_user_id, textbooks.created_at,
                       latest.version_id AS latest_version_id, latest.sequence AS latest_version_sequence,
                       latest.status AS latest_version_status,
                       COALESCE(latest.chapter_count, 0) AS chapter_count,
                       COALESCE(latest.assignment_count, 0) AS assignment_count
                FROM education_textbooks AS textbooks
                JOIN education_memberships AS memberships ON memberships.household_id = textbooks.household_id
                LEFT JOIN LATERAL (
                    SELECT versions.version_id, versions.sequence, versions.status,
                           (SELECT COUNT(*) FROM education_textbook_chapters WHERE version_id = versions.version_id) AS chapter_count,
                           (SELECT COUNT(*) FROM education_textbook_assignments AS assignments
                            JOIN education_textbook_publications AS publications ON publications.publication_id = assignments.publication_id
                            WHERE publications.version_id = versions.version_id) AS assignment_count
                    FROM education_textbook_versions AS versions
                    WHERE versions.textbook_id = textbooks.textbook_id
                    ORDER BY versions.sequence DESC
                    LIMIT 1
                ) AS latest ON TRUE
                WHERE memberships.user_id = %s AND memberships.role = 'parent'
                ORDER BY textbooks.created_at DESC
                """,
                (user_id,),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_textbook_for_parent(
    *, parent_user_id: str, textbook_id: str
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT textbooks.textbook_id, textbooks.household_id, textbooks.title, textbooks.slug,
                       textbooks.created_by_user_id, textbooks.created_at
                FROM education_textbooks AS textbooks
                JOIN education_memberships AS memberships ON memberships.household_id = textbooks.household_id
                WHERE textbooks.textbook_id = %s AND memberships.user_id = %s AND memberships.role = 'parent'
                """,
                (textbook_id, parent_user_id),
            )
            textbook = await cur.fetchone()
            if not textbook:
                return None
            await cur.execute(
                """
                SELECT versions.version_id, versions.sequence, versions.status, versions.extractor_name,
                       versions.extractor_version, versions.processing_error, versions.created_at,
                       versions.reviewed_at, versions.published_at,
                       publications.publication_id,
                       COALESCE(jobs.job_id::text, '') AS processing_job_id,
                       jobs.status AS processing_job_status, jobs.attempt_count AS processing_attempt_count,
                       jobs.error_message AS processing_error_message,
                       COALESCE((SELECT COUNT(*) FROM education_textbook_chapters WHERE version_id = versions.version_id), 0) AS chapter_count,
                       publications.publication_id IS NOT NULL AS is_published
                FROM education_textbook_versions AS versions
                LEFT JOIN education_processing_jobs AS jobs ON jobs.version_id = versions.version_id
                LEFT JOIN education_textbook_publications AS publications ON publications.version_id = versions.version_id
                WHERE versions.textbook_id = %s
                ORDER BY versions.sequence DESC
                """,
                (textbook["textbook_id"],),
            )
            versions = [dict(row) for row in await cur.fetchall()]
            for version in versions:
                await cur.execute(
                    """
                    SELECT chapters.chapter_id, chapters.position, chapters.slug, chapters.title,
                           chapters.page_start, chapters.page_end, chapters.markdown, chapters.teaching_material
                    FROM education_textbook_chapters AS chapters
                    WHERE chapters.version_id = %s ORDER BY chapters.position
                    """,
                    (version["version_id"],),
                )
                chapters = [dict(row) for row in await cur.fetchall()]
                for chapter in chapters:
                    await cur.execute(
                        """
                        SELECT question_id, position, prompt, options, correct_option, explanation, knowledge_point
                        FROM education_chapter_questions WHERE chapter_id = %s ORDER BY position
                        """,
                        (chapter["chapter_id"],),
                    )
                    chapter["questions"] = [dict(row) for row in await cur.fetchall()]
                version["chapters"] = chapters
                if version["publication_id"]:
                    await cur.execute(
                        """
                        SELECT assignments.assignment_id, assignments.student_user_id, assignments.created_at,
                               accounts.display_name AS student_name
                        FROM education_textbook_assignments AS assignments
                        LEFT JOIN auth_accounts AS accounts ON accounts.user_id = assignments.student_user_id
                        WHERE assignments.publication_id = %s ORDER BY assignments.created_at
                        """,
                        (version["publication_id"],),
                    )
                    version["assignments"] = [dict(row) for row in await cur.fetchall()]
                else:
                    version["assignments"] = []
    result = dict(textbook)
    result["versions"] = versions
    return result


async def get_processing_job_for_parent(
    *, parent_user_id: str, job_id: str
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT jobs.job_id, jobs.version_id, jobs.status
                FROM education_processing_jobs AS jobs
                JOIN education_textbook_versions AS versions ON versions.version_id = jobs.version_id
                JOIN education_textbooks AS textbooks ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships ON memberships.household_id = textbooks.household_id
                WHERE jobs.job_id = %s AND memberships.user_id = %s AND memberships.role = 'parent'
                """,
                (job_id, parent_user_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def publish_textbook_version(
    *, parent_user_id: str, textbook_id: str, version_id: str
) -> dict[str, Any] | None:
    publication_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT versions.version_id
                    FROM education_textbook_versions AS versions
                    JOIN education_textbooks AS textbooks ON textbooks.textbook_id = versions.textbook_id
                    JOIN education_memberships AS memberships ON memberships.household_id = textbooks.household_id
                    WHERE versions.version_id = %s AND textbooks.textbook_id = %s
                      AND memberships.user_id = %s AND memberships.role = 'parent'
                    FOR UPDATE
                    """,
                    (version_id, textbook_id, parent_user_id),
                )
                if not await cur.fetchone():
                    return None
                await cur.execute(
                    "SELECT status FROM education_textbook_versions WHERE version_id = %s",
                    (version_id,),
                )
                version = await cur.fetchone()
                if version["status"] != "review":
                    raise ValueError(
                        f"Textbook version cannot be published from {version['status']}"
                    )
                await cur.execute(
                    "SELECT COUNT(*) AS count FROM education_textbook_chapters WHERE version_id = %s",
                    (version_id,),
                )
                if (await cur.fetchone())["count"] == 0:
                    raise ValueError("Textbook version has no reviewable chapters")
                await cur.execute(
                    """
                    INSERT INTO education_textbook_publications (publication_id, version_id, published_by_user_id)
                    VALUES (%s, %s, %s)
                    RETURNING publication_id, version_id, published_by_user_id, created_at
                    """,
                    (publication_id, version_id, parent_user_id),
                )
                publication = dict(await cur.fetchone())
                await cur.execute(
                    "UPDATE education_textbook_versions SET status = 'published', published_at = NOW() WHERE version_id = %s",
                    (version_id,),
                )
    return publication


async def assign_textbook_publication(
    *, parent_user_id: str, publication_id: str, student_user_id: str
) -> dict[str, Any] | None:
    assignment_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT publications.publication_id, textbooks.household_id
                    FROM education_textbook_publications AS publications
                    JOIN education_textbook_versions AS versions ON versions.version_id = publications.version_id
                    JOIN education_textbooks AS textbooks ON textbooks.textbook_id = versions.textbook_id
                    JOIN education_memberships AS parent_memberships ON parent_memberships.household_id = textbooks.household_id
                    JOIN education_memberships AS student_memberships ON student_memberships.household_id = textbooks.household_id
                    WHERE publications.publication_id = %s AND parent_memberships.user_id = %s
                      AND parent_memberships.role = 'parent' AND student_memberships.user_id = %s
                      AND student_memberships.role = 'student'
                    """,
                    (publication_id, parent_user_id, student_user_id),
                )
                if not await cur.fetchone():
                    return None
                await cur.execute(
                    """
                    INSERT INTO education_textbook_assignments (
                        assignment_id, publication_id, student_user_id, assigned_by_user_id
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (publication_id, student_user_id) DO UPDATE SET assigned_by_user_id = EXCLUDED.assigned_by_user_id
                    RETURNING assignment_id, publication_id, student_user_id, assigned_by_user_id, created_at
                    """,
                    (assignment_id, publication_id, student_user_id, parent_user_id),
                )
                row = await cur.fetchone()
    return dict(row) if row else None


async def list_student_assignments(student_user_id: str) -> list[dict[str, Any]]:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT assignments.assignment_id, assignments.publication_id, assignments.created_at,
                       textbooks.title AS textbook_title, textbooks.slug AS textbook_slug,
                       versions.sequence AS version_sequence,
                       COALESCE((SELECT COUNT(*) FROM education_textbook_chapters WHERE version_id = versions.version_id), 0) AS chapter_count,
                       COALESCE((SELECT COUNT(*) FROM education_learning_progress AS progress
                                 WHERE progress.assignment_id = assignments.assignment_id
                                   AND progress.status IN ('read', 'check_completed')), 0) AS completed_chapter_count
                FROM education_textbook_assignments AS assignments
                JOIN education_textbook_publications AS publications ON publications.publication_id = assignments.publication_id
                JOIN education_textbook_versions AS versions ON versions.version_id = publications.version_id
                JOIN education_textbooks AS textbooks ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships ON memberships.user_id = assignments.student_user_id
                WHERE assignments.student_user_id = %s AND memberships.role = 'student'
                ORDER BY assignments.created_at DESC
                """,
                (student_user_id,),
            )
            rows = await cur.fetchall()
    return [dict(row) for row in rows]


async def get_student_learning(
    *, student_user_id: str, assignment_id: str
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT assignments.assignment_id, assignments.publication_id, textbooks.title AS textbook_title,
                       textbooks.slug AS textbook_slug, versions.sequence AS version_sequence
                FROM education_textbook_assignments AS assignments
                JOIN education_textbook_publications AS publications ON publications.publication_id = assignments.publication_id
                JOIN education_textbook_versions AS versions ON versions.version_id = publications.version_id
                JOIN education_textbooks AS textbooks ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships ON memberships.user_id = assignments.student_user_id
                WHERE assignments.assignment_id = %s AND assignments.student_user_id = %s AND memberships.role = 'student'
                """,
                (assignment_id, student_user_id),
            )
            assignment = await cur.fetchone()
            if not assignment:
                return None
            await cur.execute(
                """
                SELECT chapters.chapter_id, chapters.position, chapters.slug, chapters.title, chapters.markdown,
                       chapters.teaching_material, COALESCE(progress.status, 'not_started') AS progress_status,
                       progress.last_read_at, progress.completed_at
                FROM education_textbook_chapters AS chapters
                LEFT JOIN education_learning_progress AS progress
                  ON progress.chapter_id = chapters.chapter_id AND progress.assignment_id = %s
                JOIN education_textbook_publications AS publications ON publications.version_id = chapters.version_id
                WHERE publications.publication_id = %s
                ORDER BY chapters.position
                """,
                (assignment_id, assignment["publication_id"]),
            )
            chapters = [dict(row) for row in await cur.fetchall()]
            for chapter in chapters:
                await cur.execute(
                    """
                    SELECT questions.question_id, questions.position, questions.prompt, questions.options,
                           questions.explanation, questions.knowledge_point, answers.selected_option,
                           answers.is_correct, answers.answered_at
                    FROM education_chapter_questions AS questions
                    LEFT JOIN education_learning_answers AS answers
                      ON answers.question_id = questions.question_id AND answers.assignment_id = %s
                    WHERE questions.chapter_id = %s ORDER BY questions.position
                    """,
                    (assignment_id, chapter["chapter_id"]),
                )
                chapter["questions"] = [dict(row) for row in await cur.fetchall()]
    result = dict(assignment)
    result["chapters"] = chapters
    return result


async def update_student_progress(
    *, student_user_id: str, assignment_id: str, chapter_id: str, status: str
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                INSERT INTO education_learning_progress (assignment_id, chapter_id, status, last_read_at, completed_at, updated_at)
                SELECT assignments.assignment_id, chapters.chapter_id, %s, NOW(),
                       CASE WHEN %s IN ('read', 'check_completed') THEN NOW() ELSE NULL END, NOW()
                FROM education_textbook_assignments AS assignments
                JOIN education_textbook_publications AS publications ON publications.publication_id = assignments.publication_id
                JOIN education_textbook_chapters AS chapters ON chapters.version_id = publications.version_id
                JOIN education_memberships AS memberships ON memberships.user_id = assignments.student_user_id
                WHERE assignments.assignment_id = %s AND assignments.student_user_id = %s
                  AND chapters.chapter_id = %s AND memberships.role = 'student'
                ON CONFLICT (assignment_id, chapter_id) DO UPDATE
                SET status = EXCLUDED.status, last_read_at = NOW(),
                    completed_at = CASE WHEN EXCLUDED.status IN ('read', 'check_completed') THEN NOW() ELSE education_learning_progress.completed_at END,
                    updated_at = NOW()
                RETURNING assignment_id, chapter_id, status, last_read_at, completed_at, updated_at
                """,
                (status, status, assignment_id, student_user_id, chapter_id),
            )
            row = await cur.fetchone()
    return dict(row) if row else None


async def submit_student_answer(
    *, student_user_id: str, assignment_id: str, question_id: str, selected_option: str
) -> dict[str, Any] | None:
    answer_id = str(uuid4())
    async with get_db_connection() as conn:
        async with conn.transaction():
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    """
                    SELECT questions.question_id, questions.chapter_id, questions.correct_option
                    FROM education_textbook_assignments AS assignments
                    JOIN education_textbook_publications AS publications ON publications.publication_id = assignments.publication_id
                    JOIN education_textbook_chapters AS chapters ON chapters.version_id = publications.version_id
                    JOIN education_chapter_questions AS questions ON questions.chapter_id = chapters.chapter_id
                    JOIN education_memberships AS memberships ON memberships.user_id = assignments.student_user_id
                    WHERE assignments.assignment_id = %s AND assignments.student_user_id = %s
                      AND questions.question_id = %s AND memberships.role = 'student'
                    FOR UPDATE
                    """,
                    (assignment_id, student_user_id, question_id),
                )
                question = await cur.fetchone()
                if not question:
                    return None
                await cur.execute(
                    """
                    INSERT INTO education_learning_answers (answer_id, assignment_id, question_id, selected_option, is_correct)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (assignment_id, question_id) DO NOTHING
                    RETURNING answer_id, assignment_id, question_id, selected_option, is_correct, answered_at
                    """,
                    (
                        answer_id,
                        assignment_id,
                        question_id,
                        selected_option,
                        selected_option == question["correct_option"],
                    ),
                )
                answer = await cur.fetchone()
                if not answer:
                    await cur.execute(
                        """
                        SELECT answer_id, assignment_id, question_id, selected_option, is_correct, answered_at
                        FROM education_learning_answers WHERE assignment_id = %s AND question_id = %s
                        """,
                        (assignment_id, question_id),
                    )
                    answer = await cur.fetchone()
                await cur.execute(
                    """
                    INSERT INTO education_learning_progress (assignment_id, chapter_id, status, completed_at, updated_at)
                    VALUES (%s, %s, 'check_completed', NOW(), NOW())
                    ON CONFLICT (assignment_id, chapter_id) DO UPDATE
                    SET status = 'check_completed', completed_at = NOW(), updated_at = NOW()
                    """,
                    (assignment_id, question["chapter_id"]),
                )
    return dict(answer) if answer else None


async def list_student_learning_records(
    *, parent_user_id: str, assignment_id: str
) -> dict[str, Any] | None:
    async with get_db_connection() as conn:
        async with conn.cursor(row_factory=dict_row) as cur:
            await cur.execute(
                """
                SELECT assignments.assignment_id, assignments.student_user_id, textbooks.title AS textbook_title
                FROM education_textbook_assignments AS assignments
                JOIN education_textbook_publications AS publications ON publications.publication_id = assignments.publication_id
                JOIN education_textbook_versions AS versions ON versions.version_id = publications.version_id
                JOIN education_textbooks AS textbooks ON textbooks.textbook_id = versions.textbook_id
                JOIN education_memberships AS memberships ON memberships.household_id = textbooks.household_id
                WHERE assignments.assignment_id = %s AND memberships.user_id = %s AND memberships.role = 'parent'
                """,
                (assignment_id, parent_user_id),
            )
            assignment = await cur.fetchone()
            if not assignment:
                return None
            await cur.execute(
                """
                SELECT progress.chapter_id, chapters.title AS chapter_title, progress.status, progress.last_read_at,
                       progress.completed_at, COALESCE(answer_counts.correct_count, 0) AS correct_count,
                       COALESCE(answer_counts.answer_count, 0) AS answer_count
                FROM education_learning_progress AS progress
                JOIN education_textbook_chapters AS chapters ON chapters.chapter_id = progress.chapter_id
                LEFT JOIN LATERAL (
                    SELECT COUNT(*) FILTER (WHERE is_correct) AS correct_count, COUNT(*) AS answer_count
                    FROM education_learning_answers WHERE assignment_id = progress.assignment_id
                      AND question_id IN (SELECT question_id FROM education_chapter_questions WHERE chapter_id = progress.chapter_id)
                ) AS answer_counts ON TRUE
                WHERE progress.assignment_id = %s ORDER BY chapters.position
                """,
                (assignment_id,),
            )
            records = [dict(row) for row in await cur.fetchall()]
    result = dict(assignment)
    result["records"] = records
    return result
