# K12 家庭作业工作流 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将家庭作业从“提交即进入批改状态”的流程升级为按学科分类的日历任务，学生首次打卡即永久完成，附件和反馈可以持续追加。

**Architecture:** 在现有 `education_task_rules`、`education_tasks`、`education_task_submissions` 和 `education_task_reviews` 上做增量迁移。学生档案保存当前年级；规则和任务保存分类快照；任务完成事实由 `completed_at` 独立表达。后端继续使用 FastAPI、异步 psycopg 和现有教育资产服务，前端继续使用 React Query 与现有教育页面，不引入新的存储或 ORM。

**Tech Stack:** Python 3.13+, FastAPI, async psycopg, Alembic raw SQL, PostgreSQL, MinIO/S3-compatible storage, React 19, TypeScript, React Query, Vitest, Playwright.

---

### Task 1: Add student profiles and task classification schema

**Files:**
- Create: `migrations/versions/035_add_education_homework_workflow.py`
- Modify: `tests/unit/migrations/test_generic_migration_chain.py`
- Create: `tests/unit/migrations/test_education_homework_workflow.py`

**Step 1: Write the failing migration contract tests**

Cover the following SQL contracts:

- `education_student_profiles` has `user_id`, `household_id`, nullable `grade_code`, and foreign keys to the student membership and `education_grade_levels`.
- `education_task_rules` and `education_tasks` add `subject_code`, `type_code`, `practice_source_code`, and `grade_code` snapshot columns.
- `education_tasks` adds `completed_at` and an index by household/date.
- Rules support `once`, `daily`, `weekdays`, and `weekly` recurrence metadata.
- The review schema allows multiple reviews per submission and uses `feedback` / `revision_requested` decisions.
- Submission rows support `check_in` and `revision` kinds.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/migrations/test_education_homework_workflow.py -q`

Expected: FAIL because migration `035` does not exist.

**Step 3: Implement the migration**

Create the student profile table and backfill one nullable profile row for each existing student membership. Add foreign keys from task snapshots to the seeded dictionary tables. Keep new snapshot columns nullable so old test data and old tasks can be upgraded without inventing classifications; new service code must require them for newly created tasks.

Add `completed_at` and backfill it from the latest existing submission. Keep the legacy `submitted`, `revision_requested` status values and legacy `completed` review decision valid during this migration so the running service remains writable. A submission trigger records the first completion timestamp without changing the legacy task state. Add `submission_kind` with a non-null `check_in` default, then backfill later rows as `revision`.

The forward repair migration `036` restores write compatibility for databases that have already applied this initial schema: it adds the `submission_kind` default, completion trigger, legacy status/review-decision allowances, and strict weekly weekday validation. The strict task-status and review-decision cutover belongs with the Task 3 service change in a new `037` migration, after all writes use the new contract.

**Step 4: Run migration tests**

Run: `uv run pytest tests/unit/migrations/test_education_homework_workflow.py tests/unit/migrations/test_generic_migration_chain.py -q`

Expected: PASS.

**Step 5: Apply and verify the migration locally**

Run: `uv run alembic upgrade head` and query the new table names, columns, constraints, and row counts using the current worktree `.env`.

**Step 6: Commit**

```bash
git add migrations/versions/035_add_education_homework_workflow.py tests/unit/migrations/test_education_homework_workflow.py tests/unit/migrations/test_generic_migration_chain.py
git commit -m "feat: extend homework workflow schema"
```

### Task 2: Add student grade profile API and dictionary API

**Files:**
- Modify: `src/server/database/education_members.py`
- Create or modify: `src/server/database/education_homework.py`
- Modify: `src/server/app/education/models.py`
- Modify: `src/server/app/education/router.py`
- Modify: the existing family-account router/service that owns student account management
- Test: `tests/unit/server/services/` and `tests/unit/server/app/education/`

**Step 1: Write failing service and route tests**

Test that a parent can read and update the grade of a student in the same household, a student cannot update their own grade, and cross-household updates return 403/404. Test that subject/type dictionaries return only valid subject-type combinations and practice sources.

**Step 2: Run the focused tests**

Run: `uv run pytest tests/unit/server/app/education tests/unit/server/services -k "grade or dictionary" -q`

Expected: FAIL because the profile and dictionary functions do not exist.

**Step 3: Implement the smallest API surface**

Add parent-only profile read/update helpers and endpoints under the existing family-account/settings boundary. Add a read-only dictionary endpoint returning subjects with color, valid homework types, grades, and practice sources. Do not expose storage keys or unrelated household data.

**Step 4: Verify**

Run the focused tests and `uv run ruff check src/server/database/education_homework.py src/server/app/education/models.py src/server/app/education/router.py`.

**Step 5: Commit**

```bash
git add src/server/database/education_members.py src/server/database/education_homework.py src/server/app/education/models.py src/server/app/education/router.py tests/unit/server
git commit -m "feat: add student grade and homework dictionaries"
```

### Task 3: Replace task creation and recurrence materialization

**Files:**
- Modify: `src/server/database/education_tasks.py`
- Modify: `src/server/services/education_tasks.py`
- Modify: `src/server/app/education/models.py`
- Modify: `src/server/app/education/router.py`
- Create: `migrations/versions/037_finalize_education_homework_workflow.py`
- Test: `tests/unit/server/services/test_education_tasks.py`

**Step 1: Write failing state-machine tests**

Cover:

- New tasks require a valid subject/type pair and the assigned student's current grade.
- `practice_source_code` is accepted only for `practice`.
- A student check-in changes `open` to `completed` and records `completed_at`.
- A check-in may have no text and no attachments.
- Repeated check-in with the same idempotency key returns the original submission.
- A completed task accepts later revision submissions without changing `completed_at` or status.
- Parent cancellation cannot cancel a completed task.

**Step 2: Run tests to verify failure**

Run: `uv run pytest tests/unit/server/services/test_education_tasks.py -q`

Expected: FAIL against the old submitted/review transition.

**Step 3: Implement service and database changes**

Validate dictionary relationships in SQL and service boundaries. Extend recurrence materialization for weekdays and selected weekly weekdays. Add a dedicated check-in operation that creates the first immutable submission and atomically marks the task completed. Keep a separate append-submission operation for later revisions. Preserve idempotency and household asset ownership checks.

Add migration `037` only after the service no longer writes legacy values: convert remaining legacy task states to `completed`, convert legacy review decision `completed` to `feedback`, restrict task status to `open` / `completed` / `cancelled`, and restrict review decisions to `feedback` / `revision_requested`. Remove the temporary completion trigger once the service owns the atomic state transition.

**Step 4: Verify**

Run the focused service tests, existing education task tests, and `uv run ruff check src/server/database/education_tasks.py src/server/services/education_tasks.py src/server/app/education`.

**Step 5: Commit**

```bash
git add src/server/database/education_tasks.py src/server/services/education_tasks.py src/server/app/education tests/unit/server/services/test_education_tasks.py
git commit -m "feat: make homework completion independent from reviews"
```

### Task 4: Add task detail, submissions, reviews, and multi-asset responses

**Files:**
- Modify: `src/server/database/education_tasks.py`
- Modify: `src/server/services/education_tasks.py`
- Modify: `src/server/app/education/models.py`
- Modify: `src/server/app/education/router.py`
- Modify: `src/server/services/education_assets.py` only if a scoped helper is needed
- Test: `tests/unit/server/app/education/test_task_details.py`

**Step 1: Write failing API contract tests**

Test a task detail response with two sections: parent materials and student submissions. Verify multiple asset IDs are returned as metadata, signed download URLs are generated only after household authorization, and review history is append-only.

**Step 2: Run tests to verify failure**

Run: `uv run pytest tests/unit/server/app/education/test_task_details.py -q`

Expected: FAIL because no task-detail endpoint or timeline response exists.

**Step 3: Implement detail and timeline endpoints**

Add `GET /api/v1/education/tasks/{task_id}` with role-scoped detail. Add check-in and revision submission endpoints, and change reviews to append `feedback` or `revision_requested`. Return asset metadata and download endpoint references, not raw storage keys. Keep response models stable for both parent and student roles.

**Step 4: Verify**

Run focused route tests plus existing education asset tests and `uv run ruff check` on touched backend files.

**Step 5: Commit**

```bash
git add src/server/database/education_tasks.py src/server/services/education_tasks.py src/server/services/education_assets.py src/server/app/education tests/unit/server/app/education
git commit -m "feat: add homework detail and submission timeline"
```

### Task 5: Add calendar and progress API

**Files:**
- Modify: `src/server/database/education_tasks.py`
- Modify: `src/server/services/education_tasks.py`
- Modify: `src/server/app/education/models.py`
- Modify: `src/server/app/education/router.py`
- Test: `tests/unit/server/app/education/test_task_calendar.py`

**Step 1: Write failing calendar tests**

Test month-range queries, parent student filtering, student self-only filtering, subject colors, daily counts, completed counts, and overdue counts. Verify that a parent cannot query a student outside the household.

**Step 2: Run tests to verify failure**

Run: `uv run pytest tests/unit/server/app/education/test_task_calendar.py -q`

Expected: FAIL because calendar aggregation is not implemented.

**Step 3: Implement the calendar endpoint**

Add a bounded date-range endpoint returning daily summaries and task summaries. Reuse seeded subject colors. Limit the range to a reasonable month window and order tasks by due time. Include summary totals for today, this week, overdue, and completed.

**Step 4: Verify**

Run focused tests and the existing education task route tests.

**Step 5: Commit**

```bash
git add src/server/database/education_tasks.py src/server/services/education_tasks.py src/server/app/education tests/unit/server/app/education/test_task_calendar.py
git commit -m "feat: add homework calendar summaries"
```

### Task 6: Update frontend types, API hooks, and creation form

**Files:**
- Modify: `web/src/pages/Education/types.ts`
- Modify: `web/src/pages/Education/api.ts`
- Modify: `web/src/pages/Education/queries.ts`
- Modify: `web/src/pages/Education/EducationPage.tsx`
- Test: `web/src/pages/Education/__tests__/EducationPage.test.tsx`

**Step 1: Write failing frontend tests**

Cover dictionary loading, subject/type filtering, conditional practice-source control, default student grade display, weekly recurrence controls, multiple original-file selection, and a no-text/no-file check-in action.

**Step 2: Run tests to verify failure**

Run: `cd web && pnpm vitest run src/pages/Education/__tests__/EducationPage.test.tsx`

Expected: FAIL against the current single-file form and submitted-state UI.

**Step 3: Implement types, API functions, hooks, and form**

Represent the new task status and submission timeline. Add dictionary, calendar, detail, check-in, revision, and profile calls. Replace the single-file input with multi-file selection while retaining server-side validation. Make the form use the selected student's grade as a read-only default and show practice source only for `practice`.

**Step 4: Verify**

Run the focused Vitest suite and `cd web && pnpm lint`.

**Step 5: Commit**

```bash
git add web/src/pages/Education
git commit -m "feat: update homework creation and check-in UI"
```

### Task 7: Build task detail and attachment timeline UI

**Files:**
- Modify: `web/src/pages/Education/EducationPage.tsx`
- Create: `web/src/pages/Education/TaskDetail.tsx`
- Create or modify: `web/src/pages/Education/components/AttachmentList.tsx`
- Test: `web/src/pages/Education/__tests__/TaskDetail.test.tsx`

**Step 1: Write failing component tests**

Verify the two attachment sections, multiple image/PDF entries, immediate completed state after check-in, append-only revision submissions, feedback history, and parent/student action differences.

**Step 2: Run tests to verify failure**

Run: `cd web && pnpm vitest run src/pages/Education/__tests__/TaskDetail.test.tsx`

Expected: FAIL because the current page has no task detail timeline.

**Step 3: Implement the detail view**

Use a route or dialog consistent with the existing education page. Keep original materials above student submissions. Provide image preview, PDF download/open, check-in, add-submission, and parent feedback actions. Do not make feedback alter the completion badge.

**Step 4: Verify**

Run focused Vitest tests, the existing EducationPage suite, and `cd web && pnpm lint`.

**Step 5: Commit**

```bash
git add web/src/pages/Education
git commit -m "feat: add homework detail timeline"
```

### Task 8: Add subject-colored monthly heat calendar

**Files:**
- Create: `web/src/pages/Education/components/HomeworkCalendar.tsx`
- Modify: `web/src/pages/Education/EducationPage.tsx`
- Modify: `web/src/pages/Education/api.ts`
- Test: `web/src/pages/Education/__tests__/HomeworkCalendar.test.tsx`
- Test: `web/e2e/education-homework.spec.ts` (or the repository's existing education Playwright suite)

**Step 1: Write failing calendar tests**

Verify month navigation, daily task counts, subject color bars, completion/overdue markers, parent student switching, student self-scope, and clicking a date to filter the list.

**Step 2: Run tests to verify failure**

Run: `cd web && pnpm vitest run src/pages/Education/__tests__/HomeworkCalendar.test.tsx`

Expected: FAIL because no calendar component exists.

**Step 3: Implement the calendar**

Render a responsive month grid with bounded cell content. Use dictionary colors for subjects and separate status marks for completion and overdue state. Keep detailed task content in the list/detail view instead of overflowing calendar cells.

**Step 4: Verify**

Run Vitest, the education Playwright flow on desktop and mobile, and the required frontend server on `0.0.0.0:5177` before handoff.

**Step 5: Commit**

```bash
git add web/src/pages/Education web/e2e
git commit -m "feat: add homework subject heat calendar"
```

### Task 9: Full verification and documentation

**Files:**
- Modify: `CHANGELOG.md`
- Test: existing backend and frontend education suites

**Step 1: Run backend verification**

Run `uv run pytest tests/unit/migrations tests/unit/server -q` and `uv run ruff check src migrations tests/unit/migrations`.

**Step 2: Run frontend verification**

Run `cd web && pnpm vitest run` and `pnpm lint`, then run the focused education Playwright flow against the server on `0.0.0.0:5177`.

**Step 3: Verify database behavior**

Run `uv run alembic upgrade head`, inspect migration version and non-sensitive dictionary/task counts, and exercise one parent-to-student check-in flow against the local services.

**Step 4: Update the Chinese changelog**

Document the independent completion semantics, multi-asset timeline, student grade defaults, recurrence options, and subject-colored calendar.

**Step 5: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: record homework workflow release"
```
