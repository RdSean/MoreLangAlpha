# 家庭教材学习 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver a role-safe family textbook vertical slice from parent draft through published student learning evidence.

**Architecture:** Extend the existing `education_` module with versioned textbook metadata and a recoverable object bundle. A durable database job records explicit local processing; publication freezes a reviewed version, assignments give each student a stable reading snapshot, and all learning actions remain inside education APIs rather than a new runtime.

**Tech Stack:** Python 3.13+, FastAPI, async psycopg3, Alembic raw SQL, existing MinIO adapter, React 19, TypeScript, React Query, Tailwind, shadcn/ui, Vitest, Playwright.

---

### Task 1: Formalize approved architecture

**Files:**
- Modify: `docs/2026-08-11-family-textbook-learning-discussion.md`
- Create: `docs/plans/2026-08-12-family-textbook-learning-design.md`
- Create: `docs/plans/2026-08-12-family-textbook-learning.md`
- Modify: `CHANGELOG.md`

**Step 1:** Record the approved scope, immutable publication boundary, object bundle contract, authorization matrix, and deferred integration boundaries.

**Step 2:** Commit documentation only.

### Task 2: Add textbook persistence and lifecycle contracts

**Files:**
- Create: `migrations/versions/028_add_education_textbooks.py`
- Create: `src/server/database/education_textbooks.py`
- Create: `src/server/services/education_textbooks.py`
- Create: `tests/unit/server/services/test_education_textbooks.py`

**Step 1: Write failing tests.**

```python
def test_version_transition_requires_review_before_publication():
    assert_version_transition("review", "published")
    with pytest.raises(TextbookTransitionError):
        assert_version_transition("draft", "published")
```

**Step 2:** Run `uv run pytest tests/unit/server/services/test_education_textbooks.py -q` and verify RED because the module is absent.

**Step 3:** Add immutable version/publication, assignment, chapter/question, progress/answer, source, and processing-job tables. Add parent/student role checks and service lifecycle functions.

**Step 4:** Run the focused test file and verify GREEN.

**Step 5:** Add Chinese release notes and commit schema/service/test files.

### Task 3: Implement recoverable local processing

**Files:**
- Create: `src/server/services/education_textbook_storage.py`
- Modify: `src/server/services/education_textbooks.py`
- Modify: `src/server/database/education_textbooks.py`
- Modify: `tests/unit/server/services/test_education_textbooks.py`

**Step 1: Write failing tests.**

```python
async def test_process_claim_writes_readme_manifest_and_chapter_bundle(monkeypatch):
    result = await process_next_textbook_job()
    assert result["status"] == "review"
    assert "manifest.json" in uploaded_keys
```

**Step 2:** Run the focused test and verify RED.

**Step 3:** Implement `local_fixture` extractor, lease/attempt/error persistence, deterministic assets, readable paths, and adapter-provided storage writes. Support parent-triggered retry of failed jobs without mutating frozen source selection.

**Step 4:** Run focused tests and existing `test_education_assets.py` to verify GREEN.

**Step 5:** Add Chinese release notes and commit processing-only files.

### Task 4: Expose role-safe textbook APIs

**Files:**
- Create: `src/server/app/education/textbooks.py`
- Modify: `src/server/app/education/models.py`
- Modify: `src/server/app/setup.py`
- Create: `tests/unit/server/app/education/test_textbooks.py`

**Step 1: Write failing route/service boundary tests.**

```python
async def test_student_cannot_publish_or_assign(client):
    response = await client.post("/api/v1/education/textbooks/id/publish")
    assert response.status_code == 403
```

**Step 2:** Run focused API tests and verify RED.

**Step 3:** Add textbook CRUD, source attach, start/retry processing, review-list, publish, assignment, learner index/chapter, progress, answer and parent read-only records endpoints. Register the router.

**Step 4:** Run focused API tests plus textbook services tests and verify GREEN.

**Step 5:** Add Chinese release notes and commit route/model files.

### Task 5: Build parent textbook and student reader UI

**Files:**
- Create: `web/src/pages/Education/TextbooksPage.tsx`
- Create: `web/src/pages/Education/TextbookDetailPage.tsx`
- Create: `web/src/pages/Education/StudentLearningPage.tsx`
- Modify: `web/src/pages/Education/EducationPage.tsx`
- Modify: `web/src/pages/Education/api.ts`
- Modify: `web/src/pages/Education/queries.ts`
- Modify: `web/src/pages/Education/types.ts`
- Modify: `web/src/components/Main/Main.tsx`
- Create: `web/src/pages/Education/__tests__/TextbooksPage.test.tsx`
- Create: `web/src/pages/Education/__tests__/StudentLearningPage.test.tsx`

**Step 1: Write failing tests.**

```tsx
it('renders published textbook actions for a parent', async () => {
  render(<TextbookDetailPage />);
  expect(await screen.findByRole('button', { name: '发布版本' })).toBeVisible();
});
```

**Step 2:** Run `cd web && pnpm test -- TextbooksPage.test.tsx StudentLearningPage.test.tsx` and verify RED.

**Step 3:** Implement compact management views for parents and a deterministic reader/question panel for students. Preserve existing homework UI and restrict controls based on authenticated member role.

**Step 4:** Run focused Vitest, then `pnpm typecheck` and `pnpm build`.

**Step 5:** Add Chinese release notes and commit UI/test files.

### Task 6: End-to-end verification and handoff

**Files:**
- Modify: `CHANGELOG.md`
- Create/Modify: `web/e2e/textbook-learning.spec.js`

**Step 1:** Add role E2E coverage for parent publishing/assignment and student reading/answering.

**Step 2:** Run `uv run pytest tests/unit/server/services/test_education_textbooks.py tests/unit/server/app/education/test_textbooks.py tests/unit/server/services/test_education_assets.py tests/unit/server/services/test_education_tasks.py -q` and `make lint`.

**Step 3:** Run `cd web && pnpm test -- TextbooksPage.test.tsx StudentLearningPage.test.tsx && pnpm typecheck && pnpm build`.

**Step 4:** Start `cd web && pnpm dev --host 0.0.0.0 --port 5177`; verify `/education` from the LAN-visible listener and run the focused browser test where credentials/services permit.

**Step 5:** Record final Chinese release notes and commit each remaining scoped change atomically.
