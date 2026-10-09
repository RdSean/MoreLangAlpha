# NASA Mission Theme Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a globally switchable light NASA Mission theme while preserving Quiet Workspace, removing dark/auto theme choices, and restyling the textbook learning experience across web and mobile layouts.

**Architecture:** Keep all behavior, routes, API calls, SSE, React Query, workspace, and Docker boundaries unchanged. Move visual differences into `ThemeContext` and semantic CSS tokens, then migrate shared shell primitives and high priority education surfaces to those tokens. NASA Mission is selected through `data-theme="nasa"`; Quiet Workspace remains the compatibility theme under `data-theme="quiet"`.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind 3, CSS custom properties, Radix UI primitives, Vitest, Testing Library, Playwright.

---

### Task 1: Replace the three-state theme model with Quiet/NASA migration

**Files:**
- Modify: `web/src/contexts/ThemeContext.tsx`
- Modify: `web/src/pages/Settings/panels/UserInfoTab.tsx`
- Modify: `web/src/locales/en-US.json`
- Modify: `web/src/locales/zh-CN.json`
- Create: `web/src/contexts/__tests__/ThemeContext.test.tsx`
- Modify: theme-aware tests that mock `useTheme`, including `web/src/lib/__tests__/themeTokens.test.ts`, `web/src/components/ui/__tests__/stepper-track.test.tsx`, and affected education/chat tests

**Step 1: Write the failing migration tests**

Cover these cases in `ThemeContext.test.tsx`:

```tsx
it('defaults to quiet and stamps data-theme=quiet', () => {})
it('accepts nasa and persists it without a reload', () => {})
it('maps legacy light, dark, auto, and unknown values to quiet', () => {})
it('does not consult prefers-color-scheme', () => {})
```

Update mocks so `theme` and `preference` use `quiet | nasa` rather than `light | dark`.

**Step 2: Run the focused tests to verify they fail**

Run: `cd web && pnpm vitest run src/contexts/__tests__/ThemeContext.test.tsx src/lib/__tests__/themeTokens.test.ts`

Expected: FAIL because the existing context still exposes `light | dark | auto` and listens to the OS color scheme.

**Step 3: Implement the minimal theme migration**

- Change public theme types to `quiet | nasa`.
- Read `localStorage.theme`; accept only `quiet` and `nasa`, mapping all old values to `quiet`.
- Remove media-query listeners and the three-state toggle.
- Stamp `data-theme` with the selected theme and always use the light favicon.
- Replace the settings control with two accessible buttons labeled Quiet Workspace and NASA Mission.
- Add English and Chinese labels/descriptions; remove dark/auto labels from the rendered settings path.

**Step 4: Run focused tests**

Run: `cd web && pnpm vitest run src/contexts/__tests__/ThemeContext.test.tsx src/lib/__tests__/themeTokens.test.ts src/pages/Settings/__tests__/Settings.searchProvider.test.tsx`

Expected: PASS.

**Step 5: Commit**

```bash
git add web/src/contexts/ThemeContext.tsx web/src/contexts/__tests__/ThemeContext.test.tsx web/src/pages/Settings/panels/UserInfoTab.tsx web/src/locales/en-US.json web/src/locales/zh-CN.json web/src/lib/__tests__/themeTokens.test.ts web/src/components/ui/__tests__/stepper-track.test.tsx
git commit -m "feat(web): add quiet and nasa theme preferences"
```

### Task 2: Add the NASA Mission semantic token layer

**Files:**
- Modify: `web/src/styles/tokens.css`
- Modify: `web/src/index.css`
- Modify: `web/tailwind.config.js`
- Modify: `DESIGN.md`
- Modify: `web/src/styles/__tests__/tokenRefs.test.ts`
- Create: `web/src/styles/__tests__/nasaTokens.test.ts`

**Step 1: Write failing token contract tests**

Assert that `[data-theme="nasa"]` defines the paper ground, identity stripe colors, action red, warning stripe pattern, compact radius, and NASA label font role. Assert that Quiet Workspace retains its existing light values and that every referenced `--color-*` variable is declared.

**Step 2: Run the token tests to verify they fail**

Run: `cd web && pnpm vitest run src/styles/__tests__/nasaTokens.test.ts src/styles/__tests__/tokenRefs.test.ts`

Expected: FAIL because NASA tokens and the new theme selector do not exist.

**Step 3: Implement shared and theme-specific tokens**

- Preserve current Quiet Workspace light values under `[data-theme="quiet"]`.
- Add NASA Mission values for page/canvas/card/input/elevated surfaces, text, borders, action red, four identity colors, focus ring, status roles, `--font-label`, `--radius-control`, `--radius-panel`, and `--warning-stripe`.
- Keep Chinese body typography unchanged and use a Helvetica/Arial/system sans fallback for Latin UI; keep the existing monospace stack for labels and codes.
- Replace hard-coded default selectors that assume `data-theme="light"` with the two light theme selectors where needed.
- Add `nasa-*` utilities only when a semantic token cannot be expressed through existing Tailwind color roles; do not add one-off hex utilities.
- Update `DESIGN.md` to document the two light themes and NASA accent discipline.

**Step 4: Run token and build checks**

Run: `cd web && pnpm vitest run src/styles/__tests__/nasaTokens.test.ts src/styles/__tests__/tokenRefs.test.ts && pnpm typecheck`

Expected: PASS with no undeclared token references.

**Step 5: Commit**

```bash
git add web/src/styles/tokens.css web/src/index.css web/tailwind.config.js web/src/styles/__tests__/tokenRefs.test.ts web/src/styles/__tests__/nasaTokens.test.ts DESIGN.md
git commit -m "feat(web): add NASA Mission design tokens"
```

### Task 3: Restyle the shared app shell and primitives

**Files:**
- Modify: `web/src/App.css`
- Modify: `web/src/components/Sidebar/Sidebar.css`
- Modify: `web/src/components/Sidebar/AppSidebar.tsx`
- Modify: `web/src/components/BottomTabBar/BottomTabBar.css`
- Modify: shared primitive styles under `web/src/components/ui/`, especially `button.tsx`, `card.tsx`, `dialog.tsx`, `input.tsx`, `textarea.tsx`, `dropdown-menu.tsx`, `popover.tsx`, and `mobile-bottom-sheet.tsx`
- Modify: `web/src/components/brand/LangAlphaMark.tsx` and the selected logo/favicons if the current asset has a dark-only dependency
- Create or extend: shell component tests under `web/src/components/Sidebar/__tests__/` and `web/src/components/BottomTabBar/__tests__/`

**Step 1: Add failing shell assertions**

Cover NASA theme rendering for the sidebar task badge, identity stripe, active navigation marker, mobile bottom bar, and minimum button hit area. Keep route and collapse behavior assertions unchanged.

**Step 2: Run focused shell tests**

Run: `cd web && pnpm vitest run src/components/Sidebar src/components/BottomTabBar`

Expected: FAIL for the new NASA-specific structure/classes or styles.

**Step 3: Implement the shell treatment**

- Add a reusable circular task badge with text fallback and an identity stripe built from the four muted colors.
- Keep the existing sidebar width, resize handle, collapse persistence, route matching, and keyboard navigation.
- Replace pill-like mobile navigation surfaces with a flat bordered task bar and red active marker.
- Route all shared controls through semantic tokens, reduce default radii to the NASA compact values, and keep focus rings neutral.
- Add low-opacity texture pseudo-elements only to large shell surfaces; ensure `pointer-events: none` and no text overlap.
- Keep every icon control at least 44px on mobile.

**Step 4: Run focused tests and lint**

Run: `cd web && pnpm vitest run src/components/Sidebar src/components/BottomTabBar && pnpm eslint src/components/Sidebar src/components/BottomTabBar src/components/ui`

Expected: PASS; any existing advisory warnings are recorded without weakening type or build gates.

**Step 5: Commit**

```bash
git add web/src/App.css web/src/components/Sidebar web/src/components/BottomTabBar web/src/components/ui web/src/components/brand/LangAlphaMark.tsx
git commit -m "feat(web): apply NASA Mission shell styling"
```

### Task 4: Restyle the textbook learning session for desktop and mobile

**Files:**
- Modify: `web/src/pages/Education/StudentTextbookLearningPage.tsx`
- Modify: `web/src/pages/Education/TextbookWorkbenchPage.css`
- Modify: `web/src/pages/Education/components/BookNavigator.tsx`
- Modify: `web/src/pages/Education/components/BookNavigator.css`
- Modify: `web/src/pages/Education/components/BookReader.tsx`
- Modify: `web/src/pages/Education/components/LessonConversation.tsx`
- Modify: `web/src/pages/Education/components/LessonConversation.css`
- Modify: `web/src/pages/Education/components/PersonalNotebook.tsx`
- Modify: `web/src/pages/Education/components/BookLessonExport.tsx`
- Modify: `web/src/pages/Education/__tests__/StudentTextbookLearningPage.test.tsx`, `BookNavigator.test.tsx`, `LessonConversation.test.tsx`, and `BookLessonExport.test.tsx`

**Step 1: Write failing interaction and responsive assertions**

Add assertions for:

- NASA task labels and the circular student/task badge.
- Current knowledge point and chapter numbering remaining accessible as text.
- Desktop three-region structure and mobile single-column structure.
- Directory, notes, question input, export, loading, error, and blocked states remaining reachable.
- Minimum mobile action dimensions and no horizontal overflow in the rendered shell.

**Step 2: Run the education tests to verify failures**

Run: `cd web && pnpm vitest run src/pages/Education/__tests__/StudentTextbookLearningPage.test.tsx src/pages/Education/__tests__/BookNavigator.test.tsx src/pages/Education/__tests__/LessonConversation.test.tsx src/pages/Education/__tests__/BookLessonExport.test.tsx`

Expected: FAIL only for the new NASA structure and class/token expectations; existing data-flow assertions should remain green.

**Step 3: Implement the learning-session treatment**

- Add a task header with textbook code, knowledge-point label, return control, and circular task badge while preserving URL search state and query behavior.
- Style the navigator as a chapter manifest with numbered rows, identity-colored status markers, search, and a red current edge marker.
- Keep reader prose at a readable max width with paper surfaces, fine rules, source/material metadata, and monospaced NASA labels.
- Style conversation turns with a clear question/answer split, small mission metadata, and an input bar that respects safe areas.
- Style notebook counts and saved materials as compact paper panels with labels and accessible form fields.
- Use warning stripes only for processing/error/blocked states and keep action red for the decisive action or status.
- Preserve Dialog/Sheet behavior on mobile and add bottom padding so fixed input/navigation bars never hide content.

**Step 4: Run education tests and typecheck**

Run: `cd web && pnpm vitest run src/pages/Education/__tests__/StudentTextbookLearningPage.test.tsx src/pages/Education/__tests__/BookNavigator.test.tsx src/pages/Education/__tests__/LessonConversation.test.tsx src/pages/Education/__tests__/BookLessonExport.test.tsx && pnpm typecheck`

Expected: PASS.

**Step 5: Commit**

```bash
git add web/src/pages/Education/StudentTextbookLearningPage.tsx web/src/pages/Education/TextbookWorkbenchPage.css web/src/pages/Education/components/BookNavigator.tsx web/src/pages/Education/components/BookNavigator.css web/src/pages/Education/components/BookReader.tsx web/src/pages/Education/components/LessonConversation.tsx web/src/pages/Education/components/LessonConversation.css web/src/pages/Education/components/PersonalNotebook.tsx web/src/pages/Education/components/BookLessonExport.tsx web/src/pages/Education/__tests__
git commit -m "feat(education): restyle textbook learning as NASA Mission"
```

### Task 5: Migrate remaining global surfaces and remove dark-path assumptions

**Files:**
- Modify: CSS and component files found by the audit in `web/src/pages/ChatAgent`, `web/src/pages/Documents`, `web/src/pages/Automations`, `web/src/pages/Settings`, `web/src/pages/Dashboard`, `web/src/pages/Plugins`, and `web/src/pages/Login`
- Modify: theme-aware viewers and canvas helpers such as `web/src/lib/themeTokens.ts`, `web/src/pages/ChatAgent/components/viewers/CodeEditor.tsx`, and related CSS
- Modify: affected tests that assert `light/dark` theme values

**Step 1: Create an audit list**

Run:

```bash
cd web
rg -n "dark:|data-theme=['\"](light|dark)|theme === ['\"](light|dark)|var\(--color-[^)]+, *#|linear-gradient|box-shadow|rounded-(lg|xl|2xl|3xl)" src
```

Classify each match as token migration, intentional content styling, or a code/editor palette that needs an explicit Quiet/NASA light mapping.

**Step 2: Add regression assertions for representative pages**

Extend existing page tests to render under both `data-theme="quiet"` and `data-theme="nasa"` and assert that key surfaces remain readable and that no dark-only branch is selected.

**Step 3: Migrate styles**

- Replace direct surface/text/border values with semantic tokens.
- Replace dark-only branches with a light token mapping or remove them when they only served the deleted theme.
- Keep code syntax highlighting, PDF/print output, charts, and image assets legible in both light themes.
- Preserve page-specific layouts and API behavior.

**Step 4: Run broad frontend checks**

Run: `cd web && pnpm test && pnpm typecheck && pnpm lint`

Expected: tests and typecheck pass; lint may report existing advisory warnings, but no new errors are introduced.

**Step 5: Commit**

```bash
git add web/src/pages web/src/lib web/src/components web/src/styles
git commit -m "refactor(web): remove dark theme assumptions"
```

### Task 6: Verify build, browser behavior, and document the release

**Files:**
- Modify: `CHANGELOG.md`
- Modify: relevant Playwright fixtures/specs under `web/e2e/` if selectors need stable NASA labels
- Create: `docs/plans/2026-10-10-nasa-mission-theme-verification.md` only if the repository's existing verification pattern requires a separate record

**Step 1: Run the production gate**

Run: `cd web && pnpm build`

Expected: TypeScript, Vite build, and critical-path budget pass.

**Step 2: Run the LAN-visible dev server**

Run: `cd web && pnpm dev --host 0.0.0.0 --port 5177`

Verify the local and LAN URL return HTTP 200. Do not start or modify Docker services for this frontend-only change.

**Step 3: Run browser checks**

Run the existing education and shell Playwright specs, adding only stable semantic selectors where needed. Check 375px, 768px, 1024px, and 1440px viewports; switch Quiet Workspace/NASA Mission; inspect textbook directory, reader, notebook, conversation, export, loading, error, and blocked states.

**Step 4: Update the Chinese changelog**

Add a dated entry describing the two light themes, NASA Mission visual system, dark/auto preference migration, responsive textbook session treatment, and validation results. Do not claim real model, PDF, or backend behavior was revalidated unless it was actually run.

**Step 5: Commit verification documentation**

```bash
git add CHANGELOG.md web/e2e docs/plans
git commit -m "docs: record NASA Mission theme verification"
```

Expected: final `git status` shows only the user's pre-existing `docs/plans/2026-10-03-textbook-business-activity.md` modification and the untracked textbook PDF.
