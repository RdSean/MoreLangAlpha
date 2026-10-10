# Education Calendar Ledger Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the education page's flat homework list with a calendar-ledger view, fixed core subject sections, parent check-in support, and completion points feedback.

**Architecture:** Reuse the existing education calendar API and React Query cache. The page will request a bounded month window in the household timezone, select one occurrence date, and render a one-page subject ledger. Points are derived from completed tasks and are therefore idempotent; the backend will authorize parent check-in within the same household while preserving the actual actor in the submission record.

**Tech Stack:** React 19, TypeScript, React Query, Tailwind semantic tokens, FastAPI, async psycopg, Vitest, pytest.

---

### Task 1: Add parent check-in authorization and points data

**Files:** `src/server/services/education_tasks.py`, `src/server/database/education_tasks.py`, `src/server/app/education/router.py`, focused service/router tests.

- Write failing tests for same-household parent check-in, foreign parent denial, and actor attribution.
- Extend check-in service/database parameters to accept the caller and assigned student; validate parent household membership.
- Keep idempotency and asset ownership checks, and record `submitted_by_user_id` as the caller.
- Expose a lightweight points total from existing completed task calendar progress or a dedicated scoped endpoint only if needed.

### Task 2: Add calendar ledger helpers and page tests

**Files:** `web/src/pages/Education/EducationPage.tsx`, `web/src/pages/Education/types.ts`, `web/src/pages/Education/queries.ts`, tests.

- Write failing tests for calendar loading, selected-day ledger, fixed 语文/数学/英语 sections, hiding other empty subjects, and points rendering.
- Use household timezone date boundaries and month navigation.
- Render a single page with calendar hero and selected-day subject ledger.
- Keep existing create, submission, review, cancel, textbook links and mobile targets.

### Task 3: Add completion feedback

**Files:** `web/src/pages/Education/EducationPage.tsx`, tests, `CHANGELOG.md`.

- Write a failing test that successful first check-in increments the displayed derived point count and invokes a short success sound.
- Use Web Audio only after a confirmed mutation, with reduced-motion/accessibility-safe behavior and no persistence side effects.
- Keep repeat submissions from changing the score by deriving points from completed task count.

### Task 4: Verify and commit

- Run focused Vitest and pytest suites, then typecheck/build.
- Run the frontend on `0.0.0.0:5177` and verify HTTP reachability.
- Update Chinese `CHANGELOG.md`.
- Commit only the feature files and plan/changelog changes; preserve existing user modifications.



## Execution notes

- Completed in the existing `feature/more-to-skills-textbook-refactor` worktree; no changes made to `local-main`.
- Calendar statistics now include `total_points` (all completed tasks in the authorized student/household scope). No schema migration or separate mutable points counter is needed.
- Parent check-in uses the authenticated actor and enforces same-household authorization in the transaction; sibling students and foreign household parents are rejected.
- Calendar and notebook are shared by both roles. Core sections are always present, optional subjects are generated from actual day tasks, and timeline/attachment queries load only when opening a record.
- Audio context is prepared during the confirmation click and plays only after the successful response. Existing completion data is refreshed through React Query invalidation.
- Verification: 36 frontend tests, 48 backend unit tests, 1 real PostgreSQL integration test, 10 Chromium E2E tests; production build/critical-path budget, TypeScript and changed-file lint pass. Verified desktop/mobile screenshots and LAN HTTP 200 on port 5177.
- Future ICS: frontend can parse a local file for preview; persistent shared import and automatic URL subscriptions need backend storage, periodic synchronization, UID/recurrence/timezone handling, and validated subscription fetching. Not implemented in this change.
