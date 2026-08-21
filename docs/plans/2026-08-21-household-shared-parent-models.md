# Household Shared Parent Models Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the household creator's existing model configuration the single shared model source for all household students, while removing the duplicate household endpoint pool and preserving student model preferences.

**Architecture:** Add an explicit model owner to `education_households`. Resolve a student's household model availability from the owner's existing API keys, provider configuration, model preferences, and custom models; store only a student's public model reference. Route student LLM calls through the owner's configuration with household/student provenance, never through student credentials or the removed endpoint tables.

**Tech Stack:** Python 3.13, FastAPI, async psycopg, Alembic raw SQL, existing LLM model manifest/configuration, React 19, TypeScript, TanStack Query, Vitest.

---

### Task 1: Replace household pool schema with owner and student model references

**Files:**
- Modify: `migrations/versions/033_add_household_llm_pool.py`
- Modify: `src/server/database/auth_accounts.py`
- Modify: `src/server/database/education_members.py`
- Create: `src/server/database/household_shared_models.py`
- Test: `tests/unit/server/database/test_household_shared_models.py`
- Test: `tests/unit/server/services/test_family_accounts.py`

**Step 1: Write the failing tests**

Cover creation of a household with `model_owner_user_id`, lookup of the owner for a student, rejection when the owner is not a parent member of the same household, and student preference rows storing a public model key rather than an endpoint UUID or credential fields.

**Step 2: Run the focused tests**

Run: `uv run pytest tests/unit/server/database/test_household_shared_models.py tests/unit/server/services/test_family_accounts.py -q`

Expected: FAIL because the owner column and shared-model database helpers do not exist.

**Step 3: Implement the schema and database helpers**

Rewrite the unapplied `033` migration for the approved design: add `model_owner_user_id` to `education_households` with a foreign key to `users`, initialize it during household creation, retain only a `student_llm_preferences` table with `(user_id, household_id, model_key, updated_at)`, and retain non-secret usage provenance columns without endpoint foreign keys. Remove `household_llm_endpoints`, `household_llm_settings`, their indexes, and endpoint foreign keys. Add queries that return the household owner, verify owner membership/role, read a student's preference, upsert/clear a preference, and list household membership context.

**Step 4: Make account creation set the owner**

Update `create_local_account`/household creation to insert the creating parent as `model_owner_user_id`; child creation continues to join the parent's household and does not create or copy model credentials.

**Step 5: Run the tests**

Run: `uv run pytest tests/unit/server/database/test_household_shared_models.py tests/unit/server/services/test_family_accounts.py -q`

Expected: PASS.

**Step 6: Commit**

```bash
git add migrations/versions/033_add_household_llm_pool.py src/server/database/auth_accounts.py src/server/database/education_members.py src/server/database/household_shared_models.py tests/unit/server/database/test_household_shared_models.py tests/unit/server/services/test_family_accounts.py
git commit -m "feat: assign household model owner"
```

### Task 2: Build the owner-backed shared model availability service

**Files:**
- Create: `src/server/services/household_shared_models.py`
- Modify: `src/server/services/llm/config.py`
- Modify: `src/server/database/api_keys.py`
- Modify: `src/server/app/api_keys.py`
- Test: `tests/unit/server/services/test_household_shared_models.py`
- Test: `tests/unit/server/handlers/test_resolve_llm_config.py`

**Step 1: Write failing service tests**

Test that a student resolves to the household creator, not to their own user ID; the availability projection includes every owner model with usable credentials and custom model configuration; the owner's preferred model is marked as the default; no-key catalog entries are omitted; and owner credentials never appear in the projection.

**Step 2: Run the focused tests**

Run: `uv run pytest tests/unit/server/services/test_household_shared_models.py tests/unit/server/handlers/test_resolve_llm_config.py::TestStudentHouseholdSharedModels -q`

Expected: FAIL because the service and owner-aware credential lookup do not exist.

**Step 3: Implement model projection**

Add a service that resolves a member's household and `model_owner_user_id`, loads the owner's `user_api_keys` and `other_preference`, and composes stable public model entries from the existing manifest/catalog plus `custom_models`. Include only models whose provider has a usable owner credential, stored base URL, local-provider configuration, or valid server-owned provider access under current host rules. Deduplicate by public model name and preserve manifest display metadata. Return the owner's configured default (`preferred_model` for PTC and `preferred_flash_model` fallback for Flash) without exposing API keys, full URLs, or raw custom provider secrets.

Add owner-scoped helpers to `api_keys.py`/model configuration code so the runtime can read and classify a model using the owner credentials while the authenticated student remains the audit subject. Keep student API-key CRUD blocked.

**Step 4: Replace the sealed endpoint resolver**

Change the student branch in `src/server/services/llm/config.py` to accept a public owner model key, validate it against the current owner-backed availability projection, load the owner's custom model/provider configuration, and construct the normal LLM client with owner credentials. Set `CredentialSource.HOUSEHOLD`, household ID, owner ID, student ID, public model name, and a non-secret model snapshot in runtime metadata. Never consult student preferences for provider credentials, personal BYOK, OAuth, or platform fallback.

**Step 5: Run the tests**

Run: `uv run pytest tests/unit/server/services/test_household_shared_models.py tests/unit/server/handlers/test_resolve_llm_config.py::TestStudentHouseholdSharedModels -q`

Expected: PASS.

**Step 6: Commit**

```bash
git add src/server/services/household_shared_models.py src/server/services/llm/config.py src/server/database/api_keys.py src/server/app/api_keys.py tests/unit/server/services/test_household_shared_models.py tests/unit/server/handlers/test_resolve_llm_config.py
git commit -m "feat: resolve student models from parent configuration"
```

### Task 3: Replace family LLM APIs and remove duplicate pool management

**Files:**
- Modify: `src/server/app/family_llm.py`
- Delete: `src/server/services/household_llm_pool.py`
- Delete: `src/server/database/household_llm_pool.py`
- Modify: `tests/unit/server/app/test_family_llm.py`
- Delete or rewrite: `tests/unit/server/services/test_household_llm_pool.py`
- Delete or rewrite: `tests/unit/server/database/test_household_llm_pool.py`
- Modify: `tests/integration/test_household_llm_pool_db.py`

**Step 1: Write failing API contract tests**

Test that `GET /api/v1/family/llm-availability` returns owner-backed models and selected preference/default; `PUT /api/v1/family/llm-preference` accepts only an available public model key and affects only the current student; parent and student requests cannot create/update/delete pool endpoints; and no response contains secrets.

**Step 2: Run the focused tests**

Run: `uv run pytest tests/unit/server/app/test_family_llm.py -q`

Expected: FAIL against the old endpoint CRUD contracts.

**Step 3: Implement the new API**

Keep only availability and student-preference routes. Have parent availability use the same owner-backed projection for read-only visibility. Return `model_key`, display name, provider, model ID, capabilities, selected source, and explicit empty-state metadata. Validate preference keys server-side and return `409`/`404` for missing or disabled models. Remove endpoint CRUD request models, service imports, and legacy pool routes; do not leave a second write path.

**Step 4: Update integration fixtures and database assertions**

Replace endpoint-table fixtures with owner/member, user API-key, custom-model, and student-preference fixtures. Verify deleting a household cascades preferences and that usage rows retain non-secret household/model snapshots.

**Step 5: Run tests**

Run: `uv run pytest tests/unit/server/app/test_family_llm.py tests/integration/test_household_llm_pool_db.py -q`

Expected: PASS for the rewritten contracts; unrelated repository fixture failures remain outside this change.

**Step 6: Commit**

```bash
git add src/server/app/family_llm.py tests/unit/server/app/test_family_llm.py tests/unit/server/services/test_household_llm_pool.py tests/unit/server/database/test_household_llm_pool.py tests/integration/test_household_llm_pool_db.py
git rm src/server/services/household_llm_pool.py src/server/database/household_llm_pool.py
git commit -m "refactor: remove duplicate household model pool"
```

### Task 4: Make the parent Model settings page the only management UI

**Files:**
- Modify: `web/src/pages/Settings/Settings.tsx`
- Modify: `web/src/pages/Settings/api.ts`
- Modify: `web/src/pages/Settings/queries.ts`
- Modify: `web/src/pages/Settings/panels/ModelTab.tsx`
- Delete: `web/src/pages/Settings/panels/HouseholdModelPoolTab.tsx`
- Modify: `web/src/pages/Settings/__tests__/Settings.family.test.tsx`
- Delete or rewrite: `web/src/pages/Settings/__tests__/HouseholdModelPoolTab.test.tsx`
- Modify: `web/src/pages/Settings/__tests__/familyLlmApi.test.ts`

**Step 1: Write failing UI tests**

Assert that a parent sees model/provider management only under the existing `model` tab, no `family-models` tab is rendered, and a student sees neither provider credentials nor personal model-management controls. API tests should cover availability and preference only.

**Step 2: Run the focused tests**

Run: `cd web && pnpm vitest run src/pages/Settings/__tests__/Settings.family.test.tsx src/pages/Settings/__tests__/familyLlmApi.test.ts`

Expected: FAIL because the old family-models tab and pool API helpers remain.

**Step 3: Implement the UI cleanup**

Remove the family-models navigation and panel. Keep `ModelTab` as the parent's full management surface, including Setup/Provider custom models. Add an owner/read-only household availability notice only where useful; do not add duplicate endpoint forms. Remove pool API types, methods, query keys, mutations, and cache invalidations. Keep only availability and student preference hooks.

**Step 4: Run the tests**

Run: `cd web && pnpm vitest run src/pages/Settings/__tests__/Settings.family.test.tsx src/pages/Settings/__tests__/familyLlmApi.test.ts`

Expected: PASS.

**Step 5: Commit**

```bash
git add web/src/pages/Settings/Settings.tsx web/src/pages/Settings/api.ts web/src/pages/Settings/queries.ts web/src/pages/Settings/panels/ModelTab.tsx web/src/pages/Settings/__tests__/Settings.family.test.tsx web/src/pages/Settings/__tests__/familyLlmApi.test.ts
git rm web/src/pages/Settings/panels/HouseholdModelPoolTab.tsx web/src/pages/Settings/__tests__/HouseholdModelPoolTab.test.tsx
git commit -m "refactor: use parent model settings for household models"
```

### Task 5: Update student chat model selection and empty/error states

**Files:**
- Modify: `web/src/pages/ChatAgent/components/chatView/familyModelAvailability.ts`
- Modify: `web/src/pages/ChatAgent/components/ChatView.tsx`
- Modify: `web/src/components/ui/chat-input.modelMenu.tsx`
- Modify: `web/src/components/ui/chat-input.tsx`
- Modify: `web/src/pages/ChatAgent/components/__tests__/familyModelAvailability.test.ts`
- Modify: relevant ChatInput/ChatView tests

**Step 1: Write failing tests**

Cover all owner-backed models appearing in the student selector, selected owner default on first load, persisted student preference, refresh after owner configuration changes, and explicit “家庭尚未配置可用模型”/retry states instead of “Sonnet5” or an indefinite spinner.

**Step 2: Run focused tests**

Run: `cd web && pnpm vitest run src/pages/ChatAgent/components/__tests__/familyModelAvailability.test.ts src/components/ui/*test*`

Expected: FAIL for the old endpoint-shaped data and misleading loading/error states.

**Step 3: Implement selector wiring**

Keep the existing family model selector mechanics but change its option type to public model keys and owner model metadata. Ensure a model choice writes only the student preference. Do not update `user_preferences.preferred_model` from the student UI. When availability is empty, disable send/model selection as appropriate and display the empty state; when availability fails, show a retry action that refetches the household projection.

**Step 4: Run focused tests**

Run: `cd web && pnpm vitest run src/pages/ChatAgent/components/__tests__/familyModelAvailability.test.ts`

Expected: PASS.

**Step 5: Commit**

```bash
git add web/src/pages/ChatAgent/components/chatView/familyModelAvailability.ts web/src/pages/ChatAgent/components/ChatView.tsx web/src/components/ui/chat-input.modelMenu.tsx web/src/components/ui/chat-input.tsx web/src/pages/ChatAgent/components/__tests__/familyModelAvailability.test.ts
git commit -m "fix: show shared parent models to students"
```

### Task 6: Remove misleading student model configuration access and update changelog

**Files:**
- Modify: `web/src/pages/Settings/Settings.tsx`
- Modify: `web/src/pages/Settings/panels/ModelTab.tsx`
- Modify: `src/server/app/api_keys.py`
- Modify: `CHANGELOG.md`
- Test: `tests/unit/server/app/test_api_keys.py` or the existing API-key test module

**Step 1: Write the failing access tests**

Verify all student API-key/provider/model-management routes return `403`, while the student read-only household availability route succeeds. Verify a student cannot change personal `preferred_model` values through the model settings UI.

**Step 2: Implement access cleanup**

Keep backend authorization as the source of truth and ensure every provider/key/model management endpoint uses the existing student guard. Render a student-safe read-only model summary or omit the Model tab entirely; never render controls that are guaranteed to fail. Preserve parent access to the original model page.

**Step 3: Run tests**

Run: `uv run pytest tests/unit/server/app/test_api_keys.py -q` and `cd web && pnpm vitest run src/pages/Settings`

Expected: PASS.

**Step 4: Update changelog and commit**

Add a concise Chinese entry describing the single parent model source, student shared-model selection, and removal of duplicate household pool management. Then run `git diff --check`, stage only the implementation files and changelog, and create an atomic commit.

### Task 7: Verification and runtime smoke test

**Files:** None.

**Step 1: Run focused backend checks**

Run: `uv run ruff check src tests` and the focused unit/integration commands from Tasks 1-3.

**Step 2: Run focused frontend checks**

Run: `cd web && pnpm vitest run` for affected tests and `pnpm tsc --noEmit`.

**Step 3: Apply the migration to the project test database**

Run the project migration command used by the repository, confirm `education_households.model_owner_user_id` and `student_llm_preferences.model_key` exist, and confirm the removed endpoint tables are absent. Do not touch unrelated containers or read/modify `temp_pwd.txt`.

**Step 4: Start services and smoke-test**

Start the backend and frontend according to `AGENTS.md` (`server.py --reload`, frontend on `0.0.0.0:5177`). Log in as the owner and student: configure two parent models once, verify both appear to the student, select one as student, change the owner's configuration, refresh the student view, and verify the new availability plus preserved student preference behavior.

**Step 5: Final verification**

Run `git status --short`, `git diff --check`, and confirm no credentials, generated files, or `temp_pwd.txt` are staged. Update the changelog if any verified behavior changed during smoke testing.
