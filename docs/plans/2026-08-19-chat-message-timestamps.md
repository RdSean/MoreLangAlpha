# Chat Session And Message Timestamps Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Display the existing conversation start time in the chat header and
the existing send time below every user and assistant message.

**Architecture:** Reuse `getThread` from the existing API facade to read
`conversation_threads.created_at` in `ChatView`; do not add an endpoint or
change persistence. Reuse each `MessageRecord.timestamp` in `MessageBubble`,
formatted by the shared locale-aware date formatter.

**Tech Stack:** React 19, TypeScript, react-i18next, Vitest, Testing Library,
Tailwind utility classes, existing `@/lib/format` helpers.

---

### Task 1: Add failing tests for the header timestamp

**Files:**
- Modify: `web/src/pages/ChatAgent/components/__tests__/ChatView.mount.test.tsx`

**Step 1: Mock the existing thread lookup**

Extend the existing API barrel mock with `getThread`, returning a thread row
whose `created_at` is a fixed ISO timestamp.

**Step 2: Add the expectation**

Mount `ChatView` and assert a `time[data-testid="thread-created-at"]` element
contains the formatted start time and has the matching `dateTime` value.

**Step 3: Run the focused test**

Run: `pnpm exec vitest run src/pages/ChatAgent/components/__tests__/ChatView.mount.test.tsx`

Expected: FAIL because ChatView does not yet render the element.

### Task 2: Add failing tests for per-message timestamps

**Files:**
- Modify: `web/src/pages/ChatAgent/components/messageList/__tests__/MessageBubble.userQoL.test.tsx`

**Step 1: Add user and assistant cases**

Use fixed `Date` values and assert a semantic `time[data-testid="message-timestamp"]`
with the corresponding `dateTime` value for each role.

**Step 2: Cover legacy absence**

Render a message without a timestamp and assert no message timestamp element is
present.

**Step 3: Run the focused test**

Run: `pnpm exec vitest run src/pages/ChatAgent/components/messageList/__tests__/MessageBubble.userQoL.test.tsx`

Expected: FAIL because MessageBubble does not yet render message times.

### Task 3: Implement the header timestamp

**Files:**
- Modify: `web/src/pages/ChatAgent/components/ChatView.tsx`
- Modify: `web/src/locales/en-US.json`
- Modify: `web/src/locales/zh-CN.json`

**Step 1: Fetch the existing thread metadata**

Import `getThread`, track the resolved non-`__default__` id, and fetch its
`created_at` with cancellation handling. Ignore lookup failures so chat remains
usable.

**Step 2: Render the metadata**

Use `createDateFormatter({ dateStyle: 'medium', timeStyle: 'short' })` and
render a localized label plus `<time data-testid="thread-created-at">` in the
top bar when the value is valid.

**Step 3: Run the header test**

Run the Task 1 Vitest command and expect PASS.

### Task 4: Implement per-message timestamps

**Files:**
- Modify: `web/src/pages/ChatAgent/components/messageList/MessageBubble.tsx`

**Step 1: Format the existing message date**

Use `createDateFormatter({ hour: 'numeric', minute: '2-digit' })` and guard
against absent or invalid values.

**Step 2: Render the semantic time**

Place the short localized time immediately below the normal message content,
aligned with the message role and styled with the tertiary text token.

**Step 3: Run the message test**

Run the Task 2 Vitest command and expect PASS.

### Task 5: Verify, document, and commit

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Run focused tests**

Run both timestamp test files and confirm zero failures.

**Step 2: Run frontend checks**

Run `pnpm lint` and `pnpm build` from `web/` (or the repository's equivalent
frontend checks) and inspect all output.

**Step 3: Update the changelog**

Add a concise Chinese entry describing the two display additions.

**Step 4: Inspect the diff**

Confirm only timestamp feature files are staged; preserve the pre-existing
`src/ptc_agent/agent/prompts/templates/flash_system.md.j2` change.

**Step 5: Commit**

```bash
git add docs/plans/2026-08-19-chat-message-timestamps-design.md \
  docs/plans/2026-08-19-chat-message-timestamps.md \
  web/src/pages/ChatAgent/components/ChatView.tsx \
  web/src/pages/ChatAgent/components/messageList/MessageBubble.tsx \
  web/src/pages/ChatAgent/components/__tests__/ChatView.mount.test.tsx \
  web/src/pages/ChatAgent/components/messageList/__tests__/MessageBubble.userQoL.test.tsx \
  web/src/locales/en-US.json web/src/locales/zh-CN.json CHANGELOG.md
git commit -m "feat: show chat session and message timestamps"
```
