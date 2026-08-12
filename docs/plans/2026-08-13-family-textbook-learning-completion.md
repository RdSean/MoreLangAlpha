# Family Textbook Learning Completion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the approved family textbook vertical slice from parent candidate sources through reviewed publication, student learning evidence, and parent read-only review.

**Architecture:** Preserve the current versioned `education_` model and add only approved-scope gaps: a parent-only candidate asset index, a safe frozen review projection, an explicit multi-source processing UI, responsive student panels, and role-safe browser acceptance tests. PostgreSQL remains the authorization/index source and MinIO remains private object storage.

**Tech Stack:** Python 3.13+, FastAPI, async psycopg3, Alembic raw SQL, React 19, TypeScript, React Query, Tailwind, shadcn/ui, Vitest, Playwright.

---

## Audited Boundary

Already delivered: durable version/job records, immutable publications and assignments, local PDF processing, recoverable bundles, student evidence, canonical Flash learning spaces, and basic role-specific pages.

This plan closes these approved-scope gaps:

1. A parent cannot select existing candidate sources or combine multiple assets before processing.
2. Parent review lacks safe source metadata, page mappings, and extracted Markdown.
3. Parent mutation failures have no recovery feedback in the UI.
4. The student reader has a desktop layout but no separate mobile directory/check panels.
5. Browser coverage does not prove parent-to-student-to-parent flow.

Deferred: OCR, Datalab, rich Markdown editing, open-ended grading, printing, schedules, chapter locking, and multi-textbook curricula.

### Task 1: Parent Candidate Source Index

**Files:**
- Modify: `src/server/database/education_assets.py`
- Modify: `src/server/services/education_assets.py`
- Modify: `src/server/app/education/assets.py`
- Test: `tests/unit/server/app/education/test_assets.py`
- Test: `tests/unit/server/services/test_education_assets.py`

**Step 1: Write failing tests**

```python
async def test_parent_lists_only_household_candidate_assets(client):
    response = await client.get('/api/v1/education/assets')
    assert response.status_code == 200
    assert response.json()[0]['original_filename'] == 'body.pdf'

async def test_student_cannot_list_parent_candidate_sources(client):
    response = await client.get('/api/v1/education/assets')
    assert response.status_code == 403
```

**Step 2: Verify RED**

Run: `uv run pytest tests/unit/server/app/education/test_assets.py tests/unit/server/services/test_education_assets.py -q`

Expected: the new `GET /api/v1/education/assets` contract fails because it does not exist.

**Step 3: Minimal implementation**

- Query only the authenticated parent's household assets in descending creation order.
- Return safe metadata: id, filename, MIME type, byte size, creation time.
- Reject students in the service layer; do not expose `storage_key` or signed URLs.

**Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/server/app/education/test_assets.py tests/unit/server/services/test_education_assets.py -q`

**Step 5: Commit**

```bash
git add src/server/database/education_assets.py src/server/services/education_assets.py src/server/app/education/assets.py tests/unit/server/app/education/test_assets.py tests/unit/server/services/test_education_assets.py CHANGELOG.md
git commit -m 'feat(education): list parent textbook source candidates'
```

### Task 2: Safe Parent Review Projection

**Files:**
- Modify: `src/server/database/education_textbooks.py`
- Modify: `src/server/services/education_textbooks.py`
- Modify: `src/server/app/education/models.py`
- Modify: `src/server/app/education/textbooks.py`
- Test: `tests/unit/server/app/education/test_textbooks.py`
- Test: `tests/unit/server/database/test_education_textbook_jobs.py`

**Step 1: Write failing tests**

```python
async def test_parent_detail_returns_safe_sources_and_page_mappings(client):
    response = await client.get('/api/v1/education/textbooks/<id>')
    version = response.json()['versions'][0]
    assert version['sources'][0]['original_filename'] == 'body.pdf'
    assert version['chapters'][0]['page_start'] == 1
    assert 'storage_key' not in response.text
```

**Step 2: Verify RED**

Run: `uv run pytest tests/unit/server/app/education/test_textbooks.py tests/unit/server/database/test_education_textbook_jobs.py -q`

**Step 3: Minimal implementation**

- Add version-scoped source metadata and chapter page start/end to the parent-only detail query.
- Preserve the parent household join and keep source bytes behind the existing asset download endpoint.

**Step 4: Verify GREEN**

Run: `uv run pytest tests/unit/server/app/education/test_textbooks.py tests/unit/server/database/test_education_textbook_jobs.py -q`

**Step 5: Commit**

```bash
git add src/server/database/education_textbooks.py src/server/services/education_textbooks.py src/server/app/education/models.py src/server/app/education/textbooks.py tests/unit/server/app/education/test_textbooks.py tests/unit/server/database/test_education_textbook_jobs.py CHANGELOG.md
git commit -m 'feat(education): expose parent textbook review metadata'
```

### Task 3: Parent Multi-source Processing and Review UI

**Files:**
- Modify: `web/src/pages/Education/api.ts`
- Modify: `web/src/pages/Education/queries.ts`
- Modify: `web/src/pages/Education/types.ts`
- Modify: `web/src/pages/Education/TextbookDetailPage.tsx`
- Create: `web/src/pages/Education/__tests__/TextbookDetailPage.test.tsx`

**Step 1: Write failing UI tests**

```tsx
it('submits selected existing and newly uploaded sources explicitly', async () => {
  render(<TextbookDetailPage />);
  await user.click(screen.getByRole('button', { name: '开始加工' }));
  await user.click(screen.getByRole('checkbox', { name: 'body.pdf' }));
  await user.click(screen.getByRole('checkbox', { name: 'workbook.pdf' }));
  await user.click(screen.getByRole('button', { name: '创建加工任务' }));
  expect(start).toHaveBeenCalledWith({ textbookId: 'textbook-1', sourceAssetIds: ['asset-1', 'asset-2'] });
});
```

**Step 2: Verify RED**

Run: `cd web && pnpm vitest run src/pages/Education/__tests__/TextbookDetailPage.test.tsx`

**Step 3: Minimal implementation**

- Add typed candidate-source API/query support.
- Let a parent select existing assets and add an optional new asset before making an explicit processing request.
- Display compact overview, content, teaching, and student review tabs with source metadata, page bounds, Markdown, material, and frozen questions.
- Use the project toast pattern for failures and retain dialog selections after failure.

**Step 4: Verify GREEN**

Run: `cd web && pnpm vitest run src/pages/Education/__tests__/TextbooksPage.test.tsx src/pages/Education/__tests__/TextbookDetailPage.test.tsx && pnpm build`

**Step 5: Commit**

```bash
git add web/src/pages/Education/api.ts web/src/pages/Education/queries.ts web/src/pages/Education/types.ts web/src/pages/Education/TextbookDetailPage.tsx web/src/pages/Education/__tests__/TextbookDetailPage.test.tsx CHANGELOG.md
git commit -m 'feat(education): complete parent textbook review workflow'
```

### Task 4: Responsive Student Reader

**Files:**
- Modify: `web/src/pages/Education/StudentLearningPage.tsx`
- Modify: `web/src/pages/Education/__tests__/StudentLearningPage.test.tsx`

**Step 1: Write failing test**

```tsx
it('opens directory and knowledge checks in separate mobile panels', async () => {
  render(<StudentLearningPage />);
  await user.click(screen.getByRole('button', { name: '目录' }));
  expect(screen.getByRole('navigation', { name: '章节目录' })).toBeVisible();
  await user.click(screen.getByRole('button', { name: '知识检查' }));
  expect(screen.getByRole('heading', { name: '知识检查' })).toBeVisible();
});
```

**Step 2: Verify RED**

Run: `cd web && pnpm vitest run src/pages/Education/__tests__/StudentLearningPage.test.tsx`

**Step 3: Minimal implementation**

- Preserve desktop three columns.
- Keep chapter reading primary on small viewports and expose directory/checks in accessible dialogs or sheets.
- Preserve stable chapter links, learning progress, frozen answers, and absence of parent controls.

**Step 4: Verify GREEN**

Run: `cd web && pnpm vitest run src/pages/Education/__tests__/StudentLearningPage.test.tsx`

**Step 5: Commit**

```bash
git add web/src/pages/Education/StudentLearningPage.tsx web/src/pages/Education/__tests__/StudentLearningPage.test.tsx CHANGELOG.md
git commit -m 'feat(education): add mobile textbook learning panels'
```

### Task 5: Parent-to-student Browser Acceptance

**Files:**
- Modify: `web/e2e/education.spec.js`
- Modify: `CHANGELOG.md`

**Step 1: Write failing browser flow**

```js
test('parent publishes and assigns a textbook, student learns, and parent reads evidence', async ({ browser }) => {
  // Parent creates, processes, reviews, publishes, and assigns.
  // Student opens the assignment and answers a frozen question.
  // Parent opens read-only evidence.
});
```

**Step 2: Verify RED**

Run: `cd web && pnpm playwright test e2e/education.spec.js --grep 'publishes and assigns'`

**Step 3: Minimal implementation**

- Mock source index, processing, publication, assignment, answer, records, and transcript routes.
- Assert students never see parent controls and the parent evidence surface has no write control.
- Exercise desktop and mobile viewports.

**Step 4: Full acceptance**

```bash
uv run pytest tests/unit/server/app/education/test_assets.py tests/unit/server/services/test_education_assets.py tests/unit/server/app/education/test_textbooks.py tests/unit/server/services/test_education_textbooks.py tests/unit/server/services/test_education_learning_chat.py tests/unit/server/services/test_education_learning_transcript.py tests/unit/server/database/test_education_textbook_jobs.py -q
make lint
cd web && pnpm vitest run src/pages/Education/__tests__/TextbooksPage.test.tsx src/pages/Education/__tests__/TextbookDetailPage.test.tsx src/pages/Education/__tests__/StudentLearningPage.test.tsx && pnpm build && pnpm playwright test e2e/education.spec.js
```

**Step 5: LAN verification and commit**

- Run `cd web && pnpm dev --host 0.0.0.0 --port 5177`, confirm `lsof` shows `*:5177`, and inspect the browser flow.

```bash
git add web/e2e/education.spec.js CHANGELOG.md
git commit -m 'test(education): verify textbook learning vertical slice'
```
