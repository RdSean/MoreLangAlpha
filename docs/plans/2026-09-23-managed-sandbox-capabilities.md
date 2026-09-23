# Managed Sandbox Capabilities Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unify writable-directory ownership across PTC sandboxes and give
textbook processing the normal PTC tool surface while preserving managed-root
isolation, progress integrity and package validation.

**Architecture:** Provider/runtime code guarantees that uploaded paths and
their parent directories belong to the sandbox runtime user. PTCSandbox uses
one shared directory-preparation contract for normal and managed sessions;
managed textbook policies then declare their business layout and capabilities.
Textbook jobs enable web, code execution, normal sandbox Bash, preview and
widgets while MCP/Vault remain disabled. Managed write validation enforces
zone/path safety only; package schemas, hashes and declared assets are checked
at import/finalization.

**Tech Stack:** Python 3.13+, PTCSandbox, Docker/Daytona providers, pytest,
psycopg, `book-to-skill`, FastAPI.

**Baseline:** `codex/library-textbook-assets` at `45929196`.

---

## Problems To Solve

1. Docker tar upload creates files as the sandbox user but can leave their
   parent directories owned by root. Managed Bash and code execution then
   fail with `Permission denied`.
2. The textbook Bash whitelist is too narrow. The model attempts ordinary
   inspection commands, gets rejected, and spends time probing the environment.
3. The textbook managed policy disables tools that are required for the full
   `book-to-skill` workflow.
4. `validate_managed_textbook_write()` encodes package schema and exact output
   filenames at write time. This blocks legitimate scratch files and couples
   writer behavior to import policy.
5. Diagnostic events such as `probe:noop` can be projected as real stages,
   including an invalid `chapter_analysis / skipped`.

## Product Decisions

1. Provider ownership behavior is common to all sandboxes. Normal PTC,
   workspace sandboxes and managed textbook sandboxes must use the same
   mechanism.
2. PTC and textbook processing may keep different root paths. They do not need
   to share one physical directory:
   - normal PTC: `/home/workspace`
   - managed textbook: `/managed/textbook-job/<job_id>`
3. The backend pre-creates the managed root contract:
   - `inputs/` read-only
   - `work/` writable
   - `outputs/` writable
   - `outputs/book-skill/` writable
   - `.langalpha/` writable only for the append helper
4. Agents may create child directories under `work/` and `outputs/`.
5. Agents must not create or replace contract parents, write `inputs/`, modify
   `.agents/`, or bypass the progress helper.
6. Textbook managed policies enable:
   - web
   - code execution
   - normal sandbox Bash without a command-text whitelist
   - preview
   - widgets
   - existing Read/Glob/Grep/Write/Edit filesystem tools
7. MCP and Vault remain disabled unless a later product decision explicitly
   enables them.
8. Once code execution is enabled, command-text allowlisting is not a security
   boundary. Security comes from sandbox isolation, fixed roots, disabled
   secrets, and post-run validation.
9. Mandatory full-pipeline stages cannot be marked `skipped`. Diagnostic
   `probe:*` and `diagnostic:*` events are ignored and rejected.

## Strict Write Validation: Why It Exists And How It Changes

The current validator was strict for four reasons:

1. It prevented path traversal, absolute paths and writes outside the managed
   job root.
2. It prevented accidental writes to frozen inputs, skill directories and
   unrelated sandbox state.
3. It enforced the exact package filenames from the first managed contract.
4. It tried to catch malformed JSON before PostgreSQL or object storage.

Only the first two reasons are write-layer responsibilities. The last two
belong to finalization/import:

- The writer should enforce root containment, forbidden zones, size bounds,
  UTF-8/NUL safety and append-only progress rules.
- The importer should validate `book_package.json`, projections, candidate
  ownership, asset declarations, sizes and hashes.

The new rule is:

```text
write gate = file-system safety
import gate = package semantic integrity
```

This permits arbitrary scratch and canonical `book-to-skill` outputs without
weakening the database/import boundary.

### Task 1: Add Provider-Level Directory Ownership

**Files:**
- Modify: `src/ptc_agent/core/sandbox/runtime.py`
- Modify: `src/ptc_agent/core/sandbox/providers/docker.py`
- Modify: `src/ptc_agent/core/sandbox/providers/daytona.py`
- Modify: `src/ptc_agent/core/sandbox/ptc_sandbox.py`
- Test: `tests/unit/core/sandbox/test_docker_provider.py`
- Test: `tests/unit/core/sandbox/test_runtime.py`
- Test: `tests/integration/sandbox/providers/test_docker_modes.py`

**Step 1: Write the failing ownership tests**

Add a unit test that calls `DockerRuntime.upload_file()` with
`/home/workspace/a/b/file.txt` and inspects the tar passed to
`put_archive`.

Assert that the archive contains:

```text
home/
home/workspace/
home/workspace/a/
home/workspace/a/b/
home/workspace/a/b/file.txt
```

Every directory and file entry must use the container's uid/gid. Parent
directories must use mode `0755`; the file remains `0644`.

Add a real Docker integration assertion:

```python
result = await runtime.exec("id -u; id -g")
uid, gid = (int(part) for part in result.stdout.split()[:2])
result = await runtime.exec(
    "mkdir -p nested/a && test -w nested/a && "
    "touch nested/a/file && rm nested/a/file"
)
assert result.exit_code == 0
await runtime.upload_file(b"x", f"{runtime.working_dir}/nested/b/file.txt")
result = await runtime.exec(
    f"test $(stat -c %u {runtime.working_dir}/nested/b) -eq {uid} && "
    f"test $(stat -c %g {runtime.working_dir}/nested/b) -eq {gid}"
)
assert result.exit_code == 0
```

**Step 2: Run tests to verify they fail**

Run:

```bash
uv run pytest tests/unit/core/sandbox/test_docker_provider.py -q
uv run pytest -m integration tests/integration/sandbox/providers/test_docker_modes.py -q
```

Expected: the archive has no explicit directory entries; parent ownership is
root or Docker-created rather than the runtime uid/gid.

**Step 3: Implement one provider directory contract**

Add a runtime capability:

```python
async def ensure_directory(self, path: str, *, mode: int = 0o755) -> None:
    ...
```

Semantics:

- Docker tar mode: add parent directory TarInfo entries before file entries.
- Docker bind mode: `os.makedirs(..., exist_ok=True)`.
- Daytona: create folder if absent; do not fail when it exists.
- All implementations use the sandbox runtime user ownership.

Refactor both:

```python
DockerRuntime._tar_upload()
DockerRuntime.upload_files()
```

to use the same directory-entry builder. Remove the unchecked
`await self.exec("mkdir -p parent")` as the sole parent mechanism.

**Step 4: Route PTCSandbox directory setup through the provider capability**

Add a PTCSandbox helper:

```python
async def ensure_directories(
    self,
    directories: list[str],
    *,
    mode: int = 0o755,
) -> None:
    ...
```

Normal `_setup_workspace()` and managed
`setup_managed_textbook_job()` both call it. The normal directory list remains
unchanged; managed uses the list defined in Task 2.

**Step 5: Run tests**

Run:

```bash
uv run pytest tests/unit/core/sandbox/test_docker_provider.py \
  tests/unit/core/sandbox/test_runtime.py \
  tests/unit/core/sandbox/test_ptc_sandbox_delegation.py -q
uv run pytest -m integration tests/integration/sandbox/providers/test_docker_modes.py -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add src/ptc_agent/core/sandbox/runtime.py \
  src/ptc_agent/core/sandbox/providers/docker.py \
  src/ptc_agent/core/sandbox/providers/daytona.py \
  src/ptc_agent/core/sandbox/ptc_sandbox.py \
  tests/unit/core/sandbox/test_docker_provider.py \
  tests/unit/core/sandbox/test_runtime.py \
  tests/unit/core/sandbox/test_ptc_sandbox_delegation.py \
  tests/integration/sandbox/providers/test_docker_modes.py
git commit -m "fix(sandbox): preserve runtime ownership for uploaded parents"
```

---

### Task 2: Define The Managed Textbook Directory Layout

**Files:**
- Modify: `src/ptc_agent/agent/managed_execution.py`
- Modify: `src/ptc_agent/core/sandbox/ptc_sandbox.py`
- Modify: `src/server/services/education_teaching_storage.py`
- Test: `tests/unit/ptc_agent/test_managed_textbook_execution_policy.py`
- Test: `tests/unit/server/services/test_education_teaching_storage.py`

**Step 1: Write the failing layout tests**

Add a pure contract function:

```python
def managed_textbook_directories(root: str) -> tuple[str, ...]:
    ...
```

The test asserts these relative paths:

```text
work
outputs
outputs/book-skill
outputs/book-skill/chapters
outputs/content
outputs/chapters
outputs/knowledge
.langalpha
```

Assert `inputs` is not writable and `.langalpha/progress.jsonl` remains
helper-only.

**Step 2: Run the failing test**

```bash
uv run pytest tests/unit/ptc_agent/test_managed_textbook_execution_policy.py \
  -k managed_textbook_directories -v
```

Expected: FAIL because the function does not exist.

**Step 3: Pre-create the layout during managed sandbox setup**

In `setup_managed_textbook_job()`:

1. Create the job root.
2. Call `ensure_directories(managed_textbook_directories(root))`.
3. Verify each writable directory with the sandbox user.
4. Create `.langalpha/progress.jsonl` only through the provider upload API so
   the file belongs to the runtime user.

Do not use `chmod 0777` and do not grant write access to `inputs/`.

**Step 4: Keep staging as defense-in-depth**

`stage_managed_teaching_skills()` may continue uploading the empty progress
file, but it must not be the only mechanism creating writable parents.

**Step 5: Run tests**

```bash
uv run pytest tests/unit/ptc_agent/test_managed_textbook_execution_policy.py \
  tests/unit/server/services/test_education_teaching_storage.py -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add src/ptc_agent/agent/managed_execution.py \
  src/ptc_agent/core/sandbox/ptc_sandbox.py \
  src/server/services/education_teaching_storage.py \
  tests/unit/ptc_agent/test_managed_textbook_execution_policy.py \
  tests/unit/server/services/test_education_teaching_storage.py
git commit -m "fix(textbooks): precreate writable managed job layout"
```

---

### Task 3: Give Textbook Policies The Full PTC Capability Surface

**Files:**
- Modify: `src/ptc_agent/agent/managed_execution.py`
- Modify: `src/ptc_agent/agent/agent.py`
- Modify: `src/server/services/education_managed_runs.py`
- Test: `tests/unit/ptc_agent/test_managed_textbook_execution_policy.py`

**Step 1: Write failing policy tests**

Extend `ManagedExecutionPolicy` with explicit flags:

```python
enable_code_execution: bool = False
enable_bash: bool = True
enable_preview: bool = False
enable_widgets: bool = False
```

`enable_web` already exists.

Assert all textbook policy factories return:

```python
policy.enable_web is True
policy.enable_code_execution is True
policy.enable_bash is True
policy.enable_preview is True
policy.enable_widgets is True
policy.enable_mcp is False
policy.enable_vault is False
```

**Step 2: Run the failing test**

```bash
uv run pytest tests/unit/ptc_agent/test_managed_textbook_execution_policy.py \
  -k full_ptc_capabilities -v
```

Expected: FAIL.

**Step 3: Refactor managed tool construction**

Replace the current managed-only branch at `agent.py:610-652` with one helper
that adds tools according to policy:

```python
tools = [TodoWrite]
if policy.enable_code_execution:
    tools.append(create_execute_code_tool(...))
if policy.enable_bash:
    bash_validator = None
    if policy.purpose not in TEXTBOOK_PURPOSES:
        bash_validator = validate_managed_bash_command
    tools.extend([
        create_execute_bash_tool(
            backend,
            thread_id=short_thread_id,
            command_validator=bash_validator,
            fixed_working_dir=policy.filesystem_root,
        ),
        create_bash_output_tool(backend),
    ])
if policy.enable_preview:
    tools.append(create_preview_url_tool(...))
if policy.enable_widgets:
    tools.append(create_show_widget_tool(backend))
```

Read/Glob/Grep/Write/Edit remain injected through
`create_filesystem_tools()` for both normal and managed PTC.

Normal textbook Bash has no command-text whitelist. It still runs inside the
sandbox with the fixed managed root and no Vault/MCP credentials.

**Step 4: Enable the flags in every textbook policy**

Apply the capability flags to:

```text
education_structure_policy
education_lesson_policy
education_book_asset_policy
education_book_pipeline_policy
education_teaching_policy
```

**Step 5: Run tests**

```bash
uv run pytest tests/unit/ptc_agent/test_managed_textbook_execution_policy.py \
  tests/unit/ptc_agent/test_managed_textbook_execution_policy.py -q
uv run pytest tests/unit/ptc_agent -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add src/ptc_agent/agent/managed_execution.py \
  src/ptc_agent/agent/agent.py \
  src/server/services/education_managed_runs.py \
  tests/unit/ptc_agent/test_managed_textbook_execution_policy.py
git commit -m "feat(textbooks): enable full PTC capabilities for managed jobs"
```

---

### Task 4: Replace Exact Write Allowlists With Zone-Based Safety

**Files:**
- Modify: `src/ptc_agent/agent/managed_execution.py`
- Modify: `src/server/services/education_teaching_storage.py`
- Test: `tests/unit/ptc_agent/test_managed_textbook_execution_policy.py`
- Test: `tests/unit/server/services/test_education_book_pipeline_jobs.py`

**Step 1: Write failing zone tests**

Assert these writes are accepted for `book_pipeline`:

```text
work/scratch/plan.txt
outputs/book-skill/chapters/unit-1/reading-a.md
outputs/book-skill/chapters/unit-1/support.json
outputs/content/unit-1/knowledge.md
outputs/chapters/unit-1/transcript.txt
outputs/knowledge/unit-1/concepts.json
outputs/temporary.json
```

Assert these remain rejected:

```text
../outside.txt
inputs/source.md
.agents/skills/book-to-skill/SKILL.md
.langalpha/progress.jsonl
/tmp/outside.txt
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/ptc_agent/test_managed_textbook_execution_policy.py \
  -k zone_based_write -v
```

Expected: arbitrary scratch and extra canonical files are rejected.

**Step 3: Implement path-zone validation**

`validate_managed_textbook_write()` should enforce:

1. Absolute path is inside `policy.filesystem_root`.
2. No `..`, backslashes, NUL or C0 controls.
3. Writable zones are only:

```text
work/
outputs/
```

4. `inputs/` and `.agents/` are always read-only.
5. `.langalpha/progress.jsonl` can be written only by the staged helper.
6. Other `.langalpha/` files are rejected.
7. File size and JSON syntax limits remain defensive checks only where needed.

Do not enforce the four package filenames or exact chapter paths at write
time. The finalizer/import validates:

```text
book_package.json
content_tree.json
knowledge_points.json
assets_manifest.json
```

and every declared asset.

**Step 4: Add a staging/import regression**

Write extra undeclared files under `outputs/` and `work/`. Assert:

- write policy accepts them;
- the package importer downloads only declared asset paths;
- undeclared files are ignored.

**Step 5: Run tests**

```bash
uv run pytest tests/unit/ptc_agent/test_managed_textbook_execution_policy.py \
  tests/unit/server/services/test_education_book_pipeline_jobs.py -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add src/ptc_agent/agent/managed_execution.py \
  src/server/services/education_teaching_storage.py \
  tests/unit/ptc_agent/test_managed_textbook_execution_policy.py \
  tests/unit/server/services/test_education_book_pipeline_jobs.py
git commit -m "refactor(textbooks): validate write zones instead of exact outputs"
```

---

### Task 5: Harden Progress Semantics And Remove Probe Pollution

**Files:**
- Modify: `src/server/services/education_generation_progress.py`
- Modify: `src/server/services/education_structure_progress.py`
- Modify: `src/server/services/education_book_pipeline_jobs.py`
- Test: `tests/unit/server/services/test_education_generation_progress.py`
- Test: `tests/unit/server/services/test_education_structure_progress.py`
- Test: `tests/unit/server/services/test_education_book_pipeline_jobs.py`

**Step 1: Write failing event tests**

Reject:

```json
{"event_key":"probe:noop","stage":"chapter_analysis","status":"skipped"}
{"event_key":"diagnostic:test","stage":"content_processing","status":"running"}
```

Allow a valid checkpoint skip only with a dedicated field:

```json
{
  "event_key":"chapter_analysis:checkpoint:job-1",
  "stage":"chapter_analysis",
  "status":"skipped",
  "metadata":{"reason":"checkpoint_review"}
}
```

For `pause_after_chapter_analysis=false`, finalization must fail if
`chapter_analysis` has no durable `completed` event.

**Step 2: Run the failing tests**

```bash
uv run pytest tests/unit/server/services/test_education_generation_progress.py \
  -k probe -v
```

Expected: invalid probe events are currently accepted.

**Step 3: Implement event-key and skip policy**

Add stable event-key validation:

```text
<stage>:<substage-or-status>:<safe-id>
```

Reject keys beginning with:

```text
probe:
diagnostic:
test:
debug:
```

Only allow `skipped` when metadata reason is `checkpoint_review` or the stage
is explicitly optional. The progress projection must ignore rejected events.

**Step 4: Validate required stages before completion**

For a non-checkpoint full pipeline, require:

```text
chapter_analysis
content_processing
knowledge_point_generation
```

to have completed events before importing the package.

**Step 5: Run tests**

```bash
uv run pytest \
  tests/unit/server/services/test_education_generation_progress.py \
  tests/unit/server/services/test_education_structure_progress.py \
  tests/unit/server/services/test_education_book_pipeline_jobs.py -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add src/server/services/education_generation_progress.py \
  src/server/services/education_structure_progress.py \
  src/server/services/education_book_pipeline_jobs.py \
  tests/unit/server/services/test_education_generation_progress.py \
  tests/unit/server/services/test_education_structure_progress.py \
  tests/unit/server/services/test_education_book_pipeline_jobs.py
git commit -m "fix(textbooks): reject diagnostic and invalid skipped progress"
```

---

### Task 6: Update Managed Overlay And End-To-End Verification

**Files:**
- Modify: `plugins/langalpha_local/skills/book-to-skill/reference/langalpha-managed.md`
- Modify: `src/server/services/education_structure_jobs.py`
- Modify: `tests/unit/middleware/skills/test_native_book_learning_skills.py`
- Modify: `tests/unit/server/services/test_education_structure_jobs.py`
- Modify: `tests/integration/test_unified_book_processing_progress.py`
- Modify: `tests/integration/sandbox/providers/test_docker_modes.py`
- Modify: `CHANGELOG.md`

**Step 1: Write failing overlay and smoke tests**

Overlay/prompt assertions:

```text
Read, Glob and Grep are available for inspection
Write and Edit are available inside managed output zones
ordinary sandbox Bash is available
web, preview, widgets and code execution are allowed
MCP and Vault are disabled
do not emit probe/diagnostic progress events
```

Real Docker smoke:

```text
mkdir -p outputs/book-skill/chapters/unit-1
echo scratch > work/scratch.txt
python .langalpha/progress.py '<valid completed event>'
```

The smoke test must run as the sandbox user and verify:

- all commands succeed;
- `ls`, `wc`, `head` and `grep` work;
- progress append works;
- `inputs/` remains read-only;
- files remain inside the managed root.

**Step 2: Run failing tests**

```bash
uv run pytest tests/unit/middleware/skills/test_native_book_learning_skills.py \
  tests/unit/server/services/test_education_structure_jobs.py -q
uv run pytest -m integration \
  tests/integration/test_unified_book_processing_progress.py \
  tests/integration/sandbox/providers/test_docker_modes.py -q
```

Expected: overlay and smoke assertions fail before implementation.

**Step 3: Update managed documentation and prompt**

State the tool matrix explicitly:

```text
Read/Glob/Grep: inspection
Write/Edit: work/ and outputs/ only
Bash: ordinary sandbox commands with fixed managed root
ExecuteCode: allowed
Web: allowed
Preview/Widget: allowed
MCP/Vault: disabled
```

State the write-zone contract and diagnostics prohibition.

**Step 4: Run affected and full verification**

```bash
uv run pytest tests/unit -q
uv run pytest -m integration \
  tests/integration/test_unified_book_processing_progress.py \
  tests/integration/sandbox/providers/test_docker_modes.py -q
uv run ruff check src migrations tests/unit \
  tests/integration/test_unified_book_processing_progress.py \
  tests/integration/sandbox/providers/test_docker_modes.py
cd web && pnpm vitest run src/pages/Education && pnpm typecheck && pnpm build
```

Expected: PASS.

**Step 5: Commit**

```bash
git add plugins/langalpha_local/skills/book-to-skill/reference/langalpha-managed.md \
  src/server/services/education_structure_jobs.py \
  tests/unit/middleware/skills/test_native_book_learning_skills.py \
  tests/unit/server/services/test_education_structure_jobs.py \
  tests/integration/test_unified_book_processing_progress.py \
  tests/integration/sandbox/providers/test_docker_modes.py \
  CHANGELOG.md
git commit -m "docs(book-to-skill): document managed sandbox capabilities"
```

---

### Task 7: Add Compact Replay Profile For Education Jobs Only

**Files:**
- Modify: `src/server/services/runs/sse_producer.py`
- Modify: `src/server/services/education_structure_jobs.py`
- Modify: `src/server/services/education_book_pipeline_jobs.py`
- Modify: `src/server/services/education_lesson_jobs.py`
- Modify: `src/server/services/education_book_asset_jobs.py`
- Test: `tests/unit/server/services/runs/test_sse_producer.py`
- Test: `tests/unit/server/services/test_education_book_pipeline_jobs.py`
- Test: `tests/unit/server/services/test_education_structure_jobs.py`
- Test: `tests/unit/server/services/test_education_lesson_jobs.py`
- Test: `tests/integration/test_unified_book_processing_progress.py`

**Step 1: Write the failing education-stream tests**

Add a profile parameter to `RunSSEProducer`:

```python
replay_profile: Literal["full", "education_compact"] = "full"
```

For `education_compact`, assert these event types are emitted:

```text
metadata
warning
error
interrupt
model_retry
model_fallback
```

Assert these high-volume or raw events are not emitted to the run replay
stream or accumulated in `conversation_responses.sse_events`:

```text
message_chunk
tool_call_chunks
tool_calls
tool_call_result
compaction_chunk
context_window
provenance
steering_delivered
```

Add a pressure test that generates more than 150,000 raw message/tool deltas
and assert:

```python
assert emitted_replay_events < 1_000
assert stored_sse_events < 1_000
assert run_status == "completed"
assert progress_rows_written > 0
```

**Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/unit/server/services/runs/test_sse_producer.py \
  -k education_compact -v
```

Expected: FAIL because all profile values currently use the full stream.

**Step 3: Implement the compact profile before sequence allocation**

In `RunSSEProducer._format_sse_event()`:

1. Check `self.replay_profile`.
2. For `education_compact` and a non-replay event type, return an empty
   sentinel before incrementing `event_sequence` and before adding to
   `_stream_event_accumulator`.
3. Ensure `stream_workflow()` filters the empty sentinel so no empty SSE frame
   reaches `LocalRunExecutor`.
4. Keep the default `full` branch byte-for-byte behaviorally identical.

This is required because `stream_writer.buffer_event()` uses the SSE frame's
sequence ID as its event count. Filtering after ID allocation would still hit
the 150k quota.

**Step 4: Opt in only from education job call sites**

Every managed education `RunSSEProducer(...)` call passes:

```python
replay_profile="education_compact"
```

Normal PTC and Flash constructors do not pass the parameter and therefore
keep `full`.

The education frontend continues to use:

```text
GET /api/v1/education/jobs/{job_id}/progress
```

backed by `education_generation_progress_events` in PostgreSQL. It does not use
token deltas for timeline progress.

**Step 5: Add regression tests for normal PTC**

Assert `RunSSEProducer(replay_profile="full")` still emits and accumulates:

```text
message_chunk
tool_call_chunks
tool_calls
tool_call_result
```

Run the existing PTC run/SSE reader tests unchanged.

**Step 6: Run tests**

```bash
uv run pytest \
  tests/unit/server/services/runs/test_sse_producer.py \
  tests/unit/server/services/test_education_book_pipeline_jobs.py \
  tests/unit/server/services/test_education_structure_jobs.py \
  tests/unit/server/services/test_education_lesson_jobs.py -q
uv run pytest -m integration \
  tests/integration/test_unified_book_processing_progress.py -q
```

Expected: PASS. The pressure run completes without approaching the Redis
quota, while normal PTC stream shape remains unchanged.

**Step 7: Commit**

```bash
git add src/server/services/runs/sse_producer.py \
  src/server/services/education_structure_jobs.py \
  src/server/services/education_book_pipeline_jobs.py \
  src/server/services/education_lesson_jobs.py \
  src/server/services/education_book_asset_jobs.py \
  tests/unit/server/services/runs/test_sse_producer.py \
  tests/unit/server/services/test_education_book_pipeline_jobs.py \
  tests/unit/server/services/test_education_structure_jobs.py \
  tests/unit/server/services/test_education_lesson_jobs.py \
  tests/integration/test_unified_book_processing_progress.py
git commit -m "fix(education): use compact replay stream for managed jobs"
```

---

## Final Acceptance Criteria

- Docker and Daytona uploads preserve sandbox-user ownership for files and
  parent directories.
- Normal PTC and managed textbook setups share the same directory-preparation
  mechanism while keeping separate roots.
- Managed textbook jobs pre-create writable `work/`, `outputs/` and
  `.langalpha/`; `inputs/` remains read-only.
- Textbook policies enable web, code execution, normal Bash, preview, widgets,
  Read, Glob, Grep, Write and Edit.
- MCP and Vault remain disabled.
- Bash can create nested directories under `work/` and `outputs/`.
- The write gate enforces zones and path safety, not exact package filenames.
- The import gate validates package schema, candidate ownership, declared
  assets, hashes and sizes.
- `probe:*` and `diagnostic:*` events never affect the four-stage timeline.
- Non-checkpoint full pipelines require real chapter-analysis completion and
  cannot display a false `chapter_analysis / skipped`.
- Managed education jobs use `education_compact` replay by default; normal PTC
  and Flash remain on `full` replay with unchanged event semantics.
- A managed job that emits more than 150,000 raw model/tool deltas still
  persists semantic progress to PostgreSQL and completes without exceeding
  the Redis replay-event quota.
