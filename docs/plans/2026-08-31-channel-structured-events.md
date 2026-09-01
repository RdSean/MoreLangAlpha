# Channel Structured Events Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move streaming/tool presentation out of `LangAlphaFlashAdapter` into a reusable channel event pipeline, while keeping WeChat's user-facing delivery limited to the main Agent's final ordinary text.

**Architecture:** Flash remains an agent transport adapter: it parses the internal SSE stream into provider-neutral structured events and returns the agent's final response for backward compatibility. `ChannelEventDispatcher` routes those events through the selected `ChannelAdapter`; the adapter owns platform capability defaults and may render, transform, or intentionally consume presentation-only events. `GatewayRunner` creates one dispatcher per inbound turn and uses its accumulated rendered response for the durable PostgreSQL outbox, without changing agent history or the existing lease/ack transaction.

**Tech Stack:** Python 3.13, dataclasses, async HTTPX/SSE, async psycopg/PostgreSQL outbox, pytest, Ruff, `wechatbot-sdk`.

**References:**

- Hermes `BasePlatformAdapter`: https://github.com/NousResearch/hermes-agent/blob/1f99a4b2f2982fbef06df00ad673ade4e1895668/gateway/platforms/base.py
- Hermes event dispatcher: https://github.com/NousResearch/hermes-agent/blob/1f99a4b2f2982fbef06df00ad673ade4e1895668/gateway/stream_dispatch.py
- Hermes delivery boundary: https://github.com/NousResearch/hermes-agent/blob/1f99a4b2f2982fbef06df00ad673ade4e1895668/gateway/delivery.py
- Hermes structured events: https://github.com/NousResearch/hermes-agent/blob/1f99a4b2f2982fbef06df00ad673ade4e1895668/gateway/stream_events.py
- Local protocol notes: `/Users/seanlee/DevelopCode/MoreAlpha/protocol-spec.md`
- Local SDK/reference implementation: `/Users/seanlee/DevelopCode/MoreAlpha/wechatbot/python` and `/Users/seanlee/DevelopCode/MoreAlpha/agent-gateway`

---

### Task 1: Define provider-neutral structured stream events

**Files:**
- Create: `src/server/channels/events.py`
- Modify: `src/server/channels/__init__.py`
- Test: `tests/unit/server/channels/test_events.py`

**Step 1: Write the failing tests**

Add tests that construct frozen `MessageChunk`, `MessageStop`, `Commentary`, `ToolCallChunk`, `ToolCallFinished`, `GatewayNotice`, and `LongToolHint` values; assert SSE metadata fields (`agent`, `content_type`, `role`) remain available and the `StreamEvent` export is provider-neutral.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/channels/test_events.py -q`

Expected: FAIL with an import error because `src.server.channels.events` does not exist.

**Step 3: Write minimal implementation**

Implement frozen dataclasses with no provider imports or I/O. Keep event payloads presentation-only and export the explicit `StreamEvent` union. `MessageChunk` carries text plus optional source metadata; tool events carry name, preview/args, duration, status, and a stable index.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/channels/test_events.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/channels/events.py src/server/channels/__init__.py tests/unit/server/channels/test_events.py
git commit -m "feat: add provider-neutral channel stream events"
```

### Task 2: Turn ChannelAdapter into a reusable presentation base

**Files:**
- Modify: `src/server/channels/adapters/base.py`
- Modify: `src/server/channels/adapters/__init__.py`
- Modify: `src/server/channels/adapters/wechat_ilink.py`
- Modify: `tests/unit/server/channels/test_contracts.py`
- Create: `tests/unit/server/channels/test_channel_adapter_presentation.py`

**Step 1: Write the failing tests**

Add tests for base capability defaults (`supports_code_blocks=False`, `supports_draft_streaming=False`, `prefers_fresh_final_streaming=False`), default message rendering onto a small sink (`on_delta`, `on_segment_break`, `on_commentary`), default compact/verbose tool formatting, and WeChat overriding message filtering and returning `None` for tool events. Preserve the existing structural fake adapter contract test.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/channels/test_channel_adapter_presentation.py tests/unit/server/channels/test_contracts.py -q`

Expected: FAIL because `ChannelAdapter` has no presentation methods or capability defaults.

**Step 3: Write minimal implementation**

Replace the protocol-only declaration with a concrete ABC-style base that retains the six transport operations and structural `isinstance` compatibility for existing third-party/fake adapters. Add Hermes-inspired capability defaults and `render_message_event`, `format_tool_event`, and `format_tool_preview` methods. The base formatter may use a small local tool-name mapping and JSON preview; it must not import WeChat, Flash, FastAPI, or LangGraph. Implement WeChat's override to accept only `MessageChunk` events whose role is assistant/main and whose content type is ordinary text, while ignoring commentary/reasoning/subagent chunks and all tool chrome.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/channels/test_channel_adapter_presentation.py tests/unit/server/channels/test_contracts.py tests/unit/server/channels/test_wechat_message_adapter.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/channels/adapters tests/unit/server/channels/test_contracts.py tests/unit/server/channels/test_channel_adapter_presentation.py tests/unit/server/channels/test_wechat_message_adapter.py
git commit -m "refactor: make channel adapters own presentation policy"
```

### Task 3: Add the generic event dispatcher and response sink

**Files:**
- Create: `src/server/services/channels/event_dispatcher.py`
- Modify: `src/server/services/channels/__init__.py`
- Create: `tests/unit/server/services/channels/test_event_dispatcher.py`

**Step 1: Write the failing tests**

Test that message events route to the adapter/sink, tool events are formatted and delivered only when a formatter returns text, `None` consumes tool chrome, `off` disables it, `new` deduplicates consecutive tool names, and adapter exceptions are isolated from the agent run. Test that the sink exposes ordered `TextPart` output and never stores tool/commentary content unless the adapter explicitly renders it.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/services/channels/test_event_dispatcher.py -q`

Expected: FAIL because the dispatcher and sink do not exist.

**Step 3: Write minimal implementation**

Implement a synchronous `ChannelEventDispatcher` with a `PresentationSink` that supports `on_delta`, `on_segment_break`, and `on_commentary`, plus a `parts` property returning non-empty `TextPart` values. Route `MessageChunk`/`MessageStop`/`Commentary` through `ChannelAdapter.render_message_event`; route `ToolCallChunk` through `format_tool_event`; swallow presentation exceptions with debug logging. Keep the dispatcher platform-neutral and free of persistence calls.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/services/channels/test_event_dispatcher.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/services/channels/event_dispatcher.py src/server/services/channels/__init__.py tests/unit/server/services/channels/test_event_dispatcher.py
git commit -m "feat: dispatch structured channel presentation events"
```

### Task 4: Make AgentAdapter/Flash emit events without presentation filtering

**Files:**
- Modify: `src/server/channels/agent_adapters/base.py`
- Modify: `src/server/channels/agent_adapters/__init__.py`
- Modify: `src/server/channels/agent_adapters/langalpha_flash.py`
- Modify: `tests/unit/server/channels/test_langalpha_flash_adapter.py`

**Step 1: Write the failing tests**

Add an SSE fixture containing ordinary text, reasoning, commentary, tool-call start/finish, a subagent message, and run completion. Pass an `on_event` callback and assert Flash emits the corresponding structured events in order, preserving source metadata, while its returned `AgentTurnResult` retains only the compatibility final text. Add a test proving the callback is optional and existing callers still work.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/channels/test_langalpha_flash_adapter.py -q`

Expected: FAIL because `run_turn` has no event callback and `_consume_sse` drops non-text events.

**Step 3: Write minimal implementation**

Extend `AgentAdapter.run_turn` with an optional typed event callback. In Flash, translate SSE records to `MessageChunk`, `Commentary`, `ToolCallChunk`, `ToolCallFinished`, `MessageStop`, or `GatewayNotice` events and invoke the callback defensively. Remove the old channel-display filters from the event path. Retain only protocol-level extraction needed to produce the compatibility `AgentTurnResult` (main assistant ordinary text), and document that this result is not the presentation policy. Do not import any channel adapter.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/channels/test_langalpha_flash_adapter.py tests/unit/server/channels/test_contracts.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/channels/agent_adapters tests/unit/server/channels/test_langalpha_flash_adapter.py tests/unit/server/channels/test_contracts.py
git commit -m "refactor: emit structured events from flash adapter"
```

### Task 5: Connect Dispatcher to GatewayRunner and durable outbox

**Files:**
- Modify: `src/server/services/channels/gateway_runner.py`
- Modify: `src/server/database/channels.py`
- Modify: `tests/unit/server/services/channels/test_gateway_runner.py`
- Create: `tests/unit/server/services/channels/test_gateway_event_delivery.py`

**Step 1: Write the failing tests**

Test a claimed inbound turn with a fake event-capable agent and WeChat-like adapter: intermediate reasoning/commentary/tool events must not appear in the `AgentTurnResult` handed to `ack_inbound_and_enqueue_deliveries`; only rendered main text is persisted, and the original `session_ref`, deterministic outbox ordering, binding epoch, and ack call remain intact. Test an old agent adapter without `on_event` still uses its returned parts.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/services/channels/test_gateway_runner.py tests/unit/server/services/channels/test_gateway_event_delivery.py -q`

Expected: FAIL because the runner calls the agent without a dispatcher and persists unfiltered result parts.

**Step 3: Write minimal implementation**

Create a channel-specific dispatcher/sink inside `process_inbound_once`, pass its `dispatch` callback to adapters that accept `on_event` while preserving compatibility for legacy signatures, and select dispatcher-rendered parts when available. Fall back to the agent result for non-streaming/legacy adapters. Continue using `split_outbound_parts` and the existing atomic repository method; do not persist structured events or alter agent history.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/services/channels/test_gateway_runner.py tests/unit/server/services/channels/test_gateway_event_delivery.py tests/unit/server/database/test_channels.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/services/channels/gateway_runner.py src/server/database/channels.py tests/unit/server/services/channels/test_gateway_runner.py tests/unit/server/services/channels/test_gateway_event_delivery.py
git commit -m "feat: route channel events before durable outbox delivery"
```

### Task 6: Remove the temporary Flash filtering and document the contract

**Files:**
- Modify: `src/server/channels/agent_adapters/langalpha_flash.py`
- Modify: `docs/plans/2026-08-28-wechat-ilink-channel-gateway-design.md`
- Modify: `CHANGELOG.md`

**Step 1: Write the failing regression test**

Assert source inspection no longer finds presentation-specific channel filtering in Flash, and the generic contract test still rejects provider/runtime imports from contracts and base interfaces.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/channels/test_contracts.py tests/unit/server/channels/test_langalpha_flash_adapter.py -q`

Expected: FAIL while the old `_consume_sse` filtering remains.

**Step 3: Write minimal implementation**

Delete the temporary event-display filtering block and add concise Chinese documentation to the existing design plan explaining event metadata, adapter-owned rendering, dispatcher routing, presentation-only guarantees, legacy fallback, and the WeChat policy. Add a Chinese changelog entry for this refactor. Keep the existing references to the official Hermes files, protocol notes, and SDK source.

**Step 4: Run final verification**

Run: `uv run pytest tests/unit/server/channels tests/unit/server/services/channels tests/unit/server/database/test_channels.py -q`

Run: `uv run ruff check src/server/channels src/server/services/channels src/server/database/channels.py`

Run: `git diff --check`

Expected: all focused tests pass, Ruff exits 0, and there is no whitespace error. Live QR binding remains a manual provider test and is outside this refactor.

**Step 5: Commit**

```bash
git add src/server/channels/agent_adapters/langalpha_flash.py docs/plans/2026-08-28-wechat-ilink-channel-gateway-design.md CHANGELOG.md
git commit -m "docs: record channel event presentation architecture"
```

