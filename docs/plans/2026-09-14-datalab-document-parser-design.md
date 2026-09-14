# Datalab Online Document Parser — Design

**Status:** proposed 2026-09-14, awaiting review before implementation.

**Goal:** add a hosted document parser backed by Datalab's online conversion API,
alongside (not replacing) the existing local parsers; let the user tune its
per-request options from the upload wizard; and add a Usage surface that shows
what we have spent on it.

**Branch:** `feature/platform-core-migration`.

## What exists today

| Piece | Where | Note |
|---|---|---|
| Registry | `src/server/documents/providers/registry.py` | `AnydocExtractor()`, `LegacyPdfExtractor()`, plus an unavailable `ocr-document` placeholder |
| Parser protocol | `providers/base.py` | `def parse(request) -> ArtifactBundle` — **synchronous** |
| Legacy local | `providers/legacy_pdf.py` | `parser_id="legacy-pdf-text"`, all classifications, warns about missing text layers |
| AnyDoc local | `providers/anydoc.py` | `parser_id="anydoc-local"`, `text_based` only |
| Execution | `documents/executor.py` | runs `parse` inside `SpawnProcessRunner` (separate process) under `DOCUMENT_PARSE_TIMEOUT_SECONDS` (600s), from a background job worker — not in the request path |
| Recommendation | `registry._recommended_parser_id` | `anydoc-local` for `text_based`, else `legacy-pdf-text` |
| Per-request options | see below | **already plumbed end to end** |
| Usage surface | — | none |

### The per-request options channel already exists

This is the single most useful thing found while researching, because it removes
the biggest piece of work the "advanced options" request looked like it needed.
There is a JSONB column and a full path from the wizard to the provider:

```
migrations/versions/045_add_document_library.py:170   parser_options JSONB NOT NULL DEFAULT '{}'
web/src/pages/Documents/types.ts:88                   parser_options: Record<string, JsonValue>   (create-job body)
src/server/app/documents.py:397                       parser_options=request.options             (persisted)
src/server/documents/executor.py:361                  options=dict(row.get("parser_options") or {}) -> ParseRequest.options
```

So tuning Datalab from the UI needs **no migration and no new API field** — only
a Pydantic model for validation, a wizard control that fills it, and a provider
that reads `request.options`.

## What the Datalab docs changed

Findings that alter the plan. All read from the official docs on 2026-09-14.

1. **Use the current SDK, not the older package.** The example we started from
   (`import datalab` / `datalab.run_pipeline(pipeline_id=…, filepath=…)`) is the
   older generation. The current docs use
   `pip install datalab-python-sdk` / `from datalab_sdk import DatalabClient` /
   `client.convert("doc.pdf")`. Package name *and* parameter names differ.
2. **`DATALAB_API_KEY` is required** and is not among the two variables already
   added to `.env.example`. Without it nothing authenticates.
3. **`client.convert()` is the right call for this use case**, and it removes
   four mechanisms the pipeline path would have required (see Decisions).
4. **A completed request can still have failed.** The docs carry an explicit
   warning: a finished request may return `success=False` **without raising**.
   `result.success` must be checked before reading `result.markdown`.
5. **`GET /api/v1/usage` is on-prem only** ("requires a valid on-premises
   license"; invalid licence → 423). The pipeline and API key here are on the
   hosted service, so that endpoint cannot supply the Usage page.
6. **Limits are looser than ours**: PDFs up to 200 MB and 7,000 pages per
   request, against our own `DOCUMENT_MAX_UPLOAD_BYTES` of 50 MB. Free tier is
   10 requests/minute and 5 concurrent — worth knowing before a bulk import.
7. **SDK 0.5.0 cannot download EU regional results automatically**; those need
   the REST polling flow. The account's region is not EU (confirmed), so this is
   recorded as a caveat rather than a blocker.

## Decisions

### D1 — Add a parser; do not rename the existing one

Per review: a new provider, `LegacyPdfExtractor` untouched. This also removes a
compatibility hazard — `parser_id` is **persisted** on every job
(`document_jobs.py:39/54/70`), so renaming an id with history behind it would
break retry/replay for those rows.

New provider: `DatalabExtractor`, `parser_id="datalab-online"`, display name
along the lines of "Datalab（在线转换）".

### D2 — `client.convert()`, not a pipeline

The configured pipeline currently has exactly one step (Conversion), so
`convert()` is behaviourally equivalent **and** drops four mechanisms:

| Pipeline path | `convert()` |
|---|---|
| `run_pipeline` returns a handle; you poll `get_pipeline_execution` | blocks and returns the finished result (the SDK polls internally) |
| must pick a `step_index` (here: the last step) | result *is* the output |
| results are deleted from Datalab's servers **1 hour** after completion | no server-side result to lose |
| must pin a `DATALAB_PIPELINE_ID` / version | version pinning does not apply |

`client.convert()` returns exactly what we need anyway: `result.markdown`,
`result.page_count`, `result.cost_breakdown` (`list_cost_cents` /
`final_cost_cents`), `result.parse_quality_score` (0–5), and
`result.metadata.failed_pages`.

Consequence to state plainly: **`DATALAB_PIPELINE_ID` becomes unused.** It stays
in `.env` and `.env.example`, documented as reserved for the future
multi-step-pipeline path (convert → extract/segment/custom processor), which is
where that configuration earns its keep.

### D3 — Stay synchronous, inside the existing process boundary

`parse()` remains blocking. It already runs off the event loop and off the
request path, inside a spawned subprocess with a timeout, so a blocking SDK call
costs nothing architecturally.

The one thing that must be arranged deliberately is the **poll budget against
our timeout**. `convert()` polls internally with `max_polls` (default 300) and
`poll_interval` (default 1). If our subprocess is killed first, the work
continues on Datalab's side and we keep paying for a result nobody collects. So:

- the SDK poll budget must expire **before** `DOCUMENT_PARSE_TIMEOUT_SECONDS`,
  so the failure is ours and clean;
- the outer timeout may need raising for large documents; both values become
  deployment config rather than magic numbers.

### D4 — Failure and partial-failure semantics

- `result.success is False` → raise `ParserIncompatibleError` (or a dedicated
  error) with `result.error`; never write an empty artifact.
- `result.metadata.failed_pages` non-empty → still a success, but recorded in the
  artifact metadata and surfaced as the descriptor/result warning, the way
  `LegacyPdfExtractor` already warns about missing text layers.
- `parse_quality_score`, `page_count` and `cost_breakdown` go into the artifact
  metadata; the last two also feed the Usage page (D8).

### D5 — All classifications; it takes over the OCR placeholder's role

The provider declares support for `text_based`, `mixed`, `scanned`,
`image_based`, `unknown`.

Recommended-parser policy (proposed): keep **local AnyDoc for `text_based`** —
it is free and fast — and recommend **Datalab for everything else**, which is
exactly the gap the unavailable `ocr-document` placeholder was marking. That
placeholder should then be retired (or its `reason` rewritten) rather than left
sitting next to a parser that now does its job. **Please confirm** retiring it.

### D6 — Per-request options as a Pydantic model

`DatalabConversionOptions(BaseModel)`, validated at the boundary and stored
through the existing `parser_options` column. Initial surface, defaulting to the
settings the pipeline used (`balanced`, `paginate=True`):

| Field | Default | Note |
|---|---|---|
| `mode` | `balanced` | `fast` / `balanced` / `accurate` — matches the configured pipeline |
| `paginate` | `True` | matches the configured pipeline |
| `page_range` | `None` | explicit ranges, e.g. `"0-5,10"` |
| `max_pages` | `None` | mutually exclusive with `page_range` |
| `skip_cache` | `None`/`False` | force reprocessing |
| `disable_image_extraction` | `False` | |
| `disable_image_captions` | `False` | |
| `token_efficient_markdown` | `False` | |
| `extras` | `None` | e.g. `chart_understanding`, `extract_links` |

`output_format` is proposed as **fixed to markdown**: the document library's
primary artifact is `format="gfm"`, `media_type="text/markdown"`, and every
existing provider produces exactly one markdown file. Exposing HTML/JSON would
mean widening the artifact model, which is a separate piece of work. **Please
confirm** keeping it fixed for now.

Datalab also returns extracted images as a base64 dict. We propose **not**
persisting them initially (no existing provider does, and the bundle/publication
path is sized for a markdown file), while leaving `images` an obvious later
addition.

### D7 — Deployment configuration

Follow `get_volcengine_asr_config()`'s established shape: return a config object
only when every required value is present, otherwise `None` — the provider's
`available` flag then reports itself honestly and the descriptor's `reason`
explains what is missing.

Required: `ENABLE_DATALAB_DOCUMENT_PARSER`, `DATALAB_API_KEY`,
`DATALAB_PIPELINE_ID` (reserved). Proposed additions: a mode default and the
poll budget / timeout pair from D3.

### D8 — Usage surface

`GET /api/v1/usage` is on-prem only, so the Usage page is fed from **our own
records**: per conversion, `page_count` and `cost_breakdown.final_cost_cents`
(plus `list_cost_cents`) are persisted and aggregated by day.

Layout follows the screenshot reviewed on 2026-09-14 (plan/credits cards, a
usage-over-time bar chart with a 7d/14d/30d switch, and a legend), relabelled
from "credits" to what we actually have: pages processed and money spent.

Two constraints worth recording:

- **Where the per-conversion usage lands** is still open: the artifact metadata
  path already exists, but a small dedicated table is cleaner to aggregate. This
  is the first task of the plan, not an implementation detail to improvise.
- **The local branch has no charting library.** `recharts` and
  `lightweight-charts` were removed in `37fef0e9`, and a test asserts they stay
  out. The bar chart is therefore hand-rolled SVG — the same approach already
  used for the widget preset thumbnails — or the dependency decision gets
  revisited deliberately.

## Open questions

1. **Provenance of the reference screenshot.** The Usage screen was described as
   existing in the remote code, but its strings ("Track your credit
   consumption", "Usage breakdown", "Permanent credits", "Token/Infra/BYOK
   Credits") appear in **no branch or commit** of this repository after a fresh
   fetch (`origin/main` = `ddeba2a5`, 2026-09-13), and in no other checkout under
   `~/DevelopCode`. If it lives in a repo that is reachable, porting beats
   re-implementing; if it is the deployed product rather than a public repo, the
   screenshot is enough and this design proceeds from the layout alone.
2. Retire the `ocr-document` placeholder (D5)?
3. Keep `output_format` fixed to markdown for now (D6)?

## Risks

- **Cost accrual without a ceiling.** Every conversion spends money, and a bulk
  import multiplies it. There is no documented balance endpoint, so we cannot
  pre-flight a budget — only report after the fact. Worth a per-job page cap and
  an eye on the free-tier 10/min limit.
- **A killed subprocess orphans paid work** (D3). Mitigated by ordering the
  budgets, not eliminated.
- **`success=False` without an exception** is easy to miss and would write an
  empty document. Called out as its own test.
- **Two local parsers plus one remote** makes the recommendation policy
  load-bearing: getting it wrong either spends money needlessly or sends a
  scanned PDF to a parser that cannot read it.

## Out of scope

- The pipeline-based (multi-step) variant, and therefore `DATALAB_PIPELINE_ID`.
- Persisting extracted images.
- Importing the screenshot's credit-based model: there is no balance API, and our
  unit of account is pages and cents.
