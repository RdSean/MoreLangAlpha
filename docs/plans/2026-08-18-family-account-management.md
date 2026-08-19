# 家庭账户管理 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 `/settings` 下为家长提供学生账号创建、Flash 空间状态查看和只读对话浏览能力，并由后端强制执行同家庭授权。

**Architecture:** 复用现有本地 Cookie 会话、`education_memberships` 家庭关系、按学生用户 ID 确定的 Flash workspace 以及现有线程回放投影。新增家庭专用只读 API，不改变通用 workspace/thread 的拥有者授权和写接口；React Settings 以 `tab=family` 承载列表和详情，React Query 管理列表/空间/线程缓存，SSE 只用于只读回放。

**Tech Stack:** Python 3.13+, FastAPI, async psycopg3, React 19, TypeScript, React Query, Tailwind/shadcn/ui, Vitest, Ruff.

---

### Task 1: Add the family authorization and read-model service

**Files:**
- Modify: `src/server/database/auth_accounts.py`
- Create: `src/server/services/family_accounts.py`
- Create: `tests/unit/server/services/test_family_accounts.py`

**Step 1: Write the failing tests**

Add tests for:

- a parent can resolve a student in the same household;
- a student or cross-household user is rejected;
- resolving a student returns/ensures only that student's deterministic Flash workspace;
- a thread is accepted only when its owner and workspace match the target student.

Use async mocks at the database boundary; assert the service performs the relationship check before returning workspace/thread data.

**Step 2: Run the focused tests to verify RED**

Run: `uv run pytest tests/unit/server/services/test_family_accounts.py -q`

Expected: FAIL because the service and authorization helpers do not yet exist.

**Step 3: Implement the minimal service**

- Add a small database helper that returns the parent household and verifies the target student membership under a row/transaction-safe query.
- Add `list_family_children`, `get_family_child_workspace`, `list_family_child_threads`, and `get_family_child_replay_data` service functions.
- Call `get_or_create_flash_workspace(student_user_id)` only after membership authorization.
- Reuse `get_workspace_threads` and `get_replay_thread_data`; reject mismatched owner/workspace IDs before projecting data.
- Keep errors typed so routes can map not-found/forbidden/conflict cases without leaking cross-household existence.

**Step 4: Run the focused tests to verify GREEN**

Run: `uv run pytest tests/unit/server/services/test_family_accounts.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/database/auth_accounts.py src/server/services/family_accounts.py tests/unit/server/services/test_family_accounts.py
git commit -m "feat: add family account authorization service"
```

### Task 2: Expose parent-only account, workspace, thread, and replay APIs

**Files:**
- Modify: `src/server/app/auth.py`
- Modify: `src/server/app/setup.py` only if router registration is not already covered by the auth router
- Modify: `tests/unit/server/app/test_local_auth.py`

**Step 1: Write the failing route tests**

Cover these contracts:

```python
async def test_parent_can_list_children_with_flash_summary(client):
    response = await client.get("/api/v1/auth/children")
    assert response.status_code == 200

async def test_parent_can_list_child_threads_but_student_cannot(client):
    response = await client.get("/api/v1/auth/children/child-user/threads")
    assert response.status_code == 200
```

Also test `403` for a student/cross-household caller, `404` for a missing thread, and that the replay endpoint emits `replay_done` while never calling a message mutation.

**Step 2: Run the focused route tests to verify RED**

Run: `uv run pytest tests/unit/server/app/test_local_auth.py -q`

Expected: FAIL because the new GET/list/replay routes are absent.

**Step 3: Implement the routes**

- Keep existing `POST /api/v1/auth/children` unchanged for creation.
- Add `GET /api/v1/auth/children` returning student-safe fields and a `flash_workspace` summary (`workspace_id`, `name`, `status`, `updated_at`).
- Add `GET /api/v1/auth/children/{student_user_id}/workspace` and paginated `GET .../threads` with existing thread list shape.
- Add `GET .../threads/{thread_id}/replay` as a read-only `StreamingResponse`, reusing the existing checkpoint/SSE replay builders and emitting only replay events plus `replay_done`.
- Map service authorization failures to `403`/`404`; do not add front-end-only checks or extra credentials.
- Ensure path ordering keeps `/children` from being captured by the parameter route.

**Step 4: Run the route tests to verify GREEN**

Run: `uv run pytest tests/unit/server/app/test_local_auth.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/app/auth.py tests/unit/server/app/test_local_auth.py
git commit -m "feat: expose parent family account read APIs"
```

### Task 3: Add the Settings API layer, types, and React Query hooks

**Files:**
- Create: `web/src/pages/Settings/api.ts`
- Create: `web/src/pages/Settings/queries.ts`
- Modify: `web/src/pages/Settings/panels/types.ts` if shared settings types belong there
- Modify: `web/src/lib/queryKeys.ts`
- Create: `web/src/pages/Settings/__tests__/familyAccountsApi.test.ts`

**Step 1: Write the failing API/query tests**

Assert the API layer calls the family endpoints with the correct path, pagination, and cookie-backed client, and that query keys distinguish the child ID and thread page.

**Step 2: Run the focused frontend tests to verify RED**

Run: `cd web && pnpm vitest run src/pages/Settings/__tests__/familyAccountsApi.test.ts`

Expected: FAIL because the API functions and query keys are absent.

**Step 3: Implement the API layer**

- Define `FamilyChild`, `FlashWorkspaceSummary`, and `FamilyThread` interfaces with only safe fields.
- Add `listFamilyChildren`, `getFamilyChildWorkspace`, `listFamilyChildThreads`, and `streamFamilyChildThreadReplay`.
- Use the existing `api` client for JSON calls and existing `streamFetch` for the read-only SSE replay path.
- Add hierarchical `queryKeys.settings.family` keys so invalidating children refreshes summaries without clearing unrelated settings.

**Step 4: Run the focused tests to verify GREEN**

Run: `cd web && pnpm vitest run src/pages/Settings/__tests__/familyAccountsApi.test.ts`

Expected: PASS.

**Step 5: Commit**

```bash
git add web/src/pages/Settings/api.ts web/src/pages/Settings/queries.ts web/src/lib/queryKeys.ts web/src/pages/Settings/__tests__/familyAccountsApi.test.ts
git commit -m "feat: add family account frontend data layer"
```

### Task 4: Build the parent account list and create-child flow

**Files:**
- Create: `web/src/pages/Settings/panels/FamilyAccountsTab.tsx`
- Create: `web/src/pages/Settings/panels/FamilyAccountsTab.css` only if existing Settings CSS cannot express the responsive layout
- Modify: `web/src/pages/Settings/Settings.tsx`
- Modify: `web/src/pages/Settings/Settings.css`
- Create: `web/src/pages/Settings/__tests__/FamilyAccountsTab.test.tsx`

**Step 1: Write the failing UI tests**

Cover:

- a parent sees the “家庭账户” tab and child list;
- the create dialog submits username/name/password and refreshes the list;
- `409` keeps the form open with an account-conflict message;
- a student sees a no-permission state and no create control;
- each child row shows Flash status and a “查看对话” action.

**Step 2: Run the focused UI tests to verify RED**

Run: `cd web && pnpm vitest run src/pages/Settings/__tests__/FamilyAccountsTab.test.tsx`

Expected: FAIL because the tab and component are absent.

**Step 3: Implement the UI**

- Add a Settings tab URL-synced as `tab=family`, following the existing `userInfo/preferences/model/experiments` pattern.
- Gate the tab by `useAuth().member?.role`; this is presentation only and never replaces server authorization.
- Build a compact list with name, username, Flash status, last updated time, and a single primary “查看对话” action.
- Add a dialog with visible labels, password helper text, disabled/loading submit state, inline error feedback, and accessible close behavior.
- On successful creation, invalidate the family children query and reset the form; do not add delete, rename, reset-password, or workspace-name controls.
- Preserve responsive scrolling and the existing Quiet Workspace tokens.

**Step 4: Run the focused UI tests to verify GREEN**

Run: `cd web && pnpm vitest run src/pages/Settings/__tests__/FamilyAccountsTab.test.tsx`

Expected: PASS.

**Step 5: Commit**

```bash
git add web/src/pages/Settings/Settings.tsx web/src/pages/Settings/Settings.css web/src/pages/Settings/panels/FamilyAccountsTab.tsx web/src/pages/Settings/__tests__/FamilyAccountsTab.test.tsx
git commit -m "feat: add family account settings panel"
```

### Task 5: Add the read-only child Flash conversation view

**Files:**
- Create: `web/src/pages/Settings/panels/FamilyChildConversations.tsx`
- Create: `web/src/pages/Settings/__tests__/FamilyChildConversations.test.tsx`
- Modify: `web/src/pages/Settings/Settings.tsx`
- Modify: `web/src/pages/Settings/Settings.css`

**Step 1: Write the failing UI tests**

Assert that selecting a child:

- loads workspace status and paginated thread metadata;
- shows an empty state when there are no threads;
- renders user/assistant text from replay events;
- shows retry/error states;
- contains no textbox, send button, edit, delete, or share controls.

**Step 2: Run the focused UI tests to verify RED**

Run: `cd web && pnpm vitest run src/pages/Settings/__tests__/FamilyChildConversations.test.tsx`

Expected: FAIL because the read-only detail view is absent.

**Step 3: Implement the read-only view**

- Keep navigation within `tab=family&student=<id>` so browser back/deep links work without adding a new primary route.
- Fetch workspace summary and threads through the Settings query layer.
- Use the SSE parser only to coalesce `user_message` and assistant `message_chunk` text into display bubbles; ignore tool/provenance/task controls in this surface.
- Provide a back link to the child list, loading skeleton/text, empty state, retry action, and clear read-only labeling.
- Do not import or embed `ChatAgent`, its composer, or mutation helpers.

**Step 4: Run the focused UI tests to verify GREEN**

Run: `cd web && pnpm vitest run src/pages/Settings/__tests__/FamilyChildConversations.test.tsx`

Expected: PASS.

**Step 5: Commit**

```bash
git add web/src/pages/Settings/Settings.tsx web/src/pages/Settings/Settings.css web/src/pages/Settings/panels/FamilyChildConversations.tsx web/src/pages/Settings/__tests__/FamilyChildConversations.test.tsx
git commit -m "feat: add read-only child conversation view"
```

### Task 6: Verify the complete feature and hand off

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Run backend focused tests**

Run: `uv run pytest tests/unit/server/services/test_family_accounts.py tests/unit/server/app/test_local_auth.py -q`

Expected: PASS.

**Step 2: Run frontend focused tests and type checks**

Run: `cd web && pnpm vitest run src/pages/Settings/__tests__/familyAccountsApi.test.ts src/pages/Settings/__tests__/FamilyAccountsTab.test.tsx src/pages/Settings/__tests__/FamilyChildConversations.test.tsx && pnpm typecheck`

Expected: PASS.

**Step 3: Run repository checks**

Run: `uv run ruff check src/` and `cd web && pnpm build`

Expected: PASS.

**Step 4: Verify the LAN-visible frontend**

Run: `cd web && pnpm dev --host 0.0.0.0 --port 5177`

Verify the Settings page can be reached on the configured host and that a parent can open the family tab, create a child, open the child detail, and read a thread without a composer.

**Step 5: Record the completed change and commit**

Add a concise Chinese changelog entry describing the new parent-only account management and read-only Flash conversation view, then commit only the scoped feature files.

```bash
git add CHANGELOG.md
git commit -m "docs: record family account management"
```
