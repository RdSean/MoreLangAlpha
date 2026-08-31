# WeChat iLink Final Chunk Typing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add Hermes-aligned typing lifecycle, connection notifications, Markdown-aware final text chunking, and SDK-backed iLink delivery without token streaming or message editing.

**Architecture:** Keep `GatewayRunner` provider-neutral and PostgreSQL outbox as the only durable outbound path. Extend `ChannelAdapter` with no-op lifecycle, typing, and outbound-preparation hooks; Runner owns the turn-scoped cancellable typing task, while `WeChatILinkAdapter` owns iLink tickets, `FINISH` wire messages, Markdown normalization, and provider notifications.

**Tech Stack:** Python 3.13, async psycopg, `wechatbot-sdk` (`ILinkApi`), pytest/pytest-asyncio, Ruff, Alembic-compatible SQL boundary.

---

### Task 1: Extend provider-neutral contracts and adapter hooks

**Files:**
- Modify: `src/server/channels/contracts.py`
- Modify: `src/server/channels/adapters/base.py`
- Test: `tests/unit/server/channels/test_channel_adapter_presentation.py`

**Step 1: Write the failing test**

Add tests that a base adapter exposes `supports_typing=False`, no-op async
`on_binding_start`/`on_binding_stop`, no-op `send_typing`/`stop_typing`, and an
outbound-preparation hook that returns parts unchanged. Add a test for a small
`keep_typing` loop using an `asyncio.Event`: it calls the adapter's start hook,
stops when the event is set, and never propagates a provider exception.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/channels/test_channel_adapter_presentation.py -q`

Expected: FAIL because the new capability and methods do not exist.

**Step 3: Write minimal implementation**

Add provider-neutral default methods to `ChannelAdapter`:

- `supports_typing = False`;
- async `on_binding_start(credentials)` and `on_binding_stop(credentials)`;
- async `send_typing(credentials, reply_context)` and `stop_typing(...)` no-op;
- async `keep_typing(credentials, reply_context, stop_event, interval=5.0)` that
  periodically calls `send_typing`, bounds/catches errors, and always calls
  `stop_typing` in `finally`;
- `prepare_outbound_parts(parts)` returning the tuple unchanged.

Use only `BindingCredentials`, `ReplyContext`, and provider-neutral parts in the
base signatures. Do not add iLink names or HTTP behavior to this module.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/channels/test_channel_adapter_presentation.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/channels/contracts.py src/server/channels/adapters/base.py tests/unit/server/channels/test_channel_adapter_presentation.py
git commit -m "feat: add generic channel typing lifecycle hooks"
```

### Task 2: Carry binding credentials into claimed inbound turns

**Files:**
- Modify: `src/server/database/channels.py:35-60, 430-485`
- Test: `tests/unit/server/database/test_channels.py` (or the existing channel database test module)

**Step 1: Write the failing test**

Extend the database-row test fixture to include encrypted `credentials` in the
claimed-inbound query result and assert the resulting `ClaimedInbound.credentials`
contains the expected `BindingCredentials` values. Preserve compatibility with
test doubles that omit this field by keeping the dataclass field optional.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/database/test_channels.py -q`

Expected: FAIL because `ClaimedInbound` does not expose credentials and the SQL
does not decrypt them.

**Step 3: Write minimal implementation**

Add `credentials: BindingCredentials | None = None` to `ClaimedInbound`. In
`claim_pending_inbound`, select
`pgp_sym_decrypt(b.credentials_ciphertext, %s) AS credentials`, bind the same
encryption key, parse the JSON object, and construct credentials with the
claimed binding id/channel type. Treat malformed credentials as a claim error,
consistent with existing encrypted payload parsing; do not log secret values.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/database/test_channels.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/database/channels.py tests/unit/server/database/test_channels.py
git commit -m "feat: expose decrypted binding credentials to channel turns"
```

### Task 3: Add Runner-owned typing and binding lifecycle orchestration

**Files:**
- Modify: `src/server/services/channels/gateway_runner.py:1-125, 200-300`
- Modify: `src/server/services/channels/worker.py:50-75` only if shutdown delegation is needed
- Test: `tests/unit/server/services/channels/test_gateway_runner.py`

**Step 1: Write the failing tests**

Add focused tests that:

- a channel advertising `supports_typing=True` receives a turn-scoped
  `keep_typing` task with the claim credentials and reply context;
- the task is stopped on normal Agent completion and on Agent exception;
- a provider typing exception does not cause `nack_inbound`;
- `on_binding_start` is invoked once per binding lease during a Runner lifetime,
  and `on_binding_stop` is invoked by `runner.stop()`;
- existing fake claims without credentials still process normally.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/services/channels/test_gateway_runner.py -q`

Expected: FAIL because Runner does not start typing or manage binding hooks.

**Step 3: Write minimal implementation**

In `GatewayRunner`:

- import `asyncio` and keep an instance-local map of started binding ids and their
  adapter/credentials; this is process lifecycle bookkeeping, not module-global
  state;
- add a private helper to invoke optional `on_binding_start` once and another to
  invoke `on_binding_stop` safely;
- call the start helper after a binding lease is claimed; remove/stop the entry
  when the binding is expired or Runner stops;
- in `process_inbound_once`, after resolving images and before `_run_agent_turn`,
  create a task for `adapter.keep_typing(...)` only when the adapter advertises
  `supports_typing` and the claim has credentials and reply context;
- in a `finally` local to the turn, set the stop event, await/cancel the typing
  task with a bounded timeout, and let adapter cleanup send status 2;
- replace direct `split_outbound_parts(...max_text_length=...)` with
  `adapter.prepare_outbound_parts(result.parts)` when available, falling back to
  the existing helper for structural test doubles;
- never let typing errors alter Agent result handling, ack/nack decisions, or
  outbox persistence.

Preserve binding epoch fences around image resolution and Agent execution. Do not
send any outbound provider message from the Runner.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/services/channels/test_gateway_runner.py tests/unit/server/services/channels/test_gateway_event_delivery.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/services/channels/gateway_runner.py src/server/services/channels/worker.py tests/unit/server/services/channels/test_gateway_runner.py
git commit -m "feat: manage channel typing around agent turns"
```

### Task 4: Implement WeChat iLink ticket, notification, and final-message behavior

**Files:**
- Modify: `src/server/channels/adapters/wechat_ilink.py`
- Test: `tests/unit/server/channels/test_wechat_message_adapter.py`

**Step 1: Write the failing tests**

Add tests for:

- `supports_typing=True`;
- `send_typing` lazily calls `get_config` with the peer and inbound context
  token, caches `typing_ticket`, and sends status `1`;
- a cached ticket avoids a second `get_config` call; `stop_typing` sends status
  `2` and missing context is a no-op;
- `on_binding_start` calls `notify_start`, and `on_binding_stop` calls
  `notify_stop`; notification failures are swallowed;
- session-expired `send_message` remains translated to
  `ChannelBindingExpiredError`;
- each final text `OutboundMessage` uses the supplied stable `client_id`,
  `message_state=FINISH`, target binding `user_id`, and exact reply
  `context_token`.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/channels/test_wechat_message_adapter.py -q`

Expected: FAIL because the typing cache/lifecycle hooks are absent.

**Step 3: Write minimal implementation**

In `WeChatILinkAdapter`:

- add `supports_typing = True` and an instance cache keyed by
  `(credentials.binding_ref, peer_ref)` with a short TTL (600 seconds);
- implement `send_typing(credentials, reply_context)` using the SDK's
  `get_config` and `send_typing(..., status=1)`; use `reply_context.route_ref` as
  the iLink user id and its `context_token` value; catch/log non-fatal errors;
- implement `stop_typing` with cached tickets and status `2`;
- implement `on_binding_start/stop` using SDK `notify_start/notify_stop`, tracking
  started binding tokens per adapter instance so polling ticks do not notify on
  every request; failures are logged and ignored;
- keep `deliver` based on `ILinkApi.build_text_message`, with `FINISH`, explicit
  client id, target id, and context token.

Do not introduce a local context-token file cache; PostgreSQL reply context is the
source of truth.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/channels/test_wechat_message_adapter.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/channels/adapters/wechat_ilink.py tests/unit/server/channels/test_wechat_message_adapter.py
git commit -m "feat: add wechat ilink typing and connection notifications"
```

### Task 5: Port Hermes Markdown normalization and semantic final chunking

**Files:**
- Modify: `src/server/channels/adapters/wechat_ilink.py`
- Test: `tests/unit/server/channels/test_wechat_message_adapter.py`
- Test: `tests/unit/server/services/channels/test_gateway_runner.py`

**Step 1: Write the failing tests**

Add deterministic tests for:

- `# Title` becoming `【Title】` and lower-level headings becoming bold text;
- Markdown tables becoming readable key/value list rows;
- fenced code blocks remaining one unit when under the 2000-character limit;
- top-level lines/paragraphs becoming ordered text parts while indented
  continuations remain attached;
- oversized units using natural block boundaries before hard splitting;
- `GatewayRunner` calling the adapter preparation hook before acking the inbound,
  while generic adapters retain the existing simple splitter behavior.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/channels/test_wechat_message_adapter.py tests/unit/server/services/channels/test_gateway_runner.py -q`

Expected: FAIL because WeChat currently joins raw text and uses generic hard
splitting.

**Step 3: Write minimal implementation**

Port only the bounded pure helpers from the cached Hermes Weixin reference:

- heading and table rewrites;
- fenced-code-aware Markdown block splitting;
- semantic delivery units and block packing;
- final fallback hard splitting.

Expose `prepare_outbound_parts` on `WeChatILinkAdapter` to normalize each
`TextPart` and return ordered chunks, preserving non-text `MediaPart` values. Keep
the configured iLink limit (`max_text_length`, default 2000) as the only hard
limit. Do not send chunks here; this hook only prepares durable outbox parts.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/channels/test_wechat_message_adapter.py tests/unit/server/services/channels/test_gateway_runner.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/channels/adapters/wechat_ilink.py tests/unit/server/channels/test_wechat_message_adapter.py tests/unit/server/services/channels/test_gateway_runner.py
git commit -m "feat: chunk and format wechat final replies by markdown blocks"
```

### Task 6: Verify integration, documentation, and service behavior

**Files:**
- Modify: `CHANGELOG.md`
- Review: `docs/plans/2026-08-31-wechat-final-chunk-typing-design.md`
- Review: `docs/references/wechat-ilink/`

**Step 1: Run focused verification**

Run:

```bash
uv run pytest tests/unit/server/channels tests/unit/server/services/channels tests/unit/server/database -q
uv run ruff check src/server/channels src/server/services/channels src/server/database/channels.py
git diff --check
```

Expected: all focused tests pass, Ruff is clean, and there is no whitespace
failure.

**Step 2: Run broader regression verification**

Run: `uv run pytest tests/unit -q`

Expected: PASS, or document unrelated pre-existing failures precisely.

**Step 3: Update changelog**

Add a Chinese entry describing generic typing hooks, iLink connection status
notifications, lazy typing-ticket caching, and final Markdown-aware outbox
chunking. Explicitly state that no token streaming or message editing was added.

**Step 4: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: record wechat typing and final chunk delivery"
```

**Step 5: Final service check**

Do not restart the user's existing frontend/backend services on ports `5177` and
`8000`. If the channel worker is run for a smoke check, use the worktree `.env`
and stop only the process started for this check; report the exact command and
result.
