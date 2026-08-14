# Platform Model Profile Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let credential-less family textbook PTC jobs use the approved deployment-level `silicon / deepseek-ai/DeepSeek-V4-Flash` platform model profile without exposing the source account or its secret.

**Architecture:** A small LLM service reads the non-secret deployment profile and resolves its source account through existing encrypted BYOK and custom-model helpers. `resolve_model_client` invokes that profile only after OAuth and the requesting user's BYOK both fail. The managed textbook graph receives only the resolved LLM client and keeps its existing `user_id=None` capability boundary.

**Tech Stack:** Python 3.13+, FastAPI services, async psycopg, Pydantic agent configuration, pytest, existing LLM factory.

---

### Task 1: Define and test the platform-profile resolver

**Files:**
- Create: `src/server/services/llm/platform_profile.py`
- Test: `tests/unit/server/services/test_platform_model_profile.py`

**Step 1: Write failing tests for disabled and enabled profiles**

```python
async def test_profile_is_disabled_without_both_environment_values(monkeypatch):
    monkeypatch.delenv("PLATFORM_LLM_SOURCE_EMAIL", raising=False)
    monkeypatch.delenv("PLATFORM_LLM_MODEL", raising=False)
    assert await resolve_platform_llm_client(cache_key="run") is None

async def test_profile_resolves_only_the_declared_source_account(monkeypatch):
    monkeypatch.setenv("PLATFORM_LLM_SOURCE_EMAIL", "service@example.test")
    monkeypatch.setenv("PLATFORM_LLM_MODEL", "model-a")
    monkeypatch.setattr(module, "get_user_id_by_email", AsyncMock(return_value="service-user"))
    monkeypatch.setattr(module, "is_byok_active", AsyncMock(return_value=True))
    monkeypatch.setattr(module, "resolve_byok_llm_client", AsyncMock(return_value=client))
    assert await resolve_platform_llm_client(cache_key="run") is client
```
**Step 2: Run the focused test and confirm it fails because the resolver is absent**

Run: `uv run pytest tests/unit/server/services/test_platform_model_profile.py -q`

**Step 3: Implement the minimal resolver**

- Read both environment variables at call time so tests and process restarts see changes.
- Look up only the configured email, verify its BYOK state, and call
  `resolve_byok_llm_client` with the configured model.
- Use sanitized logs only; never include API keys, Base URLs, account IDs, or emails.

**Step 4: Run the focused test and confirm it passes**

Run: `uv run pytest tests/unit/server/services/test_platform_model_profile.py -q`

**Step 5: Commit**

```bash
git add src/server/services/llm/platform_profile.py tests/unit/server/services/test_platform_model_profile.py CHANGELOG.md
git commit -m "feat(llm): resolve deployment platform model profile"
```

### Task 2: Route credential-less system models through the profile

**Files:**
- Modify: `src/server/services/llm/config.py`
- Test: `tests/unit/server/handlers/chat/test_resolve_model_client.py`

**Step 1: Write a failing platform-profile fallback test**

```python
async def test_platform_profile_preempts_legacy_env_fallback(monkeypatch):
    monkeypatch.setattr(config, "resolve_platform_llm_client", AsyncMock(return_value=profile_client))
    result = await resolve_model_client("parent", "system-model", is_byok=False,
                                        allow_platform_fallback=True)
    assert result.client is profile_client
    assert result.credential_source == CredentialSource.PLATFORM
```

**Step 2: Run the focused test and confirm it fails**

Run: `uv run pytest tests/unit/server/handlers/chat/test_resolve_model_client.py -q`

**Step 3: Implement the narrow fallback**

- Keep OAuth and per-user BYOK priority unchanged.
- For a system model with platform fallback enabled, request the profile client first.
- Preserve the legacy environment-backed `create_llm` fallback when no profile is configured.
- Make a configured profile activate eager platform fallback in `resolve_llm_config`, so a managed teaching job does not hit a lazy missing-key path.

**Step 4: Run the resolver and managed-teaching tests**

Run: `uv run pytest tests/unit/server/handlers/chat/test_resolve_model_client.py tests/unit/server/services/test_education_teaching_jobs.py -q`

**Step 5: Commit**

```bash
git add src/server/services/llm/config.py tests/unit/server/handlers/chat/test_resolve_model_client.py CHANGELOG.md
git commit -m "fix(llm): use platform profile for managed fallback"
```

### Task 3: Document configuration and validate the real textbook job

**Files:**
- Modify: `.env.example`
- Modify: `CHANGELOG.md`
- Inspect: `src/server/services/education_teaching_jobs.py`

**Step 1: Add non-secret environment-variable documentation**

```text
# Optional platform fallback profile. Values identify a service-owned account;
# its encrypted BYOK credential remains in PostgreSQL.
PLATFORM_LLM_SOURCE_EMAIL=
PLATFORM_LLM_MODEL=
```

**Step 2: Configure only the local deployment runtime with the approved non-secret values**

Do not write an API key into the repository or print it. Restart only the current-worktree backend and prove its PID, working directory, listener, and effective profile-variable presence.

**Step 3: Resume the frozen real teaching job and inspect safe projections**

Use the real authenticated parent browser session. Record request status, task phase, console/network errors, and confirm no response exposes `storage_key`, `api_key`, `base_url`, sandbox details, or the source account.

**Step 4: Run verification**

Run:

```bash
uv run pytest tests/unit/server/services/test_platform_model_profile.py \
  tests/unit/server/handlers/chat/test_resolve_model_client.py \
  tests/unit/server/services/test_education_teaching_jobs.py -q
make lint
cd web && pnpm build
```

**Step 5: Commit**

```bash
git add .env.example CHANGELOG.md
git commit -m "docs(config): describe platform model profile"
```
