# Datalab Document Parser Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** add a Datalab-backed online PDF parser alongside the existing local
ones, let the upload wizard tune it from an advanced-options panel, and give the
deployment a Usage surface showing pages processed and money spent.

**Architecture:** a new `DatalabExtractor` implements the existing synchronous
`DocumentParser` protocol and calls `datalab_sdk.DatalabClient.convert()` inside
the executor's spawned subprocess. Per-request options ride the **existing**
`parser_options` JSONB channel — no new API field. Each successful conversion
writes a usage row, which a new endpoint aggregates for the Usage page.

**Tech Stack:** Python 3.13+, Pydantic v2, `datalab-python-sdk`, pytest, uv,
Alembic raw SQL; React 19, TypeScript, `recharts` (returning), vitest, pnpm.

**Design doc:** `docs/plans/2026-09-14-datalab-document-parser-design.md`
(decisions D1–D9a; the doc research is recorded there — do not re-litigate it).

**Branch:** `feature/platform-core-migration` at
`/Users/seanlee/.config/superpowers/worktrees/langalpha/platform-core-migration`.

**Rules for every task:**

- One task = one commit, with the verification output quoted in the message.
- Update `CHANGELOG.md` (Chinese) in the same commit.
- Never overwrite or delete a path in `docs/plans/core-merge-keep-list.txt`.
- Tests must be seen to fail before the implementation that makes them pass.
- Backend: `uv run pytest tests/unit -q -p no:randomly` (a single file while
  iterating), `uv run ruff check src/ migrations/`.
  Frontend: `cd web && pnpm vitest run <path>`, `pnpm typecheck`, `pnpm lint`.
- Money is integer cents everywhere. Never a float.

---

## Task 1: Deployment configuration

**Files:**

- Modify: `src/config/env.py`, `src/config/settings.py`, `.env.example`
- Test: `tests/unit/config/test_datalab_config.py`

**Step 1: Write the failing test**

Cover, in the shape `tests/unit/config/` already uses for env-backed config:

1. Nothing set → `get_datalab_config()` returns `None`.
2. `ENABLE_DATALAB_DOCUMENT_PARSER=false` with everything else set → `None`.
3. Enabled but no `DATALAB_API_KEY` → `None` (the failure mode that would
   otherwise surface as an authentication error at parse time).
4. Enabled but no `DATALAB_PIPELINE_ID` → **still configured** (the id is
   reserved, not required — D2), with a comment saying so.
5. Fully configured → an object carrying the api key, the mode default
   (`balanced`), the poll budget and the parse timeout.
6. The poll budget is **strictly less** than the parse timeout, asserted as a
   property rather than two literals — this is the ordering D3 depends on.

**Step 2: Run it and watch it fail**

```bash
uv run pytest tests/unit/config/test_datalab_config.py -q -p no:randomly
```

Expected: FAIL — `get_datalab_config` does not exist.

**Step 3: Implement**

Add to `src/config/env.py` beside the other document settings (`env.py:44-46`):

```python
# Booleans are read inline here, the way AUTH_COOKIE_SECURE is (env.py:31) —
# there is no _flag helper, and inventing one is not this task's business.
DATALAB_DOCUMENT_PARSER_ENABLED: bool = (
    os.getenv("ENABLE_DATALAB_DOCUMENT_PARSER", "false").strip().lower()
    in {"1", "true", "yes"}
)
DATALAB_API_KEY: str = os.getenv("DATALAB_API_KEY", "").strip()
DATALAB_PIPELINE_ID: str = os.getenv("DATALAB_PIPELINE_ID", "").strip()
DATALAB_CONVERSION_MODE: str = os.getenv("DATALAB_CONVERSION_MODE", "balanced").strip()
DATALAB_POLL_BUDGET_SECONDS: int = _positive_int("DATALAB_POLL_BUDGET_SECONDS", 540)
```

Add `get_datalab_config()` to `settings.py`, following
`get_volcengine_asr_config()` (`settings.py:655`) — return `None` unless every
*required* value is present, so the provider's `available` flag tells the truth
instead of failing later:

```python
def get_datalab_config() -> DatalabConfig | None:
    """Return the Datalab configuration only when it is actually usable."""
```

`DATALAB_PIPELINE_ID` is read but **not** required; document in a comment that it
is reserved for the future multi-step-pipeline path and that
`client.convert()` does not use it.

Append to `.env.example` under the existing Datalab block (`.env.example:231-235`):
the API key, the mode, and the poll budget, each with a one-line explanation.

**Step 4: Run and commit**

```bash
uv run pytest tests/unit/config -q -p no:randomly
uv run ruff check src/config
```

```bash
git add src/config .env.example tests/unit/config CHANGELOG.md
git commit -m "feat(config): add Datalab parser deployment configuration"
```

---

## Task 2: The SDK dependency

**Files:**

- Modify: `pyproject.toml`
- Test: `tests/unit/server/documents/providers/test_datalab_sdk_import.py`

**Step 1: Add it**

```bash
uv add datalab-python-sdk
```

Then pin the resolved version in `pyproject.toml` the way `firecrawl-anydoc==0.2.4`
is pinned, and record the version in the commit message.

**Step 2: Write the test that matters**

Not "the package imports in this process" — that is already true by the time the
test runs. The provider executes inside a **spawned subprocess**
(`SpawnProcessRunner`), so the assertion is that the SDK is importable from a
fresh interpreter, which is where a missing dependency would actually bite:

```python
def test_datalab_sdk_is_importable_from_a_child_interpreter():
    # The parser runs in a spawned process; an import that works only in the
    # parent would fail in production and nowhere in the test suite.
```

Use `sys.executable -c "import datalab_sdk; datalab_sdk.DatalabClient"` via
`subprocess.run` and assert the return code.

**Step 3: Run and commit**

```bash
uv run pytest tests/unit/server/documents/providers/test_datalab_sdk_import.py -q -p no:randomly
```

```bash
git add pyproject.toml uv.lock tests CHANGELOG.md
git commit -m "build: add the Datalab Python SDK"
```

---

## Task 3: Persist per-conversion usage

This is the decision the design deliberately left out of implementation order:
where usage lands. **A dedicated table**, because the Usage page aggregates by
day and by provider and should not have to parse artifact metadata to do it.

**Files:**

- Create: `migrations/versions/061_document_usage_records.py`
- Create: `src/server/database/document_usage.py`
- Test: `tests/unit/server/database/test_document_usage.py`,
  `tests/integration/test_document_usage_migration_db.py`

**Step 1: Write the migration**

Match the conventions of `045_add_document_library.py`:

```python
revision = "061_document_usage_records"
down_revision = "060_restore_finance_schema"
```

```sql
CREATE TABLE document_usage_records (
    record_id VARCHAR(16) PRIMARY KEY
        CHECK (record_id ~ '^use-[0-9A-Za-z]{12}$'),
    job_id VARCHAR(16) NOT NULL
        REFERENCES document_parse_jobs(job_id) ON DELETE CASCADE,
    owner_user_id VARCHAR(255) NOT NULL
        REFERENCES users(user_id) ON DELETE RESTRICT,
    provider_id VARCHAR(100) NOT NULL,
    pages INTEGER NOT NULL CHECK (pages >= 0),
    list_cost_cents INTEGER CHECK (list_cost_cents >= 0),
    final_cost_cents INTEGER NOT NULL CHECK (final_cost_cents >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- A job can be retried; the record must describe the job, not the attempt.
    UNIQUE (job_id)
);
CREATE INDEX idx_document_usage_owner_created
    ON document_usage_records (owner_user_id, created_at DESC);
```

`UNIQUE (job_id)` is load-bearing: retries are real (`attempt_count` exists on
the jobs table), and an upsert keyed on the job is what keeps a retry from
double-counting spend.

**Step 2: Write the failing repository tests**

1. `record_usage` inserts and returns the row.
2. Recording twice for the same job **updates** rather than duplicating (the
   retry case, asserted by counting rows).
3. `owner_user_id` scoping: another owner's rows are never returned.
4. Aggregation by day over a range, with pages and cents summed.
5. A range longer than the page's window is rejected, the way the on-prem
   analytics endpoint bounds its query to 7 days.

**Step 3: Run, watch it fail, implement**

```bash
uv run pytest tests/unit/server/database/test_document_usage.py -q -p no:randomly
```

**Step 4: Verify the migration round-trips**

```bash
uv run alembic upgrade head && uv run alembic downgrade -1 && uv run alembic upgrade head
```

**Step 5: Commit**

```bash
git add migrations src/server/database tests CHANGELOG.md
git commit -m "feat(documents): persist per-conversion usage records"
```

---

## Task 4: The options model

**Files:**

- Create: `src/server/documents/providers/datalab_options.py`
- Test: `tests/unit/server/documents/providers/test_datalab_options.py`

**Step 1: Write the failing test**

Defaults match the configured pipeline (D6): `mode="balanced"`,
`paginate=True`, `disable_image_extraction=True` (D9 — the default that avoids
producing markdown whose image references cannot resolve).

Rejections: an unknown `mode`; `page_range` together with `max_pages`;
`page_range` that is not a comma-separated list of `N` or `N-M`; a negative
`max_pages`. Unknown keys are **ignored**, not fatal, so a wizard from a newer
deploy does not break an older server — the same contract posture the artifact
work settled on.

**Step 2: Run it and watch it fail.**

**Step 3: Implement**

```python
class DatalabConversionOptions(BaseModel):
    """Per-request knobs for the Datalab conversion, stored in parser_options."""
```

Include `output_format` as a **fixed literal** `"markdown"` rather than an
omitted field, so the constraint is visible in the model and in any schema
generated from it later.

**Step 4: Commit.**

---

## Task 5: The provider

**Files:**

- Create: `src/server/documents/providers/datalab.py`
- Test: `tests/unit/server/documents/providers/test_datalab.py`

**Step 1: Write the failing test**

Stub the SDK client (never call the network in unit tests). Cover:

1. `available` is `False` when `get_datalab_config()` returns `None`, and the
   descriptor's `reason` names what is missing.
2. `available` is `True` when configured.
3. Options flow through: a request with `parser_options={"mode": "accurate",
   "page_range": "0-5"}` reaches the client as those `ConvertOptions` values.
4. Invalid stored options (a stale wizard) degrade to defaults rather than
   failing the job — assert the conversion still runs.
5. **`result.success is False` raises** and no artifact is written; this is the
   documented trap and gets its own test.
6. `metadata.failed_pages` non-empty → still succeeds, with the pages recorded in
   the artifact metadata and a warning surfaced.
7. Success writes `document.md` into `request.output_dir` and returns a bundle
   with `artifact_kind="primary_document"`, `format="gfm"`,
   `media_type="text/markdown"`, plus `page_count`, `parse_quality_score` and
   `cost_breakdown` in the metadata.
8. **An empty markdown body raises** rather than publishing an empty document
   (the same guard `AnydocExtractor` already has).
9. A usage row is recorded with the page count and cents from the result.
10. The SDK poll budget is passed explicitly and is derived from the configured
    budget — assert the argument, so D3's ordering cannot silently regress.

**Step 2: Run it and watch it fail.**

**Step 3: Implement**

```python
class DatalabExtractor:
    """Convert a document through Datalab's hosted API."""

    parser_id = "datalab-online"
```

- Build `DatalabClient(api_key=..., timeout=...)` inside `parse`, not at import
  time (the class is constructed at registry build, long before a job runs).
- Import `datalab_sdk` **inside** the method so a deployment without the extra
  can still build the registry — the same defensive posture `AnydocExtractor`
  takes with `find_spec`.
- Supported classifications: all five.

**Step 4: Run and commit.**

```bash
uv run pytest tests/unit/server/documents/providers -q -p no:randomly
uv run ruff check src/server/documents
```

```bash
git add src/server/documents/providers tests CHANGELOG.md
git commit -m "feat(documents): add the Datalab online parser"
```

---

## Task 6: Register it, retire the OCR placeholder

**Files:**

- Modify: `src/server/documents/providers/registry.py`
- Modify/Test: `tests/unit/server/documents/providers/test_registry.py`,
  `tests/unit/server/documents/test_inspection.py`

**Step 1: Write the failing test**

1. `datalab-online` appears in `parser_options` for **every** classification.
2. It is recommended for `scanned`, `image_based`, `mixed` and `unknown`.
3. `anydoc-local` is still recommended for `text_based` (the free path stays the
   default where it works).
4. `ocr-document` is **gone** from the options.
5. With Datalab unconfigured, the recommendation for `scanned` falls back to
   `legacy-pdf-text` and the option list still renders — the page must not break
   on a deployment without the key.

**Step 2: Run it and watch it fail.**

**Step 3: Implement** — in `build_default_provider_registry()` add the parser and
delete the `unavailable_parsers` entry; in `_recommended_parser_id` prefer AnyDoc
for `text_based` and Datalab otherwise, when available.

**Step 4: Run the documents suites and commit.**

---

## Task 7: The advanced-options panel in the wizard

**Files:**

- Create: `web/src/pages/Documents/components/DatalabOptionsFields.tsx`
- Modify: `web/src/pages/Documents/components/steps/MethodStep.tsx`
- Modify: `web/src/pages/Documents/types.ts` (the option shape)
- Test: `web/src/pages/Documents/__tests__/DatalabOptionsFields.test.tsx`

**Step 1: Write the failing test**

1. The panel is collapsed by default and does not affect a parse when untouched
   (the create-job body omits `parser_options`).
2. Expanding it and changing the mode puts `{mode: "accurate"}` into the
   create-job `parser_options`.
3. The panel only renders when the selected parser is `datalab-online` — the
   local parsers take no options, and showing them empty controls is worse than
   showing nothing.
4. Leaving a field at its default omits it from the payload rather than sending
   the default explicitly, so a server-side default change is not overridden by
   a stale client.

**Step 2: Run it and watch it fail.**

**Step 3: Implement** with the existing collapsible/details idiom and the
`Select`/`Input`/checkbox primitives already used in the wizard. Every label goes
through `t()` with literal keys in **both** catalogs (`keys.test.ts` enforces it).

Note in the component: the field set is hand-written here while the server
validates with a Pydantic model, so the two can drift. Pinning them is exactly
the gap the artifact-contract work called out for *request* shapes; doing it
properly is a follow-up, not this task.

**Step 4: Run and commit.**

```bash
cd web && pnpm vitest run src/pages/Documents && pnpm typecheck
```

---

## Task 8: The usage endpoint

**Files:**

- Modify: `src/server/app/documents.py` (or a new `usage` router if the module
  is already large)
- Modify: `src/server/documents/jobs.py` (or a `usage` service)
- Test: `tests/unit/server/documents/test_usage_api.py`

**Step 1: Write the failing test**

1. Returns daily buckets plus totals for the caller's own records only.
2. A `range` query of `7d` / `14d` / `30d` (matching the page's toggle) bounds
   the window; anything else is a validation error.
3. A user with no records gets an empty series and zero totals, not a 404.
4. A student account is refused (the page is parent-facing), consistent with how
   other parent-only surfaces are gated.

**Step 2: Run it and watch it fail, implement, run.**

**Step 3: Commit.**

---

## Task 9: Bring back Recharts

Separate from the page so the dependency decision is reviewable on its own.

**Files:**

- Modify: `web/package.json`, `web/pnpm-lock.yaml`
- Modify: `web/src/locales/__tests__/genericSurface.test.ts`

**Step 1: Amending the guard is the first step, not an afterthought**

`genericSurface.test.ts:67` asserts `lightweight-charts` **and** `recharts` are
absent — written when the finance surface was removed in `37fef0e9`. Add
`recharts` to the allowed set the way `react-grid-layout` was added after the
canvas work, and extend the comment: it is here for the Usage page's own bar
chart and carries no market data. `lightweight-charts` stays out.

Run the guard before and after to show it fails first and passes second.

**Step 2: Add the dependency**

```bash
cd web && pnpm add recharts
```

**Step 3: Commit**, quoting the before/after guard output.

---

## Task 10: The Usage page

**Files:**

- Create: `web/src/pages/Settings/panels/UsageTab.tsx`
- Modify: `web/src/pages/Settings/Settings.tsx` (tab registration, following the
  existing `activeTab === '...'` pattern at `Settings.tsx:143`)
- Modify: `web/src/pages/Settings/queries.ts`, `web/src/lib/queryKeys.ts`
- Modify: both locale catalogs
- Test: `web/src/pages/Settings/__tests__/UsageTab.test.tsx`

**Step 1: Write the failing test**

Beyond rendering the reviewed layout (plan card, two stat cards, chart, legend),
the states that matter:

1. Empty series renders an empty state, not an empty chart frame.
2. A single day of data still renders a visible bar.
3. The 7d/14d/30d switch refetches with the matching range.
4. When Datalab is **not** configured, the page says so plainly instead of
   showing zeros that look like "you spent nothing".

**Step 2: Run it and watch it fail.**

**Step 3: Implement**, following the reviewed screenshot's structure but with our
own units (pages, cents) and our own design tokens — the screenshot is a layout
reference, not a specification to copy pixel for pixel.

**Step 4: Run and commit.**

---

## Task 11: End-to-end verification

**Step 1: Prove it against the real API.** Configure `.env`, upload a real PDF
through the wizard, select the Datalab parser, expand the advanced panel, run
it, and confirm the markdown artifact appears in the preview. This spends a few
cents and is the only test that proves the client, the key and the account all
work together — a unit test with a stubbed client cannot.

**Step 2: Prove the failure path.** Run once with a deliberately invalid
`DATALAB_API_KEY` and confirm the job fails with a readable error rather than an
empty document.

**Step 3: Full suites.**

```bash
uv run pytest tests/unit -q -p no:randomly
uv run ruff check src/ migrations/ scripts/ops/
```

```bash
cd web && pnpm vitest run && pnpm typecheck && pnpm lint && pnpm build
```

Baselines: backend 7591 passed / 8 deselected; frontend 248 files / 2458 tests;
lint 0 errors / 55 warnings; critical path under 450 kB gz.

**Step 4: Commit the close-out** and note in the design doc what the real run
measured (pages, cost) versus what the docs predicted.

---

## Deferred: images (D9a)

Not in this plan, and listed so it is not lost. It is its own piece of work
because it touches publication limits and the preview renderer, and because the
provider being usable should not wait on it:

1. Emit each extracted image as a sibling artifact under `document_images/`,
   with a correct `media_type`.
2. Give images their own caps. The 256-artifact ceiling (`executor.py:41`) and
   the bundle-wide byte cap (`executor.py:256`) both apply today, and images
   counted into the markdown's byte budget would fail jobs that currently
   succeed.
3. Resolve relative references at render time. The preview already fetches the
   job's artifact list, so a `relative_path -> artifact_id` map exists
   client-side; the shared `Markdown` component needs an `img` override. Keep the
   stored markdown faithful — never bake absolute URLs into the record.
4. Never expose an image as a public bucket URL; these are family documents.
