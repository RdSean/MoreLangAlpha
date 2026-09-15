# Dashboard Widget Canvas Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore the upstream dashboard widget layout system (finance-free) and
land the first first-party widget, a household homework calendar.

**Architecture:** Port `web/src/pages/Dashboard/widgets/framework/*` from
`origin/main` minus the TradingView-only files, adapt the three places that
couple to the retired finance surface (`DashboardDataContext`, the market
websocket provider, the classic `Dashboard.tsx`), then register a new
`education.homeworkCalendar` definition backed by the existing
`GET /api/v1/education/tasks/calendar` endpoint. `/dashboard` gains a
`classic | custom` mode switch; the widget canvas is the default and the
current `WorkspaceOverview` becomes the classic mode.

**Tech Stack:** React 19, Vite, TypeScript, Tailwind, react-query,
`react-grid-layout@2.2.3`, zod, vitest, pnpm.

**Design doc:** `docs/plans/2026-09-11-dashboard-widget-canvas-design.md`

**Branch / worktree:** `feature/platform-core-migration` at
`/Users/seanlee/.config/superpowers/worktrees/langalpha/platform-core-migration`.
Upstream reference is `origin/main` = `ddc6e53662b800af6d89c756e84bde59d5cb06d7`.
Every `git show origin/main:<path>` below means that commit.

**Rollback:** `git reset --hard checkpoint/pre-core-merge` (pre-merge) or the
last good commit on this branch.

**Rules for every task:**

- One task = one commit, with the verification output quoted in the message.
- Update `CHANGELOG.md` in Chinese in the same commit.
- Never overwrite or delete a path in `docs/plans/core-merge-keep-list.txt`.
- `src/__tests__/genericFinanceDependencyBoundary.test.ts` forbids the strings
  `pages/MarketView/`, `lib/bars/`, `lib/marketUtils` anywhere under `src/`
  outside those trees. Nothing ported below may reference them — not even in a
  comment.
- `src/__tests__/dashboardBoundary.test.ts` forbids any file outside
  `src/pages/Dashboard/` from importing `Dashboard/`. Keep new dashboard code
  inside `src/pages/Dashboard/`.
- `src/locales/__tests__/keys.test.ts` requires every statically written
  `t('...')`, `titleKey`, `descriptionKey`, `nameKey`, `tagKey`, `bestForKey`,
  `labelKey`, `blurbKey` and every `'dashboard.*'` literal to resolve in **both**
  `en-US.json` and `zh-CN.json`.
- Tests must be seen to fail before the fix that makes them pass.

**Working commands:**

```bash
cd /Users/seanlee/.config/superpowers/worktrees/langalpha/platform-core-migration/web
pnpm vitest run src/pages/Dashboard            # dashboard slice
pnpm vitest run src/locales/__tests__/keys.test.ts
pnpm vitest run src/__tests__                   # boundary guards
pnpm typecheck && pnpm lint
```

---

## Outcome (recorded 2026-09-11, after the work landed)

All ten tasks shipped, plus two pieces of scope that arrived after the plan was
written. Landed as, oldest first:

| Commit | What |
|---|---|
| `84b53a3b` | this plan and its design doc |
| `f9812a91` | Task 0 — demo homework seeding |
| `0a69b465` | Task 1 — `react-grid-layout@2.2.3` |
| `b4d0767d` | Task 2 — framework core |
| `04c524db` | Task 3 — frame, context snapshots, framework locale copy |
| `f8369b3f` | Task 4 — the grid |
| `daec1e45` | Task 5 — the homework calendar widget |
| `f40d8c35` | Tasks 6 + 7 + 8 — canvas shell, router, gallery, presets, surviving widgets |
| `6e60bab0` | *added scope* — education two-tone icon set on subject surfaces |
| `d7452f7b` | *added scope* — period switch on the widget face + month view |

**Where the plan and the result differ, and why:**

- **Tasks 6, 7 and 8 landed as one commit.** The presets reference
  `agent.conversation` / `threads.recent` / `workspace.picker` /
  `automations.list`, so the canvas cannot be committed before those widgets
  register without shipping a preset full of blank cells. Splitting them would
  have left the guard in Task 8 red between commits.
- **Task 9 was folded into Tasks 3, 5 and 8** rather than done at the end:
  `keys.test.ts` fails as soon as a `t('…')` key is written, so each surface
  had to bring its own catalog entries.
- **`initConfig` lost its context parameter** instead of gaining a slimmed
  context. Its only upstream readers were the finance widgets, and an empty
  seam is worse than no seam. See `widgets/types.ts` for the note.
- **Deliberately not done:** the classic `Dashboard.tsx` was not ported (it
  renders the finance cards); `WorkspaceOverview` is the classic branch. The
  finance widget definitions, `lib/bars`, `lib/quotes` and their deps stay out.
- **Added after the fact, not in the plan:** the icon set (`6e60bab0`) and the
  month view plus on-face period switch (`d7452f7b`). The latter also answered
  a plan defect — the period switch was originally reachable only from the
  edit-mode settings dialog, which is too deep for a control used that often.

**Verified state:** web suite 248 files / 2419 tests passing; `typecheck`
clean; lint 0 errors / 56 warnings (unchanged baseline); build passes with the
critical path at 351.8 kB gz against a 450 kB ceiling.

**Still open, on purpose:**

1. User-level (non-bundled) MCP connector end-to-end — see the post-merge plan.
2. MinIO object cross-check for workspace file blobs — same.
3. The ~400-file product frontend gap under `web/src` (Dashboard classic,
   ChatAgent, MarketView, Onboarding, Login, `lib/bars`, `lib/quotes`).
4. The finance removal pass; `docs/plans/core-merge-*.txt` remain the index for
   it, and the widget registry guard added here
   (`widgets/__tests__/noFinanceWidgets.test.ts`) is its tripwire.

---

## Task 0: Seed demo homework data

Independent of the whole frontend plan — it can be built and run first, and it
is what makes the finished widget show anything. The local debug database
(`langalpha-platform-core-migration` stack, Postgres 15432) currently holds one
household (`lei lee` parent + `henry` student, `Asia/Tokyo`, grade `g6`) and
**zero** tasks.

**Files:**

- Create: `scripts/ops/seed_homework_demo.py`

**Step 1: Write the script**

Shape, following the conventions in `scripts/ops/backfill_workspace_file_blobs.py`
(`build_db_uri` from `_db.py`, `sys.path` prelude, `--apply` gate, argparse):

```python
"""Insert demo homework tasks for one household so the dashboard has content.

Development-only. Drives the real service layer rather than raw SQL so the
rows satisfy the same validation the app does. Idempotent: every rule carries
a `demo-seed:*` idempotency key, and re-running reports what already existed.

Usage:
    DB_HOST=127.0.0.1 DB_PORT=15432 uv run python scripts/ops/seed_homework_demo.py
    DB_HOST=127.0.0.1 DB_PORT=15432 uv run python scripts/ops/seed_homework_demo.py --apply
"""
```

Behaviour:

1. Resolve the household. `--household-id` if given, otherwise every household
   is listed and the script stops unless there is exactly one. Refuse to run
   against a household that has more than `--max-existing 0` seeded-but-foreign
   rules unless `--force`.
2. Resolve members via `list_household_membership_context`; require one
   `parent` and at least one `student`, and read the student's `grade_code`
   from `education_student_profiles`.
3. Read valid `(subject_code, type_code)` pairs from the database instead of
   hardcoding them — the dictionary is already there:

   ```sql
   SELECT subject_code, type_code FROM education_subject_homework_types
   ```

4. Create recurring rules through
   `src.server.services.education_tasks.create_task`, with `due_at` anchored to
   a *past* date so the recurrence covers the previous week too:

   | rule | frequency | weekdays | window | start |
   |---|---|---|---|---|
   | 语文预习 | `weekly` | `[1, 3, 5]` | 2 weeks back → today | 2 weeks ago |
   | 数学练习 | `weekly` | `[2, 4]` | 2 weeks back → today | 2 weeks ago |
   | 英语听读 | `daily` | — | 12 days back → today | 12 days ago |
   | 数学订正 | `weekly` | `[6]` | this week | this Monday |
   | 语文写作 | `once` | — | — | +3 days, 20:00 |
   | 英语背诵 | `once` | — | — | +9 days, 19:30 |

   Every `due_at` must be timezone-aware in the household's zone. `weekly`
   rejects an initial due date whose ISO weekday is not in `weekdays`, so pick
   the anchor date to match. `practice` type codes require a
   `practice_source_code`; use `schoolwork` / `homework`, or a non-practice
   type such as `preview` / `review` to keep it simple.

5. Mark a deterministic subset completed via
   `src.server.database.education_tasks.check_in_task` as the **student**
   (`student_user_id`), with a `demo-seed:*` idempotency key. Complete: every
   occurrence strictly before today, plus today's 语文预习. Leave everything
   else open, which produces a realistic mix of completed, open, and one
   overdue row without hand-forcing `status`.

   Read the occurrence rows with `list_calendar_task_records` over
   `[today - 14d, today + 14d]` after creating the rules, so the script
   completes exactly what exists rather than guessing.

6. Print a table of what was created and what was already present.

**Step 2: Dry run**

```bash
DB_HOST=127.0.0.1 DB_PORT=15432 uv run python scripts/ops/seed_homework_demo.py
```

Expected: prints the household, the members, the rules it *would* create, and
exits without writing.

**Step 3: Apply**

```bash
DB_HOST=127.0.0.1 DB_PORT=15432 uv run python scripts/ops/seed_homework_demo.py --apply
```

Expected: creation summary; no exceptions.

**Step 4: Verify through the API's own query path**

```bash
docker exec langalpha-platform-core-migration-postgres-1 psql -U postgres -d postgres -c "
SELECT occurrence_date, status, subject_code, title FROM education_tasks
ORDER BY occurrence_date, due_at LIMIT 40;
"
```

Expected: rows on dates in the previous week **and** the current/next week,
mixed `open` / `completed`.

**Step 5: Re-run to prove idempotency**

Run the `--apply` command again. Expected: no duplicate rows.

**Step 6: Commit**

```bash
git add scripts/ops/seed_homework_demo.py CHANGELOG.md
git commit -m "chore(ops): seed demo homework data for the dashboard"
```

---

## Task 1: Add the grid layout dependency

`react-grid-layout@2.2.3` is a pure layout library (peers: `react`,
`react-dom` only). It is what upstream's `DashboardGrid` drives; without it the
layout system cannot be restored. It is not a finance dependency, so it does not
collide with the removal commit `37fef0e9`.

**Files:**

- Modify: `web/package.json`, `web/pnpm-lock.yaml`

**Step 1: Install the pinned version**

```bash
cd web && pnpm add react-grid-layout@2.2.3
```

**Step 2: Verify the package resolves and exports what the grid needs**

```bash
cd web && node -e "
const p=require('./node_modules/react-grid-layout/package.json');
console.log('version', p.version);
console.log('exports', Object.keys(require('react-grid-layout')).join(','));
"
```

Expected: `version 2.2.3`, and the export list contains `ResponsiveGridLayout`
and `useContainerWidth`.

**Step 3: Verify nothing else moved**

```bash
cd web && git diff --stat package.json pnpm-lock.yaml
pnpm build
```

Expected: no chart library appears in the diff; build succeeds.

**Step 4: Commit**

```bash
git add web/package.json web/pnpm-lock.yaml
git commit -m "build(web): add react-grid-layout for the dashboard canvas"
```

---

## Task 2: Port the framework's pure logic

The framework splits cleanly: half of it is React-free logic (ids, geometry,
reconciliation, config schemas, snapshot serializers) that can be ported and
tested with no dashboard shell at all. Port that half first so the later UI
tasks sit on tested foundations.

**Files:**

- Create: `web/src/pages/Dashboard/widgets/types.ts`
- Create: `web/src/pages/Dashboard/widgets/framework/{WidgetRegistry.ts,ids.ts,gridConstants.ts,defaults.ts,reconcile.ts,configSchemas.ts,snapshotSerializers.ts,migrations.ts}`
- Create: `web/src/pages/Dashboard/widgets/framework/__tests__/{reconcile.test.ts,snapshotSerializers.test.ts,migrations.test.ts}`

**Step 1: Copy the files verbatim**

```bash
cd /Users/seanlee/.config/superpowers/worktrees/langalpha/platform-core-migration
mkdir -p web/src/pages/Dashboard/widgets/framework/__tests__
for f in types.ts; do
  git show origin/main:web/src/pages/Dashboard/widgets/$f > web/src/pages/Dashboard/widgets/$f
done
for f in WidgetRegistry.ts ids.ts gridConstants.ts defaults.ts reconcile.ts configSchemas.ts snapshotSerializers.ts migrations.ts; do
  git show origin/main:web/src/pages/Dashboard/widgets/framework/$f > web/src/pages/Dashboard/widgets/framework/$f
done
for f in reconcile.test.ts snapshotSerializers.test.ts migrations.test.ts; do
  git show origin/main:web/src/pages/Dashboard/widgets/framework/__tests__/$f > web/src/pages/Dashboard/widgets/framework/__tests__/$f
done
```

These files import only `zod` and each other. `defaults.ts` ships
`DEFAULT_BLUE_CHIPS = ['NVDA', ...]`; keep it for now — it is referenced by
`presets.ts`, which Task 9 replaces.

**Step 2: Adapt the two cross-tree imports**

`migrations.test.ts` imports `'../../index'` to populate the registry as a side
effect. `widgets/index.ts` does not exist yet. Create a placeholder now so the
test can resolve, and let Task 7 fill it in:

```bash
cat > web/src/pages/Dashboard/widgets/index.ts <<'EOF'
// Registry side-effect barrel. Definitions are appended by later tasks.
export { listWidgets, listWidgetsByCategory, getWidget } from './framework/WidgetRegistry';
EOF
```

(This is the only file in this plan created with a heredoc rather than
`apply_patch`; it is a one-line barrel that Task 7 overwrites from upstream.)

**Step 3: Run the ported tests**

```bash
cd web && pnpm vitest run src/pages/Dashboard/widgets/framework/__tests__/reconcile.test.ts src/pages/Dashboard/widgets/framework/__tests__/snapshotSerializers.test.ts src/pages/Dashboard/widgets/framework/__tests__/migrations.test.ts
```

Expected: 128 + 234 + 299 lines worth of assertions pass. `migrations.test.ts`
has cases naming `news.feed`; they exercise the migrator's pass-through path and
do not require the widget to exist.

**Step 4: Prove the geo tests actually guard something**

Temporarily change `ROW_HEIGHT` in `gridConstants.ts` from `8` to `9`, rerun
`reconcile.test.ts`, confirm failures, then revert. This is the "see it fail"
step — record the failure line in the commit message.

**Step 5: Typecheck and commit**

```bash
cd web && pnpm typecheck
cd .. && git add web/src/pages/Dashboard/widgets
git commit -m "feat(web): port the dashboard widget framework core"
```

---

## Task 3: Port the widget context registry and the widget frame

`WidgetFrame` is the chrome around every cell: drag grip, settings menu,
duplicate/remove, and the paperclip that publishes a context snapshot to the
chat input. It depends on the context-snapshot registry, which in turn must be
adapted to this branch's relocated snapshot type.

**Files:**

- Create: `web/src/pages/Dashboard/widgets/framework/contextSnapshot.ts`
- Create: `web/src/pages/Dashboard/widgets/framework/__tests__/contextSnapshot.test.tsx`
- Create: `web/src/pages/Dashboard/widgets/framework/WidgetFrame.tsx`
- Create: `web/src/pages/Dashboard/widgets/framework/WidgetFrame.css`
- Create: `web/src/pages/Dashboard/components/RowAttachButton.tsx`
- Create: `web/src/pages/Dashboard/components/RowAttachButton.css`

**Step 1: Copy the files**

```bash
cd /Users/seanlee/.config/superpowers/worktrees/langalpha/platform-core-migration
mkdir -p web/src/pages/Dashboard/components
git show origin/main:web/src/pages/Dashboard/widgets/framework/contextSnapshot.ts > web/src/pages/Dashboard/widgets/framework/contextSnapshot.ts
git show origin/main:web/src/pages/Dashboard/widgets/framework/__tests__/contextSnapshot.test.tsx > web/src/pages/Dashboard/widgets/framework/__tests__/contextSnapshot.test.tsx
git show origin/main:web/src/pages/Dashboard/widgets/framework/WidgetFrame.tsx > web/src/pages/Dashboard/widgets/framework/WidgetFrame.tsx
git show origin/main:web/src/pages/Dashboard/widgets/framework/WidgetFrame.css > web/src/pages/Dashboard/widgets/framework/WidgetFrame.css
git show origin/main:web/src/pages/Dashboard/components/RowAttachButton.tsx > web/src/pages/Dashboard/components/RowAttachButton.tsx
git show origin/main:web/src/pages/Dashboard/components/RowAttachButton.css > web/src/pages/Dashboard/components/RowAttachButton.css
```

**Step 2: Point the snapshot type at this branch's home**

Upstream declares `WidgetContextSnapshot` inside `contextSnapshot.ts`. This
branch already relocated it: `web/src/types/widgetContext.ts`, consumed by
`lib/contextBus.ts` and the chat input. Edit
`web/src/pages/Dashboard/widgets/framework/contextSnapshot.ts`:

- Delete the local `export interface WidgetContextSnapshot { ... }` declaration.
- Add at the top: `import type { WidgetContextSnapshot } from '@/types/widgetContext';`
- Keep `export type { WidgetContextSnapshot };` so existing importers of the
  framework path keep compiling.

**Step 3: Trim the TradingView-only branch in `WidgetFrame.tsx`**

`WidgetFrame` checks `definition.source === 'tradingview'` to disable the
paperclip. Keep the check and the `dashboard.widgets.frame.contextUnsupportedTradingView`
key — no TradingView widget is registered, so the branch is dead but harmless,
and it keeps the file diffable against upstream.

**Step 4: Run the context snapshot test**

```bash
cd web && pnpm vitest run src/pages/Dashboard/widgets/framework/__tests__/contextSnapshot.test.tsx
```

Expected: PASS. If it fails on the missing snapshot type, the relocation in
Step 2 is incomplete — fix that before continuing.

**Step 5: Typecheck and commit**

```bash
cd web && pnpm typecheck
cd .. && git add web/src/pages/Dashboard
git commit -m "feat(web): port the widget frame and context-snapshot registry"
```

---

## Task 4: Port the grid

**Files:**

- Create: `web/src/pages/Dashboard/widgets/framework/DashboardGrid.tsx`
- Create: `web/src/pages/Dashboard/widgets/framework/__tests__/DashboardGrid.test.tsx`

**Step 1: Copy**

```bash
cd /Users/seanlee/.config/superpowers/worktrees/langalpha/platform-core-migration
git show origin/main:web/src/pages/Dashboard/widgets/framework/DashboardGrid.tsx > web/src/pages/Dashboard/widgets/framework/DashboardGrid.tsx
git show origin/main:web/src/pages/Dashboard/widgets/framework/__tests__/DashboardGrid.test.tsx > web/src/pages/Dashboard/widgets/framework/__tests__/DashboardGrid.test.tsx
```

The grid imports `react-grid-layout` and `react-grid-layout/css/styles.css`,
plus `./WidgetFrame`, `./WidgetRegistry`, `./reconcile`, `./ids`,
`./gridConstants`. All exist by now. It contains a `WidgetErrorBoundary` class
that isolates one broken widget from the rest of the canvas — keep it.

**Step 2: Run**

```bash
cd web && pnpm vitest run src/pages/Dashboard/widgets/framework/__tests__/DashboardGrid.test.tsx
```

Expected: PASS.

**Step 3: Commit**

```bash
cd .. && git add web/src/pages/Dashboard/widgets/framework
git commit -m "feat(web): port the responsive dashboard grid"
```

---

## Task 5: The homework calendar widget

This is the product payload of the whole plan. Write the test first.

**Files:**

- Create: `web/src/pages/Dashboard/widgets/definitions/HomeworkCalendarWidget.tsx`
- Create: `web/src/pages/Dashboard/widgets/definitions/__tests__/HomeworkCalendarWidget.test.tsx`
- Create: `web/src/pages/Dashboard/widgets/framework/configSchemas.ts` — `HomeworkCalendarConfigSchema` (modify the copied file)

**Contract reference (already implemented, do not change):**

`web/src/pages/Education/queries.ts` → `useEducationTaskCalendar({ start_date, end_date, student_id? })`
`web/src/pages/Education/types.ts` → `EducationTaskCalendar`,
`EducationCalendarTask` (`subject_color`, `is_completed`, `is_overdue`),
`EducationTaskCalendarDay`, `EducationTaskCalendarRequest`.
`web/src/pages/Education/queries.ts` → `useEducationMembers(enabled)` gives
`EducationMember[]` (`user_id`, `name`, `role`) for name mapping.

`useEducationMembers` takes an `enabled` flag because students cannot read the
member list; call it with the current user's role as the flag so a student
account does not fire a request it will be denied.

**Step 1: Write the failing test**

Cover, in `definitions/__tests__/HomeworkCalendarWidget.test.tsx`:

1. Loading state renders the framework's loading string.
2. Empty payload renders the empty state, not a crash.
3. Given days across today / tomorrow / +4 days / +10 days / +20 days, the
   widget renders five buckets in that order with the right counts.
4. A task with `is_overdue: true` gets the overdue treatment
   (`data-overdue="true"` on its row).
5. A completed task is hidden when `showCompleted` is false and rendered with
   `data-completed="true"` when true.
6. A row's click navigates to `/education`.
7. When two tasks share an `assigned_student_id`, the member list's name for
   that id appears in the row.
8. `stats` from the payload is rendered in the header strip.
9. Pressing `‹` requests the window one length earlier: with `window: '1w'` and
   today `2026-09-11`, the next request is
   `{ start_date: '2026-08-29', end_date: '2026-09-04' }`. Pressing it again
   steps back another week, and the `This week` reset returns to offset 0.
10. The offset is not persisted: unmounting and remounting the widget renders
    the current window again.

Mock `useEducationTaskCalendar` and `useEducationMembers` with `vi.mock`, the
way `WorkspaceOverview.test.tsx` mocks `useWorkspaces`.

**Step 2: Run it and watch it fail**

```bash
cd web && pnpm vitest run src/pages/Dashboard/widgets/definitions/__tests__/HomeworkCalendarWidget.test.tsx
```

Expected: FAIL — module not found.

**Step 3: Implement**

Skeleton, mirroring `EarningsCalendarWidget.tsx` (396 lines upstream) but with
the education data source:

```tsx
// web/src/pages/Dashboard/widgets/definitions/HomeworkCalendarWidget.tsx
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { CalendarCheck } from 'lucide-react';
import { useEducationMembers, useEducationTaskCalendar } from '@/pages/Education/queries';
import { useUser } from '@/hooks/useUser';
import { registerWidget } from '../framework/WidgetRegistry';
import { useWidgetContextExport } from '../framework/contextSnapshot';
import { serializeRowsToMarkdown, wrapWidgetContext } from '../framework/snapshotSerializers';
import { HomeworkCalendarConfigSchema } from '../framework/configSchemas';
import { RowAttachButton } from '../../components/RowAttachButton';
import type { WidgetRenderProps } from '../types';

type HomeworkCalendarConfig = { window: '1w' | '2w' | '1m'; showCompleted: boolean };
type BucketKey = 'today' | 'tomorrow' | 'week' | 'next' | 'later';
```

Rules the implementation must follow:

- Date strings are local (`d.toLocaleDateString('en-CA')`), never
  `toISOString()` — the upstream widget carries a comment explaining why, and
  the same UTC day-boundary bug applies here.
- **Range stepper.** The header carries three controls: `‹` (shift the window
  back by its own length), a centre label that reads `This week` when the
  offset is 0 and the date range otherwise, and `›` (shift forward). `offset`
  is `useState(0)` — ephemeral, never persisted, so reloading always lands on
  the current window. The extra shift also means the request range is
  `start = today - offset*len - (len - 1)`, `end = today - offset*len` for
  `offset >= 0`; for the look-back case the range is entirely in the past and
  the `stats` strip must label itself as the *current* week's progress rather
  than the displayed window's, or hide itself. Prefer hiding the strip when
  `offset > 0`; it is a "where do things stand right now" summary.
- Bucket boundaries: today / tomorrow / days 2–6 / days 7–13 / day 14+,
  computed against local midnight.
- `WINDOW_DAYS = { '1w': 7, '2w': 14, '1m': 31 }` drives both the request range
  and the bucket cutoffs.
- Rows sort by `due_at` ascending within a bucket — nearest first, as the user
  asked.
- While the query is pending (`isLoading`) render the frame's loading string.
- Flatten `days[].tasks` before filtering `showCompleted`; the API returns
  both completed and open tasks for the window.
- The backend rejects a request whose `end_date - start_date >= 62` days
  (`_MAX_CALENDAR_RANGE_DAYS`), and rejects an `end_date` more than 12 months
  ahead. It places **no** bound on how far in the past `start_date` may be, so
  repeated `‹` presses are safe; still clamp the stepper at `-8` windows so a
  held key cannot spin the query key forever.
- Register the row exporter so each row can be attached individually:

```tsx
useWidgetContextExport(instance.id, {
  full: () => ({ /* ...widget_type: 'education.homeworkCalendar' */ }),
  rows: (rowId) => { /* return a snapshot for the matching task, else null */ },
});
```

Registration block:

```tsx
registerWidget<HomeworkCalendarConfig>({
  type: 'education.homeworkCalendar',
  titleKey: 'dashboard.widgets.homeworkCalendar.title',
  descriptionKey: 'dashboard.widgets.homeworkCalendar.description',
  category: 'personal',
  icon: CalendarCheck,
  component: HomeworkCalendarWidget,
  defaultConfig: { window: '2w', showCompleted: false },
  configSchema: HomeworkCalendarConfigSchema,
  defaultSize: { w: 4, h: 26 },
  minSize: { w: 3, h: 15 },
});
```

**Step 4: Run it and watch it pass**

```bash
cd web && pnpm vitest run src/pages/Dashboard/widgets/definitions/__tests__/HomeworkCalendarWidget.test.tsx
```

Expected: PASS, all eight cases.

**Step 5: Update `CHANGELOG.md` and commit**

```bash
cd .. && git add web/src/pages/Dashboard/widgets CHANGELOG.md
git commit -m "feat(web): add the household homework calendar widget"
```

---

## Task 6: The dashboard shell and the classic/custom switch

Upstream's `DashboardRouter` flips between `Dashboard.tsx` (classic) and
`DashboardCustom.tsx`. We keep the same shape but the classic branch is the
existing `WorkspaceOverview`, and `DashboardCustom` loses everything that
reads portfolio/watchlist/news data.

**Files:**

- Create: `web/src/pages/Dashboard/DashboardCustom.tsx`
- Modify: `web/src/pages/Dashboard/DashboardRouter.tsx`
- Create: `web/src/pages/Dashboard/__tests__/DashboardRouter.test.tsx`
- Create: `web/src/pages/Dashboard/widgets/framework/{useDashboardPrefs.ts,dashboardPrefsWriter.ts}`
- Create: `web/src/pages/Dashboard/widgets/framework/__tests__/useDashboardPrefs.test.tsx`

**Step 1: Copy the prefs layer**

```bash
cd /Users/seanlee/.config/superpowers/worktrees/langalpha/platform-core-migration
for f in useDashboardPrefs.ts dashboardPrefsWriter.ts; do
  git show origin/main:web/src/pages/Dashboard/widgets/framework/$f > web/src/pages/Dashboard/widgets/framework/$f
done
git show origin/main:web/src/pages/Dashboard/widgets/framework/__tests__/useDashboardPrefs.test.tsx > web/src/pages/Dashboard/widgets/framework/__tests__/useDashboardPrefs.test.tsx
```

**Step 2: Write `DashboardCustom` from scratch, not by copying**

Copying upstream's 403-line file would drag in `MarketDataWSProvider`, the four
finance dialogs, `ChatInputCard` and the market-view import that the boundary
test forbids. Write a slim version with this surface:

```tsx
interface DashboardCustomProps {
  mode: 'classic' | 'custom';
  onModeChange: (mode: 'classic' | 'custom') => void;
}

function CustomInner({ mode, onModeChange }: DashboardCustomProps) {
  const { t } = useTranslation();
  const { prefs, update, applyPreset, resetToDefault } = useDashboardPrefs();
  const [editMode, setEditMode] = useState(false);
  const [addOpen, setAddOpen] = useState(false);
  const [presetsOpen, setPresetsOpen] = useState(false);
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false);
  const [settingsFor, setSettingsFor] = useState<string | null>(null);
  // ...
}
```

Required behaviour:

- Wrap the body in `DashboardDataProvider` (the slim context from Task 7's
  prerequisite — create it here as a minimal provider exposing only
  `useDashboardContext()` with an empty-but-typed value if Task 7 has not run
  yet; Task 7 will extend it).
- Render `DashboardGrid` with `prefs`, `editMode`, `onChange` and
  `onOpenSettings`.
- A toolbar with: edit-mode toggle, "add widget" (opens `AddWidgetDialog`),
  "presets" (opens `PresetsDialog`), "reset" (opens `ConfirmDialog` with
  `resetToDefault`).
- Escape exits edit mode.
- `useScrollMemory(mainRef, 'page:dashboard-custom')`, as upstream does.
- No floating chat card, no portfolio/watchlist/news modals.

`ConfirmDialog` already exists locally at
`web/src/pages/Dashboard/components/ConfirmDialog.tsx`? No — it was deleted with
the rest. Create a small local confirm dialog inside `DashboardCustom` using
`@/components/ui/dialog`, or port
`origin/main:web/src/pages/Dashboard/components/ConfirmDialog.tsx` if it is
finance-free. Check the file first; if it only renders `title`/`message`/two
buttons, port it.

**Step 3: Rewrite `DashboardRouter.tsx`**

```tsx
import { useCallback } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useIsMobile } from '@/hooks/useIsMobile';
import { usePreferences } from '@/hooks/usePreferences';
import { queryKeys } from '@/lib/queryKeys';
import type { UserPreferences } from '@/types/api';
import WorkspaceOverview from './WorkspaceOverview';
import DashboardCustom from './DashboardCustom';
import { useDashboardPrefsWriter } from './widgets/framework/dashboardPrefsWriter';
import { migrateDashboardPrefs } from './widgets/framework/migrations';
import { getPreset } from './widgets/presets';
import { DASHBOARD_PREFS_VERSION, type DashboardPrefs } from './widgets/types';
import './widgets/index';
```

Keep upstream's three rules verbatim, because each fixes a real bug:

1. Mobile always renders classic and hides the toggle.
2. Absent/legacy prefs → classic, so nobody's first load after this ships
   silently rearranges their dashboard.
3. Cold-cache writes are refused (`if (isLoading) return;`) and the toggle
   re-reads the freshest cache before writing, so a cross-tab edit is not
   clobbered. The local branch already hit this class of bug once, in the
   ModelTab `other_preference` write.

The one change from upstream: `seed = getPreset('family-desk')` instead of
`'morning-brief'`, and `return <WorkspaceOverview />` for the classic branch.

**Step 4: Test the dispatcher**

Port `origin/main:web/src/pages/Dashboard/__tests__/DashboardRouter.test.tsx`
and adapt: assert mobile → overview, no prefs → overview, `mode: 'custom'` →
canvas, and that the first flip to custom seeds a non-empty widget list.

```bash
cd web && pnpm vitest run src/pages/Dashboard/__tests__/DashboardRouter.test.tsx
```

**Step 5: Commit**

```bash
cd .. && git add web/src/pages/Dashboard CHANGELOG.md
git commit -m "feat(web): make the widget canvas the dashboard with a classic fallback"
```

---

## Task 7: The surviving widget definitions

Four upstream definitions never touch portfolio or watchlist data. Porting them
makes the canvas immediately useful and proves the framework works with real
widgets beyond our own.

**Files:**

- Create: `web/src/pages/Dashboard/widgets/definitions/{AutomationsWidget.tsx,ConversationWidget.tsx,ConversationWidget.css,WorkspacePickerWidget.tsx,RecentThreadsWidget.tsx}`
- Modify: `web/src/pages/Dashboard/widgets/index.ts`

**Step 1: Copy**

```bash
cd /Users/seanlee/.config/superpowers/worktrees/langalpha/platform-core-migration
for f in AutomationsWidget.tsx ConversationWidget.tsx ConversationWidget.css WorkspacePickerWidget.tsx RecentThreadsWidget.tsx; do
  git show origin/main:web/src/pages/Dashboard/widgets/definitions/$f > web/src/pages/Dashboard/widgets/definitions/$f
done
```

**Step 2: Write the barrel by hand**

Upstream's `widgets/index.ts` imports 30 definitions including every TradingView
widget. Write ours with only what exists:

```ts
import './definitions/HomeworkCalendarWidget';
import './definitions/AutomationsWidget';
import './definitions/ConversationWidget';
import './definitions/WorkspacePickerWidget';
import './definitions/RecentThreadsWidget';

export { listWidgets, listWidgetsByCategory, getWidget } from './framework/WidgetRegistry';
```

`ConversationWidget` imports `../../hooks/useChatInput`. Port
`origin/main:web/src/pages/Dashboard/hooks/useChatInput.ts` too — its imports
(`chatSessionRestore`, `fileUpload`, `useWorkspaces`, `contextBus`) are all
finance-free and all present locally.

`RecentThreadsWidget` needs `@/pages/Dashboard/components/RowAttachButton`,
ported in Task 3.

**Step 3: Verify every registration resolves**

```bash
cd web && pnpm vitest run src/pages/Dashboard/widgets/framework/__tests__/migrations.test.ts
```

Expected: PASS — this loads `widgets/index` for its side effects, so a broken
import in any definition surfaces here.

**Step 4: Commit**

```bash
cd .. && git add web/src/pages/Dashboard CHANGELOG.md
git commit -m "feat(web): register the finance-free dashboard widgets"
```

---

## Task 8: The widget gallery and presets

**Files:**

- Create: `web/src/pages/Dashboard/widgets/framework/AddWidgetDialog.tsx`
- Create: `web/src/pages/Dashboard/widgets/framework/PresetsDialog.tsx`
- Create: `web/src/pages/Dashboard/widgets/framework/presets/Thumbnails.tsx`
- Create: `web/src/pages/Dashboard/widgets/framework/settings/*.tsx`
- Create: `web/src/pages/Dashboard/widgets/presets.ts`
- Create: `web/src/pages/Dashboard/widgets/framework/__tests__/{AddWidgetDialog.test.tsx,PresetsDialog.test.tsx,presets.test.ts,settings-atoms.test.tsx}`

**Step 1: Copy the gallery and settings widgets**

```bash
cd /Users/seanlee/.config/superpowers/worktrees/langalpha/platform-core-migration
mkdir -p web/src/pages/Dashboard/widgets/framework/presets web/src/pages/Dashboard/widgets/framework/settings
for f in AddWidgetDialog.tsx PresetsDialog.tsx; do
  git show origin/main:web/src/pages/Dashboard/widgets/framework/$f > web/src/pages/Dashboard/widgets/framework/$f
done
git show origin/main:web/src/pages/Dashboard/widgets/framework/presets/Thumbnails.tsx > web/src/pages/Dashboard/widgets/framework/presets/Thumbnails.tsx
for f in EnumField.tsx SettingsDoneButton.tsx SymbolField.tsx SymbolListField.tsx; do
  git show origin/main:web/src/pages/Dashboard/widgets/framework/settings/$f > web/src/pages/Dashboard/widgets/framework/settings/$f
done
```

`SymbolField` / `SymbolListField` are only used by finance widget settings.
Port them only if `configSchemas.ts` or another ported file references them;
otherwise skip them to keep the tree honest.

**Step 2: Write our presets**

Replace upstream's six finance presets with ours. Keep the exported shape
(`PresetId`, `PresetMeta`, `PRESETS_META`, `getPreset`, `makePrefs`,
`newWidgetId`) so `useDashboardPrefs`, `PresetsDialog` and `Thumbnails` compile
unchanged.

```ts
export type PresetId = 'family-desk' | 'homework-focus';
```

- `family-desk` (default, `popular: true`) — homework calendar (w4 h26, right
  rail), recent threads (w8 h20), workspace picker (w4 h16), automations
  (w4 h20), conversation (w8 h13).
- `homework-focus` — homework calendar wide at the top (w12 h24), conversation
  below, recent threads on the right.

Locale keys follow `dashboard.widgets.presets.<id>.<field>`.

**Step 3: Reduce `Thumbnails.tsx`**

The ported file is 712 lines, mostly `TYPE_VISUALS` entries and glyphs for
finance widget types. Keep the renderer (`PresetLayoutThumbnail`,
`PresetThumbnail`, the cell geometry) and:

- Replace `TYPE_VISUALS` with our five types plus
  `'education.homeworkCalendar'`.
- Delete glyph branches for `markets.*`, `news.*`, `tv.*`, `watchlist.*`,
  `portfolio*`, `insight.*`, `calendar.earnings`. Keep the default empty-state
  fallback.

**Step 4: Run the gallery tests**

```bash
cd web && pnpm vitest run src/pages/Dashboard/widgets/framework/__tests__/AddWidgetDialog.test.tsx src/pages/Dashboard/widgets/framework/__tests__/PresetsDialog.test.tsx src/pages/Dashboard/widgets/framework/__tests__/presets.test.ts
```

`presets.test.ts` enumerates upstream's preset ids — rewrite it against
`family-desk` / `homework-focus`, and add one assertion that is the point of
this whole phase: **every widget type referenced by every preset is
registered.** That test is what stops a preset from shipping a blank cell.

**Step 5: Commit**

```bash
cd .. && git add web/src/pages/Dashboard CHANGELOG.md
git commit -m "feat(web): add the widget gallery and the family presets"
```

---

## Task 9: Locale catalogs

Every `t('dashboard.widgets.*')` key the ported code writes must exist in both
catalogs, or `keys.test.ts` fails.

**Files:**

- Modify: `web/src/locales/en-US.json`, `web/src/locales/zh-CN.json`

**Step 1: Copy the framework subtree**

```bash
cd /Users/seanlee/.config/superpowers/worktrees/langalpha/platform-core-migration
git show origin/main:web/src/locales/en-US.json > /tmp/up-en.json
git show origin/main:web/src/locales/zh-CN.json > /tmp/up-zh.json
```

Merge `dashboard.widgets` from `/tmp/up-*.json` into the local catalogs, then:

- Drop the `tv*`, `presets` and `embedFallback` keys (no consumer after Task 8).
- Replace `presets` with `dashboard.widgets.presets.family-desk.*` and
  `.homework-focus.*`.
- Add `dashboard.widgets.homeworkCalendar.*`: `title`, `description`, `empty`,
  `emptyHint`, and the bucket labels `bucket_today`, `bucket_tomorrow`,
  `bucket_thisWeek`, `bucket_nextWeek`, `bucket_later`, plus the stat labels
  `stat_today`, `stat_week`, `stat_overdue`, `stat_completed`, and
  `settings.window`, `settings.window_1w`, `settings.window_2w`,
  `settings.window_1m`, `settings.showCompleted`.
- Do **not** carry over `dashboard.widgets.earningsCalendar.*`,
  `portfolio*`, `watchlist*`, `news*`, `markets*`, `insight*`, `chart*`.

Local `dashboard.overview.*` keys stay untouched — classic mode still uses them.

**Step 2: Run the parity test**

```bash
cd web && pnpm vitest run src/locales/__tests__/keys.test.ts
```

Expected: PASS. The failure mode is a list of unresolved keys with file and
line; fix each by adding it to both catalogs.

**Step 3: Commit**

```bash
cd .. && git add web/src/locales CHANGELOG.md
git commit -m "feat(web): add the dashboard canvas locale catalog"
```

---

## Task 10: Boundary guards and full verification

**Files:**

- Create: `web/src/pages/Dashboard/widgets/__tests__/noFinanceWidgets.test.ts`

**Step 1: Write the guard**

```ts
import { describe, it, expect } from 'vitest';
import '../index';
import { listWidgets } from '../framework/WidgetRegistry';

const RETIRED_TYPES = [
  'markets.overview', 'markets.miniChartGrid', 'news.feed', 'insight.brief',
  'calendar.earnings', 'portfolio.holdings', 'watchlist.list',
  'personal.portfolioWatchlist', 'chart.symbol',
];

describe('dashboard widget registry', () => {
  it('registers no retired finance widget', () => {
    const types = listWidgets().map((w) => w.type);
    expect(types.filter((t) => RETIRED_TYPES.includes(t))).toEqual([]);
    expect(types.filter((t) => t.startsWith('tv.'))).toEqual([]);
  });
});
```

Run it, confirm it passes, then temporarily add `'news.feed'` to the registry
import list and confirm it fails before reverting.

**Step 2: Full dashboard slice**

```bash
cd web && pnpm vitest run src/pages/Dashboard
```

**Step 3: Boundary guards**

```bash
cd web && pnpm vitest run src/__tests__ src/locales
```

Expected: `genericFinanceDependencyBoundary` and `dashboardBoundary` both pass.
If either fails, a ported file references `pages/MarketView`, `lib/bars`,
`lib/marketUtils`, or something outside `pages/Dashboard` imports `Dashboard/`.

**Step 4: Whole frontend suite**

```bash
cd web && pnpm vitest run
pnpm typecheck && pnpm lint && pnpm build
```

Baseline to match: 237 files / 2271 tests, 0 lint errors. Expect the file and
test counts to rise. The `react-refresh/only-export-components` warning count
must not grow — keep new module-level constants private where possible.

**Step 5: Manual check on the running dev server**

```bash
cd web && pnpm dev --host 0.0.0.0 --port 5177
```

Backend is expected on 18000 against Postgres 15432 / Redis 16379 / MinIO 19000
(`langalpha-platform-core-migration` compose stack). Open
`http://localhost:5177/dashboard` and confirm:

1. First load shows the canvas with the family preset.
2. The homework calendar renders real household tasks, nearest first.
3. Dragging, resizing and reloading preserves the layout.
4. "+" on the calendar publishes a context chip into the chat input.
5. The classic toggle returns `WorkspaceOverview` intact.

**Step 6: Commit**

```bash
cd .. && git add web/src/pages/Dashboard CHANGELOG.md
git commit -m "test(web): guard the canvas against the retired finance widgets"
```

---

## Deferred on purpose

- Finance widget removal (bundles → APIs → tools → skills → frontend →
  migrations) — a separate phase, unchanged by this plan.
- A dedicated calendar *grid* view (month grid) — the bucket list answers
  "what is coming up and where does it stand"; a month view is a different
  question and can be added as a second widget later.
- Student-facing variant — the backend already narrows a student's view to
  their own tasks, and this plan deliberately does not add a separate
  component for it.
