# Household LLM Pool Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 LLM Endpoint 变成家庭级模型池，由家长维护加密凭证，学生只能查看、切换和保存个人使用偏好，并让下一次聊天请求实时使用家庭最新配置。

**Architecture:** 在现有 `education_households` / `education_memberships` 关系之上新增家庭 Endpoint、家庭默认值和学生偏好三组表。Endpoint 的密钥只在服务端通过现有 pgcrypto 加密层读取；学生接口只返回无凭证模型摘要。聊天解析器把 `family:<endpoint_id>` 作为内部模型键，学生请求按“有效学生偏好 -> 有效家庭默认 -> 无模型”解析，并把家庭凭证标记为新的 `CredentialSource.HOUSEHOLD`；运行元数据和账单同时保留家庭、发起学生、Endpoint 及模型快照。

**Tech Stack:** Python 3.13+, FastAPI, async psycopg, Alembic raw SQL, PostgreSQL/pgcrypto, Redis cache, Pydantic, React 19, TypeScript, TanStack Query, Vitest, Ruff, pytest.

---

## Scope and settled contracts

实现以下已经批准的行为，不重新引入学生个人 Endpoint 双轨：

- 家长可以新增、编辑、启用/禁用、删除家庭 Endpoint，并设置或清除家庭默认 Endpoint。
- Endpoint 包含 `display_name`、`provider`、`model_id`、可选 `base_url` 和加密 API Key；API Key 可选以支持本地无密钥服务。`provider` 必须是模型 manifest 中的可用 provider，SDK/协议沿用现有 provider 配置。
- 学生只能读取启用 Endpoint 摘要、更新自己的 `endpoint_id` 偏好；不得读取 API Key、完整凭证、Vault 引用或家长管理接口。
- 学生首次使用优先家庭默认；手动选择后保存个人偏好；家长修改默认不覆盖学生偏好。
- 偏好 Endpoint 被删除或禁用后，下一次请求自动回退有效家庭默认；没有可用模型时返回明确的 `no_model_available`，不创建 run、不发起空模型调用。
- `family:<uuid>` 是只在请求和前端模型选择器中使用的稳定模型键；历史记录保存真实模型/provider/display name 快照，不依赖 Endpoint 当前名称。
- 家庭凭证归属家庭/家长账单，学生发起者单独审计；兼容现有 `is_byok` 布尔字段时，`HOUSEHOLD` 视为非平台凭证，但新增 `credential_source` 和 Endpoint 字段表达真实来源。
- 本次使用测试数据库，可在执行前清理旧 `user_api_keys`、用户模型偏好、对话、workspace 和 checkpoint；不设计生产迁移兼容分支，也不复制旧 Key。

## Task 1: Add household model-pool schema

**Files:**
- Create: `migrations/versions/033_add_household_llm_pool.py`
- Test: `tests/unit/migrations/test_generic_migration_chain.py` (extend head/chain assertions)
- Test: `tests/integration/test_household_llm_pool_db.py`

**Step 1: Write the failing migration contract test.**

Add a migration-chain assertion that revision `033` follows `032`, and an integration fixture assertion that the upgrade creates these tables and constraints:

```python
assert tables >= {
    "household_llm_endpoints",
    "household_llm_settings",
    "student_llm_preferences",
}
```

The integration test must insert two households and prove that a default/preference endpoint cannot cross household boundaries through the composite foreign keys.

**Step 2: Run the tests to verify the contract fails.**

Run: `uv run pytest tests/unit/migrations/test_generic_migration_chain.py tests/integration/test_household_llm_pool_db.py -q`

Expected: the new table/ revision assertions fail because revision `033` and the tables do not exist.

**Step 3: Implement the migration.**

Use `revision = "033"`, `down_revision = "032"`, and raw `op.execute` SQL consistent with existing migrations. Create:

```sql
CREATE TABLE household_llm_endpoints (
    endpoint_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    household_id UUID NOT NULL REFERENCES education_households(household_id) ON DELETE CASCADE,
    display_name VARCHAR(128) NOT NULL,
    provider VARCHAR(64) NOT NULL,
    model_id VARCHAR(255) NOT NULL,
    base_url TEXT,
    api_key BYTEA,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_by VARCHAR(255) NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (household_id, endpoint_id),
    CHECK (length(trim(display_name)) > 0),
    CHECK (length(trim(provider)) > 0),
    CHECK (length(trim(model_id)) > 0)
);
CREATE TABLE household_llm_settings (
    household_id UUID PRIMARY KEY REFERENCES education_households(household_id) ON DELETE CASCADE,
    default_endpoint_id UUID,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (household_id, default_endpoint_id)
        REFERENCES household_llm_endpoints(household_id, endpoint_id)
        ON DELETE SET NULL (default_endpoint_id)
);
CREATE TABLE student_llm_preferences (
    user_id VARCHAR(255) PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    household_id UUID NOT NULL,
    endpoint_id UUID,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    FOREIGN KEY (household_id, user_id)
        REFERENCES education_memberships(household_id, user_id)
        ON DELETE CASCADE,
    FOREIGN KEY (household_id, endpoint_id)
        REFERENCES household_llm_endpoints(household_id, endpoint_id)
        ON DELETE SET NULL (endpoint_id)
);
```

Add indexes on `(household_id, enabled, sort_order, display_name)` and `(household_id, user_id)`. Add nullable `household_id`, `llm_endpoint_id`, `credential_source`, `model_snapshot JSONB` columns to `conversation_usages`, with foreign keys using `ON DELETE SET NULL` so deleting an Endpoint never destroys usage history. Do not store plaintext credentials or expose these columns through a generic user API.

**Step 4: Run the migration tests.**

Run: `uv run pytest tests/unit/migrations/test_generic_migration_chain.py tests/integration/test_household_llm_pool_db.py -q`

Expected: PASS, including upgrade and downgrade cleanup. Run `uv run alembic heads` and expect `033 (head)`.

**Step 5: Commit the schema only.**

```bash
git add migrations/versions/033_add_household_llm_pool.py tests/unit/migrations/test_generic_migration_chain.py tests/integration/test_household_llm_pool_db.py
git commit -m "feat: add household LLM pool schema"
```

## Task 2: Implement encrypted pool CRUD and household policy service

**Files:**
- Create: `src/server/database/household_llm_pool.py`
- Create: `src/server/services/household_llm_pool.py`
- Test: `tests/unit/server/services/test_household_llm_pool.py`
- Test: `tests/integration/test_household_llm_pool_db.py`

**Step 1: Write failing service tests.**

Cover these exact functions and outcomes:

```python
await create_endpoint(parent_id, {...})
await list_parent_pool(parent_id)                 # includes masked_key only
await update_endpoint(parent_id, endpoint_id, ...) # omitted api_key keeps old key
await set_household_default(parent_id, endpoint_id)
await resolve_student_model(student_id)            # preference -> default -> None
```

Assert that a student, a non-member parent, and a parent from another household receive `ParentMembershipRequiredError`/`FamilyModelAccessError`; assert that the raw key is passed to `pgp_sym_encrypt` and never appears in returned summaries. Cover disabled preference fallback and deletion-triggered null preference.

**Step 2: Run the tests and verify failure.**

Run: `uv run pytest tests/unit/server/services/test_household_llm_pool.py tests/integration/test_household_llm_pool_db.py -q`

Expected: import/implementation failures.

**Step 3: Implement database functions.**

Use `get_db_connection`, `dict_row`, and `_get_encryption_key` from `src.server.database.encryption`. Implement:

- `get_membership_for_user(user_id)` reuse from `education_members.py` and require role `parent` or `student` as appropriate.
- `list_household_endpoints(household_id, include_disabled=False)` returning safe rows; parent-only detail may include `masked_api_key`, never plaintext.
- `get_endpoint_for_runtime(household_id, endpoint_id)` decrypting only inside the server runtime query.
- `create_household_endpoint`, `update_household_endpoint`, `delete_household_endpoint`, `set_household_default`, `get_household_availability`, `upsert_student_preference`.

Encrypt values with `pgp_sym_encrypt(%s, %s)`, decrypt only with `pgp_sym_decrypt` in the runtime path, and use transactions for endpoint update plus default cleanup. On an update with `api_key=None` distinguish “field omitted” from “clear key” using a sentinel. Never log `api_key`, decrypted values, or `base_url`.

**Step 4: Implement policy and resolution helpers.**

In `src/server/services/household_llm_pool.py`, add:

```python
FAMILY_MODEL_PREFIX = "family:"
class FamilyModelAccessError(PermissionError): ...
class NoFamilyModelAvailableError(LookupError): ...
async def require_parent_household(user_id: str) -> str: ...
async def get_household_context(user_id: str) -> dict[str, str]: ...
async def resolve_student_endpoint(user_id: str) -> dict[str, Any] | None: ...
async def resolve_family_model_key(user_id: str, model_key: str | None) -> dict[str, Any] | None: ...
def public_model_key(endpoint_id: str) -> str: ...
```

`resolve_student_endpoint` must clear an invalid/disabled preference in the same logical operation before falling back to the valid household default. `resolve_family_model_key` must check membership and enabled status, so a student cannot submit another household’s UUID. Return provider/model/base URL/key only to the server resolver; route serializers receive the safe projection.

**Step 5: Run service and integration tests.**

Run: `uv run pytest tests/unit/server/services/test_household_llm_pool.py tests/integration/test_household_llm_pool_db.py -q`

Expected: PASS. Run `make lint`; expected Ruff passes for the new modules.

**Step 6: Commit CRUD and policy.**

```bash
git add src/server/database/household_llm_pool.py src/server/services/household_llm_pool.py tests/unit/server/services/test_household_llm_pool.py tests/integration/test_household_llm_pool_db.py
git commit -m "feat: add encrypted household LLM pool service"
```

## Task 3: Add parent and student FastAPI APIs

**Files:**
- Create: `src/server/app/family_llm.py`
- Modify: `src/server/app/setup.py`
- Test: `tests/unit/server/app/test_family_llm.py`

**Step 1: Write failing route tests.**

Use dependency overrides/mocks for `CurrentUserId` and assert this contract:

```text
GET    /api/v1/family/llm-pool
POST   /api/v1/family/llm-pool
PATCH  /api/v1/family/llm-pool/{endpoint_id}
DELETE /api/v1/family/llm-pool/{endpoint_id}
PUT    /api/v1/family/llm-pool/default
GET    /api/v1/family/llm-availability
PUT    /api/v1/family/llm-preference
```

Test that parent responses include endpoint id, display name, provider, model, base URL and masked key but never raw key; student availability includes only enabled model summaries, `selected_endpoint_id`, `default_endpoint_id` and `model_key`. Test 403 for student CRUD, 404/403 for cross-household IDs, 409 for selecting disabled endpoints, 409 `no_model_available` semantics when sending is attempted without a model.

**Step 2: Run route tests to verify failure.**

Run: `uv run pytest tests/unit/server/app/test_family_llm.py -q`

Expected: router import/path failures.

**Step 3: Implement Pydantic contracts and routes.**

Define request models with length limits and URL validation (`http://`/`https://` only), a nullable `api_key` update sentinel, and response models that deliberately omit secret fields. Parent write routes call `require_parent_household` before every database operation. Student preference updates accept only an endpoint UUID or `null`, verify same household and enabled status, and return the refreshed availability projection.

Register `family_llm.router` in `src/server/app/setup.py` near the existing `auth_router`/education routers. Keep parent-only account/space read APIs unchanged.

**Step 4: Run route tests and OpenAPI import checks.**

Run: `uv run pytest tests/unit/server/app/test_family_llm.py -q` and `uv run python -c "from src.server.app.setup import app; assert any(r.path == '/api/v1/family/llm-availability' for r in app.routes)"`.

Expected: PASS and the route assertion succeeds.

**Step 5: Commit the API surface.**

```bash
git add src/server/app/family_llm.py src/server/app/setup.py tests/unit/server/app/test_family_llm.py
git commit -m "feat: expose household LLM pool APIs"
```

## Task 4: Integrate family endpoint resolution into the LLM runtime

**Files:**
- Modify: `src/ptc_agent/config/agent.py`
- Modify: `src/server/services/llm/config.py`
- Modify: `src/server/services/llm/availability.py`
- Modify: `src/server/handlers/chat/error_handling.py`
- Modify: `src/server/services/llm/service.py`
- Modify: `src/server/handlers/chat/flash_run.py`
- Modify: `src/server/handlers/chat/ptc_run.py`
- Modify: `src/server/handlers/chat/request_prep.py`
- Test: `tests/unit/server/handlers/test_resolve_llm_config.py`
- Test: `tests/unit/server/services/test_llm_service.py`

**Step 1: Write failing resolver tests.**

Add tests for:

1. Student with no personal preference resolves the enabled household default.
2. Student preference wins over household default.
3. Disabled/deleted preference falls back and is cleared.
4. No default and non-empty pool returns no selected model until preference is set.
5. Empty pool raises an HTTP 409/400 detail with `type == "no_model_available"` before `create_llm` or a run is started.
6. `family:<endpoint_id>` from a student in another household returns 404/403 rather than resolving.
7. Family credentials create a client with the endpoint's decrypted key/base URL, set `CredentialSource.HOUSEHOLD`, and never include the key in config metadata.
8. PTC/Flash role clients reuse the household main client when no separate student role model is configured.

**Step 2: Run the focused resolver tests to verify failure.**

Run: `uv run pytest tests/unit/server/handlers/test_resolve_llm_config.py -q`

Expected: failures for missing `HOUSEHOLD`, family key handling, and no-model error.

**Step 3: Add the new credential source and runtime primitive.**

Add `CredentialSource.HOUSEHOLD = "household"`. In `src/server/services/llm/config.py`, add a family branch before personal custom-model classification:

```python
family_endpoint = await resolve_family_model_key(user_id, requested_or_preferred_key)
if family_endpoint:
    client = create_llm_from_custom(
        {
            "name": family_endpoint["display_name"],
            "model_id": family_endpoint["model_id"],
            "provider": family_endpoint["provider"],
        },
        api_key=family_endpoint["api_key"],
        base_url=family_endpoint["base_url"],
        cache_key=thread_id,
    )
    return ResolvedClient(client, ModelSource.SYSTEM, CredentialSource.HOUSEHOLD)
```

The actual implementation must use a small helper (`resolve_household_llm_client`) and preserve provider-specific manifest SDK behavior. Validate `provider` against non-platform entries in `ModelConfig.flat_providers` when the parent saves an endpoint; `create_llm_from_custom` then accepts the pool's arbitrary `model_id` while inheriting the manifest provider SDK and headers. For a family key, `family:<uuid>` is the requested identity; the client model identity is the endpoint `model_id`. Set `config.resolved_model` to the endpoint model snapshot and carry a non-secret `family_endpoint_id`/`household_id` in a separate runtime field or request metadata. Do not place the decrypted key in Pydantic serialization, logs, exceptions, SSE, or checkpoints.

For a student, determine role/household before reading `get_model_preference`, then derive the model key from the family preference/default when `request_model` is absent. If `request_model` is supplied, accept only a `family:<uuid>` key belonging to the student household; do not consult student `user_preferences` or `user_api_keys` as a fallback. Preserve the existing personal BYOK/OAuth/platform order for parent and non-family users. Add a dedicated `no_model_available` HTTP error in `availability.py`/`error_handling.py`; do not let the current bootstrap `ValueError` become a 500.

Update `src/server/services/llm/service.py` so `HOUSEHOLD` is treated like a resolved user credential for the credit/materialization guard. Update Flash/PTC setup metadata with a safe `credential_source`, `household_id`, `family_endpoint_id`, `model_id`, `provider`, and `display_name` snapshot.

**Step 4: Run resolver/service tests.**

Run: `uv run pytest tests/unit/server/handlers/test_resolve_llm_config.py tests/unit/server/services/test_llm_service.py -q`

Expected: PASS, with existing 66+ resolver tests remaining green plus the new family cases.

**Step 5: Commit runtime resolution.**

```bash
git add src/ptc_agent/config/agent.py src/server/services/llm/config.py src/server/services/llm/availability.py src/server/handlers/chat/error_handling.py src/server/services/llm/service.py src/server/handlers/chat/flash_run.py src/server/handlers/chat/ptc_run.py src/server/handlers/chat/request_prep.py tests/unit/server/handlers/test_resolve_llm_config.py tests/unit/server/services/test_llm_service.py
git commit -m "feat: resolve student chat through household LLM endpoints"
```

## Task 5: Make admission, quota, and history billing family-aware

**Files:**
- Modify: `src/server/dependencies/usage_limits.py`
- Modify: `src/server/app/threads/create.py`
- Modify: `src/server/app/threads/messaging.py`
- Modify: `src/server/services/runs/finalization.py`
- Modify: `src/server/services/runs/coordinator.py`
- Modify: `src/server/services/persistence/usage.py`
- Modify: `src/server/database/conversation/usage.py`
- Modify: `src/server/database/conversation/replay_rows.py`
- Modify: `src/server/database/conversation/threads_read.py`
- Test: `tests/unit/server/app/test_threads_credit_gate.py`
- Test: `tests/unit/server/services/test_usage_persistence.py`
- Test: `tests/unit/server/services/test_run_finalization.py`

**Step 1: Write failing admission and snapshot tests.**

Assert that a student with an enabled family endpoint is admitted even with no personal API key/OAuth token, that the empty-pool request returns `no_model_available` before `create_thread`/`start_run`, and that a completed run writes:

```json
{
  "household_id": "...",
  "llm_endpoint_id": "...",
  "credential_source": "household",
  "model_snapshot": {
    "display_name": "家庭 DeepSeek Flash",
    "provider": "deepseek",
    "model_id": "deepseek-chat"
  }
}
```

Assert that this safe snapshot survives Endpoint rename/delete and that raw API keys do not occur in response metadata, replay rows, usage rows, or logs.

**Step 2: Run tests to verify failure.**

Run: `uv run pytest tests/unit/server/app/test_threads_credit_gate.py tests/unit/server/services/test_usage_persistence.py tests/unit/server/services/test_run_finalization.py -q`

Expected: missing family admission/usage fields and incorrect credential classification.

**Step 3: Implement the gates and persistence path.**

- Extend `ChatAuthResult` with `has_household_model` and `household_id`; collect it in `enforce_chat_limit` using a single safe availability query. A family model counts as own-credential for the existing negative-balance rule, but the durable row records `credential_source="household"` rather than lying about a user BYOK key.
- In `threads/create.py`, use the same family-aware credential check before auto-title creation. If no family model exists for a student, skip title LLM work and return the no-model contract rather than creating a model-less run.
- In `threads/messaging.py`, after `resolve_llm_config`, classify `HOUSEHOLD` alongside OAuth/BYOK for quota enforcement and propagate the safe family snapshot into run metadata.
- In `finalization.py`, copy only an allow-listed snapshot into `conversation_responses.metadata`; never copy arbitrary config/request data.
- Pass the snapshot from `RunHandle` metadata into `UsagePersistenceService.persist_usage`; update `create_usage_record` SQL and the read projections to write/read the new nullable columns. Keep old usage rows valid with nulls.
- Ensure retries/regenerates use the newly resolved Endpoint for new runs while old snapshots remain unchanged.

**Step 4: Run focused and integration tests.**

Run: `uv run pytest tests/unit/server/app/test_threads_credit_gate.py tests/unit/server/services/test_usage_persistence.py tests/unit/server/services/test_run_finalization.py tests/unit/server/handlers/test_streaming_handler_metadata.py -q`

Expected: PASS. Run `uv run pytest -m integration tests/integration/test_household_llm_pool_db.py -q` against the project test PostgreSQL.

**Step 5: Commit billing/history integration.**

```bash
git add src/server/dependencies/usage_limits.py src/server/app/threads/create.py src/server/app/threads/messaging.py src/server/services/runs/finalization.py src/server/services/runs/coordinator.py src/server/services/persistence/usage.py src/server/database/conversation/usage.py src/server/database/conversation/replay_rows.py src/server/database/conversation/threads_read.py tests/unit/server/app/test_threads_credit_gate.py tests/unit/server/services/test_usage_persistence.py tests/unit/server/services/test_run_finalization.py
git commit -m "feat: record household model billing and snapshots"
```

## Task 6: Build the parent model-pool settings panel

**Files:**
- Create: `web/src/pages/Settings/panels/HouseholdModelPoolTab.tsx`
- Modify: `web/src/pages/Settings/Settings.tsx`
- Modify: `web/src/pages/Settings/api.ts`
- Modify: `web/src/pages/Settings/queries.ts`
- Modify: `web/src/lib/queryKeys.ts`
- Modify: `web/src/pages/Settings/Settings.css` only if layout rules are needed
- Test: `web/src/pages/Settings/__tests__/HouseholdModelPoolTab.test.tsx`
- Test: `web/src/pages/Settings/__tests__/familyLlmApi.test.ts`

**Step 1: Write failing frontend contract tests.**

Mock the API and render the parent tab. Cover:

- list loading/error/retry and empty state;
- create form with display name/provider/model/base URL/API key;
- edit preserves the key when the field is blank and can explicitly clear it;
- enabled toggle, delete, set default, clear default;
- student role cannot see the management tab or mutation controls;
- raw key is never rendered after a successful response.

**Step 2: Run the tests to verify failure.**

Run: `cd web && pnpm exec vitest run src/pages/Settings/__tests__/HouseholdModelPoolTab.test.tsx src/pages/Settings/__tests__/familyLlmApi.test.ts`

Expected: missing API functions/component failures.

**Step 3: Implement the API/query layer.**

Add TypeScript types for parent endpoint summaries and mutations; add `queryKeys.settings.family.llmPool()`, `availability()`, and `preference()`. Use TanStack Query mutations that invalidate the pool and availability keys after every parent write. Keep API payloads explicit and omit `api_key` on edits unless the parent changed it.

**Step 4: Implement the settings panel and route.**

Add a `家庭模型池` secondary settings tab visible only for `member.role === 'parent'`. Use existing shadcn `Dialog`, `Input`, `Select`, `Button`, and Lucide icons. Display masked keys, provider/model, base URL, enabled status and default marker. The page does not manage workspace names, student passwords, or student conversations. Destructive delete requires the existing dialog confirmation pattern; no custom client-only authorization is trusted.

**Step 5: Run frontend tests/typecheck.**

Run: `cd web && pnpm exec vitest run src/pages/Settings/__tests__/HouseholdModelPoolTab.test.tsx src/pages/Settings/__tests__/familyLlmApi.test.ts && pnpm exec tsc --noEmit`

Expected: PASS and no TypeScript errors.

**Step 6: Commit the parent UI.**

```bash
git add web/src/pages/Settings/panels/HouseholdModelPoolTab.tsx web/src/pages/Settings/Settings.tsx web/src/pages/Settings/api.ts web/src/pages/Settings/queries.ts web/src/lib/queryKeys.ts web/src/pages/Settings/Settings.css web/src/pages/Settings/__tests__/HouseholdModelPoolTab.test.tsx web/src/pages/Settings/__tests__/familyLlmApi.test.ts
git commit -m "feat: add parent household model pool settings"
```

## Task 7: Add the student model availability and preference UX

**Files:**
- Modify: `web/src/pages/Settings/api.ts`
- Modify: `web/src/pages/Settings/queries.ts`
- Modify: `web/src/lib/queryKeys.ts`
- Modify: `web/src/components/ui/chat-input.tsx`
- Modify: `web/src/components/ui/chat-input.modelMenu.tsx`
- Modify: `web/src/components/ui/chat-input.models.ts`
- Modify: `web/src/pages/ChatAgent/components/ChatView.tsx`
- Modify: `web/src/pages/ChatAgent/hooks/useChatMessages.ts`
- Modify: `web/src/pages/ChatAgent/session/stream/processStreamEvent.ts`
- Test: `web/src/components/ui/__tests__/chat-input.familyModel.test.tsx`
- Test: `web/src/pages/ChatAgent/components/chatView/__tests__/familyModelAvailability.test.tsx`

**Step 1: Write failing student UI tests.**

Mock availability responses and cover:

- first load selects the family default without writing a student preference;
- a saved preference is selected and displayed;
- selecting another endpoint sends `PUT /family/llm-preference` and remains selected after refetch;
- a disabled preference is replaced by the server-provided default;
- no default with non-empty pool shows selectable models but no fake Sonnet 5 label;
- empty pool disables send/new run and displays “暂无可用模型” with a retry/refresh action;
- students never see endpoint CRUD, API key, provider edit, or personal BYOK controls;
- parent/non-student chat behavior and existing model reporting tests remain unchanged.

**Step 2: Run the tests to verify failure.**

Run: `cd web && pnpm exec vitest run src/components/ui/__tests__/chat-input.familyModel.test.tsx src/pages/ChatAgent/components/chatView/__tests__/familyModelAvailability.test.tsx`

Expected: missing availability query/model-key behavior failures.

**Step 3: Implement student availability/query behavior.**

Use the `GET /api/v1/family/llm-availability` response as the only student model source. Track a safe `model_key` (`family:<uuid>`) separately from the display model name. On selection, call the preference mutation and invalidate availability. Do not write `preferred_flash_model` or `user_api_keys` for student selection. Use server-reported `selected_source`/`resolved_model` to prevent the UI from inventing a default.

**Step 4: Integrate the chat menu and send gate.**

Teach `ChatInput`/`ChatInputModelMenu` to render family summaries in Flash mode, report the opaque model key to `ChatView`, and preserve it for resume/retry/regenerate. When no model is available, make the send action inert and show the server-safe error state; do not enter the loading stream. Keep the existing per-message model metadata display and ensure SSE/replay code only consumes non-secret snapshots.

**Step 5: Run frontend tests/typecheck.**

Run: `cd web && pnpm exec vitest run src/components/ui/__tests__/chat-input.familyModel.test.tsx src/pages/ChatAgent/components/chatView/__tests__/familyModelAvailability.test.tsx src/components/ui/__tests__/chat-input.modelReporting.test.tsx && pnpm exec tsc --noEmit`

Expected: PASS and no TypeScript errors.

**Step 6: Commit the student UX.**

```bash
git add web/src/components/ui/chat-input.tsx web/src/components/ui/chat-input.modelMenu.tsx web/src/components/ui/chat-input.models.ts web/src/pages/ChatAgent/components/ChatView.tsx web/src/pages/ChatAgent/hooks/useChatMessages.ts web/src/pages/ChatAgent/session/stream/processStreamEvent.ts web/src/pages/Settings/api.ts web/src/pages/Settings/queries.ts web/src/lib/queryKeys.ts web/src/components/ui/__tests__/chat-input.familyModel.test.tsx web/src/pages/ChatAgent/components/chatView/__tests__/familyModelAvailability.test.tsx
git commit -m "feat: let students switch household models"
```

## Task 8: Remove student personal-model paths and reset test data

**Files:**
- Modify: `src/server/services/llm/config.py` (student branch only)
- Modify: `src/server/app/api_keys.py` (student access response/write guard)
- Modify: `src/server/app/users.py` or shared education access helper, whichever is already used for role gates
- Create: `scripts/reset_household_llm_test_data.sql` (safe, explicit test database script)
- Test: `tests/unit/server/app/test_api_keys.py`
- Test: `tests/unit/server/handlers/test_resolve_llm_config.py`

**Step 1: Write failing isolation tests.**

Set up a student with a populated `user_api_keys` row and `preferred_flash_model`, plus a household model. Assert that Flash resolves only the family model, API-key CRUD returns 403 for the student, and a parent/non-family user retains existing API-key behavior.

**Step 2: Run isolation tests to verify failure.**

Run: `uv run pytest tests/unit/server/app/test_api_keys.py tests/unit/server/handlers/test_resolve_llm_config.py -q`

Expected: current student user-level settings are still consulted.

**Step 3: Implement role isolation and the reset script.**

Make the student branch explicit and early: family availability/selection is authoritative; do not read or mutate student `user_preferences.other_preference` model fields or `user_api_keys`. Hide/deny the legacy API-key route for student roles with a backend 403. Leave parent/non-student BYOK/OAuth and custom-model paths intact.

The reset script must require an explicit database name supplied by the operator and contain only project tables, for example:

```sql
TRUNCATE TABLE
  conversation_feedback, conversation_usages, conversation_responses,
  conversation_queries, conversation_threads, checkpoints, checkpoint_blobs,
  checkpoint_writes, store, student_llm_preferences,
  household_llm_settings, household_llm_endpoints,
  user_api_keys, user_preferences, workspaces, education_memberships,
  education_households, users
RESTART IDENTITY CASCADE;
```

Before running it, inspect the exact project PostgreSQL container/database. Never run it against an unspecified URL, production database, or unrelated volume. Do not include credentials in the script or commit generated dumps.

**Step 4: Run isolation tests and the reset dry check.**

Run: `uv run pytest tests/unit/server/app/test_api_keys.py tests/unit/server/handlers/test_resolve_llm_config.py -q` and `git diff --check`.

Expected: PASS; the reset script is only reviewed in this task and is executed manually only against the approved test database.

**Step 5: Commit the isolation boundary.**

```bash
git add src/server/services/llm/config.py src/server/app/api_keys.py src/server/app/users.py scripts/reset_household_llm_test_data.sql tests/unit/server/app/test_api_keys.py tests/unit/server/handlers/test_resolve_llm_config.py
git commit -m "feat: isolate student models to household pool"
```

## Task 9: End-to-end verification and documentation

**Files:**
- Modify: `CHANGELOG.md`
- Test: `tests/integration/test_household_llm_pool_db.py`
- Test: `tests/unit/server/app/test_family_llm.py`
- Test: `web/src/pages/Settings/__tests__/HouseholdModelPoolTab.test.tsx`

**Step 1: Add the acceptance matrix.**

The integration test must exercise one parent, two students and a second household:

1. Parent creates DeepSeek Flash and Anthropic endpoints; sets DeepSeek as default.
2. Both students see the same enabled summaries but no secrets.
3. Student A selects Anthropic; Student B continues to resolve DeepSeek.
4. Parent changes default to DeepSeek/other endpoint; Student A remains on Anthropic.
5. Parent disables Anthropic; Student A falls back to the valid default and preference is cleared.
6. Parent deletes the default; students receive an empty/no-model state without a run.
7. Cross-household endpoint UUID and student API-key mutation are rejected.
8. A completed Flash run stores household/endpoint/model snapshots and replay never exposes a key/base URL secret.

**Step 2: Run the complete verification suite.**

Run:

```bash
make lint
uv run pytest tests/unit -q
uv run pytest -m integration
cd web && pnpm exec vitest run && pnpm exec tsc --noEmit
git diff --check
```

Expected: all commands pass. If PostgreSQL/Redis are not running, start only project-scoped services with `make up` after inspecting exact existing container names and ports; do not remove unrelated containers, images, volumes, or networks. Start frontend verification with `cd web && pnpm dev --host 0.0.0.0 --port 5177` and confirm the page is reachable on the LAN.

**Step 3: Update the changelog.**

Add a concise Chinese entry describing the household pool, parent-only Endpoint management, student selection/preference, automatic fallback, encrypted credentials, and model/billing snapshots. Do not mention keys, URLs, test credentials, or local database contents.

**Step 4: Commit documentation only.**

```bash
git add CHANGELOG.md
git commit -m "docs: document household LLM pool"
```

## Execution notes and commit boundaries

- Execute tasks in order; each task is intentionally small enough to review and revert independently.
- Before every implementation edit, run the task's failing test first. Do not combine the prior student model-display fixes in this feature commits; those are already in the branch and must remain untouched.
- Never use `git reset --hard`, `git checkout --`, or broad cleanup commands. The only destructive operation permitted by this plan is the explicitly reviewed test-database reset script in Task 8.
- At completion, run `git status --short` and verify that only intentional feature commits/files remain; preserve the unrelated untracked `密码.md` and never stage it.
