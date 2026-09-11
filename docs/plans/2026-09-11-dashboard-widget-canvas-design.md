# Dashboard Widget Canvas Design

**Status:** approved 2026-09-11, not yet implemented.

## Goal

Restore the upstream dashboard **layout system** — the widget grid, frames,
registry, presets and persisted layout — and start building our own widgets on
top of it. The first widget is a homework calendar that answers "what has been
assigned recently, and where does each task stand?" at a glance.

The upstream *definitions* (portfolio, watchlist, news, earnings, TradingView)
are deliberately not restored. They are the finance surface the local branch
removed on purpose, and `docs/plans/core-merge-*.txt` already keeps the removal
pass ordered for later.

## What exists today

- `web/src/pages/Dashboard/` holds only `DashboardRouter.tsx` (returns
  `WorkspaceOverview`) and `WorkspaceOverview.tsx` — a 191-line hand-written
  page: header, three action buttons, recent-threads and workspaces columns.
- The whole upstream `widgets/` tree (framework, definitions, presets — 60+
  files) was deleted in `37fef0e9 refactor(web): remove financial chart
  dependencies`, together with `lib/bars`, `lib/quotes`, `lib/marketUtils`,
  `lightweight-charts` and `recharts`.
- The backend already serves household-scoped homework data:

  ```
  GET /api/v1/education/tasks/calendar?start_date&end_date[&student_id]
  → { days: [{ date, task_count, completed_count, overdue_count, tasks[] }],
      stats: { today_count, week_count, overdue_count, completed_count } }
  ```

  Each task carries `subject_code`, `subject_color`, `is_completed`,
  `is_overdue`, `due_at`, `assigned_student_id`. A parent omitting
  `student_id` gets the whole household; passing it narrows to one child; a
  student only ever sees their own tasks. The frontend hook
  `useEducationTaskCalendar` already exists in `pages/Education/queries.ts`.

So the household scoping the dashboard needs — parents and student accounts
reading the same source with the same rights — is a backend rule that is
already implemented. No backend change is required for this feature.

## Approach

### Phase 1 — restore the layout system, finance-free

Port `web/src/pages/Dashboard/widgets/framework/*` from `origin/main` minus the
TradingView-only pieces, plus `widgets/types.ts` and the `dashboard.widgets.*`
i18n subtree (skipping the `tv*` keys). Add `react-grid-layout@2.2.3`; it is a
pure layout library with `react` / `react-dom` as its only peers, not a finance
dependency.

Three deliberate deviations from upstream, each forced rather than chosen:

1. **`DashboardDataContext` is rewritten slim.** Upstream builds it from
   `useDashboardData` / `useWatchlistData` / `usePortfolioData`, which import
   `@/lib/marketUtils` and `@/lib/quotes`. `src/__tests__/genericFinanceDependencyBoundary.test.ts`
   forbids any surviving file from referencing `lib/marketUtils`, `lib/bars` or
   `pages/MarketView`, so those hooks cannot be ported. The slim context keeps
   the provider, the `useDashboardContext` hook and the `initConfig` signature,
   and drops the portfolio / watchlist / news modal slices that no surviving
   widget reads.
2. **`DashboardCustom` loses the market websocket provider.** Upstream wraps it
   in `MarketDataWSProvider` from `@/pages/MarketView/contexts/MarketDataWSContext`,
   which the same boundary test forbids.
3. **`Dashboard.tsx` (classic) is not ported.** It renders the finance cards
   directly. The local `WorkspaceOverview` takes its place as the classic mode.

### Phase 2 — the homework calendar widget

A new definition, `education.homeworkCalendar`, modelled on
`EarningsCalendarWidget` but fed by `useEducationTaskCalendar`:

- Buckets `today / tomorrow / this week / next week / later`, sorted
  nearest-due-first, so the top of the widget is always the most urgent task.
- A stat strip at the top reads the API's own `stats` payload: today, this
  week, overdue, completed.
- Each row shows a subject colour dot, the title, the child's name (mapped from
  `assigned_student_id` via `useEducationMembers`) and the due time. Overdue
  rows render in the danger colour; completed rows are dimmed and struck
  through.
- Clicking a row navigates to `/education`.
- Config: window `1w | 2w | 1m` (default `2w`), `showCompleted` (default
  `false` — the widget answers "what is still outstanding").
- It registers a context exporter, so the framework's existing "+ add to
  conversation" button lets a parent drop the outstanding list straight into
  chat.

### Phase 3 — presets

Upstream ships six finance presets. Replace them with ours, defaulting to a
"family desk": homework calendar, recent threads, workspace picker,
automations, conversation input.

### First-pass widget set

Besides the new calendar, four upstream definitions survive the finance cut
unchanged and come along in phase 1: `AutomationsWidget`,
`ConversationWidget`, `WorkspacePickerWidget`, `RecentThreadsWidget`. None of
them reads portfolio or watchlist data.

## Ownership of the dashboard route

`/dashboard` keeps both modes, following upstream's `DashboardRouter` shape:
`mode: 'classic' | 'custom'` in `other_preference.dashboard`, with the widget
canvas as the default and `WorkspaceOverview` as the classic mode, plus a
header toggle. Mobile stays classic, as upstream does. This keeps the existing
overview reachable and makes the whole change reversible by flipping a
preference.

## Testing

- Widget: bucketing, nearest-first ordering, overdue styling, completed
  filtering, empty state, row navigation, student-name mapping.
- Registry: the canvas registers no finance widget.
- Framework: the upstream framework tests that are not TradingView-specific are
  ported as-is.
- Boundary: `genericFinanceDependencyBoundary` and `dashboardBoundary` must stay
  green — they are the regression guard for this whole phase.

## Risks

- `react-grid-layout@2.2.3` is a major version the local lockfile has never
  resolved. It is pinned in upstream's lockfile, so the API surface
  (`ResponsiveGridLayout`, `useContainerWidth`) is known-good, but the install
  is the first thing to verify.
- The i18n parity test (`src/locales/__tests__/keys.test.ts`) enforces literal
  `t('...')` keys, so every new widget string must be a literal.
- The classic/custom toggle writes to `other_preference.dashboard`; the local
  ModelTab bug fixed earlier in this branch was exactly this class of error.
  Persisted-layout writes must go through the framework's
  `dashboardPrefsWriter`, never a raw preference write.
