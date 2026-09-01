# WeChat iLink Context Message Budget Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver complete WeChat answers without exceeding iLink's 2000-character message cap or 10-message-per-context budget, with durable continuation on a new user context.

**Architecture:** Keep the generic channel gateway and PostgreSQL outbox as the only transport path. Make the WeChat adapter produce greedily packed provider-sized parts, add a provider-neutral continuation record for tails that exceed nine content bubbles, and classify iLink business rate-limit errors separately from retryable transport failures.

**Tech Stack:** Python 3.13+, FastAPI services, async psycopg/Alembic SQL, pytest, existing `WechatILinkAdapter`, `GatewayRunner`, and encrypted channel persistence.

---

### Task 1: Lock down packing and budget behavior with failing unit tests

**Files:**
- Modify: `tests/unit/server/channels/test_wechat_message_adapter.py`
- Modify: `tests/unit/server/services/channels/test_gateway_runner.py`
- Create or modify: `tests/unit/server/database/test_channels.py`

**Step 1: Write failing tests**

Cover greedy merging of several short Markdown units into one provider-sized
part, preservation of oversized code blocks, a hard ten-message budget with a
continuation notice, and classification of a business `ret=-2` response.

**Step 2: Run focused tests**

Run `uv run pytest tests/unit/server/channels/test_wechat_message_adapter.py tests/unit/server/services/channels/test_gateway_runner.py tests/unit/server/database/test_channels.py -q`.

Expected: the new packing, budget, and continuation assertions fail before
production changes.

### Task 2: Implement provider-sized greedy packing

**Files:**
- Modify: `src/server/channels/adapters/wechat_ilink.py`

**Step 1: Replace per-unit append behavior**

Feed all normalized delivery units to a single packer. Keep fenced blocks
intact and use natural newline/space fallback for a unit larger than 2000.

**Step 2: Run adapter tests**

Run the focused adapter test file and confirm all packing assertions pass.

### Task 3: Add typed iLink business error classification

**Files:**
- Modify: `src/server/channels/contracts.py`
- Modify: `src/server/channels/adapters/wechat_ilink.py`
- Modify: `src/server/services/channels/gateway_runner.py`
- Modify: `tests/unit/server/channels/test_wechat_message_adapter.py`
- Modify: `tests/unit/server/services/channels/test_gateway_runner.py`

**Step 1: Add a context-budget exception and classify `ret=-2`**

Preserve the provider code and redacted detail. Keep `-14` mapped to session
expiry. Ensure the worker does not perform generic exponential retries for the
context budget error.

**Step 2: Run focused error tests**

Run the adapter and gateway tests; expected result is green with no binding
reauthentication on `ret=-2`.

### Task 4: Persist and resume continuation tails

**Files:**
- Create: `migrations/versions/044_add_channel_continuations.py`
- Modify: `src/server/database/channels.py`
- Modify: `src/server/services/channels/gateway_runner.py`
- Modify: `src/server/channels/contracts.py`
- Modify: `tests/unit/migrations/test_channel_gateway_continuation_migration.py`
- Modify: `tests/unit/server/database/test_channels.py`
- Modify: `tests/unit/server/services/channels/test_gateway_runner.py`

**Step 1: Add encrypted continuation persistence**

Store binding/session scope, encrypted remaining text parts, expiry, and
ordering metadata. Add claim/ack/fail operations with the same binding epoch
fences as the existing outbox.

**Step 2: Handle explicit continuation inbound**

Before opening a Flash turn, match a small exact continuation command such as
`继续`. If a pending tail exists, enqueue it with the new inbound's reply
context and do not invoke Flash. Keep unrelated messages independent.

**Step 3: Run persistence and runner tests**

Run the focused database and runner tests; verify lease loss and binding epoch
changes cannot resurrect stale continuation state.

### Task 5: Integrate the ten-message budget into durable outbox creation

**Files:**
- Modify: `src/server/services/channels/gateway_runner.py`
- Modify: `src/server/database/channels.py`
- Modify: `tests/unit/server/services/channels/test_gateway_runner.py`

**Step 1: Reserve one slot when the response exceeds ten parts**

Write at most nine answer parts plus the continuation notice, persist the tail,
and enqueue the visible parts atomically with inbound completion.

**Step 2: Add retry-safe continuation tests**

Assert worker restart, duplicate claims, and a second `继续` cannot duplicate or
drop a tail.

### Task 6: Verify, document, and restart local services

**Files:**
- Modify: `CHANGELOG.md`

**Step 1: Run verification**

Run focused channel tests, migration tests, Ruff, and then the full unit suite
with unrelated pre-existing failures reported separately.

**Step 2: Inspect diff and secrets**

Run `git diff --check`, inspect status, and ensure `.env`, QR state, tokens, and
generated files are not staged.

**Step 3: Restart services**

Restart only the current worktree's backend on `8000` and channel worker; leave
the existing frontend on `5177` intact. Confirm health, worker PID, and logs.

**Step 4: Commit atomically**

Update the Chinese changelog and commit the verified implementation without
credentials or generated files.
