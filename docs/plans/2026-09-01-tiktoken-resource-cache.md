# Deterministic tiktoken Resource Cache Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship `cl100k_base` with LangAlpha, prepare a stable verified runtime cache at startup, retain approximate counting when exact preparation fails, and expose a localized retry warning in model settings.

**Architecture:** A provider-neutral resource module owns the official URL, digest, fixed cache resolution, verification, atomic seeding, and bounded download. Compaction consumes only a verified cache and never permanently caches its approximate fallback. A small authenticated runtime-resource API and model-settings component expose status and retry without allowing caller-controlled download inputs.

**Tech Stack:** Python 3.13, tiktoken, FastAPI, asyncio, pytest, React 19, TypeScript, TanStack Query, Vitest, i18next, Docker.

---

### Task 1: Add the verified vocabulary resource manager

**Files:**
- Create: `src/ptc_agent/tokenizer_resource.py`
- Create: `src/ptc_agent/resources/tiktoken/cl100k_base.tiktoken`
- Create: `tests/unit/ptc_agent/test_tokenizer_resource.py`

**Step 1: Write the failing resource-manager tests**

Cover these contracts with temporary cache directories and monkeypatched
download responses:

```python
def test_valid_cache_is_reused_without_download(tmp_path, monkeypatch): ...
def test_bundled_vocabulary_seeds_missing_cache_atomically(tmp_path, monkeypatch): ...
def test_missing_local_vocabulary_downloads_verified_official_copy(tmp_path, monkeypatch): ...
def test_hash_mismatch_returns_approximate_and_leaves_no_cache(tmp_path, monkeypatch): ...
def test_environment_cache_directory_overrides_repository_default(tmp_path, monkeypatch): ...
```

Assertions must verify the official SHA-256, tiktoken URL-cache filename
`9b5ad71b2ce5302211f9c61530b329a4922fc6a4`, absence of leftover temporary
files, and a public status shape containing only `encoding`, `status`, `exact`,
and `error_code`.

**Step 2: Run the tests and confirm they fail**

Run:

```bash
uv run pytest tests/unit/ptc_agent/test_tokenizer_resource.py -q
```

Expected: FAIL because `ptc_agent.tokenizer_resource` does not exist.

**Step 3: Download and verify the official code resource**

Download only:

```text
https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken
```

Place it at the resource path above, verify its size is `1681126` bytes, and
verify SHA-256:

```text
223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7
```

Do not commit any temporary download file.

**Step 4: Implement the minimal resource manager**

Define immutable constants and a frozen status value:

```python
CL100K_BASE_ENCODING = "cl100k_base"
CL100K_BASE_URL = "https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
CL100K_BASE_SHA256 = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
CL100K_BASE_CACHE_KEY = "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"

@dataclass(frozen=True, slots=True)
class TokenizerResourceStatus:
    encoding: str
    status: Literal["ready", "approximate"]
    exact: bool
    error_code: str | None = None
```

Implement:

```python
def resolve_tiktoken_cache_dir() -> Path: ...
def get_tokenizer_resource_status() -> TokenizerResourceStatus: ...
def prepare_tokenizer_resource(*, allow_download: bool = True) -> TokenizerResourceStatus: ...
```

The default directory is repository-relative `var/cache/tiktoken`; an explicit
`TIKTOKEN_CACHE_DIR` remains authoritative. Preparation sets the standard
environment variable, verifies existing cache, atomically copies a valid
bundled resource, then performs one bounded official download only when both
local options are unusable. Network, hash, and permission failures return
`approximate` rather than raising.

**Step 5: Run focused tests**

```bash
uv run pytest tests/unit/ptc_agent/test_tokenizer_resource.py -q
uv run ruff check src/ptc_agent/tokenizer_resource.py tests/unit/ptc_agent/test_tokenizer_resource.py
```

Expected: all tests pass and Ruff reports no errors.

**Step 6: Commit**

```bash
git add src/ptc_agent/tokenizer_resource.py src/ptc_agent/resources/tiktoken/cl100k_base.tiktoken tests/unit/ptc_agent/test_tokenizer_resource.py
git commit -m "feat: bundle and prepare cl100k tokenizer resource"
```

### Task 2: Integrate startup preparation and recoverable compaction fallback

**Files:**
- Modify: `src/ptc_agent/agent/middleware/compaction/utils.py`
- Modify: `src/server/app/setup.py`
- Modify: `tests/unit/middleware/compaction/test_utils.py`
- Create: `tests/unit/server/app/test_tokenizer_startup.py`

**Step 1: Add failing recovery and startup tests**

Extend the compaction test so an approximate result is not stored in
`_tiktoken_encoder`, then simulate the cache becoming ready and assert that the
next call obtains and caches the real tiktoken encoder:

```python
def test_tiktoken_fallback_recovers_without_process_restart(monkeypatch): ...
```

Add an async startup-helper test showing that preparation runs in a worker
thread and that an approximate status logs degradation without raising:

```python
@pytest.mark.asyncio
async def test_prepare_tokenizer_at_startup_is_non_fatal(monkeypatch, caplog): ...
```

**Step 2: Run tests and confirm failure**

```bash
uv run pytest tests/unit/middleware/compaction/test_utils.py tests/unit/server/app/test_tokenizer_startup.py -q
```

Expected: FAIL because compaction still permanently caches the approximate
encoder and the startup helper is absent.

**Step 3: Implement the integration**

Change `_get_tiktoken_encoder()` to:

```python
status = prepare_tokenizer_resource(allow_download=False)
if not status.exact:
    return _ApproximateTokenEncoder()
_tiktoken_encoder = tiktoken.get_encoding(CL100K_BASE_ENCODING)
return _tiktoken_encoder
```

The exception path must also return, but not assign, the approximation.

Add a small async setup helper that calls
`prepare_tokenizer_resource(allow_download=True)` through `asyncio.to_thread`
and invoke it near the start of FastAPI lifespan after logging is configured.
Log `ready` at info level and `approximate` at error level with the stable error
code only.

**Step 4: Run focused regression tests**

```bash
uv run pytest tests/unit/middleware/compaction/test_utils.py tests/unit/server/app/test_tokenizer_startup.py -q
uv run ruff check src/ptc_agent/agent/middleware/compaction/utils.py src/server/app/setup.py tests/unit/middleware/compaction/test_utils.py tests/unit/server/app/test_tokenizer_startup.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/ptc_agent/agent/middleware/compaction/utils.py src/server/app/setup.py tests/unit/middleware/compaction/test_utils.py tests/unit/server/app/test_tokenizer_startup.py
git commit -m "fix: recover exact token counting after offline startup"
```

### Task 3: Expose authenticated tokenizer status and retry

**Files:**
- Create: `src/server/app/runtime_resources.py`
- Modify: `src/server/app/setup.py`
- Create: `tests/unit/server/app/test_runtime_resources.py`

**Step 1: Write failing API tests**

Create a test FastAPI app using the established `create_test_app()` helper and
cover:

```python
async def test_get_tokenizer_status_returns_safe_public_shape(client): ...
async def test_retry_download_returns_ready_status(client): ...
async def test_retry_download_returns_503_when_approximation_remains(client): ...
```

Assert that retry requires `CurrentUserId`, accepts no request URL/body, runs
preparation in a thread, and never exposes raw exception text or filesystem
paths.

**Step 2: Run tests and confirm failure**

```bash
uv run pytest tests/unit/server/app/test_runtime_resources.py -q
```

Expected: FAIL because the router is absent.

**Step 3: Implement and register the router**

Add:

```text
GET  /api/v1/runtime-resources/tokenizer
POST /api/v1/runtime-resources/tokenizer/download
```

Both endpoints require `CurrentUserId`. GET returns the current verified cache
status without network I/O. POST invokes the same preparation service with
downloads enabled. If exact counting remains unavailable, return HTTP 503 with
a stable detail code such as `tokenizer_vocabulary_unavailable`.

Register the router in `src/server/app/setup.py` alongside other application
routers.

**Step 4: Run focused tests and lint**

```bash
uv run pytest tests/unit/server/app/test_runtime_resources.py tests/unit/server/app/test_generic_router_registration.py -q
uv run ruff check src/server/app/runtime_resources.py src/server/app/setup.py tests/unit/server/app/test_runtime_resources.py
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/app/runtime_resources.py src/server/app/setup.py tests/unit/server/app/test_runtime_resources.py
git commit -m "feat: expose tokenizer resource recovery API"
```

### Task 4: Add the localized model-settings warning

**Files:**
- Modify: `web/src/api/model.ts`
- Modify: `web/src/lib/queryKeys.ts`
- Create: `web/src/pages/Settings/components/TokenizerStatusAlert.tsx`
- Modify: `web/src/pages/Settings/panels/ModelTab.tsx`
- Modify: `web/src/locales/zh-CN.json`
- Modify: `web/src/locales/en-US.json`
- Create: `web/src/pages/Settings/__tests__/Settings.tokenizerStatus.test.tsx`

**Step 1: Write failing UI tests**

Mock the resource API and verify:

```typescript
it('hides the tokenizer alert when exact counting is ready', async () => { ... });
it('shows a prominent localized alert while approximate counting is active', async () => { ... });
it('retries the fixed download and removes the alert on success', async () => { ... });
it('keeps the alert visible and shows a localized failure after retry fails', async () => { ... });
```

The alert must use `role="alert"`; the action must be disabled and show its
downloading label while the mutation is pending.

**Step 2: Run tests and confirm failure**

```bash
cd web && pnpm test --run src/pages/Settings/__tests__/Settings.tokenizerStatus.test.tsx
```

Expected: FAIL because the API client and alert component are absent.

**Step 3: Implement API types and query key**

Add a strict client type:

```typescript
export interface TokenizerResourceStatus {
  encoding: 'cl100k_base';
  status: 'ready' | 'approximate';
  exact: boolean;
  error_code: string | null;
}
```

Add GET and POST functions for the fixed resource endpoints and a
`queryKeys.runtimeResources.tokenizer()` key.

**Step 4: Implement and place the alert**

`TokenizerStatusAlert` owns its query and retry mutation. Render it above
`ModelTierConfig` in `ModelTab`. Use existing theme tokens, Lucide icons, and
the standard small `Button`; do not add a modal or a new settings section.

Add equivalent keys under `settings` in both locale files for the title,
description, retry action, downloading action, and retry failure.

**Step 5: Run frontend verification**

```bash
cd web && pnpm test --run src/pages/Settings/__tests__/Settings.tokenizerStatus.test.tsx
cd web && pnpm typecheck
```

Expected: tests and TypeScript checks pass.

**Step 6: Commit**

```bash
git add web/src/api/model.ts web/src/lib/queryKeys.ts web/src/pages/Settings/components/TokenizerStatusAlert.tsx web/src/pages/Settings/panels/ModelTab.tsx web/src/locales/zh-CN.json web/src/locales/en-US.json web/src/pages/Settings/__tests__/Settings.tokenizerStatus.test.tsx
git commit -m "feat: surface tokenizer recovery in model settings"
```

### Task 5: Configure Docker cache seeding and operator documentation

**Files:**
- Modify: `deploy/Dockerfile.backend`
- Modify: `deploy/Dockerfile.dev`
- Modify: `.env.example`
- Create: `tests/unit/test_tiktoken_dockerfiles.py`
- Modify: `CHANGELOG.md`

**Step 1: Write failing static Dockerfile tests**

For both backend Dockerfiles assert:

```python
assert "TIKTOKEN_CACHE_DIR=/app/var/cache/tiktoken" in source
assert "9b5ad71b2ce5302211f9c61530b329a4922fc6a4" in source
assert "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7" in source
assert "sha256sum -c" in source
assert "chown" in source
```

Also assert that `deploy/Dockerfile.web` and `Dockerfile.sandbox` do not gain
the backend cache configuration.

**Step 2: Run the test and confirm failure**

```bash
uv run pytest tests/unit/test_tiktoken_dockerfiles.py -q
```

Expected: FAIL because the backend images are not configured yet.

**Step 3: Update both backend Dockerfiles**

After `COPY src/ src/`, set:

```dockerfile
ENV TIKTOKEN_CACHE_DIR=/app/var/cache/tiktoken
```

Create the directory, verify the bundled source with `sha256sum -c`, copy it
to the fixed tiktoken cache-key filename, and explicitly `chown` the directory
to the image's existing runtime UID/GID. Do not introduce a new `USER`, since
that could break Docker socket and browser behavior.

**Step 4: Document the optional environment override**

Add a commented `.env.example` entry explaining that configuration is not
required and is intended only for a custom or persistent cache location.

Add a Chinese `CHANGELOG.md` section covering the bundled exact vocabulary,
startup repair, approximate fallback, settings warning/retry, and Docker cache
seeding.

**Step 5: Run static checks without building images**

```bash
uv run pytest tests/unit/test_tiktoken_dockerfiles.py -q
git diff --check
```

Expected: PASS. Do not run `docker build`.

**Step 6: Commit**

```bash
git add deploy/Dockerfile.backend deploy/Dockerfile.dev .env.example tests/unit/test_tiktoken_dockerfiles.py CHANGELOG.md
git commit -m "build: seed verified tiktoken cache in backend images"
```

### Task 6: Full verification and service refresh

**Files:**
- Modify only if verification finds a scoped defect.

**Step 1: Verify the committed resource directly**

```bash
wc -c src/ptc_agent/resources/tiktoken/cl100k_base.tiktoken
shasum -a 256 src/ptc_agent/resources/tiktoken/cl100k_base.tiktoken
```

Expected: `1681126` bytes and the fixed official SHA-256.

**Step 2: Run focused backend tests**

```bash
uv run pytest tests/unit/ptc_agent/test_tokenizer_resource.py tests/unit/middleware/compaction/test_utils.py tests/unit/server/app/test_tokenizer_startup.py tests/unit/server/app/test_runtime_resources.py tests/unit/test_tiktoken_dockerfiles.py -q
```

Expected: PASS.

**Step 3: Run broader backend checks**

```bash
uv run ruff check src/ptc_agent/tokenizer_resource.py src/ptc_agent/agent/middleware/compaction/utils.py src/server/app/runtime_resources.py src/server/app/setup.py tests/unit/ptc_agent/test_tokenizer_resource.py tests/unit/middleware/compaction/test_utils.py tests/unit/server/app/test_tokenizer_startup.py tests/unit/server/app/test_runtime_resources.py tests/unit/test_tiktoken_dockerfiles.py
uv run pytest tests/unit -q
```

Expected: Ruff and unit suite pass.

**Step 4: Run frontend checks**

```bash
cd web && pnpm test --run src/pages/Settings/__tests__/Settings.tokenizerStatus.test.tsx
cd web && pnpm typecheck
```

Expected: PASS.

**Step 5: Inspect final history and worktree**

```bash
git status --short
git log --oneline -8
```

Expected: no uncommitted task files and atomic commits for each substantial
change.

**Step 6: Restart runtime services without changing assigned ports**

Restart the backend on `0.0.0.0:8000` and the channel worker using the existing
worktree service mechanism. Keep the frontend on `0.0.0.0:5177`; restart it
only if the running Vite process is not already serving this worktree. Verify
the backend health endpoint and LAN-facing frontend reachability. Do not build
Docker images.
