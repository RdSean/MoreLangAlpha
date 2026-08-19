# Student Flash Route Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let a student enter their private Flash chat instead of remaining on the loading surface after Flash workspace creation.

**Architecture:** `StudentFlashChat` remains the root `/chat` redirector for a student. It renders its child chat route for a workspace or thread deep link, relying on existing server-side ownership checks for those resources.

**Tech Stack:** React 19, React Router, Vitest, Testing Library, TypeScript.

---

### Task 1: Specify Student Flash Route Behavior

**Files:**
- Create: `web/src/pages/Education/__tests__/StudentFlashChat.test.tsx`
- Modify: `web/src/pages/Education/StudentFlashChat.tsx:7-22`

**Step 1: Write the failing test**

Render the component as a student at `/chat`. Mock the Flash workspace API to
resolve one UUID, assert that the loading status appears initially, then assert
that the route changes to `/chat/<uuid>` and the child chat content renders.
Add a thread-deep-link assertion that no Flash redirect API call occurs and the
child content renders.

**Step 2: Run test to verify it fails**

Run: `pnpm vitest run src/pages/Education/__tests__/StudentFlashChat.test.tsx`

Expected: the post-redirect assertion fails because the component always
returns `PageLoading` for a student.

**Step 3: Write minimal implementation**

Use the current router location to distinguish root `/chat` from workspace and
thread routes. Preserve the existing one-time Flash workspace request only for
the root route, and render `children` for all non-root student chat routes.

**Step 4: Run test to verify it passes**

Run: `pnpm vitest run src/pages/Education/__tests__/StudentFlashChat.test.tsx`

Expected: all focused tests pass.

**Step 5: Commit**

```bash
git add web/src/pages/Education/StudentFlashChat.tsx \
  web/src/pages/Education/__tests__/StudentFlashChat.test.tsx
git commit -m "fix: render student Flash chat after redirect"
```

### Task 2: Verify the Student Entry Path

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Run targeted verification**

Run:

```bash
pnpm vitest run src/pages/Education/__tests__/StudentFlashChat.test.tsx
pnpm typecheck
pnpm build
```

**Step 2: Record the fixed behavior**

Add a Chinese changelog entry explaining that students now enter their private
Flash workspace after the deterministic workspace redirect, without exposing
model configuration or parent-only features.

**Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: record student Flash route fix"
```
