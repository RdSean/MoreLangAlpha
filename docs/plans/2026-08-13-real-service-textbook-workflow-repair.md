# Real Service Textbook Workflow Repair Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Repair and prove the real parent textbook workflow from creation through upload, processing, review, publication, and assignment against the current worktree's services.

**Architecture:** Treat the live `5177` browser, `8000` FastAPI service, PostgreSQL, and private MinIO storage as separate boundaries that need evidence before code changes. Keep the versioned `education_` model and service-side household authorization intact; make the frontend route from creation to the textbook detail page and render a state-driven next-action workflow without exposing storage keys.

**Tech Stack:** Python 3.13+, FastAPI, async psycopg3, MinIO/S3-compatible private storage, React 19, TypeScript, React Query, Vitest, Playwright, agent-browser.

---

### Task 1: Establish the Real-Service Baseline

**Files:**
- Create: `docs/plans/2026-08-13-real-service-textbook-workflow-repair.md`
- Inspect: `web/vite.config.*`, `server.py`, education routes, service configuration, running process command lines

**Step 1: Prove listener ownership before starting services**

Run `lsof` and inspect process working directories, command lines, and git HEADs for ports `5177` and `8000`.

**Step 2: Start only current-worktree services when no matching listener exists**

Run the frontend as `pnpm dev --host 0.0.0.0 --port 5177` and the FastAPI server from this worktree with its normal development command. Capture each PID, working directory, effective command, listener address, and response headers.

**Step 3: Confirm dependencies without mutating unrelated state**

Use health/auth endpoints and project-scoped Docker inspection to prove database access. Do not enumerate, delete, or overwrite unrelated MinIO objects.

**Step 4: Commit the execution plan**

```bash
git add docs/plans/2026-08-13-real-service-textbook-workflow-repair.md
git commit -m 'docs(education): plan real service textbook repair'
```

### Task 2: Reproduce the Parent Failure Against Real Services

**Files:**
- Inspect: `web/src/pages/Education/TextbooksPage.tsx`
- Inspect: `web/src/pages/Education/TextbookDetailPage.tsx`
- Inspect: `web/src/pages/Education/api.ts`
- Inspect: `web/src/pages/Education/queries.ts`
- Inspect: `src/server/app/education/*.py`
- Inspect: `src/server/services/education_*.py`

**Step 1: Use a real authenticated parent browser session**

Record the login/session restoration request and establish the family role from the real `/api/v1/auth/me` response. Do not use a mocked route or fabricated browser storage.

**Step 2: Create a uniquely named disposable textbook draft**

Record the create request, response, resulting URL, console errors, and the visible DOM/state conditions. Do not delete existing user textbooks.

**Step 3: Trace the first post-create page boundary**

Record the React route/navigation result, textbook detail request(s), response(s), and the conditions that decide whether source selection, processing, review, publication, and assignment controls render.

**Step 4: State one root-cause hypothesis**

Compare the broken path with existing working parent detail behavior and identify whether the failure is client navigation/rendering, API contract/data, authorization, environment/service origin, or a combination.

### Task 3: Add a Focused Failing Regression Test

**Files:**
- Modify: the narrowest existing education unit/UI test file discovered in Task 2
- Modify only if proved necessary: corresponding frontend or backend implementation file

**Step 1: Write one failing test for the evidenced regression**

For a creation-navigation defect, assert the mutation navigates directly to `/education/textbooks/:id` and the detail action panel renders all valid next steps for a draft. For a backend contract defect, assert the service preserves parent authorization and returns only safe fields needed to render the action panel.

**Step 2: Run the focused test and capture the expected failure**

Run the individual Vitest or pytest target. The failure must demonstrate the observed real-service regression, not an unrelated mock setup error.

**Step 3: Implement the smallest root-cause fix**

Keep API calls in the existing API/query layers, retain source selection, and keep mutations and storage authorization on the server. Do not expose `storage_key`, signed object URLs, or cross-household assets.

**Step 4: Run focused tests and update the Chinese changelog**

Update `CHANGELOG.md` with the user-visible repair and the real-service scope.

**Step 5: Commit the atomic implementation**

```bash
git add <changed implementation files> <test files> CHANGELOG.md
git commit -m 'fix(education): restore textbook workflow after creation'
```

### Task 4: Verify the Full Parent Workflow on Real Services

**Files:**
- Inspect: existing education job/pipeline code and route contracts

**Step 1: Restart only services sourced from this worktree after the fix**

Record their process source and confirm `0.0.0.0:5177` is listening.

**Step 2: Run the real parent upload and processing flow**

Using the authenticated parent, upload a small, newly created valid PDF for this verification only. Confirm the real upload request and safe asset response; confirm storage writes only under `education/` through the application boundary.

**Step 3: Create and execute a processing job**

Select the source, create the job, wait for its real status transition, and record job/detail API responses plus browser console and network evidence.

**Step 4: Review, publish, and assign if the process reaches review**

Inspect extracted content, source metadata, chapters, and questions in the parent UI, publish the candidate version, and assign it to a safe existing test student only when one is identifiable without exposing unrelated household data.

**Step 5: Verify learning evidence where safely available**

If a safe test student exists, log in as that student, answer one frozen question through the real service, then return as parent and confirm the resulting record is read-only. Otherwise record the missing safe test account as an acceptance gap.

### Task 5: Run Regression and Build Verification

**Files:**
- Modify: `CHANGELOG.md` only if a further substantive correction is verified

**Step 1: Run focused backend education tests**

Run affected `tests/unit/server/**/education*` targets with `uv run pytest`.

**Step 2: Run focused frontend education tests**

Run the affected Vitest targets and the existing mock Playwright education suite, reporting mock results separately from real-service evidence.

**Step 3: Run lint and production build**

Run `make lint`, frontend `pnpm build`, and any directly affected type checks.

**Step 4: Verify final live-process provenance**

Capture listener address, PID, command, working directory, git branch, and HEAD for both `5177` and `8000`.

**Step 5: Finalize branch workflow**

Use `superpowers:verification-before-completion`, then `superpowers:finishing-a-development-branch`. Do not claim completion without a successful real-service browser loop.
