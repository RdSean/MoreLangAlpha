# Lesson Generation Prompt Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an optional persisted user prompt to knowledge-point lesson generation and expose it consistently in API, status, prompt assembly and UI.

**Architecture:** Store normalized lesson guidance in the existing
`education_generation_jobs.processing_brief` column. The queue path treats
`(auto_grading, prompt)` as part of active-job identity. Lesson prompt assembly
appends a bounded guidance section that cannot override the managed contract.
The React lesson page submits, restores and displays the same value.

**Tech Stack:** Python 3.13+, FastAPI, Pydantic, async psycopg, React 19,
TypeScript, Vitest, Testing Library.

---

### Task 1: Persist Lesson Prompt And Enforce Active-Job Conflicts

**Files:**
- Modify: `src/server/app/education/models.py`
- Modify: `src/server/app/education/textbooks.py`
- Modify: `src/server/database/education_textbooks.py`
- Modify: `src/server/services/education_lesson_jobs.py`
- Test: `tests/unit/server/app/education/test_textbook_structures.py`
- Test: `tests/unit/server/database/test_education_structure_models.py`
- Test: `tests/unit/server/services/test_education_lesson_jobs.py`

**Step 1: Write failing request and queue tests**

Add an API test that posts:

```json
{"auto_grading": false, "prompt": "使用中文讲解，保留英文术语"}
```

Assert the service receives the normalized prompt. Add model coverage that a
4001-character prompt is rejected and a multiline prompt is accepted.

Add database tests that an active lesson job with the same prompt and
auto-grading setting is reused, while a different prompt raises
`LessonGenerationConflictError` and leaves the stored prompt unchanged.

**Step 2: Run tests to verify they fail**

```bash
uv run pytest \
  tests/unit/server/app/education/test_textbook_structures.py \
  tests/unit/server/database/test_education_structure_models.py \
  tests/unit/server/services/test_education_lesson_jobs.py -q
```

Expected: request-model and call-signature failures because `prompt` is not yet
supported.

**Step 3: Implement persistence and conflict handling**

- Add `prompt: str = Field(default="", max_length=4000)` to
  `GenerateKnowledgePointLessonRequest`.
- Normalize with `.strip()` in the route/service boundary.
- Extend `queue_and_launch_lesson_for_parent`,
  `queue_lesson_generation_for_parent` and
  `create_lesson_generation_job` with `prompt`.
- Store the prompt in `processing_brief`.
- Compare normalized prompt and `auto_grading` when reusing an active job.
- Include `processing_brief` in lesson status/job projections as `prompt`.

**Step 4: Run tests to verify they pass**

Run the Step 2 command. Expected: PASS.

**Step 5: Run Ruff**

```bash
uv run ruff check \
  src/server/app/education/models.py \
  src/server/app/education/textbooks.py \
  src/server/database/education_textbooks.py \
  src/server/services/education_lesson_jobs.py \
  tests/unit/server/app/education/test_textbook_structures.py \
  tests/unit/server/database/test_education_structure_models.py \
  tests/unit/server/services/test_education_lesson_jobs.py
```

**Step 6: Commit**

```bash
git add src/server/app/education/models.py \
  src/server/app/education/textbooks.py \
  src/server/database/education_textbooks.py \
  src/server/services/education_lesson_jobs.py \
  tests/unit/server/app/education/test_textbook_structures.py \
  tests/unit/server/database/test_education_structure_models.py \
  tests/unit/server/services/test_education_lesson_jobs.py
git commit -m "feat(education): persist lesson generation prompt"
```

### Task 2: Apply Prompt To The Managed Lesson Prompt

**Files:**
- Modify: `src/server/services/education_lesson_jobs.py`
- Test: `tests/unit/server/services/test_education_lesson_jobs.py`

**Step 1: Write failing prompt tests**

Add a test that `managed_lesson_prompt` receives a prompt such as
`"使用中文讲解，保留英文术语；给出三个例子"` and assert:

- the exact normalized guidance appears in the prompt;
- it explicitly controls language, audience, structure, length, difficulty,
  style or exercises;
- it explicitly cannot override the knowledge point, source refs, output
  paths/schema or managed safety contract.

Add a test that an empty prompt adds no user-guidance section.

**Step 2: Run tests to verify they fail**

```bash
uv run pytest \
  tests/unit/server/services/test_education_lesson_jobs.py \
  -k 'generation_prompt or lesson_prompt' -v
```

**Step 3: Implement bounded prompt assembly**

Pass `prompt=str(job.get("processing_brief") or "")` from the lesson launch
path into `managed_lesson_prompt`. Sanitize/escape the guidance and append it
after the fixed lesson contract with explicit precedence language.

**Step 4: Run tests and regression**

```bash
uv run pytest tests/unit/server/services/test_education_lesson_jobs.py -q
uv run ruff check src/server/services/education_lesson_jobs.py \
  tests/unit/server/services/test_education_lesson_jobs.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/services/education_lesson_jobs.py \
  tests/unit/server/services/test_education_lesson_jobs.py
git commit -m "feat(education): apply lesson generation prompt"
```

### Task 3: Add The Prompt Input And Restore It In The Lesson UI

**Files:**
- Modify: `web/src/pages/Education/types.ts`
- Modify: `web/src/pages/Education/api.ts`
- Modify: `web/src/pages/Education/queries.ts`
- Modify: `web/src/pages/Education/KnowledgePointLessonReviewPage.tsx`
- Test: `web/src/pages/Education/__tests__/KnowledgePointLessonReviewPage.test.tsx`
- Test: `web/src/pages/Education/__tests__/queries.test.tsx`
- Modify: `CHANGELOG.md`

**Step 1: Write failing frontend tests**

Assert the lesson page:

- renders a `课程生成要求（可选）` textarea;
- submits the trimmed prompt with `autoGrading`;
- restores the prompt from lesson-generation status;
- shows a conflict error without clearing the user's entry;
- keeps the prompt visible for regeneration.

Add an API-layer test that the generation request body includes `prompt`.

**Step 2: Run tests to verify they fail**

```bash
cd web
pnpm vitest run \
  src/pages/Education/__tests__/KnowledgePointLessonReviewPage.test.tsx \
  src/pages/Education/__tests__/queries.test.tsx
```

Expected: FAIL because no textarea or request field exists.

**Step 3: Implement the UI and API types**

- Add `prompt` to lesson request/status types.
- Pass `prompt` through `generateKnowledgePointLesson` and mutation variables.
- Add the textarea to the initial generation and regeneration surfaces.
- Prefill from `lessonGeneration.data.prompt` only when the user has not typed.
- Preserve textarea content after 409/error and display the server message.

**Step 4: Run frontend verification**

```bash
cd web
pnpm vitest run src/pages/Education
pnpm typecheck
pnpm build
```

Expected: PASS.

**Step 5: Run backend regression**

```bash
uv run pytest tests/unit/server/services/test_education_lesson_jobs.py \
  tests/unit/server/app/education/test_textbook_structures.py -q
uv run ruff check \
  src/server/services/education_lesson_jobs.py \
  src/server/app/education/models.py \
  src/server/app/education/textbooks.py \
  src/server/database/education_textbooks.py
```

Expected: PASS.

**Step 6: Commit**

```bash
git add CHANGELOG.md web/src/pages/Education/types.ts \
  web/src/pages/Education/api.ts \
  web/src/pages/Education/queries.ts \
  web/src/pages/Education/KnowledgePointLessonReviewPage.tsx \
  web/src/pages/Education/__tests__/KnowledgePointLessonReviewPage.test.tsx \
  web/src/pages/Education/__tests__/queries.test.tsx
git commit -m "feat(education): add lesson generation prompt input"
```
