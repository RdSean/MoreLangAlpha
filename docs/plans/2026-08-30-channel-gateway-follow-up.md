# Channel Gateway Follow-up Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove WeChat leakage from the generic gateway and make iLink QR reconfiguration, timeout recovery, and long replies match the SDK behavior.

**Architecture:** `ChannelAdapter` owns provider limits, image resolution and provider expiry. `GatewayRunner` consumes only generic contracts and writes the durable outbox. The linking service passes an existing encrypted binding only for a new QR request and atomically accepts an SDK `binded_redirect` reuse.

**Tech Stack:** Python 3.13, FastAPI, async psycopg, PostgreSQL, pytest, React 19/Vitest, `wechatbot-sdk`.

---

### Task 1: Generalize gateway contracts

**Files:**
- Modify: `src/server/channels/contracts.py`
- Modify: `src/server/channels/adapters/base.py`
- Modify: `src/server/channels/adapters/wechat_ilink.py`
- Modify: `src/server/services/channels/gateway_runner.py`
- Test: `tests/unit/server/channels/test_contracts.py`
- Test: `tests/unit/server/services/channels/test_gateway_runner.py`

**Step 1: Write the failing tests**

Add tests requiring a fake adapter to expose its outbound text limit and image resolver, and requiring `GatewayRunner` to treat a generic `ChannelBindingExpiredError` as reauthentication without importing WeChat.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/channels/test_contracts.py tests/unit/server/services/channels/test_gateway_runner.py -q`

Expected: FAIL because the generic exception/capabilities do not exist.

**Step 3: Write minimal implementation**

Add the generic exception and the two minimal Adapter operations. Replace the runner's concrete exception import, `channel_type == "wechat"`, and `hasattr(download_image)` branch with adapter-contract calls.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/channels/test_contracts.py tests/unit/server/services/channels/test_gateway_runner.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/channels src/server/services/channels/gateway_runner.py tests/unit/server/channels tests/unit/server/services/channels/test_gateway_runner.py
git commit -m "refactor: generalize channel gateway capabilities"
```

### Task 2: Reuse known iLink bindings on QR reconfiguration

**Files:**
- Modify: `src/server/channels/contracts.py`
- Modify: `src/server/channels/adapters/base.py`
- Modify: `src/server/channels/adapters/wechat_ilink.py`
- Modify: `src/server/services/channels/linking.py`
- Modify: `src/server/database/channels.py`
- Modify: `web/src/pages/Settings/panels/ChannelsTab.tsx`
- Test: `tests/unit/server/channels/test_wechat_link_adapter.py`
- Test: `tests/unit/server/services/channels/test_linking.py`
- Test: `tests/unit/server/database/test_channels.py`
- Test: `web/src/pages/Settings/__tests__/ChannelsTab.test.tsx`

**Step 1: Write the failing tests**

Require `begin_link` to pass an existing token as `local_token_list`, map `binded_redirect` to a linked result marked as reuse, preserve an existing binding during finalization, and expose reconfiguration to an active user.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/channels/test_wechat_link_adapter.py tests/unit/server/services/channels/test_linking.py tests/unit/server/database/test_channels.py -q`

Expected: FAIL because QR challenges never receive prior credentials and reuse is not representable.

**Step 3: Write minimal implementation**

Add optional prior credentials to `begin_link` and an explicit `reuse_existing_binding` result flag. Pass existing active credentials only inside `start_link`; keep the token out of attempts and API responses. In the repository, verify the active existing row and finalize the attempt without retiring the binding when the reuse flag is set. Add a visible reconfigure action for active bindings.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/channels/test_wechat_link_adapter.py tests/unit/server/services/channels/test_linking.py tests/unit/server/database/test_channels.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/channels src/server/services/channels/linking.py src/server/database/channels.py web/src/pages/Settings tests/unit/server/channels tests/unit/server/services/channels/test_linking.py tests/unit/server/database/test_channels.py web/src/pages/Settings/__tests__/ChannelsTab.test.tsx
git commit -m "fix: reuse active wechat bindings during reconfiguration"
```

### Task 3: Recover QR polling timeouts without an API error

**Files:**
- Modify: `src/server/services/channels/linking.py`
- Test: `tests/unit/server/services/channels/test_linking.py`

**Step 1: Write the failing test**

Make `adapter.poll_link` time out. Assert that finalization receives `LinkStatus.WAITING`, the lease is released through normal finalization, and the returned response remains pollable.

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/server/services/channels/test_linking.py -q`

Expected: FAIL with `TimeoutError`.

**Step 3: Write minimal implementation**

Catch only `asyncio.TimeoutError` around the bounded provider request and finalize a waiting result before returning the current attempt. Do not mask provider terminal statuses or credential parse errors.

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/server/services/channels/test_linking.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/services/channels/linking.py tests/unit/server/services/channels/test_linking.py
git commit -m "fix: recover timed out wechat link polls"
```

### Task 4: Preserve natural text boundaries and channel provenance

**Files:**
- Modify: `src/server/services/channels/gateway_runner.py`
- Modify: `src/server/channels/contracts.py`
- Modify: `src/server/channels/agent_adapters/langalpha_flash.py`
- Test: `tests/unit/server/services/channels/test_gateway_runner.py`
- Test: `tests/unit/server/channels/test_langalpha_flash_adapter.py`

**Step 1: Write the failing tests**

Require a 2,000-character boundary to prefer paragraph, line, and space breaks before hard cuts. Require a non-WeChat channel claim to reach Flash as its own `platform` value.

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/server/services/channels/test_gateway_runner.py tests/unit/server/channels/test_langalpha_flash_adapter.py -q`

Expected: FAIL because splitting hard-cuts and Flash always sends `wechat`.

**Step 3: Write minimal implementation**

Implement the SDK's natural-boundary algorithm in the generic splitter and add `channel_type` to `AgentTurn`; populate it from the claimed inbound row and use it in the Flash request body.

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/server/services/channels/test_gateway_runner.py tests/unit/server/channels/test_langalpha_flash_adapter.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/services/channels/gateway_runner.py src/server/channels/contracts.py src/server/channels/agent_adapters/langalpha_flash.py tests/unit/server/services/channels/test_gateway_runner.py tests/unit/server/channels/test_langalpha_flash_adapter.py
git commit -m "fix: preserve channel reply boundaries and provenance"
```

### Task 5: Document and verify the completed follow-up

**Files:**
- Modify: `docs/plans/2026-08-28-wechat-ilink-channel-gateway-design.md`
- Modify: `CHANGELOG.md`

**Step 1: Update documentation**

Record the generic contract boundary, `binded_redirect` reuse behavior, timeout recovery, and natural text splitting. Keep explicit non-goals current.

**Step 2: Run final verification**

Run: `uv run pytest tests/unit/server/channels tests/unit/server/services/channels tests/unit/server/database/test_channels.py tests/unit/server/app/test_channels_api.py tests/unit/config/test_channel_gateway_config.py -q`

Run: `cd web && pnpm exec vitest run src/pages/Settings/__tests__/ChannelsTab.test.tsx src/pages/Settings/__tests__/channelsApi.test.ts --reporter=dot`

Run: `uv run ruff check src/server/channels src/server/services/channels src/server/database/channels.py src/server/app/channels.py src/server/models/channels.py src/config/models.py`

**Step 3: Commit**

```bash
git add docs/plans/2026-08-28-wechat-ilink-channel-gateway-design.md CHANGELOG.md
git commit -m "docs: record channel gateway follow-up"
```
