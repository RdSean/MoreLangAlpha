# Generic Workspace Frontend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove the financial frontend product surface and replace the finance dashboard with a Quiet Workspace general dashboard.

**Architecture:** Keep the existing React application shell, chat route, workspace/file APIs, automation route, design tokens, and React Query. First remove public finance routes and navigation, then replace the dashboard with a compact generic entry surface. Remove the MarketView-specific chart/annotation graph only after the generic chat artifact paths no longer import it; this avoids breaking ChatAgent through hidden type and lazy-component dependencies.

**Tech Stack:** React 19, Vite, TypeScript, Tailwind, shadcn/Radix, Lucide, React Query, Vitest, Playwright.

---

### Task 1: Lock the public generic route contract

**Files:**
- Create: `web/src/components/Main/__tests__/genericRoutes.test.tsx`
- Modify: `web/src/components/Main/Main.tsx`
- Modify: `web/src/components/nav/navItems.ts`
- Modify: `web/src/locales/en-US.json`
- Modify: `web/src/locales/zh-CN.json`

**Step 1: Write the failing test.**

Render the main route table with lazy pages mocked. Assert `/dashboard`, `/chat`, `/automations`, and `/settings` resolve; assert `NAV_ITEMS` has no `/market`; assert no public route resolves `/market` or `/news/:id`.

**Step 2: Run RED.**

Run: `cd web && pnpm test -- genericRoutes.test.tsx`

Expected: the market navigation item and route assertions fail.

**Step 3: Implement the smallest route change.**

- Remove MarketView and news-detail lazy imports and routes from `Main.tsx`.
- Remove the market navigation item and its `ChartCandlestick` import.
- Remove only the now-unused sidebar translation key; do not bulk-edit unrelated locale sections yet.

**Step 4: Run GREEN.**

Run: `cd web && pnpm test -- genericRoutes.test.tsx && pnpm typecheck`

Expected: route contract passes and TypeScript identifies the next set of route-level dependencies.

**Step 5: Commit.**

```bash
git add web/src/components/Main web/src/components/nav web/src/locales/en-US.json web/src/locales/zh-CN.json
git commit -m "refactor(web): remove financial public routes"
```

### Task 2: Replace the finance dashboard with a generic workspace overview

**Files:**
- Create: `web/src/pages/Dashboard/WorkspaceOverview.tsx`
- Create: `web/src/pages/Dashboard/__tests__/WorkspaceOverview.test.tsx`
- Modify: `web/src/pages/Dashboard/DashboardRouter.tsx`
- Modify: `web/src/pages/Dashboard/Dashboard.css`
- Delete: `web/src/pages/Dashboard/Dashboard.tsx`
- Delete: `web/src/pages/Dashboard/DashboardCustom.tsx`
- Delete: finance-only `web/src/pages/Dashboard/components/`, `hooks/`, `utils/`, and `widgets/`

**Step 1: Write the failing view test.**

Mock existing workspace/thread summary hooks and assert the overview renders three actions linked to `/chat`, `/automations`, and the active workspace file panel. Assert it uses current `Button` and token-backed surface classes rather than legacy dashboard selectors.

**Step 2: Run RED.**

Run: `cd web && pnpm test -- WorkspaceOverview.test.tsx`

Expected: fail because `WorkspaceOverview` does not exist.

**Step 3: Implement the overview.**

- Build a compact, full-width Quiet Workspace page using the existing `Button`, Lucide icons, page/card tokens, and responsive grid.
- Reuse only general workspace/thread data already exposed by the existing frontend API layer. Do not introduce dashboard preference persistence, finance mock data, new backend endpoints, or education placeholders.
- Point `DashboardRouter` directly to `WorkspaceOverview`; remove classic/custom preference dispatch and financial widget registry side effects.

**Step 4: Delete dead dashboard files and re-run typecheck.**

Delete references in dependency order. Use `pnpm typecheck` after each logical deletion batch to find the next import edge rather than retaining compatibility shims.

**Step 5: Verify GREEN.**

Run: `cd web && pnpm test -- WorkspaceOverview.test.tsx && pnpm typecheck && pnpm build`

Expected: tests, typecheck, and critical-path bundle verification pass.

**Step 6: Commit.**

```bash
git add web/src/pages/Dashboard web/src/lib web/src/hooks
git commit -m "refactor(web): add generic workspace dashboard"
```

### Task 3: Remove the finance chart and MarketView dependency graph

**Files:**
- Delete: `web/src/pages/MarketView/`
- Delete: `web/src/lib/bars/`, `web/src/lib/marketUtils.ts`, finance-only `web/src/types/market.ts`
- Modify: `web/src/contexts/AuthContext.tsx`
- Modify: `web/src/pages/ChatAgent/session/stream/processStreamEvent.ts`
- Modify: `web/src/pages/ChatAgent/session/types.ts`
- Modify: `web/src/pages/ChatAgent/components/charts/`
- Modify: `web/src/pages/ChatAgent/components/workspaceActions.tsx`
- Modify: `web/src/pages/Onboarding/registry/gettingStarted.ts`
- Delete: finance-only tests, chart annotation tests, and market-watch tests

**Step 1: Write the failing dependency-boundary test.**

Create a focused Vitest/source-boundary test which asserts `ChatAgent`, auth, onboarding, route files, and generic libraries contain no imports from `pages/MarketView`, `lib/bars`, or market-only API modules.

**Step 2: Run RED.**

Run: `cd web && pnpm test -- genericFinanceDependencyBoundary.test.ts`

Expected: fail with the current MarketView imports in ChatAgent, auth, onboarding, and dashboard widgets.

**Step 3: Remove chart-specific chat artifacts.**

- Drop chart selection context, annotation SSE handling, inline financial chart cards, chart storage imports, and MarketView thread cleanup.
- Preserve non-chart agent artifacts, chat SSE, file attachments, workspace navigation, and generic visualizations.

**Step 4: Delete MarketView and related library modules.**

Delete page files only when every importing module is removed or converted. Remove stale onboarding entries and direct redirect links to `/market`.

**Step 5: Verify GREEN.**

Run: `cd web && pnpm test -- genericFinanceDependencyBoundary.test.ts && pnpm typecheck && pnpm build`

**Step 6: Commit.**

```bash
git add web/src/pages/MarketView web/src/pages/ChatAgent web/src/lib web/src/contexts web/src/pages/Onboarding web/src/types
git commit -m "refactor(web): remove financial chart dependencies"
```

### Task 4: Remove finance localization and release-verify the generic surface

**Files:**
- Modify: `web/src/locales/en-US.json`
- Modify: `web/src/locales/zh-CN.json`
- Modify: `CHANGELOG.md`
- Create: `web/e2e/generic-workspace.spec.ts`

**Step 1: Write the failing browser assertion.**

Use Playwright to assert the dashboard has no market navigation, route, quote, portfolio, or news cards and that desktop/mobile navigation reaches Chat and Automations.

**Step 2: Run RED.**

Run: `cd web && pnpm test:e2e -- generic-workspace.spec.ts`

**Step 3: Remove stale finance-only translation branches.**

Delete keys exclusively consumed by removed source files. Keep generic terms such as "market" only where they have an unrelated, independently used meaning.

**Step 4: Verify GREEN and LAN handoff.**

Run: `cd web && pnpm test && pnpm typecheck && pnpm build && pnpm test:e2e -- generic-workspace.spec.ts`

Check port `5177` is unused, then run:

```bash
pnpm dev --host 0.0.0.0 --port 5177
```

Capture desktop and mobile screenshots with the browser test tooling; verify no blank content, overflow, finance references, or overlapping text.

**Step 5: Record and commit.**

Add a Chinese `CHANGELOG.md` entry and commit only this task's files:

```bash
git add CHANGELOG.md web/src/locales web/e2e/generic-workspace.spec.ts
git commit -m "refactor(web): complete generic workspace surface"
```
