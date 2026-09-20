# Book-to-Skill Textbook Pipeline Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make `book-to-skill` the canonical textbook structure, chapter-knowledge, and per-knowledge-point lesson engine while removing the obsolete teaching-package pipeline and its incompatible validations.

**Architecture:** The library remains responsible only for high-fidelity Markdown and assets. The textbook service starts a `book-to-skill` structure job, optionally preserves its chapter-level knowledge assets, then starts one `book-to-skill` lesson job per accepted knowledge point. PostgreSQL and MinIO own reviewable structures, source evidence, lesson revisions, and publication snapshots. `the-knowledge-guy` is retained as an optional student interaction/course layer, not as the lesson authoring engine.

**Tech Stack:** Python 3.13+, FastAPI, async psycopg3, Alembic raw SQL, Pydantic, PostgreSQL, MinIO/S3, managed PTC runs, React 19, TypeScript, React Query, Vitest, Playwright, pytest, Ruff.

---

## Fixed Decisions

- Keep `book-to-skill`; do not build a replacement textbook parser.
- `book-to-skill` owns:
  - `--managed-textbook-structure <job>`
  - `--managed-textbook-assets <job>`
  - `--managed-textbook-lesson <job>`
- `the-knowledge-guy` owns optional follow-up, interactive teaching, practice rendering, and personalized learning after publication.
- `lesson.md` means the static full content of one Mentrix-style knowledge-point page. It excludes follow-up chat, highlights, notes, progress, and personalized summary.
- `chapters/<book>-<slug>.md` means a chapter-level knowledge toolkit produced by `book-to-skill`; it is not a lesson and may feed lesson generation.
- `position` means order within a parent and is service-generated.
- `slug` means a stable logical identifier and is service-generated or service-normalized.
- Source references are optional provenance, not a publication requirement.
- Prefer source identity and quote excerpts. Markdown character offsets are
  optional best-effort metadata and must never block structure review.
- Do not ask models to calculate line numbers, character offsets, PDF pages, or
  bounding boxes.
- `book-to-skill` output is treated as a high-value draft, not as an adversarial
  payload that must reproduce the service's preferred shape.
- The service post-processes before validating. It derives missing deterministic
  metadata, normalizes optional fields, resolves source evidence, and records
  non-blocking warnings.
- Hard failure is reserved for unsafe paths, unreadable output, absent usable
  content, or integrity/security violations. Format variation alone must not
  discard a valid book-to-skill result.
- Legacy teaching packages, chapter lessons, old learning progress, and their compatibility paths are removed rather than migrated.

## Target Flow

```text
Library
  PDF / worksheet / book
  -> high-fidelity Markdown + assets

Textbook content version
  -> book-to-skill structure job
       -> structure.json
       -> service-generated position/slug
       -> service-resolved Markdown char offsets
  -> parent reviews and accepts Units / knowledge points

Optional chapter knowledge assets
  -> book-to-skill assets job
       -> chapters/*.md
       -> glossary.md / patterns.md / cheatsheet.md
       -> chapters_manifest.json

Per knowledge-point lesson
  -> book-to-skill lesson job
       -> lesson.md
       -> optional practice.json
  -> parent reviews and approves immutable revision

Publication
  -> freeze structure + lesson revisions
  -> assign to student
  -> knowledge-point learning
  -> follow-up / highlights / notes / personalized summary
```

## Processing and Validation Policy

The service must optimize for successful assimilation of `book-to-skill` output:

1. Parse and preserve every usable Unit, knowledge point, chapter asset, and
   lesson section.
2. Derive `position`, final `slug`, database IDs, storage paths, hashes, and
   timestamps in the service.
3. Preserve source identity and quote excerpts when supplied. Do not require
   offsets for review or publication.
4. If an exact or normalized quote match is cheaply available, store offsets as
   optional debug metadata. Never fail the task when offsets are unavailable.
5. Store warnings without blocking structure review when content remains usable.
6. Only hard-fail malformed/unreadable files, unsafe writes, absent usable
   content, or invalid security boundaries.

Warning examples:

```text
source_quote_unresolved
source_quote_ambiguous_first_match_used
optional_field_defaulted
unit_slug_generated
knowledge_point_slug_generated
```

## Removal Inventory

### Delete Completely

| Area | Files / Tables | Reason |
|---|---|---|
| Old teaching-package validation | `src/server/services/education_teaching_validation.py` | Validates the removed `langalpha-managed-teaching-package/v1` format |
| Old full bundle validation | `src/server/services/education_teaching_assets.py` | Validates removed concept-index / toolkit / practice / teaching-package bundle |
| Old teaching-package orchestration | `src/server/services/education_managed_ptc.py` | Dedicated to `education_teaching_packages` |
| Old teaching-package UI | `web/src/pages/Education/TeachingRunDrawer.tsx` and related tests | No longer reachable from the user flow |
| Old teaching-package API | `/teaching-packages/*`, `/teaching-jobs/*`, old publish endpoint | Replaced by structure + lesson APIs |
| Old tables | `education_teaching_packages`, package chapters/questions, jobs, attempts, events, archive staging | No compatibility requirement |
| Old chapter learning | `education_chapter_questions`, `education_learning_progress`, `education_learning_answers` | Replaced by lesson revisions and knowledge-point learning assets |
| Old legacy textbook sources | `education_textbook_sources` legacy branch and `LegacyTextbookSource` frontend type | New sources are always artifact-backed |

### Extract Before Delete

| Current file | Extract to | Reason |
|---|---|---|
| `src/server/services/education_teaching_jobs.py` | `src/server/services/education_managed_runs.py` | Structure and lesson jobs still need graph construction, agent config resolution, run dispatch, and shared terminal handling |
| `src/server/services/education_teaching_storage.py` | `education_source_storage.py` and `education_artifact_storage.py` | Separate source staging from structure/lesson/archive storage |
| `_MANAGED_SKILL_NAMES` | Per-policy explicit skill names | Structure, assets, and lesson jobs have different skill requirements |
| `validate_managed_textbook_write()` | Mode-specific functions | Remove the dead v2 teaching-package branch |

### Keep

- `book-to-skill` normal pipeline: `SKILL.md`, chapter toolkits, glossary, patterns, cheatsheet, nutshell, raw assets, manifest.
- `the-knowledge-guy` interactive walk/course/quiz behavior.
- `education_textbook_structures`, `education_structure_units`, `education_structure_knowledge_points`.
- `education_kp_lessons`, `education_kp_lesson_revisions`, `education_publication_kp_lessons`.
- `education_learning_kp_progress`, `education_learning_items`.
- Existing review, approval, publication, assignment, and student learning pages.

## Task 1: Add Golden Contract Fixtures

**Files:**

- Create: `tests/fixtures/education/book_to_skill_structure_minimal.json`
- Create: `tests/fixtures/education/book_to_skill_lesson_minimal.md`
- Modify: `tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py`

**Step 1: Add synthetic structure fixture**

Use only synthetic source text and quotes. Required shape:

```json
{
  "format": "langalpha-managed-textbook-structure/v1",
  "units": [
    {
      "title": "Unit 1: Demonstration",
      "summary": "Synthetic fixture",
      "unit_type": "teaching",
      "confidence": 0.95,
      "source_refs": [
        {
          "source_id": "source-1",
          "quote": "Synthetic source sentence."
        }
      ],
      "knowledge_points": [
        {
          "title": "Synthetic knowledge point",
          "summary": "Synthetic fixture",
          "confidence": 0.9,
          "source_refs": [
            {
              "source_id": "source-1",
              "quote": "Synthetic source sentence."
            }
          ]
        }
      ]
    }
  ]
}
```

**Step 2: Add lesson fixture**

The fixture must contain the Mentrix-style static course sections:

```markdown
# Synthetic knowledge point

## 学习目标

## 读前热身

## 分步讲解

## 例子

## 复习
```

**Step 3: Add contract tests**

Assert:

- Structure fixture does not require model-authored `position` or `slug`.
- Every source ref contains `source_id` and `quote` and no model-authored `start/end`.
- Lesson fixture is valid Markdown and no JSON lesson object is required.
- No teaching-package paths or `langalpha-managed-teaching-package/v1` appear in the contract.

**Step 4: Run tests**

```bash
uv run pytest tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py -q
```

Expected: initially fails on the new contract assertions.

**Step 5: Commit**

```bash
git add tests/fixtures/education tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py
git commit -m "test(education): freeze book-to-skill textbook contracts"
```

## Task 2: Extract Shared Managed Execution Runtime

**Files:**

- Create: `src/server/services/education_managed_runs.py`
- Modify: `src/server/services/education_structure_jobs.py`
- Modify: `src/server/services/education_lesson_jobs.py`
- Modify: `tests/unit/server/services/test_education_structure_jobs.py`
- Modify: `tests/unit/server/services/test_education_lesson_jobs.py`

**Step 1: Write failing import tests**

Add tests asserting that structure and lesson jobs import graph/config helpers from `education_managed_runs`, not `education_teaching_jobs`.

**Step 2: Move shared helpers**

Move without behavior changes:

- `build_managed_teaching_graph`
- `resolve_managed_teaching_agent_config`
- shared run heartbeat wrapper
- shared `RunCoordinator` / `LocalRunExecutor` dispatch helpers that do not depend on teaching-package tables

Recommended names:

```python
async def build_managed_education_graph(...)
async def resolve_managed_education_agent_config(...)
```

**Step 3: Update imports**

Structure and lesson services must use the new module.

**Step 4: Run tests**

```bash
uv run pytest \
  tests/unit/server/services/test_education_structure_jobs.py \
  tests/unit/server/services/test_education_lesson_jobs.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/services/education_managed_runs.py \
  src/server/services/education_structure_jobs.py \
  src/server/services/education_lesson_jobs.py \
  tests/unit/server/services/test_education_structure_jobs.py \
  tests/unit/server/services/test_education_lesson_jobs.py
git commit -m "refactor(education): extract shared managed run runtime"
```

## Task 3: Add Optional Best-Effort Source Anchors

**Files:**

- Create: `src/server/services/education_source_refs.py`
- Create: `tests/unit/server/services/test_education_source_refs.py`

**Step 1: Write failing tests**

Cover:

- Unique exact quote resolves to the correct character offsets.
- Whitespace-normalized quote resolves to the original source span.
- Duplicate quote uses the first match and records
  `source_quote_ambiguous_first_match_used`.
- Missing quote is retained with `resolution_status="unresolved"` and warning
  `source_quote_unresolved`.
- Unknown `source_id` falls back to the only source when exactly one source
  exists; otherwise it remains unresolved with a warning.
- Unsafe source IDs and paths still fail.
- Missing offsets never change the structure status from `review`.

**Step 2: Implement resolver**

API:

```python
def resolve_source_ref(
    *,
    sources: Mapping[str, str],
    source_id: str,
    quote: str,
    occurrence: int = 1,
) -> dict[str, Any]:
    ...
```

Return:

```json
{
  "source_id": "source-1",
  "quote": "exact source sentence",
  "start": 123,
  "end": 145,
  "resolution_status": "resolved"
}
```

Unresolved refs return `start: null`, `end: null`, and
`resolution_status: "unresolved"`; they do not fail the whole structure.

**Step 3: Run tests**

```bash
uv run pytest tests/unit/server/services/test_education_source_refs.py -q
```

Expected: PASS.

**Step 4: Commit**

```bash
git add src/server/services/education_source_refs.py \
  tests/unit/server/services/test_education_source_refs.py
git commit -m "feat(education): resolve source quotes server-side"
```

## Task 4: Replace Structure Validation Contract

**Files:**

- Modify: `src/server/services/education_structure_validation.py`
- Modify: `tests/unit/server/services/test_education_structure_validation.py`
- Modify: `plugins/langalpha_local/skills/book-to-skill/reference/managed-textbook-contract.md`
- Modify: `plugins/langalpha_local/skills/book-to-skill/SKILL.md`

**Step 1: Write failing tests**

Cover:

- Unit position is generated from array order.
- Unit slug is generated or normalized by the service.
- Knowledge-point position is generated inside each Unit.
- Knowledge-point slug is generated or normalized by the service.
- Model-provided position/slug may be ignored or used only as optional hints.
- Chinese titles fall back to stable `kp-01`, `kp-02` slugs.
- Source refs accept model-authored `quote` and service-resolved `start/end`.
- A line-number-like `start/end` from older output is ignored and replaced by
  service resolution.
- Missing optional summaries/confidence values receive safe defaults with
  warnings.
- A malformed optional Unit is skipped only when other usable Units remain and
  a warning is recorded.
- The structure fails only when no usable Unit/knowledge content remains.

**Step 2: Change normalized structure**

Service output must contain:

```python
{
    "position": generated_position,
    "slug": generated_or_normalized_slug,
    "title": title,
    "summary": summary,
    "source_refs": resolved_refs,
    "confidence": confidence,
    "status": "review",
}
```

**Step 3: Update contract**

Add a complete nested example:

```json
{
  "title": "Unit 1A: The World's Game",
  "slug": "unit-1a-the-worlds-game",
  "source_refs": [{"source_id": "source-1", "quote": "exact source quote"}],
  "knowledge_points": [{
    "title": "足球的起源与现代规则",
    "slug": "football-origin",
    "confidence": 0.95,
    "source_refs": [{"source_id": "source-1", "quote": "exact source quote"}]
  }]
}
```

State explicitly:

- `position` is service-owned.
- `slug` is optional as a model hint, service-owned as the final value.
- `start/end` must not be emitted by the model.

**Step 4: Run tests**

```bash
uv run pytest tests/unit/server/services/test_education_structure_validation.py \
  tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/services/education_structure_validation.py \
  tests/unit/server/services/test_education_structure_validation.py \
  plugins/langalpha_local/skills/book-to-skill/reference/managed-textbook-contract.md \
  plugins/langalpha_local/skills/book-to-skill/SKILL.md \
  tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py
git commit -m "refactor(education): make structure identity service-owned"
```

## Task 5: Preserve Unit and Knowledge-Point Identity Across Edits

**Files:**

- Modify: `src/server/database/education_textbooks.py`
- Modify: `tests/unit/server/database/test_education_structure_models.py`

**Step 1: Write failing tests**

Cover:

- Editing a Unit title preserves its UUID and slug.
- Reordering Units changes `position` but preserves UUID and slug.
- Editing a knowledge-point title preserves its UUID and slug.
- A newly added knowledge point receives a new UUID and unique slug.
- A removed knowledge point is deleted.

**Step 2: Change `replace_structure_contents()`**

Match existing rows by `(structure_id, slug)` and `(unit_id, slug)`. Reuse IDs for matching slugs. Generate fallback slugs before replacement if necessary.

**Step 3: Run tests**

```bash
uv run pytest tests/unit/server/database/test_education_structure_models.py -q
```

Expected: PASS.

**Step 4: Commit**

```bash
git add src/server/database/education_textbooks.py \
  tests/unit/server/database/test_education_structure_models.py
git commit -m "fix(education): preserve structure identity across edits"
```

## Task 6: Replace Lesson Authoring With Book-to-Skill Mode

**Files:**

- Modify: `src/ptc_agent/agent/managed_execution.py`
- Modify: `src/server/services/education_lesson_jobs.py`
- Modify: `src/server/services/education_teaching_storage.py`
- Modify: `plugins/langalpha_local/skills/book-to-skill/SKILL.md`
- Modify: `plugins/langalpha_local/skills/book-to-skill/reference/managed-textbook-contract.md`
- Modify: `plugins/langalpha_local/skills/the-knowledge-guy/reference/managed-textbook-contract.md`
- Modify: `tests/unit/server/services/test_education_lesson_jobs.py`
- Modify: `tests/unit/server/services/test_education_lesson_validation.py`
- Modify: `tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py`

**Step 1: Write failing tests**

Cover:

- Lesson policy allows only `book-to-skill`.
- Lesson prompt reads `book-to-skill` and its managed lesson contract.
- Lesson context contains only the target knowledge point and source excerpts.
- `outputs/lesson.md` is the primary output.
- `outputs/practice.json` remains optional and only when auto-grading is requested.
- `the-knowledge-guy` is not invoked for lesson generation.

**Step 2: Change the lesson policy**

```python
def education_lesson_policy(job_id: str) -> ManagedExecutionPolicy:
    return ManagedExecutionPolicy(
        allowed_skill_names=frozenset({"book-to-skill"}),
        filesystem_root=f"/managed/textbook-job/{UUID(job_id)}",
        purpose="lesson",
        allow_subagents=True,
    )
```

**Step 3: Update lesson prompt and staging**

Prompt `book-to-skill` with:

- Unit title.
- Knowledge-point title and summary.
- Exact source excerpts.
- Optional chapter toolkit if present.
- Processing Profile.
- Auto-grading flag.

Expected output remains:

```text
outputs/lesson.md
outputs/practice.json  # optional
```

**Step 4: Move `the-knowledge-guy` out of authoring**

Delete its `Managed knowledge-point lesson mode`. Keep normal walk/course/quiz behavior and future student-follow-up integration.

**Step 5: Run tests**

```bash
uv run pytest \
  tests/unit/server/services/test_education_lesson_jobs.py \
  tests/unit/server/services/test_education_lesson_validation.py \
  tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add src/ptc_agent/agent/managed_execution.py \
  src/server/services/education_lesson_jobs.py \
  src/server/services/education_teaching_storage.py \
  plugins/langalpha_local/skills/book-to-skill/SKILL.md \
  plugins/langalpha_local/skills/book-to-skill/reference/managed-textbook-contract.md \
  plugins/langalpha_local/skills/the-knowledge-guy/reference/managed-textbook-contract.md \
  tests/unit/server/services/test_education_lesson_jobs.py \
  tests/unit/server/services/test_education_lesson_validation.py \
  tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py
git commit -m "feat(education): author lessons through book-to-skill"
```

## Task 7: Preserve Book-to-Skill Chapter Assets

**Files:**

- Modify: `plugins/langalpha_local/skills/book-to-skill/SKILL.md`
- Modify: `plugins/langalpha_local/skills/book-to-skill/reference/managed-textbook-contract.md`
- Modify: `src/server/services/education_teaching_storage.py`
- Modify: `src/server/services/education_structure_jobs.py`
- Create: `tests/unit/server/services/test_education_book_assets.py`

**Step 1: Define managed asset mode**

Add:

```text
--managed-textbook-assets <job>
```

Allowed outputs:

```text
outputs/chapters/*.md
outputs/glossary.md
outputs/patterns.md
outputs/cheatsheet.md
outputs/nutshell.md
outputs/chapters_manifest.json
```

Remove old `-knowledge.json`, `-practice.json`, and `teaching-package.json` outputs.

**Step 2: Archive assets**

Store generated chapter assets under the structure bundle prefix:

```text
education/<household>/<textbook>/v<version>/structures/v<sequence>/book-skill/
```

Persist only a service-authored manifest and hashes in PostgreSQL. Do not expose sandbox paths.

**Step 3: Make the asset stage optional**

Lesson generation must work without chapter assets by using the KP source excerpts directly. When assets exist, pass only matching chapter toolkit excerpts into the lesson context.

**Step 4: Run tests**

```bash
uv run pytest tests/unit/server/services/test_education_book_assets.py \
  tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add plugins/langalpha_local/skills/book-to-skill/SKILL.md \
  plugins/langalpha_local/skills/book-to-skill/reference/managed-textbook-contract.md \
  src/server/services/education_teaching_storage.py \
  src/server/services/education_structure_jobs.py \
  tests/unit/server/services/test_education_book_assets.py \
  tests/unit/ptc_agent/test_managed_textbook_skill_contracts.py
git commit -m "feat(education): preserve book-to-skill chapter assets"
```

## Task 8: Remove Old Teaching-Package Backend

**Files:**

- Delete: `src/server/services/education_teaching_validation.py`
- Delete: `src/server/services/education_teaching_assets.py`
- Delete: `src/server/services/education_managed_ptc.py`
- Modify: `src/server/app/education/textbooks.py`
- Modify: `src/server/app/education/models.py`
- Modify: `src/server/services/education_textbooks.py`
- Modify: `src/server/database/education_textbooks.py`
- Delete: old teaching-package tests listed in Removal Inventory

**Step 1: Remove API routes**

Remove:

```text
POST /textbook-versions/{id}/teaching-packages
GET  /teaching-jobs/{id}
POST /teaching-jobs/{id}/cancel
POST /teaching-jobs/{id}/resume
GET  /teaching-packages/{id}/assets
GET  /teaching-packages/{id}/chapters/{chapter_id}/assets/{kind}
POST /textbooks/{textbook_id}/versions/{version_id}/publish
```

Keep structure publication:

```text
POST /textbook-versions/{version_id}/structure-publications
```

**Step 2: Remove old service and DB functions**

Delete teaching-package queueing, projection, archive staging, retry, cancellation, completion, and asset-reading functions.

**Step 3: Update document teaching usage**

Replace teaching-package usage with structure/lesson usage, or temporarily return an empty structure-based usage list without querying deleted tables.

**Step 4: Run tests**

```bash
uv run pytest \
  tests/unit/server/app/education/test_textbook_structures.py \
  tests/unit/server/app/education/test_textbooks.py \
  tests/unit/server/services/test_education_textbooks.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add -A src/server/app/education src/server/services src/server/database tests/unit/server
git commit -m "refactor(education): remove legacy teaching package backend"
```

## Task 9: Remove Legacy Teaching-Package Frontend

**Files:**

- Delete: `web/src/pages/Education/TeachingRunDrawer.tsx`
- Delete: `web/src/pages/Education/__tests__/TeachingRunDrawer.test.tsx`
- Modify: `web/src/pages/Education/api.ts`
- Modify: `web/src/pages/Education/queries.ts`
- Modify: `web/src/pages/Education/types.ts`
- Modify: `web/src/pages/Documents/components/TeachingUsagePanel.tsx`
- Modify: `web/src/pages/Documents/types.ts`
- Modify: `web/src/pages/Documents/hooks.ts`

**Step 1: Remove obsolete API functions and types**

Remove teaching-package job/asset functions and types. Keep:

```text
createTextbookStructure
getLatestTextbookStructure
generateKnowledgePointLesson
createKnowledgePointLessonRevision
approveKnowledgePointLesson
publishTextbookStructure
```

**Step 2: Update document usage**

Show structure/lesson usage derived from artifact-backed textbook sources. Do not query removed teaching-package tables.

**Step 3: Run frontend tests**

```bash
cd web
pnpm vitest run src/pages/Education src/pages/Documents
pnpm typecheck
```

Expected: PASS.

**Step 4: Commit**

```bash
git add web/src/pages/Education web/src/pages/Documents
git commit -m "refactor(web): remove teaching package workflow"
```

## Task 10: Migrate Database to Structure-Only Publication

**Files:**

- Create: `migrations/versions/070_remove_legacy_teaching_packages.py`
- Create: `tests/unit/migrations/test_remove_legacy_teaching_packages.py`
- Modify: legacy textbook queries in `src/server/database/education_textbooks.py`

**Step 1: Write migration tests**

Assert:

- Legacy teaching tables are dropped.
- `education_textbook_publications.teaching_package_id` is dropped.
- `education_textbook_publications.structure_id` becomes `NOT NULL`.
- Legacy chapter-learning tables are dropped.
- New knowledge-point lesson and learning tables remain.

**Step 2: Add migration**

Before dropping tables, delete or invalidate legacy publications and learning rows that cannot be represented by structure-only publications.

Drop in dependency order:

```text
education_teaching_archive_staging
education_teaching_events
education_teaching_attempts
education_teaching_jobs
education_learning_answers
education_teaching_package_questions
education_teaching_package_chapters
education_teaching_packages
education_chapter_questions
education_learning_progress
education_textbook_sources
```

Before dropping `education_teaching_packages`, remove the legacy publication
foreign key and `teaching_package_id` column:

```sql
ALTER TABLE education_textbook_publications
DROP COLUMN teaching_package_id;

ALTER TABLE education_textbook_publications
ALTER COLUMN structure_id SET NOT NULL;
```

Do not drop `education_practice_sources` without checking homework foreign
keys. It is shared with homework dictionaries and is not exclusively textbook
state.

**Step 3: Update assignment and publication queries**

All publication queries join only:

```text
publication -> structure -> Units -> knowledge points -> lesson revisions
```

**Step 4: Run migration and focused tests**

```bash
uv run pytest tests/unit/migrations/test_remove_legacy_teaching_packages.py \
  tests/unit/server/database/test_published_structure_learning.py -q
uv run alembic upgrade head
uv run alembic downgrade 069_learning_items_and_profiles
uv run alembic upgrade head
```

Expected: PASS.

**Step 5: Commit**

```bash
git add migrations/versions/070_remove_legacy_teaching_packages.py \
  tests/unit/migrations/test_remove_legacy_teaching_packages.py \
  src/server/database/education_textbooks.py
git commit -m "feat(education): make publications structure-only"
```

## Task 11: Add Structure and Lesson Retry Recovery

**Files:**

- Modify: `src/server/services/education_structure_jobs.py`
- Modify: `src/server/services/education_lesson_jobs.py`
- Modify: `src/server/services/education_structure_review.py`
- Modify: `src/server/app/education/textbooks.py`
- Modify: `web/src/pages/Education/TextbookStructurePage.tsx`
- Modify: `web/src/pages/Education/KnowledgePointLessonReviewPage.tsx`
- Modify: `web/src/pages/Education/api.ts`
- Modify: `web/src/pages/Education/queries.ts`

**Step 1: Write failing backend tests**

Cover:

- Failed structure job can be requeued without creating a new structure row.
- A failed structure job with an existing sandbox does not re-read the PDF.
- Retry creates a new attempt linked to the same structure job.
- Lesson retry remains bounded by `MAX_LESSON_GENERATION_ATTEMPTS`.

**Step 2: Add APIs**

```text
POST /structure-generation-jobs/{job_id}/resume
POST /knowledge-point-lessons/{lesson_id}/regenerate
```

Use the existing `requeue_generation_job()` rather than adding a second queue mechanism.

**Step 3: Add UI actions**

Failed structure page must show:

```text
重新运行结构分析
```

Lesson review page must show failed state, error summary, and retry action.

**Step 4: Run tests**

```bash
uv run pytest tests/unit/server/services/test_education_structure_jobs.py \
  tests/unit/server/services/test_education_lesson_jobs.py -q
cd web
pnpm vitest run src/pages/Education/__tests__/TextbookStructurePage.test.tsx \
  src/pages/Education/__tests__/KnowledgePointLessonReviewPage.test.tsx
pnpm typecheck
```

Expected: PASS.

**Step 5: Commit**

```bash
git add src/server/services src/server/app/education/textbooks.py \
  web/src/pages/Education
git commit -m "feat(education): add structure and lesson retry recovery"
```

## Task 12: Add Source Preview and Validation Diagnostics

**Files:**

- Modify: `src/server/services/education_source_refs.py`
- Modify: `src/server/services/education_structure_jobs.py`
- Modify: `src/server/services/education_lesson_jobs.py`
- Modify: `web/src/pages/Education/TextbookStructurePage.tsx`
- Modify: `web/src/pages/Education/components/StructureSourcePanel.tsx`

**Step 1: Persist safe validation diagnostics**

Examples:

```text
source_quote_not_found
source_quote_ambiguous
unit_slug_invalid
unit_conflict_at_line
duplicate_slug
```

Do not persist raw model output or sandbox paths.

**Step 2: Show source evidence**

The structure review page must show:

- Source filename when available.
- Quote excerpt when available.
- A context excerpt only when offsets were resolved cheaply.

Do not display character ranges as required metadata. They are diagnostic
details only.

**Step 3: Run tests**

```bash
uv run pytest tests/unit/server/services/test_education_source_refs.py \
  tests/unit/server/services/test_education_structure_validation.py -q
cd web
pnpm vitest run src/pages/Education/__tests__/TextbookStructurePage.test.tsx
pnpm typecheck
```

Expected: PASS.

**Step 4: Commit**

```bash
git add src/server/services web/src/pages/Education
git commit -m "feat(education): surface source evidence diagnostics"
```

## Task 13: End-to-End Acceptance With Real RE3

**Files:**

- Modify: `web/e2e/education-textbook-learning.spec.js`
- Modify: `CHANGELOG.md`

**Step 1: Run real structure generation**

Use the completed library document:

```text
document_id: doc-2spsb1AQdrRp
filename: REX 3e SB3.pdf
parse_job_id: job-KVIZjMQU4iTd
primary artifact: art-H7ZGMir0xRQ9
embedded images: 144
```

Expected:

- Structure succeeds with no positional or slug retry.
- Source refs retain quotes when book-to-skill supplies them.
- Missing or unresolved offsets do not fail the structure.
- Ambiguous or unresolved quotes produce warnings, not failed archives.
- The full textbook structure is reviewable.
- ToC-only Units may be present with zero knowledge points only if product review accepts that behavior.

**Step 2: Generate one lesson**

Select `世界运动：足球的历史与流行原因`.

Expected `lesson.md`:

- Matches the Mentrix-style full knowledge-point page.
- Contains warm-up, explanation, tables, vocabulary, review.
- Contains no chat transcript or personalized summary.
- Source evidence remains linked to the structure layer.

**Step 3: Publish and learn**

Approve structure and lesson, publish, assign to a student, open the student knowledge-point page.

**Step 4: Run browser and API checks**

```bash
cd web
pnpm playwright test e2e/education-textbook-learning.spec.js --project=chromium
pnpm typecheck
pnpm build
```

Expected: PASS.

**Step 5: Final verification**

```bash
uv run pytest \
  tests/unit/server/services/test_education_source_refs.py \
  tests/unit/server/services/test_education_structure_validation.py \
  tests/unit/server/services/test_education_structure_jobs.py \
  tests/unit/server/services/test_education_lesson_jobs.py \
  tests/unit/server/services/test_education_lesson_validation.py \
  tests/unit/server/app/education/test_textbook_structures.py \
  tests/unit/server/database/test_published_structure_learning.py -q
uv run ruff check src/server src/ptc_agent plugins
```

Expected: PASS.

**Step 6: Commit**

```bash
git add web/e2e/education-textbook-learning.spec.js CHANGELOG.md
git commit -m "test(education): verify book-to-skill textbook pipeline"
```

## Final Acceptance Checklist

- `book-to-skill` is the only textbook structure and lesson authoring engine.
- `the-knowledge-guy` is no longer required for lesson authoring.
- `position` and `slug` are service-owned.
- Source offsets are computed by the service from exact quotes.
- `lesson.md` means one Mentrix-style knowledge-point page.
- `chapters/*.md` means chapter-level knowledge extracted by `book-to-skill`.
- Old `teaching-package` code, tables, APIs, UI, and tests are removed.
- Publications reference only structures and lesson revisions.
- Failed structure jobs can be resumed without creating a new structure version.
- A real RE3 structure and one full lesson pass parent review, publication, assignment, and student learning.

## Implementation Notes

### 2026-09-20 real RE3 acceptance

- Real source: `doc-2spsb1AQdrRp` / `job-KVIZjMQU4iTd` / `REX 3e SB3.pdf`.
- Structure generation completed with one attempt: 20 Units, 84 knowledge points,
  7 recoverable source warnings, archived under `structures/v2`, then accepted.
- One real lesson completed and was approved: 17KB Markdown with learning
  goals, warm-up, step-by-step explanation, vocabulary, common mistakes,
  review, and exercises.
- Publication correctly remains blocked by the existing gate until all 84
  accepted knowledge points have approved lessons. The remaining work is
  content generation/review, not a pipeline defect.
