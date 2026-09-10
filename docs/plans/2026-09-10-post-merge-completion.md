# Post-Merge Completion Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Finish the staged `origin/main` platform-core merge: re-apply the local
education and household features onto the upstream shapes, get every unit suite
green, land the deferred workspace-file blob persistence, and prove the PTC agent
runs with a Docker sandbox.

**Architecture:** The merge is already applied for everything the classifier
called TAKE (platform code the local branch merely carried an older copy of).
What is left is the local product surface: the managed-textbook (education) line,
which extends platform classes with extra methods and parameters rather than
importing local modules, and the household LLM resolution, which upstream split
across `llm/{config,clients,availability}.py`. Both are re-applied onto the
upstream shapes instead of reverting upstream. Local-only product files and their
tests are never overwritten.

**Tech Stack:** Python 3.13+, FastAPI, Pydantic, LangGraph, async psycopg, Alembic
raw SQL, pytest, Docker sandbox provider, uv, pnpm.

**Branch:** `feature/platform-core-migration`, worktree
`/Users/seanlee/.config/superpowers/worktrees/langalpha/platform-core-migration`.

**Rollback:** `git reset --hard checkpoint/pre-core-merge`.
Merge commits so far: `df740f00` (TAKE set applied), `da954580` (household
billing provenance + first failures cleared).

**Rules for every task:**

- Never overwrite or delete a path in `docs/plans/core-merge-keep-list.txt`.
- Prefer upstream's shape; re-apply local behaviour on top of it.
- One task = one commit, with the verification output quoted in the message.
- Update `CHANGELOG.md` (Chinese) and the migration runbook when a task lands.

---

## Task 1: Re-apply the managed-textbook integration points

**Why:** nine `tests/unit/ptc_agent` failures are all "the local education feature
extended a platform class and the extension was dropped".

**Files:**

- Modify: `src/ptc_agent/core/sandbox/ptc_sandbox.py`
- Modify: `src/ptc_agent/core/session.py`
- Modify: `src/ptc_agent/agent/graph.py`
- Modify: `src/ptc_agent/agent/agent.py`
- Modify: the bash tool factory used by managed execution
- Delete: `tests/unit/ptc_agent/core/sandbox/test_generic_sandbox_packages.py`
  (asserts retired finance packages are skipped; this branch keeps finance)

**Step 1: See the exact failures**

Run: `uv run pytest tests/unit/ptc_agent -q`
Expected: FAIL with `PTCSandbox has no attribute setup_managed_textbook_job`,
`Session has no attribute initialize_managed_textbook`,
`build_ptc_graph_with_session() got an unexpected keyword argument 'managed_policy'`,
`module 'ptc_agent.agent.agent' has no attribute 'get_skill_registry'`,
`create_execute_bash_tool() got an unexpected keyword argument 'command_validator'`.

**Step 2: Recover each local piece from the checkpoint**

```bash
git show checkpoint/pre-core-merge:src/ptc_agent/core/sandbox/ptc_sandbox.py | rg -n "setup_managed_textbook_job" -A 30
git show checkpoint/pre-core-merge:src/ptc_agent/core/session.py | rg -n "initialize_managed_textbook" -A 45
git show checkpoint/pre-core-merge:src/ptc_agent/agent/graph.py | rg -n "managed_policy" -B 4 -A 22
git show checkpoint/pre-core-merge:src/ptc_agent/agent/agent.py | rg -n "get_skill_registry" -B 4 -A 18
```

**Step 3: Paste them into the upstream files**

Each restored symbol goes back with its docstring, next to the upstream method it
belongs to. `build_ptc_graph_with_session` gets `managed_policy: Any | None = None`
back plus the managed branch that nulls `user_id`, `store` and `on_signed_url`,
forces `plan_mode = False`, and sets `disable_subagents` from the policy.

**Step 4: Run the suite**

Run: `uv run pytest tests/unit/ptc_agent -q`
Expected: PASS, 0 failures.

**Step 5: Commit**

```bash
git add -A src/ptc_agent tests/unit/ptc_agent
git commit -m "fix: re-apply managed-textbook hooks on the upstream runtime"
```

---

## Task 2: Re-home the household LLM resolution on the upstream split

**Why:** `src/server/services/llm/config.py` locally is the pre-split monolith
(client building + BYOK walking + household resolution), while upstream split it
into `clients.py`, `availability.py` and `config.py`. The merge keeps the monolith
for now, which is why `availability.py` carries one compat alias.

**Files:**

- Modify: `src/server/services/llm/config.py` (take upstream's version)
- Modify: `src/server/services/llm/clients.py` (take upstream's version)
- Modify: `src/server/services/llm/availability.py` (take upstream's; drop the
  `raise_byok_key_required = _raise_byok_key_required` alias)
- Create: `src/server/services/llm/household.py`
- Modify: every caller of `resolve_household_llm_client`, `get_household_context`,
  `resolve_byok_llm_client`, `resolve_model_client`, `classify_model`,
  `resolved_model_name`
- Test: `tests/unit/llms/test_household_billing_metadata.py`,
  `tests/unit/server/handlers/test_resolve_llm_config*.py`

**Step 1: Confirm the upstream shapes**

Run: `git show origin/main:src/server/services/llm/config.py | rg -n "^def |^class "`
Expected: only `ModelSelection`, `load_user_context`, `select_model`,
`apply_compaction`; the client-building half lives in `clients.py`.

**Step 2: Take the three upstream files and delete the alias**

```bash
git checkout origin/main -- src/server/services/llm/config.py src/server/services/llm/clients.py src/server/services/llm/availability.py
```

**Step 3: Move the household logic into `household.py`**

From `git show checkpoint/pre-core-merge:src/server/services/llm/config.py`:
`get_household_context`, `_student_household_context`,
`_resolve_student_household_config`, `_household_runtime_metadata`, and
`resolve_household_llm_client` already rewritten for plan A (billing principal =
owner; client stamped `billing_type="byok"`, `credential_source="household"`,
`household_id`, `model_owner_user_id`, `student_user_id`).

**Step 4: Wire it into upstream's selection path**

`select_model` / `load_user_context` call the household resolver when the account
is a household student. Keep the local rule: a student never falls back to a
personal model.

**Step 5: Fix the callers**

Re-point imports at the upstream names (`clients.py` for client resolution,
`config.py` for selection) and `household.py` for the household entry points.
Do not add new aliases.

**Step 6: Run the focused suites**

Run: `uv run pytest tests/unit/llms tests/unit/server/handlers/test_resolve_llm_config.py tests/unit/server/services/test_household_shared_models.py -q`
Expected: PASS.

**Step 7: Commit**

```bash
git add -A src/server/services/llm tests
git commit -m "refactor: move household LLM resolution onto the upstream llm split"
```

---

## Task 3: Merge the remaining hand-merge files

Still unmerged from `docs/plans/core-merge-hand-merge.txt`:
`src/server/app/setup.py`, `src/server/app/threads/create.py`,
`src/server/app/threads/messaging.py`, `src/server/app/workspaces.py`,
`src/server/app/vault.py`, `src/server/handlers/chat/error_handling.py`,
`src/server/handlers/chat/request_prep.py`,
`src/server/services/runs/recovery.py`,
`src/server/services/persistence/usage.py`,
`src/server/services/user_data_io.py`, `src/server/utils/api.py`,
`src/server/app/mcp_servers.py`, `src/server/app/api_keys.py`.

**Step 1: For each file, list the local-only symbols**

```bash
git show checkpoint/pre-core-merge:<file> | rg -n "^def |^async def |^class " > /tmp/local-syms.txt
git show origin/main:<file> | rg -n "^def |^async def |^class " > /tmp/origin-syms.txt
diff /tmp/local-syms.txt /tmp/origin-syms.txt
```

**Step 2: Take the upstream file, then re-insert only the local-only symbols**

```bash
git checkout origin/main -- <file>
```

For `setup.py` that means the education, documents, channels, family, speech and
runtime-resource routers; for `threads/messaging.py` the student flash route
guard; for `workspaces.py` the local ownership checks the education routes rely
on.

**Step 3: Verify after each file**

Run: `uv run python -c "import src.server.app.setup"` then
`uv run pytest tests/unit/server -q -x`
Expected: import OK, no new failures versus the previous file.

**Step 4: Commit per coherent group** (routes, handlers, services), not one giant
commit.

---

## Task 4: Retire the local-only tests whose subject moved upstream

**Files:** the non-product entries from:

```bash
python3 - <<'PY'
import subprocess, re
def tree(ref):
    return set(subprocess.run(['git','ls-tree','-r','--name-only',ref,'tests'],capture_output=True,text=True).stdout.split())
local_only = {p for p in tree('HEAD') - tree('origin/main') if p.endswith('.py')}
keep = re.compile(r'(education|student|homework|textbook|document|pdf|channel|wechat|household|family|speech|asr|tokenizer)')
print('\n'.join(sorted(p for p in local_only if not keep.search(p))))
PY
```

**Rule:** `tests/unit/migrations/test_*_migration.py` validate our local `046`–`057`
chain — keep them. `tests/unit/server/app/test_local_auth.py`,
`test_runtime_resources.py`, `test_skills.py`,
`tests/unit/server/auth/test_local_sessions.py`,
`tests/unit/server/services/test_task_calendar.py` and
`test_platform_model_profile.py` are local product — keep them. Everything else
whose subject moved upstream is replaced by the upstream test file that covers it,
or deleted when upstream deleted it (the `test_multimodal_model_call.py` →
`test_multimodal_read.py` + `test_multimodal_strip.py` rename is the worked
example, already done).

**Step 1:** For each candidate check for an upstream replacement:
`git ls-tree -r --name-only origin/main tests | rg <subject>`.
**Step 2:** Take the replacement, delete the local file, and record the mapping in
the commit message.
**Step 3:** Run `uv run pytest tests/unit -q` after each batch of five.

---

## Task 5: Drive the three suites to green

**Step 1:** `uv run pytest tests/unit/middleware -q` — run in slices
(`tests/unit/middleware/*.py`, then `compaction/`, then `skills/`), because the
whole directory outruns the command window.
**Step 2:** `uv run pytest tests/unit/ptc_agent -q`
**Step 3:** `uv run pytest tests/unit/server -q` — slices: `services`, `app`,
`handlers`, `database`, `models`, `utils`.
**Step 4:** Classify every failure as local-product (fix), stale contract (retire)
or merge gap (port), and record the classification in the commit.
**Step 5:** Finish with the whole `tests/unit` in slices until green, plus
`uv run ruff check src`.

---

## Task 6: Land the deferred workspace-file blob persistence (`056` renumbered)

**Files (currently untracked on purpose):**
`src/server/services/persistence/{_rows,backup,blobs,resolve,restore,transfer}.py`,
`src/server/services/workspace_file_gc.py`, plus
`src/server/database/workspace_file_blobs.py` from `origin/main`.

**Step 1:** Create `migrations/versions/058_workspace_file_blobs.py` (next free
number; `056`/`057` are taken) porting upstream's blob registry, reference and GC
tables onto the local chain.
**Step 2:** Test upgrade/downgrade/upgrade on the isolated database:
`DB_HOST=127.0.0.1 DB_PORT=15432 uv run alembic upgrade head`.
**Step 3:** Wire read/write: `persistence/file.py`, the workspace-file routes,
backup/restore, the backfill and the GC service; keep the PostgreSQL inline path
as the fallback when object storage is unconfigured.
**Step 4:** Verify a real upload/read/restore against the isolated MinIO.
**Step 5:** Commit.

---

## Task 7: End-to-end verification — PTC agent plus Docker sandbox

**Step 1:** Restart the host backend against the isolated infra:

```bash
DB_HOST=127.0.0.1 DB_PORT=15432 REDIS_URL='redis://:redis@127.0.0.1:16379/0' \
STORAGE_ENDPOINT_URL='http://127.0.0.1:19000' SERVER_BASE_URL='http://localhost:18000' \
EGRESS_RELAY_LOOPBACK_URL='http://127.0.0.1:18000' \
uv run python server.py --reload --host 0.0.0.0 --port 18000
```

**Step 2:** Confirm `SANDBOX_PROVIDER=docker` and that the image exists:
`docker images | rg langalpha-sandbox`.
**Step 3:** Create a PTC workspace in the UI, send one message, and check: the
sandbox container appears in `docker ps`, `/health` stays 200, the turn streams to
`run_end`, and `workspace_mcp_tool_schemas` fills once the user-level MCP server is
discovered inside the sandbox.
**Step 4:** Verify a stdio MCP connector end to end in that workspace (that path is
PTC-only by design).
**Step 5:** Record the evidence in the runbook.

---

## Task 8: Close out

- Update `CHANGELOG.md` (Chinese) and the runbook's remaining-work list.
- Keep the classification lists until the merge is fully done, then remove them.
- Final commit; leave the branch clean apart from intentionally untracked items.
